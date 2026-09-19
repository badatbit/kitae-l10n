# -*- coding: utf-8 -*-
"""ko 전각 문자 리뷰 목록(work/fullwidth-review.md)을 만든다 — 기존 파일의 메모를 보존한다.

    python tools/fullwidth_review.py            # work/fullwidth-review.md 갱신(메모 보존)
    python tools/fullwidth_review.py --fresh    # 메모를 버리고 새로

수집 대상: ASCII 대응이 있는 전각 전부 — U+3000 공백, 、。, U+FF01~FF5E(숫자·로마자·
괄호·마침표·％＆／ 포함). 마크업(`%２%` 등) 안은 제외. 보호 항목(uipatch.is_fixed)과
일반 항목을 나눠 싣는다.

**재생성 규칙(2026-09-19, 덮어쓰기 사고 뒤):**
  * 기존 파일은 `fullwidth-review.bak.md` 로 먼저 복사한다.
  * 표의 각 행에 `메모` 칸이 있다. 재생성 때 같은 행(파일 + offset/창·줄)의 메모를
    그대로 옮긴다. 목록에서 빠진 행의 메모는 맨 아래 "사라진 행의 메모" 절로 보낸다.
  * 다른 칸(ko 등)은 번역 파일이 단일 출처라 다시 계산한다 — 결정은 번역 파일에 적고,
    이 파일에는 메모만 적는다.
"""
import collections
import datetime
import glob
import io
import json
import os
import re
import shutil
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from kitae.build.uipatch import is_fixed          # noqa: E402
from kitae.core.windows import MARKUP_ALL         # noqa: E402

OUT = os.path.join(ROOT, "work", "fullwidth-review.md")
MARK = {"　": "[全]", " ": "[EN]", " ": "[EM]", " ": "[FS]",
        " ": "[Q4]", "\t": "[TAB]", "\n": "⏎"}


def is_fw(c):
    o = ord(c)
    return o == 0x3000 or o in (0x3001, 0x3002) or 0xFF01 <= o <= 0xFF5E


def vis(s):
    return "".join(MARK.get(c, c) for c in s).replace("|", "\\|")


def collect():
    rows, total = [], collections.Counter()
    for f in sorted(glob.glob(os.path.join(ROOT, "translation", "**", "*.json"), recursive=True)):
        rel = os.path.relpath(f, ROOT).replace("\\", "/")
        raw = io.open(f, encoding="utf-8").read()
        lines = [l.strip() for l in raw.split("\n")]
        d = json.loads(raw)
        ents = d.get("entries") if isinstance(d, dict) else None
        if not isinstance(ents, list):
            continue
        cur = 0
        for e in ents:
            t = e.get("text") if isinstance(e, dict) else None
            ko = (t or {}).get("ko") if isinstance(t, dict) else None
            if not ko:
                continue
            needle = '"ko": ' + json.dumps(ko, ensure_ascii=False)
            ln = next((i + 1 for i in range(cur, len(lines))
                       if lines[i] == needle + "," or lines[i] == needle), None)
            if ln:
                cur = ln
            fx = ("ja" in t and "avail" in e and is_fixed(e))
            body = MARKUP_ALL.sub("", ko)
            fw = sorted({c for c in body if is_fw(c)})
            if not fw:
                continue
            for c in body:
                if is_fw(c):
                    total[c] += 1
            off = e.get("offset")
            loc = f"offset {off}" if off is not None else f"창 {e.get('window')} 줄 {e.get('line')}"
            key = f"{rel.split('/')[-1]}|{loc}"
            rows.append(dict(rel=rel, ln=ln, fixed=fx, loc=loc, key=key,
                             fw="".join(MARK.get(c, c) for c in fw), ko=ko,
                             ja=(t or {}).get("ja", "")))
    return rows, total


ROW = re.compile(r"^\| \[([^\]]+)\]\([^)]*\) \| ([^|]*?) \|")


def load_memos(path):
    """기존 파일의 표에서 {키: 메모} — 머리글의 마지막 칸이 `메모` 인 표만 읽는다."""
    memos = {}
    if not os.path.exists(path):
        return memos
    has_memo = False
    for line in io.open(path, encoding="utf-8"):
        if line.startswith("| 파일:줄 |"):
            has_memo = line.strip().strip("|").split("|")[-1].strip() == "메모"
            continue
        m = ROW.match(line)
        if not m or not has_memo:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        fname = m.group(1).split(":")[0]
        loc = m.group(2).strip()
        if not loc.startswith(("offset", "창")):
            loc = "offset " + loc                # 보호 항목 표는 offset 숫자만 적는다
        memo = cells[-1]
        if memo:
            memos[f"{fname}|{loc}"] = memo
    return memos


