# -*- coding: utf-8 -*-
"""빌드 오케스트레이션.

순서가 중요하다. 각 단계가 앞 단계의 산출물을 전제한다.

  1. 폰트   번역에 실제로 쓰인 글자만 빈 글리프 칸에 넣는다
  2. 대사   .SMF 재작성 — 문자열이 밀리므로 .MSG 오프셋을 다시 계산한다
  3. 타이밍 글자 수가 바뀐 창은 MTG 타이밍을 새 길이로 리샘플한다
            (엔진이 글자와 타이밍 배열을 나란히 훑기 때문에 안 맞으면 죽는다)
  4. 디스크 원본 사본에 두 아카이브를 제자리 패치 (EDC/ECC 재계산)
  5. 폰트   크기가 같으므로 LBA 이동 없이 DLL만 교체

항상 원본 덤프에서 새로 시작한다 — 이전 빌드의 중간 산출물이 섞여 들어가
"폰트만 바꿨는데 대사도 바뀌어 있는" 상황을 한 번 겪었다.

## ★ 중간에 죽어도 `dist/` 는 건드리지 않는다

예전에는 `dist/` 에 원본을 복사해 놓고 거기를 직접 패치했다. 그래서 빌드가
도중에 죽으면 **반쯤 패치된 이미지가 그대로 남았다.** 한 번은 로그를 `head`
로 자르는 바람에 파이프가 닫혀 빌드가 죽었는데, 리소스까지만 들어가고 폰트가
순정으로 남아 게임에서 한글 자리마다 한자가 나왔다. 이미지 자체는 멀쩡히
돌아가니 겉으로는 "번역이 안 됐다" 로만 보인다 — 제일 나쁜 실패다.

지금은 `work/stage` 에서 다 만들고 마지막에 한 번에 `dist/` 로 옮긴다.
옮기는 동안에는 `dist/BUILD-INCOMPLETE` 가 놓이므로, 그 순간에 죽더라도
다음 빌드가 알아채고 알려 준다.
"""
import datetime
import glob
import os
import shutil
import sys
import traceback

from kitae import translation
from kitae.core.cab import Cab
from kitae.core.windows import clss_objects, script_windows

MARKER = "BUILD-INCOMPLETE"


def _work(cfg, *parts):
    p = cfg.path(cfg["work_dir"], *parts)
    os.makedirs(os.path.dirname(p) or p, exist_ok=True)
    return p


def _rows_for(doc, lang, src):
    """(window, line) -> {source, target} — 기존 빌드 모듈이 기대하는 형태."""
    out = {}
    for e in doc["entries"]:
        t = e.get("text") or {}
        out[(e["window"], e["line"])] = {
            "source": t.get(src, ""),
            "target": t.get(lang, "") or "",
        }
    return out



def _timing_specs(doc, lang, wins, strs):
    """window -> (원문 줄별 글자수, 번역 줄별 문장) — 길이가 바뀐 유성 창만.

    번역이 비어 있는 줄은 원문이 그대로 남으므로 원문을 쓴다. 줄 수는 양쪽이
    같아야 하고(번역은 줄 단위로 관리한다) 그래야 줄 경계 시각을 원본에서
    물려받을 수 있다. 글자 수가 아니라 문장을 넘기는 건 쉼을 문장부호 뒤로
    당기기 위해서다 — kitae.build.mtg 의 _snap 참고.
    """
    from kitae.core.windows import display_len, MARKUP
    from kitae.build.hangul import glyph_string
    by = {}
    for e in doc["entries"]:
        t = ((e.get("text") or {}).get(lang) or "")
        by[(e["window"], e["line"])] = t

    out = {}
    for m in wins:
        w = m["window"]
        if m["want"] is None or not m["strings"]:
            continue                        # 무성 창은 타이밍이 없다
        orig, new = [], []
        for n, si in enumerate(m["strings"]):
            src = strs[si]
            t = by.get((w, n), "")
            orig.append(display_len(src))
            # 번역은 글리프 단위(합자 = 1)로 센다 — hangul.glyph_string. 원문 폴백은 예전대로.
            new.append(glyph_string(t) if t.strip() else MARKUP.sub("", src))
        if orig != [len(t) for t in new]:
            out[w] = (orig, new)
    return out


def guide_rows(cfg, lang, src):
    """{msl 이름: {(창, 줄): {source, target}}} — translation/guide/*.json.

    가이드북 본문은 대사와 다른 아카이브(SOZ.CB)에 있어서 `scripts` 목록과
    따로 다닌다. 작업대가 없으면 조용히 건너뛴다 — 아직 안 뽑았을 뿐이다.
    """
    import json
    d = cfg.path("translation", "guide")
    out = {}
    if not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(d, f), encoding="utf-8") as fh:
            doc = json.load(fh)
        rows = _rows_for(doc, lang, src)
        if any(r["target"].strip() for r in rows.values()):
            out[doc.get("script") or f[:-5] + ".msl"] = rows
    return out


