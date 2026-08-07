# -*- coding: utf-8 -*-
"""번역문 텍스트를 translation/<SCRIPT>.json 에 넣는다.

넣기 전에 전부 검사한다. 하나라도 어긋나면 쓰지 않는다 —
  1. 창 번호가 원문에 있는가
  2. 줄 수가 원문과 같은가 (.MSG 가 창별 줄 수를 고정한다)
  3. 인라인 마크업이 원문과 같은 집합인가 (@S@ 재생제어, &이름& 치환)
  4. 화면 폭을 넘지 않는가 (전각 1칸, 반각 0.5칸, 상한 25칸)
  5. 폰트에 넣을 수 있는 글자인가 (한글은 배정, 나머지는 cp932)
"""
import io
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"f:\dev-kitahe\kitahe-l10n")
from kitae.core.windows import MARKUP          # noqa: E402
from kitae.build.hangul import is_hangul        # noqa: E402

SRC = [r"f:\dev-kitahe\kitahe-l10n\work\ko_%s.txt" % s for s in "abcd"]
DST = r"f:\dev-kitahe\kitahe-l10n\translation\KOTORI_01.json"
MAX_CELLS = 25.0


def cells(s):
    """화면에서 차지하는 칸 수. 반각(단바이트)은 절반이다."""
    n = 0.0
    for ch in MARKUP.sub("", s):
        try:
            n += 0.5 if len(ch.encode("cp932")) == 1 else 1.0
        except UnicodeEncodeError:
            n += 1.0                            # 한글 — 전각 칸에 배정된다
    return n


def parse():
    out, cur = {}, None
    for path in SRC:
        for raw in io.open(path, encoding="utf-8"):
            line = raw.rstrip("\n")
            m = re.fullmatch(r"\[(\d+)\]", line.strip())
            if m:
                cur = int(m.group(1))
                out[cur] = []
            elif cur is not None and line.strip():
                out[cur].append(line)
    return out


ko = parse()
doc = json.load(io.open(DST, encoding="utf-8"))
orig = {}
for e in doc["entries"]:
    orig.setdefault(e["window"], []).append((e["line"], e["text"]["ja"]))
for v in orig.values():
    v.sort()

bad = []
for w, lines in sorted(ko.items()):
    if w not in orig:
        bad.append(f"창{w}: 원문에 없음")
        continue
    ja = [t for _, t in orig[w]]
    if len(lines) != len(ja):
        bad.append(f"창{w}: 줄 {len(ja)} → {len(lines)}")
        continue
    for i, (a, b) in enumerate(zip(ja, lines)):
        ma, mb = sorted(MARKUP.findall(a)), sorted(MARKUP.findall(b))
        if ma != mb:
            bad.append(f"창{w} 줄{i}: 마크업 {ma} → {mb}")
        c = cells(b)
        if c > MAX_CELLS:
            bad.append(f"창{w} 줄{i}: {c:.1f}칸 (상한 {MAX_CELLS})  {b}")
        for ch in MARKUP.sub("", b):
            if is_hangul(ch):
                continue
            try:
                ch.encode("cp932")
            except UnicodeEncodeError:
                bad.append(f"창{w} 줄{i}: 인코딩 불가 {ch!r}")

missing = sorted(set(orig) - set(ko))
if missing:
    bad.append(f"번역 없는 창 {len(missing)}개: {missing[:12]}")

if bad:
    print(f"검사 실패 {len(bad)}건")
    for b in bad[:40]:
        print("  " + b)
    raise SystemExit(1)

n = 0
for e in doc["entries"]:
    t = ko.get(e["window"])
    if t and e["line"] < len(t):
        e["text"]["ko"] = t[e["line"]]
        n += 1
io.open(DST, "w", encoding="utf-8").write(
    json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

chars = {c for v in ko.values() for s in v for c in s if is_hangul(c)}
print(f"검사 통과 — 창 {len(ko)}개 / {n}줄 기록")
print(f"쓰인 한글 {len(chars)}자 (폰트 칸 3,384개 중)")
