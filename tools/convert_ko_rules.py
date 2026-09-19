# -*- coding: utf-8 -*-
"""`ko` 를 docs/KO-TEXT-RULES.md 대로 일괄 변환한다 (2026-09-18, 1회. 되돌리기는 git).

  1. 전각 → ASCII: `．，、！？：／－～＝＋（）＜＞’。` 와 전각 숫자. 전각 로마자는
     **두 글자 이상의 토큰**만 ASCII 로(`ＪＲ`→`JR`, `Ｙｏｕ’ｒｅ`→`You're`), 한 글자
     토큰(`Ａ 버튼`·`１Ｆ`·`Ｐ있음`)은 고정폭 전각으로 남긴다(§3-2).
     → 2026-09-19: 가이드북(translation/guide)의 한 글자 토큰(`ｍ`·`Ｆ`·`Ｐ`·`Ｂ`·`Ｇ`·`Ｓ`, 100줄)은
       단위·형식명이라 §3-2 기본값대로 ASCII 로 바꿨다(사용자 지시). 버튼 라벨만 전각.
     → 2026-09-19 정책: 전각 로마자는 `Ａ 버튼…`/`Ｂ 버튼…` 두 줄이 왼쪽 정렬로 설 때 그 첫 글자에만.
       나머지는 전부 ASCII 로 일괄 변환(대사·퀴즈·UI 128항목).
  2. 공백: 줄 첫머리(마크업 뒤 포함)의 전각 공백 → EM SPACE, 반각 공백 → EN SPACE(칸 맞춤).
     어절 사이 전각 공백 하나 → `' '`, 둘 이상 → EM SPACE(정렬). UI 도 같다.
  3. `. , ! ? :` 뒤 공백, 줄 끝 공백 제거 — kitae.core.textrules.fix_spacing.
  4. 보호 항목(uipatch.is_fixed)은 건드리지 않는다. 단어장·용어집의 ko 도 같이 바꾼다.

실행: python tools/convert_ko_rules.py [--dry]
"""
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from kitae.core.windows import MARKUP_ALL                   # noqa: E402
from kitae.core import textrules as T                       # noqa: E402
from kitae.build.uipatch import is_fixed                    # noqa: E402

FW = {"．": ".", "，": ",", "、": ",", "！": "!", "？": "?", "：": ":", "／": "/",
      "－": "-", "～": "~", "＝": "=", "＋": "+", "（": "(", "）": ")", "＜": "<",
      "＞": ">", "’": "'", "。": "."}
for _i in range(10):
    FW[chr(0xFF10 + _i)] = chr(0x30 + _i)
FW_ROMAN = {chr(0xFF21 + i): chr(0x41 + i) for i in range(26)}
FW_ROMAN.update({chr(0xFF41 + i): chr(0x61 + i) for i in range(26)})
ROMAN = re.compile("[Ａ-Ｚａ-ｚ]+(?:[’'][Ａ-Ｚａ-ｚ]+)*")
EN, EM, IDEO = T.EN_SPACE, T.EM_SPACE, T.IDEO_SPACE
LEAD = re.compile(f"^((?:{MARKUP_ALL.pattern})*)([{IDEO} ]+)")


def _chars(seg):
    def roman(m):
        tok = m.group()
        letters = tok.replace("’", "").replace("'", "")
        if len(letters) == 1:
            return tok                                  # 한 글자 토큰 = 고정폭 전각
        return "".join(FW_ROMAN.get(c, FW.get(c, c)) for c in tok)
    seg = ROMAN.sub(roman, seg)
    return "".join(FW.get(c, c) for c in seg)