def quiz_chars(cfg, lang):
    """퀴즈 번역이 쓰는 글자. 폰트에 같이 넣어야 화면에 빈칸이 안 뜬다."""
    import json
    p = cfg.path("translation", "quiz", "Quiz.json")
    if not os.path.exists(p):
        return ""
    with open(p, encoding="utf-8") as fh:
        doc = json.load(fh)
    return "".join((e.get("text") or {}).get(lang) or "" for e in doc["entries"])


def _errlog(cfg, exc):
    """죽은 자리를 파일로 남긴다.

    stdout 이 이미 닫혀 있을 수 있다(파이프를 `head` 로 자른 경우). 그때는
    print 가 또 터지므로 파일이 유일하게 믿을 수 있는 자국이다.
    """
    path = cfg.path(cfg["work_dir"], "build-error.txt")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        stamp = datetime.datetime.now().isoformat(timespec="seconds")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"빌드 실패 {stamp}\n\n")
            fh.write("".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__)))
            fh.write("\ndist/ 는 그대로 두었습니다 — 직전 이미지가 살아 있습니다.\n")
    except Exception:
        return None
    return path


def build(cfg, scripts, lang, want_font=True, verbose=False):
    """`_build` 를 감싸 실패를 반드시 남긴다."""
    try:
        return _build(cfg, scripts, lang, want_font, verbose)
    except OSError as e:
        # 로그를 `head`·`less` 로 자르면 여기로 온다. stdout 은 이미 못 쓴다.
        # 윈도우는 BrokenPipeError 가 아니라 EINVAL(22) 로 온다 — 둘 다 잡는다
        path = _errlog(cfg, e)          # 파이프가 아니어도 자국은 먼저 남긴다
        if not isinstance(e, BrokenPipeError) and e.errno not in (22, 32):
            sys.stderr.write(f"\n빌드 실패 → {path}\n")
            raise
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except Exception:
            pass
        sys.stderr.write(f"\n빌드가 끊겼습니다(출력 파이프가 닫힘) → {path}\n")
        return 1
    except BaseException as e:                 # KeyboardInterrupt 도 남긴다
        path = _errlog(cfg, e)
        sys.stderr.write(f"\n빌드 실패 → {path}\n")
        raise