def render(rows, total, memos):
    def link(r):
        return f"[{r['rel'].split('/')[-1]}:{r['ln']}](../{r['rel']}#L{r['ln']})"
    out = [f"# ko 전각 문자 리뷰 목록 ({datetime.date.today()} 갱신)\n",
           "생성: `python tools/fullwidth_review.py` — 재생성해도 `메모` 칸은 행(파일+위치)별로 보존되고, "
           "이전 파일은 `fullwidth-review.bak.md` 로 남는다. 결정은 번역 파일에 적고 여기에는 메모만.\n",
           "ASCII 대응이 있는 전각 전부: U+3000 공백, 、。, ！～｝(U+FF01~FF5E: 숫자·로마자·괄호·마침표·％＆／ 포함). "
           "마크업(`%２%` 등) 안은 제외. 표기: [全]=U+3000, [EN]=U+2002, [EM]=U+2003, [FS]=U+2007, [Q4]=U+2005, ⏎=줄바꿈. "
           "`／`(24px 구분 기호)·`％＆`(마크업 충돌)·A/B 두 줄의 `ＡＢ` 는 정책상 의도된 것.\n"]
    out.append("## 글자별 총계\n\n| 전각 | 횟수 | 이름 |\n|---|---|---|")
    for c, n in sorted(total.items(), key=lambda x: -x[1]):
        out.append(f"| `{MARK.get(c, c)}` U+{ord(c):04X} | {n} | {unicodedata.name(c, '?')} |")
    prot = [r for r in rows if r["fixed"]]
    norm = [r for r in rows if not r["fixed"]]
    out.append(f"\n- 보호 항목(raw 인코딩, 엔진 글리프): {len(prot)}항목\n- 일반 항목: {len(norm)}항목\n")
    out.append("## 일반 항목 (가변폭 텍스트)\n\n| 파일:줄 | 위치 | 전각 | ko | 메모 |\n|---|---|---|---|---|")
    used = set()
    for r in norm:
        memo = memos.get(r["key"], ""); used.add(r["key"])
        out.append(f"| {link(r)} | {r['loc']} | `{r['fw']}` | {vis(r['ko'])} | {memo} |")
    out.append("\n## 보호 항목 (엔진이 바이트로 다루는 UI 문자열)\n")
    bymod = collections.defaultdict(list)
    for r in prot:
        bymod[r["rel"].split("/")[-1][:-5]].append(r)
    for mod, rs in sorted(bymod.items(), key=lambda x: -len(x[1])):
        out.append(f"\n### {mod} — {len(rs)}항목\n\n| 파일:줄 | offset | 전각 | ko | ja | 메모 |\n|---|---|---|---|---|---|")
        for r in rs:
            memo = memos.get(r["key"], ""); used.add(r["key"])
            out.append(f"| {link(r)} | {r['loc'].replace('offset ', '')} | `{r['fw']}` | {vis(r['ko'])} | {vis(r['ja'])} | {memo} |")
    left = {k: v for k, v in memos.items() if k not in used}
    if left:
        out.append("\n## 사라진 행의 메모 (목록에서 빠진 항목)\n")
        for k, v in sorted(left.items()):
            out.append(f"- {k}: {v}")
    return "\n".join(out) + "\n"


def main():
    rows, total = collect()
    memos = {} if "--fresh" in sys.argv else load_memos(OUT)
    if os.path.exists(OUT):
        shutil.copy2(OUT, OUT.replace(".md", ".bak.md"))
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(render(rows, total, memos))
    print(f"{OUT}: {len(rows)}항목 (보호 {sum(1 for r in rows if r['fixed'])}, 일반 "
          f"{sum(1 for r in rows if not r['fixed'])}), 메모 {len(memos)}개 보존"
          + (", 백업 fullwidth-review.bak.md" if os.path.exists(OUT.replace('.md', '.bak.md')) else ""))


if __name__ == "__main__":
    main()
