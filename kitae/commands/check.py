# -*- coding: utf-8 -*-
"""빌드에 필요한 것들이 갖춰졌는지 점검."""
import glob
import importlib
import io
import json
import os
import re

from kitae.config import CONFIG_NAME, Config

GROUP = "setup"
HELP = "환경·원본·폰트가 준비됐는지 확인한다"


def _row(ok, label, detail=""):
    print(f"  {'OK  ' if ok else 'FAIL'}  {label:<22} {detail}")
    return ok


def glossary(cfg, lang):
    """확정 표기를 어긴 줄. [(파일, 창, 줄, 일본어, 번역, 기대한 표기)]

    긴 표기부터 지워 나간다 — `北海大学` 를 먼저 처리하지 않으면 그 안의
    `北海大` 가 걸려서 멀쩡한 줄을 어겼다고 한다.
    """
    p = cfg.path("translation", "glossary.json")
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8") as fh:
        terms = json.load(fh)["terms"]
    terms.sort(key=lambda t: -len(t["ja"]))

    # 공백은 종류(' '·EN·EM·U+3000)가 갈래마다 달라 표기 비교에선 하나로 본다
    def norm(s):
        return re.sub("[　   ]+", " ", s)

    bad = []
    root = cfg.path("translation")
    for f in sorted(glob.glob(os.path.join(root, "**", "*.json"), recursive=True)):
        with io.open(f, encoding="utf-8") as fh:
            try:
                doc = json.load(fh)
            except ValueError:
                continue
        if not isinstance(doc, dict) or "entries" not in doc:
            continue
        for e in doc["entries"]:
            ja, ko = e["text"]["ja"], norm(e["text"].get(lang) or "").strip()
            if not ko:
                continue
            rest_ja, rest_ko = ja, ko
            for t in terms:
                want = norm(t["ko"])
                while t["ja"] in rest_ja:
                    rest_ja = rest_ja.replace(t["ja"], "", 1)
                    if want in rest_ko:
                        rest_ko = rest_ko.replace(want, "", 1)
                    else:
                        bad.append((os.path.relpath(f, cfg.root),
                                    e.get("window"), e.get("line"),
                                    ja, ko, t["ko"]))
                        break
    return bad


from kitae.core.windows import MARKUP_ALL as MARKUP     # 마크업은 한 곳(windows)에서


def _docs(cfg):
    """translation/**/*.json 중 entries 를 가진 문서. [(상대경로, doc)]"""
    root = cfg.path("translation")
    out = []
    for f in sorted(glob.glob(os.path.join(root, "**", "*.json"), recursive=True)):
        if os.path.basename(f) in ("glossary.json", "wordbook.json"):
            continue
        with io.open(f, encoding="utf-8") as fh:
            try:
                doc = json.load(fh)
            except ValueError:
                out.append((os.path.relpath(f, cfg.root), None))
                continue
        if isinstance(doc, dict) and isinstance(doc.get("entries"), list):
            out.append((os.path.relpath(f, cfg.root), doc))
    return out


def markup_parity(cfg, src, lang):
    """마크업 토큰(`@..@` `&..&` `%N%`)이 원문과 번역에서 같은 개수·종류인지.

    `@S@`·`&主人公名前&`·`%2%` 는 제어 코드라 번역이 그대로 옮겨야 한다. 하나라도
    빠지면 재생 속도·이름 치환·선택지 번호가 어긋난다. [(파일, 창, 줄, 원문토큰, 번역토큰)]
    """
    bad = []
    for rel, doc in _docs(cfg):
        if doc is None:
            continue
        for e in doc["entries"]:
            t = e.get("text") or {}
            ja, ko = t.get(src) or "", t.get(lang) or ""
            if not ko.strip():
                continue
            a, b = sorted(MARKUP.findall(ja)), sorted(MARKUP.findall(ko))
            if a != b:
                bad.append((rel, e.get("window", e.get("offset")), e.get("line"), a, b))
    return bad