def _build(cfg, scripts, lang, want_font=True, verbose=False):
    from kitae.build import smf as smf_mod, mtg as mtg_mod, disc as disc_mod
    from kitae.build import hangul, uipatch

    src_lang = cfg["source"]

    # 0. 늘 원본에서 새로 시작한다 ------------------------------------------
    # 지난 산출물이 섞이면 "폰트만 바꿨는데 대사도 바뀌어 있는" 일이 생긴다.
    # 실제로 폰트에서 한 번, UI 재배치에서 한 번 겪었다. 그래서
    #   * work/build 는 매번 비우고
    #   * 입력은 전부 **원본 디스크**에서 꺼낸 work/orig 캐시를 쓴다
    #     (work/cb 는 사람이 언팩해 둔 것이라 바뀌어 있을 수 있다)
    build_dir = cfg.path(cfg["work_dir"], "build")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir, exist_ok=True)

    try:
        plot_cb = uipatch.original(cfg, "/RESOURCE/PLOT.CB")
        mtg_cb = uipatch.original(cfg, "/RESOURCE/MTG.CB")
    except Exception as e:
        print(f"원본 디스크에서 꺼낼 수 없습니다: {e}")
        return 1

    docs = {s: translation.load(cfg, s) for s in scripts}
    rows = {s: _rows_for(docs[s], lang, src_lang) for s in scripts}
    guides = guide_rows(cfg, lang, src_lang)

    # 1. 폰트 --------------------------------------------------------------
    font_dll = None
    if want_font:
        # 대사와 시스템 UI 에 쓰인 글자를 함께 모은다 — 폰트는 하나뿐이다
        chars = {c for s in scripts for r in rows[s].values()
                 for c in r["target"] if hangul.is_hangul(c)}
        chars |= {c for c in uipatch.texts(cfg, lang) if hangul.is_hangul(c)}
        # 가이드북 본문도 같은 폰트를 쓴다 — 여기서 빠지면 화면에 빈칸이 뜬다
        chars |= {c for r in guides.values() for v in r.values()
                  for c in v["target"] if hangul.is_hangul(c)}
        chars |= {c for c in quiz_chars(cfg, lang) if hangul.is_hangul(c)}
        if chars:
            print(f"폰트: {len(chars)}자 주입 → TRF/TRFSTRINGS.DLL")
            font_dll = hangul.inject(cfg, chars, verbose=verbose)
            # 전진폭 실험 — 2바이트 패치. 근거는 kitae/build/advance.py
            # 가변폭이 켜져 있으면 그쪽이 전진 계산을 통째로 가져간다
            if cfg.get("font_variable"):
                from kitae.build import vwstub
                blob, note = vwstub.apply(cfg, open(font_dll, "rb").read())
                with open(font_dll, "wb") as fh:
                    fh.write(blob)
                print(f"  {note}")
            elif cfg.get("font_advance") is not None:
                from kitae.build import advance
                adv = cfg["font_advance"]
                cur = open(font_dll, "rb").read()
                if adv == "probe":
                    blob, done = advance.probe(cur)
                else:
                    blob, done = advance.patch(
                        cur, int(adv), draw=bool(cfg.get("font_advance_draw")))
                with open(font_dll, "wb") as fh:
                    fh.write(blob)
                for d in done:
                    print(f"  전진폭: {d}")
        else:
            print("폰트: 새로 넣을 글자 없음")

    # 2~3. 대사와 타이밍 ----------------------------------------------------
    plot = Cab(plot_cb)
    mtg = Cab(mtg_cb)
    new_smf, new_set = {}, {}
    t_scripts = t_wins = 0            # 타이밍 재생성 집계 (기본 로그는 총계만)
    if verbose:
        print("대사·타이밍 재작성:")
    for s in scripts:
        original = plot.read(s + ".SMF")
        blob, warns, bad = smf_mod.rebuild_smf(s, rows[s], original,
                                              encode=hangul.encoder(cfg))
        new_smf[s + ".SMF"] = blob
        for w in warns[:5]:
            print(f"  주의 {s}: {w}")
        if bad:
            print(f"  {s}: 인코딩 불가 {len(bad)}건 — 폰트 코드페이지 확인 필요")
        wins, strs_all = script_windows(s, plot, mtg)
        changed = _timing_specs(docs[s], lang, wins, strs_all)
        if changed:
            name = s.lower() + ".SET"
            new_set[name], n, warn = mtg_mod.rebuild_set(s, mtg.read(name),
                                                         changed)
            t_scripts += 1
            t_wins += n
            if verbose:
                print(f"    {s}: {n}창 재생성")
                for w, (o, t) in sorted(changed.items())[:8]:
                    print(f"        창{w}: 줄 {o} → {[len(x) for x in t]}"
                          + (f"  ⚠ {warn[w]}ms 넘침" if w in warn else ""))

    # 2b. 에뮬레이터 버그 우회 ---------------------------------------------------
    # 번역이 아니라 에뮬레이터가 못 그리는 자리를 피해 가는 패치다.
    # 근거·잃는 것·끄는 법: docs/EMULATOR-BUGS.md
    fixes = cfg.get("emulator_fixes") or {}
    if fixes.get("choice_gate", True):
        from kitae.build import ebgate
        new_eb, n_gate = ebgate.patch_all(plot)
        if n_gate:
            new_smf.update(new_eb)
            print(f"  에뮬레이터 우회 · 선택지 게이트 {n_gate}곳 제거 "
                  f"({len(new_eb)}개 대본)")

    out_plot = _work(cfg, "build", "PLOT.CB")
    smf_mod.repack_cab(plot_cb, new_smf, out_plot)
    print(f"대사: {len(scripts)}대본 재작성 → RESOURCE/PLOT.CB "
          f"({os.path.getsize(out_plot):,} / {os.path.getsize(plot_cb):,})")
    out_mtg = None
    if new_set:
        out_mtg = _work(cfg, "build", "MTG.CB")
        smf_mod.repack_cab(mtg_cb, new_set, out_mtg)
        print(f"타이밍: {t_wins}창 재생성 ({t_scripts}대본) → RESOURCE/MTG.CB "
              f"({os.path.getsize(out_mtg):,} / {os.path.getsize(mtg_cb):,})")

    # 3b. 가이드북 본문 ------------------------------------------------------
    # SOZ.CB 안의 guide*.msl. 창 표가 있으므로 줄 수를 지켜야 하는 것은
    # 대사와 같다. 타이밍은 없다 — 음성이 붙지 않는 화면이다.
    out_soz = None
    if guides:
        from kitae.build import msl as msl_mod
        soz_cb = uipatch.original(cfg, "/RESOURCE/SOZ.CB")
        soz = Cab(soz_cb)
        new_msl = {}
        g_done = g_total = 0
        for name, r in sorted(guides.items()):
            blob, warns, bad = msl_mod.rebuild(soz.read(name), r,
                                               encode=hangul.encoder(cfg))
            new_msl[name] = blob
            done = sum(1 for v in r.values() if v["target"].strip())
            g_done += done
            g_total += len(r)
            if verbose:
                print(f"    {name}: {done}/{len(r)}줄")
            for w in warns[:3]:
                print(f"    주의 {name}: {w}")
            if bad:
                print(f"    {name}: 인코딩 불가 {len(bad)}건")
        out_soz = _work(cfg, "build", "SOZ.CB")
        smf_mod.repack_cab(soz_cb, new_msl, out_soz)
        print(f"가이드: {g_done}/{g_total}줄 ({len(new_msl)}건) → RESOURCE/SOZ.CB "
              f"({os.path.getsize(out_soz):,} / {os.path.getsize(soz_cb):,})")

    # 3b'. SOZ.CB 지도 라벨 -------------------------------------------------
    # 가이드 본문(위)과 별개로, 지도 위 한글 라벨을 dds 텍스처에 주입한다.
    # typelet compose_file 이 만든 이미지를 게임 포맷에 넣는다(kitae.build.soz).
    # 라벨 포함 SOZ.CB 는 원 슬롯을 넘으므로 디스크 단계에서 재배치한다.
    _jaguk = cfg.path("images", "jaguk.json")
    if os.path.exists(_jaguk):
        from kitae.build import soz as soz_mod
        soz_base = out_soz or uipatch.original(cfg, "/RESOURCE/SOZ.CB")
        srepl, srep = soz_mod.build_replacements(
            Cab(soz_base),
            soz_mod.load_composer(_jaguk, typelet_root=cfg.typelet_root()),
            cache_dir=cfg.path(cfg["work_dir"], "imgcache"))
        if srepl:
            out_soz = _work(cfg, "build", "SOZ_final.CB")
            smf_mod.repack_cab(soz_base, srepl, out_soz)
            sng = sum(1 for _, k, _ in srep if k in ("glyph", "glyph+base"))
            print(f"지도 라벨: 글리프 {sng} · 래스터 {len(srep) - sng} 맵 "
                  f"→ RESOURCE/SOZ.CB ({os.path.getsize(out_soz):,})")

    # 3c. 퀴즈 문제 ----------------------------------------------------------
    # M05.CB 안의 Quiz.mhd. 문제 292개가 CLSS 객체로 들어 있다.
    out_m05 = None
    qpath = cfg.path("translation", "quiz", "Quiz.json")
    if os.path.exists(qpath):
        import json as _json
        from kitae.build import quiz as quiz_mod
        with open(qpath, encoding="utf-8") as fh:
            qdoc = _json.load(fh)
        qrows = {}
        for e in qdoc["entries"]:
            t = (e.get("text") or {}).get(lang) or ""
            if not t.strip():
                continue
            r = qrows.setdefault(e["window"], {"choices": [None] * 3})
            if e["line"] == 0:
                r["q"] = t
            else:
                r["choices"][e["line"] - 1] = t
        if qrows:
            m05_cb = uipatch.original(cfg, "/RESOURCE/M05.CB")
            m05 = Cab(m05_cb)
            blob, qbad = quiz_mod.rebuild(m05.read("Quiz.mhd"),
                                          qrows, encode=hangul.encoder(cfg))
            out_m05 = _work(cfg, "build", "M05.CB")
            smf_mod.repack_cab(m05_cb, {"Quiz.mhd": blob}, out_m05)
            print(f"퀴즈: {len(qrows)}문제 → RESOURCE/M05.CB "
                  f"({os.path.getsize(out_m05):,} / {os.path.getsize(m05_cb):,})")
            if qbad:
                print(f"    인코딩 불가 {len(qbad)}건")

    # 3d. SOZ 외 컨테이너 이미지 주입 ---------------------------------------
    # runner 는 어떤 컨테이너·멤버가 있는지 일일이 적지 않는다. `images/erased/`
    # 하위 폴더 하나가 곧 한 컨테이너(= RESOURCE/<C>.CB)다. 무엇을 넣을지(한글
    # overlay / 지우기 no-text / 안 건드림)는 전부 jaguk 원장의 규칙이 정하고,
    # compose 가 최종 이미지를 돌려준다. 여기선 그걸 각 CB 의 모든 SET 에
    # 래스터(제자리)로 주입만 한다 — 새 이미지·새 컨테이너가 늘어도 코드는 그대로.
    #   · SOZ 는 글리프 패킹 + 슬롯 재배치가 필요해 위(3b')에서 따로 처리한다.
    #   · M05 처럼 이미 다른 것(퀴즈)으로 패치된 CB 는 그 산출물 위에 이어 넣는다.
    image_cbs = {}                       # "RESOURCE/<C>.CB" -> 빌드 경로
    if os.path.exists(_jaguk):
        from kitae.build import soz as soz_mod
        compose = soz_mod.load_composer(_jaguk, typelet_root=cfg.typelet_root())
        image_cbs = _inject_container_images(cfg, compose, {"M05": out_m05})

    # 4~5. 디스크 -----------------------------------------------------------
    dist, stage, track = _stage_disc(cfg)

    # 대사·타이밍·SOZ·퀴즈 산출물에, 이미지 주입본(image_cbs)을 덮어쓴다.
    # image_cbs 의 M05 는 퀴즈 산출물 위에 이미지를 얹은 것이라 그게 최종본이다.
    disc_builds = {"RESOURCE/PLOT.CB": out_plot,
                   "RESOURCE/MTG.CB": out_mtg,
                   "RESOURCE/SOZ.CB": out_soz,
                   "RESOURCE/M05.CB": out_m05}
    disc_builds.update(image_cbs)
    # 디버그 부팅(옵션 debug_boot): 타이틀 씬의 태스크를 씬 셀렉터로 — kitae.build.debugboot
    disc_builds["RESOURCE/SCN/SCV.CB"] = _debug_boot_scv(cfg)
    _patch_cbs(cfg, track, disc_builds)

    # 6. 시스템 UI ----------------------------------------------------------
    # 폰트를 넣은 TRFSTRINGS 위에 UI 패치를 얹어야 한다 — 같은 파일이다.
    base = {}
    if font_dll:
        base["TRFSTRINGS"] = open(font_dll, "rb").read()
    if verbose:
        print("UI 패치:")
    ui, _warn = uipatch.patch_all(cfg, lang, hangul.encoder(cfg), base,
                                  verbose=verbose)
    if font_dll and "/TRF/TRFSTRINGS.DLL" not in ui:
        ui["/TRF/TRFSTRINGS.DLL"] = base["TRFSTRINGS"]
    # 이름화면 힌트 한글 — 폰트 텍스처 베이크 소스에 번역 글자를 주입 (근거: nameinfont.py)
    nkey = "/TRF/TRFNAMEIN.DLL"
    if nkey in ui:
        from kitae.build import nameinfont
        blob2, nchar = nameinfont.patch(cfg, lang, hangul.encoder(cfg), ui[nkey])
        if nchar:
            ui[nkey] = blob2
            print(f"  이름화면 힌트 폰트: 굽기 소스에 한글 {nchar}자 주입")
    # 주인공 성/이름 사이 전각공백 — &主人公名前& 이 「성이름」으로 붙는 것.
    # UI 패치된 KITAE 위에 조립부 스텁을 얹는다(파일 크기 불변, 제자리 교체).
    # config 의 name_separator 가 켜져 있을 때만 적용 (기본 off).
    kkey = "/TRF/KITAE.DLL"
    if cfg.get("name_separator"):
        from kitae.build import namesep
        kbase = ui.get(kkey) or open(uipatch.original(cfg, kkey), "rb").read()
        try:
            ui[kkey], nnote = namesep.apply(kbase)
            print(f"  {nnote}")
        except Exception as e:                 # 조립부가 다르면 건너뛴다
            print(f"  이름 공백 패치 건너뜀: {e}")

    # ★ 스탭롤 스크롤 줄(CTRFCharout, TRFNCHAR.DLL) 가변폭 — HOOK6. 처음 20줄은 CTRFTXOut(HOOK5)
    # 이지만 재사용 줄은 CTRFCharout 이 w=24 상수로 그린다. 폭표는 TRFSTRINGS 의 것을 폰트 vtable
    # 거리로 찾는다 (근거: vwstub.apply_nchar, docs/PROPORTIONAL-WIDTH.md HOOK6).
    if font_dll and cfg.get("font_variable") and cfg.get("vw_txout", True):
        from kitae.build import vwstub
        ckey = "/TRF/TRFNCHAR.DLL"
        cbase = ui.get(ckey) or open(uipatch.original(cfg, ckey), "rb").read()
        try:
            ui[ckey], cnote = vwstub.apply_nchar(cfg, cbase)
            print(f"  {cnote}")
        except Exception as e:                 # 코드가 다르면 건너뛴다 — 스크롤 줄은 고정폭으로 남는다
            print(f"  TRFNCHAR 훅 건너뜀: {e}")

    # ★ 메뉴 팝업(CGeneralMenu, MENUSELECT.DLL) 가변폭 — HOOK7b. TRFSTRINGS 쪽 HOOK7a(아틀라스 촘촘히)와
    # 짝이라 vw_menu 는 둘을 함께 켠다(근거: vwstub.apply_menu, docs/PROPORTIONAL-WIDTH.md HOOK7).
    if font_dll and cfg.get("font_variable") and cfg.get("vw_txout", True) and cfg.get("vw_menu"):
        from kitae.build import vwstub
        mkey = "/TRF/MENUSELECT.DLL"
        mbase = ui.get(mkey) or open(uipatch.original(cfg, mkey), "rb").read()
        ui[mkey], mnote = vwstub.apply_menu(cfg, mbase)   # 실패는 빌드 실패 — 7a 만 걸리면 팝업 행이 어긋난다
        print(f"  {mnote}")

    # u16 글리프-코드 와이드 문자열(환영 패널 등) — cp932 추출기가 못 잡는 형식
    from kitae.build import wstr
    nw = wstr.apply(cfg, ui, hangul.encoder(cfg))
    if nw:
        print(f"  와이드 문자열(글리프코드) 패치: {nw}곳")

    # 코드 상수(레이아웃 좌표 등) 직접 패치 — data/dllpatch.json
    from kitae.build import binpatch
    nbp = binpatch.apply(cfg, ui)
    if nbp:
        print(f"  DLL 코드 상수 패치: {nbp}곳")

    for disc_path, blob in sorted(ui.items()):
        out = _work(cfg, "build", *disc_path.strip("/").split("/"))
        with open(out, "wb") as fh:
            fh.write(blob)
        orig_size = os.path.getsize(uipatch.original(cfg, disc_path))
        if len(blob) == orig_size:
            disc_mod.replace_same_size(track, disc_path.lstrip("/"), blob)
        else:
            # PE 섹션을 붙여 커진 경우 — 자리를 다시 잡고 디렉터리를 고친다
            print(f"  {disc_path}: {orig_size:,} → {len(blob):,} bytes")
            tmp = track + ".tmp"
            disc_mod.patch(disc_path.lstrip("/"), blob, tmp, track)
            os.replace(tmp, track)

    # 7. 씬 제목 -----------------------------------------------------------
    # 이동 목적지가 씬 제목의 장소 필드와 대조되므로 UI 와 같은 문자열로 맞춘다
    from kitae.build import scenes
    inis, n = scenes.rebuild(cfg, lang, hangul.encoder(cfg))
    if inis:
        orig_inis = os.path.getsize(uipatch.original(cfg, scenes.INIS))
        print(f"씬 제목: {n}곳 → RESOURCE/INIS.CB ({len(inis):,} / {orig_inis:,})")
        tmp = track + ".tmp"
        disc_mod.patch(scenes.INIS.lstrip("/"), inis, tmp, track)
        os.replace(tmp, track)

    diff = disc_mod.diff_against(track, cfg.track(3))
    print(f"\n원본과 다른 파일: {diff}")

    return _export_dist(cfg, dist, stage)


