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
            new.append(MARKUP.sub("", t if t.strip() else src))
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


def build(cfg, scripts, lang, want_font=True):
    """`_build` 를 감싸 실패를 반드시 남긴다."""
    try:
        return _build(cfg, scripts, lang, want_font)
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


def _build(cfg, scripts, lang, want_font=True):
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
            font_dll = hangul.inject(cfg, chars)
            print(f"폰트: {len(chars)}자 주입 → {os.path.relpath(font_dll, cfg.root)}")
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
            for w, (o, t) in sorted(changed.items())[:8]:
                print(f"  · {s} 창{w}: 줄 {o} → {[len(x) for x in t]}"
                      + (f"  ⚠ {warn[w]}ms 넘침" if w in warn else ""))
            print(f"  {s}: 타이밍 {n}창 재생성 (줄별 시각·쉼 위치 보존)")

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
    print(f"PLOT.CB {os.path.getsize(out_plot):,} / 원본 "
          f"{os.path.getsize(plot_cb):,}")
    out_mtg = None
    if new_set:
        out_mtg = _work(cfg, "build", "MTG.CB")
        smf_mod.repack_cab(mtg_cb, new_set, out_mtg)
        print(f"MTG.CB  {os.path.getsize(out_mtg):,} / 원본 "
              f"{os.path.getsize(mtg_cb):,}")

    # 3b. 가이드북 본문 ------------------------------------------------------
    # SOZ.CB 안의 guide*.msl. 창 표가 있으므로 줄 수를 지켜야 하는 것은
    # 대사와 같다. 타이밍은 없다 — 음성이 붙지 않는 화면이다.
    out_soz = None
    if guides:
        from kitae.build import msl as msl_mod
        soz_cb = uipatch.original(cfg, "/RESOURCE/SOZ.CB")
        soz = Cab(soz_cb)
        new_msl = {}
        for name, r in sorted(guides.items()):
            blob, warns, bad = msl_mod.rebuild(soz.read(name), r,
                                               encode=hangul.encoder(cfg))
            new_msl[name] = blob
            done = sum(1 for v in r.values() if v["target"].strip())
            print(f"  가이드 {name}: {done}/{len(r)}줄")
            for w in warns[:3]:
                print(f"    주의 {w}")
            if bad:
                print(f"    인코딩 불가 {len(bad)}건")
        out_soz = _work(cfg, "build", "SOZ.CB")
        smf_mod.repack_cab(soz_cb, new_msl, out_soz)
        print(f"SOZ.CB  {os.path.getsize(out_soz):,} / 원본 "
              f"{os.path.getsize(soz_cb):,}")

    # 3b'. SOZ.CB 지도 라벨 -------------------------------------------------
    # 가이드 본문(위)과 별개로, 지도 위 한글 라벨을 dds 텍스처에 주입한다.
    # typelet compose_file 이 만든 이미지를 게임 포맷에 넣는다(kitae.build.soz).
    # 라벨 포함 SOZ.CB 는 원 슬롯을 넘으므로 디스크 단계에서 재배치한다.
    _jaguk = cfg.path("images", "jaguk.json")
    if os.path.exists(_jaguk):
        from kitae.build import soz as soz_mod
        soz_base = out_soz or uipatch.original(cfg, "/RESOURCE/SOZ.CB")
        srepl, srep = soz_mod.build_replacements(
            Cab(soz_base), soz_mod.load_composer(_jaguk))
        if srepl:
            out_soz = _work(cfg, "build", "SOZ_final.CB")
            smf_mod.repack_cab(soz_base, srepl, out_soz)
            sng = sum(1 for _, k, _ in srep if k in ("glyph", "glyph+base"))
            print(f"  지도 라벨: 글리프 {sng}, 래스터 {len(srep) - sng} 맵  "
                  f"→ SOZ.CB {os.path.getsize(out_soz):,}")

    # 3b''. M08.CB 이름판(BGHut) 이미지 ------------------------------------
    # SOZ 와 같은 SET+DDS 아틀라스 구조. 합성 한글 이미지(images/injected/M08)를
    # BGHut.set 에 주입한다. soz 모듈을 컨테이너 인자로 재사용.
    out_m08 = None
    if os.path.exists(_jaguk):
        from kitae.build import soz as soz_mod
        m08_cb = uipatch.original(cfg, "/RESOURCE/M08.CB")
        # raster(제자리 덮어쓰기) — 글리프 패킹은 텍스처를 키워 슬롯을 넘는다.
        mrepl, mrep = soz_mod.build_replacements(
            Cab(m08_cb), soz_mod.load_composer(_jaguk),
            set_prefix="bghut", container="M08", raster_only=True)
        if mrepl:
            out_m08 = _work(cfg, "build", "M08.CB")
            smf_mod.repack_cab(m08_cb, mrepl, out_m08)
            nd = sum(n for _, _, n in mrep)
            print(f"  M08 이름판: 텍스처 {nd} 맵 → M08.CB "
                  f"{os.path.getsize(out_m08):,} / 원본 {os.path.getsize(m08_cb):,}")

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
            print(f"  퀴즈 Quiz.mhd: {len(qrows)}문제")
            if qbad:
                print(f"    인코딩 불가 {len(qbad)}건")
            out_m05 = _work(cfg, "build", "M05.CB")
            smf_mod.repack_cab(m05_cb, {"Quiz.mhd": blob}, out_m05)
            print(f"M05.CB  {os.path.getsize(out_m05):,} / 원본 "
                  f"{os.path.getsize(m05_cb):,}")

    # 4~5. 디스크 -----------------------------------------------------------
    # `dist/` 가 아니라 `work/stage` 에서 만든다. 중간에 죽어도 직전 이미지가
    # 살아 있어야 한다 — 위 도크스트링의 `★` 참고.
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

    for disc_path, built in (("RESOURCE/PLOT.CB", out_plot),
                             ("RESOURCE/MTG.CB", out_mtg),
                             ("RESOURCE/SOZ.CB", out_soz),
                             ("RESOURCE/M05.CB", out_m05),
                             ("RESOURCE/M08.CB", out_m08)):
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

    # 6. 시스템 UI ----------------------------------------------------------
    # 폰트를 넣은 TRFSTRINGS 위에 UI 패치를 얹어야 한다 — 같은 파일이다.
    base = {}
    if font_dll:
        base["TRFSTRINGS"] = open(font_dll, "rb").read()
    ui, _warn = uipatch.patch_all(cfg, lang, hangul.encoder(cfg), base)
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
        print(f"INIS.CB {len(inis):,} / 원본 {orig_inis:,}  (씬 제목 {n}곳)")
        tmp = track + ".tmp"
        disc_mod.patch(scenes.INIS.lstrip("/"), inis, tmp, track)
        os.replace(tmp, track)

    diff = disc_mod.diff_against(track, cfg.track(3))
    print(f"\n원본과 다른 파일: {diff}")

    # 8. 내보내기 -----------------------------------------------------------
    # 여기까지 왔으면 이미지는 완성이다. 이제야 dist/ 를 갈아 끼운다.
    # 트랙을 마지막에 옮긴다 — 중간에 죽어도 .gdi 가 옛 트랙을 가리키느니
    # 아예 없는 편이 낫다. 옮기는 동안만 MARKER 가 놓인다.
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
