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
"""
import glob
import os
import shutil

from kitae import translation
from kitae.core.cab import Cab
from kitae.core.windows import clss_objects, script_windows


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


def build(cfg, scripts, lang, want_font=True):
    from kitae.build import smf as smf_mod, mtg as mtg_mod, disc as disc_mod
    from kitae.build import hangul

    src_lang = cfg["source"]
    cb_dir = cfg.path(cfg["work_dir"], "cb", "RESOURCE")
    plot_cb = os.path.join(cb_dir, "PLOT.CB")
    mtg_cb = os.path.join(cb_dir, "MTG.CB")
    for p in (plot_cb, mtg_cb):
        if not os.path.exists(p):
            print(f"{p} 가 없습니다 — kitae unpack RESOURCE/PLOT.CB 등으로 꺼내세요")
            return 1

    docs = {s: translation.load(cfg, s) for s in scripts}
    rows = {s: _rows_for(docs[s], lang, src_lang) for s in scripts}

    # 1. 폰트 --------------------------------------------------------------
    font_dll = None
    if want_font:
        chars = {c for s in scripts for r in rows[s].values()
                 for c in r["target"] if hangul.is_hangul(c)}
        if chars:
            font_dll = hangul.inject(cfg, chars)
            print(f"폰트: {len(chars)}자 주입 → {os.path.relpath(font_dll, cfg.root)}")
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

    # 4~5. 디스크 -----------------------------------------------------------
    dist = cfg.dir("out_dir")
    os.makedirs(dist, exist_ok=True)
    orig_dir = cfg.dir("orig_dir")
    for name in sorted(os.listdir(orig_dir)):
        p = os.path.join(orig_dir, name)
        if os.path.isfile(p):
            shutil.copyfile(p, os.path.join(dist, name))
    track = glob.glob(os.path.join(dist, "*track03.bin"))[0]

    for disc_path, built in (("RESOURCE/PLOT.CB", out_plot),
                             ("RESOURCE/MTG.CB", out_mtg)):
        if not built:
            continue
        tmp = track + ".tmp"
        disc_mod.patch(disc_path, open(built, "rb").read(), tmp, track)
        os.replace(tmp, track)

    if font_dll:
        disc_mod.replace_same_size(track, "TRF/TRFSTRINGS.DLL",
                                   open(font_dll, "rb").read())

    diff = disc_mod.diff_against(track, cfg.track(3))
    print(f"\n원본과 다른 파일: {diff}")
    gdi = glob.glob(os.path.join(dist, "*.gdi"))
    if gdi:
        print(f'실행:  redream.exe "{os.path.abspath(gdi[0])}"')
    return 0