# ── 디스크 단계 헬퍼 — 전체 빌드(_build)와 이미지 전용 빌드(build_images)가
#    같은 코드를 쓴다 (스테이징·CB 적용·내보내기).

def _stage_disc(cfg):
    """work/stage 에 원본 트랙을 깔고 (dist, stage, track) 을 돌려준다.

    `dist/` 가 아니라 `work/stage` 에서 만든다. 중간에 죽어도 직전 이미지가
    살아 있어야 한다 — _build 도크스트링의 `★` 참고."""
    dist = cfg.dir("out_dir")
    os.makedirs(dist, exist_ok=True)
    if os.path.exists(os.path.join(dist, MARKER)):
        print(f"  지난 빌드가 {MARKER} 를 남겼습니다 — dist/ 가 반쪽일 수 있습니다")
    stage = cfg.path(cfg["work_dir"], "stage")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, exist_ok=True)
    orig_dir = cfg.dir("orig_dir")
    for name in sorted(os.listdir(orig_dir)):
        p = os.path.join(orig_dir, name)
        if os.path.isfile(p):
            shutil.copyfile(p, os.path.join(stage, name))
    track = glob.glob(os.path.join(stage, "*track03.bin"))[0]
    return dist, stage, track


def _debug_boot_scv(cfg):
    """옵션 `debug_boot` 가 참이면 타이틀 씬을 씬 셀렉터로 바꾼 SCV.CB 경로, 아니면 None.

    제품판에 남은 개발용 씬 셀렉터(TRFSCENELAUNCH)로 부팅하는 디스크를 만든다 —
    근거와 구조는 kitae/build/debugboot.py 머리말, docs/SCRIPT-SYSTEM.md."""
    if not cfg.get("debug_boot"):
        return None
    from kitae.build import debugboot, uipatch
    out = _work(cfg, "build", "SCV.CB")
    debugboot.build(cfg, uipatch.original(cfg, debugboot.SCV_DISC), out)
    print(f"디버그 부팅: 타이틀(P00S052) 태스크 CKitaTitle → CTRFSceneLaunch "
          f"→ RESOURCE/SCN/SCV.CB ({os.path.getsize(out):,})")
    return out