def schema(cfg, langs):
    """번역 파일 형식. 대사·가이드·퀴즈는 (window,line) 열쇠, ui 는 offset 열쇠.
    text 는 dict 이고 언어 키는 문자열이어야 하며 열쇠는 파일 안에서 유일해야 한다.
    [(파일, 문제)]"""
    bad = []
    for rel, doc in _docs(cfg):
        if doc is None:
            bad.append((rel, "JSON 파싱 실패"))
            continue
        seen = set()
        for i, e in enumerate(doc["entries"]):
            if not isinstance(e, dict):
                bad.append((rel, f"entries[{i}] 가 dict 가 아님")); continue
            key = (e.get("window"), e.get("line")) if "window" in e else ("off", e.get("offset"))
            if key[1] is None and key[0] is None:
                bad.append((rel, f"entries[{i}] 열쇠(window/line 또는 offset) 없음"))
            elif key in seen:
                bad.append((rel, f"열쇠 중복 {key}"))
            seen.add(key)
            t = e.get("text")
            if not isinstance(t, dict):
                bad.append((rel, f"entries[{i}] text 가 dict 가 아님")); continue
            for lang in langs:
                if lang in t and not isinstance(t[lang], str):
                    bad.append((rel, f"entries[{i}] text.{lang} 가 문자열이 아님"))
            if not isinstance(t.get(langs[0]), str):
                bad.append((rel, f"entries[{i}] 원문 text.{langs[0]} 없음"))
    return bad


def text_rules(cfg, lang):
    """한국어 문자 규칙(docs/KO-TEXT-RULES.md). [(파일, 열쇠, 줄, 문제)]

    보호 항목(uipatch.is_fixed — 엔진이 바이트로 조립하는 UI 문자열)은 건너뛴다.
    줄 길이(글리프 25·600px)는 대사에만 본다(가이드·UI 는 다른 상자를 쓴다)."""
    from kitae.core import textrules as T
    from kitae.build.uipatch import is_fixed
    try:
        from kitae.build.widths import Widths
        W = Widths(cfg)
    except Exception:
        W = None
    limit = T.LIMIT_GLYPHS_EXT if cfg.get("vw_extension") else T.LIMIT_GLYPHS
    bad = []
    for rel, doc in _docs(cfg):
        if doc is None:
            continue
        is_ui = rel.replace("\\", "/").startswith("translation/ui/")
        is_dialogue = "/" not in rel.replace("\\", "/")[len("translation/"):]
        for e in doc["entries"]:
            t = e.get("text") or {}
            ko = t.get(lang) or ""
            ja = t.get("ja") or ""
            # 원문을 그대로 두는 항목: ko==ja, 또는 공백만 EN(←ASCII)·EM(←U+3000)으로 바꾼 것
            # (스탭롤에서 번역하지 않은 일본어 이름·회사명 — 폭표에서 전각 공백이 12 라 EM 으로 맞춘다)
            kept = ko.strip() == ja.strip() or ko.strip() == ja.replace(" ", T.EN_SPACE).replace(T.IDEO_SPACE, T.EM_SPACE).strip()
            if not ko.strip() or (is_ui and is_fixed(e)) or kept:
                continue                        # 빈 줄·보호 항목·원문 유지 항목
            key = e.get("window", e.get("offset"))
            for ch, n in T.bad_chars(ko).items():
                what = "전각 공백 U+3000" if ch == T.IDEO_SPACE else f"허용 밖 글자 {ch!r} U+{ord(ch):04X}"
                bad.append((rel, key, e.get("line"), f"{what} ×{n}"))
            for ln, msg in T.space_violations(ko):
                bad.append((rel, key, ln, msg))
            if is_dialogue:
                for ln, l in enumerate(ko.split("\n")):
                    g = T.line_glyphs(l)
                    if g > limit:
                        bad.append((rel, key, ln, f"줄 길이 {g}글리프 > {limit}"))
                    if W is not None:
                        px = T.line_px(l, W)
                        if px > T.LIMIT_PX:
                            bad.append((rel, key, ln, f"줄 폭 {px}px > {T.LIMIT_PX}"))
    return bad


def ui_padding(cfg, lang):
    """보호 항목(is_fixed)의 **칸 채움** 검토. [(파일, 오프셋, 원문, 번역)]

    엔진이 고정 칸에 그대로 쓰는 문자열은 원문이 뒤를 전각 공백으로 채워 칸 수를 맞춰 둔다.
    번역이 그 꼬리를 빼면 남는 칸이 안 채워지고, 그 칸을 그릴 때 글꼴 아틀라스에 남아 있던
    **다른 글자가 비친다** — 2026-09-24 이름 화면에서 세이브가 없을 때(이름 칸이 빌 때)
    `デブ？　　　` → `데부？` 가 이렇게 잔상을 냈다(TRFNAMEIN 0x14854).

    스탭롤처럼 꼬리 공백이 장식인 항목도 걸리므로 **실패로 막지 않고 목록만** 보여 준다.
    걸린 항목은 원문 칸 수대로 채워야 하는지 사람이 판단한다."""
    from kitae.build.uipatch import is_fixed
    out = []
    for rel, doc in _docs(cfg):
        if doc is None or not rel.replace("\\", "/").startswith("translation/ui/"):
            continue
        for e in doc["entries"]:
            t = e.get("text") or {}
            ja, ko = t.get("ja") or "", t.get(lang) or ""
            if not ko.strip() or not is_fixed(e):
                continue
            if ja.endswith("　") and len(ko) != len(ja):
                out.append((rel, e.get("offset"), ja, ko))
    return out