def convert(text, ui=False):
    # 1) 문자 (마크업은 그대로)
    parts, pos = [], 0
    for m in MARKUP_ALL.finditer(text):
        parts.append(_chars(text[pos:m.start()]))
        parts.append(m.group())
        pos = m.end()
    parts.append(_chars(text[pos:]))
    text = "".join(parts)
    # 2) 공백 — 줄 단위
    out = []
    for line in text.split("\n"):
        m = LEAD.match(line)
        if m:
            pad = "".join(EM if c == IDEO else EN for c in m.group(2))
            line = m.group(1) + pad + line[m.end():]
        # UI 도 같은 규칙 — 어절 하나는 ' '(9px). 전부 EM 으로 두면 안내문이 고정폭처럼 보인다(9/18 실제 발생).
        line = re.sub(f"{IDEO}{{2,}}", lambda mm: EM * len(mm.group()), line)
        line = line.replace(IDEO, " ")
        out.append(line)
    text = "\n".join(out)
    # 3) 문장부호 뒤 공백, 줄 끝 공백
    return T.fix_spacing(text)


def _docs():
    for f in sorted(glob.glob("translation/**/*.json", recursive=True)):
        name = os.path.basename(f)
        if name in ("glossary.json", "wordbook.json"):
            continue
        raw = io.open(f, encoding="utf-8").read()
        doc = json.loads(raw)
        if isinstance(doc, dict) and isinstance(doc.get("entries"), list):
            yield f, raw, doc


# 사람이 정한 보호 항목 — 반각 공백으로 칸을 맞춘 라벨(원문엔 ASCII 가 없어 자동 판정 밖)
FIXED = {("KITATITLE", 67976), ("TRFOPTIONGAME", 89984), ("TRFOPTIONGAME", 90008)}
# 저장 슬롯 장소 필드는 도시 8B 와 합쳐 30B — 스폿명 22B 이하(어절 공백 셀도 2B)
RETEXT = {("TRFVMSVIEW", 65252): "0JR삿포로역 남쪽 출구"}   # 스폿명 어절 공백은 raw 에서도 셀(9px), 22B


def main():
    dry = "--dry" in sys.argv
    stats = {}
    for f, raw, doc in _docs():
        rel = f.replace("\\", "/")
        is_ui = rel.startswith("translation/ui/")
        mod = doc.get("module")
        changed = 0
        for e in doc["entries"]:
            t = e.get("text") or {}
            ko = t.get("ko") or ""
            if is_ui:
                if (mod, e.get("offset")) in FIXED:
                    e["fixed"] = True
                if (mod, e.get("offset")) in RETEXT:
                    t["ko"] = RETEXT[(mod, e.get("offset"))]
                    changed += 1
                    continue
                if is_fixed(e):
                    continue
            if not ko.strip():
                continue
            new = convert(ko, ui=is_ui)
            if new != ko:
                t["ko"] = new
                changed += 1
        stats[rel] = changed
        if changed and not dry:
            with io.open(f, "w", encoding="utf-8", newline="") as fh:
                fh.write(json.dumps(doc, ensure_ascii=False, indent=2)
                         + ("\n" if raw.endswith("\n") else ""))
    # 단어장·용어집: "ko": "…" 값만 줄 단위 치환 (형식 보존)
    for f in ("translation/wordbook.json", "translation/glossary.json"):
        if not os.path.exists(f):
            continue
        raw = io.open(f, encoding="utf-8").read()

        def fix(m):
            val = json.loads(m.group(2))
            return m.group(1) + json.dumps(convert(val), ensure_ascii=False)
        new = re.sub(r'("ko":\s*)("(?:[^"\\]|\\.)*")', fix, raw)
        stats[f] = sum(1 for a, b in zip(raw.split("\n"), new.split("\n")) if a != b)
        if new != raw and not dry:
            io.open(f, "w", encoding="utf-8", newline="").write(new)
    tot = sum(stats.values())
    print(f"{'(dry) ' if dry else ''}변경 항목 {tot}개")
    for k, v in sorted(stats.items(), key=lambda x: -x[1])[:12]:
        print(f"  {v:5d}  {k}")


if __name__ == "__main__":
    main()