def _patch_cbs(cfg, track, disc_builds):
    """빌드된 CB 들을 트랙에 적용한다. 값이 None 인 항목은 건너뛴다."""
    from kitae.build import disc as disc_mod
    for disc_path, built in disc_builds.items():
        if not built:
            continue
        tmp = track + ".tmp"
        if disc_path == "RESOURCE/SOZ.CB":
            # 라벨 포함 SOZ.CB 는 원 슬롯을 넘을 수 있다 → apply_to_disc 가 슬롯에
            # 맞으면 제자리 패치, 넘치면 뒤 DEBUG.CB(테스트 잔재)를 축소·이동해
            # 공간을 만든다(다른 파일 LBA 불변).
            from kitae.build import soz as soz_mod
            soz_mod.apply_to_disc(track, tmp, open(built, "rb").read(),
                                  cfg.path(cfg["work_dir"], "stage"))
        else:
            disc_mod.patch(disc_path, open(built, "rb").read(), tmp, track)
        os.replace(tmp, track)


def _export_dist(cfg, dist, stage):
    """스테이지를 dist/ 로 옮긴다 — 트랙을 마지막에, MARKER 로 반쪽을 표시.

    트랙을 마지막에 옮긴다 — 중간에 죽어도 .gdi 가 옛 트랙을 가리키느니
    아예 없는 편이 낫다. 옮기는 동안만 MARKER 가 놓인다."""
    marker = os.path.join(dist, MARKER)
    open(marker, "w", encoding="utf-8").write("옮기는 중입니다\n")
    names = sorted(os.listdir(stage),
                   key=lambda n: (n.endswith("track03.bin"), n))
    for name in names:
        s, d = os.path.join(stage, name), os.path.join(dist, name)
        try:
            os.replace(s, d)                   # 같은 볼륨이면 즉시 끝난다
        except OSError:                        # dist/ 를 다른 드라이브로 잡은 경우
            shutil.move(s, d)
    os.remove(marker)
    shutil.rmtree(stage, ignore_errors=True)

    err = cfg.path(cfg["work_dir"], "build-error.txt")
    if os.path.exists(err):
        os.remove(err)

    gdi = glob.glob(os.path.join(dist, "*.gdi"))
    if gdi:
        print(f'실행:  redream.exe "{os.path.abspath(gdi[0])}"')
    return 0


