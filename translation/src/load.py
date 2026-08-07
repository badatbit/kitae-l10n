# -*- coding: utf-8 -*-
"""번역문 텍스트를 translation/<SCRIPT>.json 에 넣는다.

넣기 전에 전부 검사한다. 하나라도 어긋나면 쓰지 않는다 —
  1. 창 번호가 원문에 있는가
  2. 줄 수가 원문과 같은가 (.MSG 가 창별 줄 수를 고정한다)
  3. 인라인 마크업이 원문과 같은 집합인가 (@S@ 재생제어, &이름& 치환)
  4. 화면 폭을 넘지 않는가 (상한 25칸)
  5. 폰트에 넣을 수 있는 글자인가 (한글은 배정, 나머지는 cp932)
  6. 반각(단바이트) 글자가 없는가 — 원문이 그 자리에 쓰던 게 아니라면

반각 금지가 6번인 이유: 엔진은 타이밍 항목을 글자가 아니라 **바이트** 단위로
소비한다. 반각을 섞으면 배열이 줄 중간에서 바닥나고, 남은 글자가 프레임당
하나씩 쏟아진다(줄 뒷부분이 날아간다). 원문 23,030줄 중 반각을 그리는 줄은
39개뿐이고 그중 타이밍이 있는 줄은 0개다 — 게임이 하지 않는 조합이다.
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r"f:\dev-kitahe\kitahe-l10n")
from kitae.core.windows import MARKUP          # noqa: E402
from kitae.build.hangul import is_hangul        # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = [os.path.join(HERE, "ko_%s.txt" % s) for s in "abcd"]
DST = os.path.join(HERE, os.pardir, "KOTORI_01.json")
MAX_CELLS = 25.0


def halfwidth(s):
    """그려지는 반각(단바이트) 글자들. 마크업은 그려지지 않으니 뺀다."""
    out = []
    for ch in MARKUP.sub("", s):
        try:
            if len(ch.encode("cp932")) == 1:
                out.append(ch)
        except UnicodeEncodeError:
            pass                                # 한글 — 전각 칸에 배정된다
    return out


def cells(s):
    """화면에서 차지하는 칸 수. 전각만 쓰므로 글자 수와 같다."""
    return len(MARKUP.sub("", s))


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
            bad.append(f"창{w} 줄{i}: {c}칸 (상한 {MAX_CELLS})  {b}")
        # 원문이 그 자리에서 쓰던 반각만 허용한다 (예: '*4')
        extra = set(halfwidth(b)) - set(halfwidth(a))
        if extra:
            bad.append(f"창{w} 줄{i}: 반각 {sorted(extra)!r} — 타이밍이 "
                       f"바이트 단위라 줄 뒤가 날아간다  {b}")
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