def run(args):
    cfg = Config.load()
    print(f"저장소: {cfg.root}")
    ok = True

    ok &= _row(cfg.exists, CONFIG_NAME,
               "" if cfg.exists else "kitae init 을 먼저 실행하세요")

    for mod, why in (("PIL", "이미지 변환"), ("capstone", "역어셈블(선택)")):
        try:
            importlib.import_module(mod)
            _row(True, mod, why)
        except ImportError:
            if mod == "capstone":
                _row(True, mod, f"{why} — 없음, 선택 사항")
            else:
                ok &= _row(False, mod, f"{why} — pip install pillow")

    d = cfg.dir("orig_dir")
    has_dir = bool(cfg["orig_dir"]) and os.path.isdir(d)
    ok &= _row(has_dir, "원본 덤프", d or "미설정")
    if has_dir:
        track = cfg.track(3)
        ok &= _row(bool(track), "데이터 트랙",
                   os.path.basename(track) if track else "track03 을 못 찾음")
        gdi = cfg.gdi()
        _row(bool(gdi), ".gdi", os.path.basename(gdi) if gdi else "없음(선택)")

    ttf = cfg["font"].get("ttf")
    ttf_path = cfg.path(ttf) if ttf else ""
    _row(bool(ttf) and os.path.exists(ttf_path), "폰트",
         ttf_path or "미설정 — 번역 언어에 새 글자가 필요하면 설정해야 함")

    langs = cfg["languages"]
    ok &= _row(cfg["source"] in langs and cfg["target"] in langs, "언어",
               f"{langs}  원문 {cfg['source']} → {cfg['target']}")

    n = 0
    if os.path.isdir(cfg.translation_dir):
        n = len([f for f in os.listdir(cfg.translation_dir)
                 if f.lower().endswith(".json")])
    _row(True, "번역 파일", f"{n}개 (translation/)")

    bad = glossary(cfg, cfg["target"])
    if bad is None:
        _row(True, "확정 표기", "glossary.json 없음 — 검사 생략")
    else:
        ok &= _row(not bad, "확정 표기",
                   "일치" if not bad else f"어긋난 곳 {len(bad)}곳")
        for f, w, ln, ja, ko, want in bad[:10]:
            print(f"          {f} [{w}.{ln}]  `{want}` 이어야 한다")
            print(f"            원문 {ja}")
            print(f"            번역 {ko}")
        if len(bad) > 10:
            print(f"          … {len(bad) - 10}곳 더")

    bad = markup_parity(cfg, cfg["source"], cfg["target"])
    ok &= _row(not bad, "마크업 정합",
               "원문·번역 토큰 일치" if not bad else f"어긋난 곳 {len(bad)}곳")
    for f, w, ln, a, b in bad[:12]:
        print(f"          {f} [{w}.{ln}]  원문 {a} ≠ 번역 {b}")
    if len(bad) > 12:
        print(f"          … {len(bad) - 12}곳 더")

    bad = schema(cfg, [cfg["source"], cfg["target"]])
    ok &= _row(not bad, "번역 파일 형식",
               "정상" if not bad else f"문제 {len(bad)}건")
    for f, msg in bad[:10]:
        print(f"          {f}: {msg}")

    bad = text_rules(cfg, cfg["target"])
    ok &= _row(not bad, "문자 규칙",
               "KO-TEXT-RULES 준수" if not bad else f"위반 {len(bad)}곳")
    for f, w, ln, msg in bad[:15]:
        print(f"          {f} [{w}.{ln}]  {msg}")
    if len(bad) > 15:
        print(f"          … {len(bad) - 15}곳 더")

    pad = ui_padding(cfg, cfg["target"])
    _row(True, "칸 채움 검토",
         "원문 꼬리 전각공백과 칸 수가 같음" if not pad else
         f"칸 수가 다른 보호 항목 {len(pad)}건(막지 않음)")
    for rel, off, ja, ko in pad[:8]:
        print(f"          {rel} {off:#x}: 원문 {ja!r}({len(ja)}칸) → 번역 {ko!r}({len(ko)}칸)")

    print("\n준비됨" if ok else "\n미비 항목이 있습니다")
    return 0 if ok else 1