def _inject_container_images(cfg, compose, prebuilt):
    """`images/erased/` 의 SOZ 외 컨테이너에 이미지 주입 → {"RESOURCE/<C>.CB": 경로}.

    runner 는 어떤 컨테이너·멤버가 있는지 일일이 적지 않는다. `images/erased/`
    하위 폴더 하나가 곧 한 컨테이너(= RESOURCE/<C>.CB)다. 무엇을 넣을지(한글
    overlay / 지우기 no-text / 안 건드림)는 전부 jaguk 원장의 규칙이 정하고,
    compose 가 최종 이미지를 돌려준다. 여기선 그걸 각 CB 의 모든 SET 에
    래스터(제자리)로 주입만 한다 — 새 이미지·새 컨테이너가 늘어도 코드는 그대로.
      · SOZ 는 글리프 패킹 + 슬롯 재배치가 필요해 호출자(3b')가 따로 처리한다.
      · prebuilt: 앞 단계가 이미 만든 베이스 (예: 퀴즈 패치된 M05) — 그 위에 잇는다.
    """
    from kitae.build import soz as soz_mod
    from kitae.build import uipatch
    from kitae.core.gdfs import GdFs
    image_cbs = {}
    erased_root = cfg.path("images", "erased")
    if not os.path.isdir(erased_root):
        return image_cbs
    _ofs = GdFs(track=glob.glob(
        os.path.join(cfg.dir("orig_dir"), "*track03.bin"))[0])
    for cont in sorted(os.listdir(erased_root)):
        if cont == "SOZ" or not os.path.isdir(os.path.join(erased_root, cont)):
            continue
        base = prebuilt.get(cont) or uipatch.original(cfg, f"/RESOURCE/{cont}.CB")
        # 앞 단계(퀴즈)의 <C>.CB 를 덮어쓰지 않도록 별도 파일로 낸다 —
        # 슬롯 초과로 건너뛰면 앞 산출물이 그대로 최종본으로 남아야 한다.
        outp = _work(cfg, "build", f"{cont}.img.CB")
        cap = ((_ofs.find(f"RESOURCE/{cont}.CB")[1] + 2047) // 2048) * 2048
        # 제자리 패치는 슬롯을 못 넘으니(다음 파일 침범) 원화질로 먼저,
        # erased 가 무거워 넘치면 색을 낮춰 가장 높은 화질로 슬롯에 맞춘다.
        rep, kused = soz_mod.build_to_fit(base, compose, cont, cap, outp,
                                          cache_dir=cfg.path(cfg["work_dir"],
                                                             "imgcache"))
        if rep is None:
            print(f"  ⚠ {cont} 이미지: 최저 색수로도 슬롯 초과 — 이번 빌드는 건너뜀")
            continue
        done = ", ".join(f"{mp}×{n}" for mp, k, n in rep if n)
        if not done:
            continue                    # 주입할 멤버 없음(정상)
        image_cbs[f"RESOURCE/{cont}.CB"] = outp
        qnote = "원화질" if kused is None else f"{kused}색 감축"
        print(f"이미지: {cont} {done} ({qnote}) → RESOURCE/{cont}.CB "
              f"({os.path.getsize(outp):,} / 슬롯 {cap:,})")
    return image_cbs


def build_images(cfg, rerender=False, lang=None):
    """이미지만 빌드 — jaguk compose 로 이미지 CB 를 만들어 디스크에 반영한다.

    `kitae build image` 의 본체. jaguk 은 이미지 생성(compose)으로만 쓰인다 —
    다른 jaguk 서브커맨드를 부르지 않는다 (raiki build image 와 같은 관계).

    대사·폰트·UI 는 재계산하지 않는다: 직전 `kitae build` 가 work/build 에
    남긴 산출물(PLOT/MTG/M05 CB · TRF DLL)을 그대로 다시 얹는다. 산출물이
    없으면 그 파일은 원본 그대로 둔다(= 이미지 단독 패치). 씬 제목(INIS)은
    캐시 파일이 없어 재계산한다(빠르다).

    rerender=True 면 images/injected/ 캐시를 비워 jaguk 렌더부터 다시 한다
    (raiki build image --inject 에 대응).
    """
    from kitae.build import smf as smf_mod, disc as disc_mod
    from kitae.build import hangul, uipatch, soz as soz_mod

    lang = cfg.check_lang(lang or cfg["target"])
    _jaguk = cfg.path("images", "jaguk.json")
    if not os.path.exists(_jaguk):
        print("images/jaguk.json 이 없습니다 — 이미지 원장이 없는 프로젝트")
        return 1
    if rerender:
        shutil.rmtree(cfg.path("images", "injected"), ignore_errors=True)
        print("  injected 캐시 비움 — jaguk 렌더부터 다시")

    wb = cfg.path(cfg["work_dir"], "build")

    def cached(*parts):
        p = os.path.join(wb, *parts)
        return p if os.path.exists(p) else None

    compose = soz_mod.load_composer(_jaguk, typelet_root=cfg.typelet_root())

    # SOZ 라벨·카드 — 직전 빌드의 가이드 포함 SOZ.CB 위에 (없으면 원본)
    out_soz = None
    soz_base = cached("SOZ.CB") or uipatch.original(cfg, "/RESOURCE/SOZ.CB")
    srepl, srep = soz_mod.build_replacements(
        Cab(soz_base), compose,
        cache_dir=cfg.path(cfg["work_dir"], "imgcache"))
    if srepl:
        out_soz = _work(cfg, "build", "SOZ_final.CB")
        smf_mod.repack_cab(soz_base, srepl, out_soz)
        sng = sum(1 for _, k, _ in srep if k in ("glyph", "glyph+base"))
        print(f"지도 라벨: 글리프 {sng} · 래스터 {len(srep) - sng} 맵 "
              f"→ RESOURCE/SOZ.CB ({os.path.getsize(out_soz):,})")

    image_cbs = _inject_container_images(cfg, compose, {"M05": cached("M05.CB")})

    dist, stage, track = _stage_disc(cfg)
    disc_builds = {"RESOURCE/PLOT.CB": cached("PLOT.CB"),
                   "RESOURCE/MTG.CB": cached("MTG.CB"),
                   "RESOURCE/SOZ.CB": out_soz or cached("SOZ_final.CB"),
                   "RESOURCE/M05.CB": cached("M05.CB"),
                   "RESOURCE/SCN/SCV.CB": cached("SCV.CB") if cfg.get("debug_boot") else None}
    disc_builds.update(image_cbs)
    _patch_cbs(cfg, track, disc_builds)

    # 직전 빌드의 UI·폰트 DLL — work/build/TRF/*.DLL 을 그대로 다시 얹는다
    trf_dir = os.path.join(wb, "TRF")
    if os.path.isdir(trf_dir):
        dlls = [n for n in sorted(os.listdir(trf_dir))
                if n.upper().endswith(".DLL")]
        for name in dlls:
            disc_path = f"/TRF/{name}"
            blob = open(os.path.join(trf_dir, name), "rb").read()
            orig_size = os.path.getsize(uipatch.original(cfg, disc_path))
            if len(blob) == orig_size:
                disc_mod.replace_same_size(track, disc_path.lstrip("/"), blob)
            else:
                tmp = track + ".tmp"
                disc_mod.patch(disc_path.lstrip("/"), blob, tmp, track)
                os.replace(tmp, track)
        print(f"  UI/폰트 DLL 재적용: {len(dlls)}개 (work/build/TRF)")

    # 씬 제목(INIS) — 캐시 파일이 없어 재계산
    from kitae.build import scenes
    inis, n = scenes.rebuild(cfg, lang, hangul.encoder(cfg))
    if inis:
        tmp = track + ".tmp"
        disc_mod.patch(scenes.INIS.lstrip("/"), inis, tmp, track)
        os.replace(tmp, track)
        print(f"  씬 제목 {n}곳 재적용")

    diff = disc_mod.diff_against(track, cfg.track(3))
    print(f"\n원본과 다른 파일: {diff}")
    return _export_dist(cfg, dist, stage)
