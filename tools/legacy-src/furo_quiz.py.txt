# -*- coding: utf-8 -*-
"""風呂 8월 1일 밤 — 이름 맞히기 퀴즈의 **선택지**.

창 1·7·12·16 이 선택지다. 이 창들은 창 표시 명령(0x6B/0x6C)이 아니라
선택지 명령으로 열려서 씬 지도에 안 잡히고, 그래서 **날짜가 붙지 않는다.**
`date == "08-01"` 로 거른 [[furo_0801]] 에서 통째로 빠져 있었다.

## 옮기면서 걸린 것 — 한자 말장난 퀴즈

오답은 정답과 **한자만 다르고 읽기가 같은** 이름이다.

    春野琴梨 / 春野小鳥 / 春野琴里   ← 셋 다 「はるの ことり」

음차하면 셋 다 `하루노 코토리` 가 되어 **퀴즈가 성립하지 않는다.**
그래서 오답을 소리가 다른 이름으로 바꿨다 — 정답 하나에 그럴듯한 오답 셋이라는
구조는 지키면서, 한국어 화면에서 실제로 고를 수 있게 만드는 쪽을 택했다.

椎名 조 · 大里 조 · ローズヒル 조는 원문부터 소리가 갈리므로 그대로 음차한다.

`大里高校` 는 [[furo_0801]] 의 정답 대사와 표기를 맞춰야 한다. 선택지 상자가
좁아서 `오오사토고등학교`(８칸)는 위험하므로 양쪽 다 **`오오사토고교`** 로 줄였다.
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
DST = os.path.join(HERE, os.pardir, "風呂.json")
MARKUP = re.compile(r"@[^@]{0,8}@|&[^&]{0,16}&")
MAX = 12          # 선택지 상자는 좁다. 대사 ２５칸과 따로 잡는다

KO = {
 # 비행기에서 만난 사람 — ★椎名薫
 (1, 0): "시이나　헤키로",
 (1, 1): "시이나마치　유코",
 (1, 2): "시이나　카오루",
 (1, 3): "시이나　카오리",
 # 공항에 마중 나온 사람 — ★春野琴梨
 (7, 0): "하루노　코토리",
 (7, 1): "하루노　코토미",
 (7, 2): "하루노　코토네",
 (7, 3): "오오토리　코토리",
 # 코토리의 학교 — ★大里高校
 (12, 0): "오오사토고교",
 (12, 1): "나카사토고교",
 (12, 2): "코사토고교",
 (12, 3): "아마사토고교",
 # 신세 지는 아파트 — ★ローズヒル
 (16, 0): "로자비",
 (16, 1): "로즈힐",
 (16, 2): "로데시아",
 (16, 3): "로잔느",
}

# 정답 자리 — 다른 화면의 표기와 어긋나면 안 되는 곳이다
ANSWER = {(1, 2): "시이나　카오루", (7, 0): "하루노　코토리",
          (12, 0): "오오사토고교", (16, 1): "로즈힐"}

ASK = {
 (7, 1): "**읽기가 같고 한자만 다른 오답이다.** 원문은 정답 `春野琴梨` 에 오답 "
         "`春野小鳥`・`春野琴里` 를 붙였는데 셋 다 「はるの ことり」로 읽는다. "
         "즉 이 퀴즈는 소리가 아니라 **한자 표기를 아는지** 묻는 문제다. "
         "음차하면 셋 다 `하루노 코토리` 가 되어 고를 수가 없으므로 오답을 "
         "`코토미`・`코토네` 로 소리를 갈랐다. 퀴즈는 풀리지만 원문이 노린 "
         "'한자 표기 문제'라는 성격은 사라진다. 대안은 "
         "①`하루노 코토리(小鳥)` 처럼 한자 병기 ②지금처럼 소리를 가르기 "
         "③이 창만 원문 한자 유지. 어느 쪽으로 갈지.",
 (7, 3): "`鳳琴梨` 는 성이 `おおとり` 라 원문에서도 소리가 다르다. "
         "`오오토리　코토리` 로 그대로 음차했다 — 손대지 않아도 되는 오답이다.",
 (1, 3): "`椎名薫`(카오루) 과 `椎名香`(카오리) 는 **한 글자 차이의 비슷한 소리**다. "
         "원문의 헷갈림 정도가 한국어에서도 그대로 살아난 드문 경우라 음차만 했다. "
         "[[furo_quiz]] 창 7 과 달리 손볼 것이 없다.",
 (12, 0): "`大里高校` 를 `오오사토고교` 로 줄였다. 선택지 상자가 좁아 "
          "`오오사토고등학교` 는 넘칠 위험이 있다. 이 표기를 본문 대사와 "
          "[[kotori_02]] 창 80 에도 함께 반영했다.",
}


def cells(s):
    return len(MARKUP.sub("", s))


def halfwidth(s):
    out = []
    for c in MARKUP.sub("", s):
        try:
            if len(c.encode("cp932")) == 1:
                out.append(c)
        except UnicodeEncodeError:
            pass
    return out


doc = json.load(io.open(DST, encoding="utf-8"))
by = {(e["window"], e["line"]): e for e in doc["entries"]}

bad = []
for k, ko in KO.items():
    e = by.get(k)
    if e is None:
        bad.append(f"{k}: 원문에 없는 자리")
        continue
    if cells(ko) > MAX:
        bad.append(f"{k}: {cells(ko)}칸 > {MAX}  {ko}")
    h = halfwidth(ko)
    if h:
        bad.append(f"{k}: 반각 {h}  {ko}")
    if MARKUP.findall(e["text"]["ja"]):
        bad.append(f"{k}: 원문에 마크업이 있다  {e['text']['ja']}")

# 선택지 넷이 서로 달라야 고를 수 있다
for w in sorted({w for w, _l in KO}):
    grp = [ko for (ww, _l), ko in KO.items() if ww == w]
    if len(set(grp)) != len(grp):
        bad.append(f"창{w}: 선택지가 겹친다 {grp}")

# 정답 표기가 본문 대사와 어긋나지 않는가
body = "\n".join(e["text"].get("ko") or "" for e in doc["entries"])
for k, ans in ANSWER.items():
    if KO[k] != ans:
        bad.append(f"{k}: 정답 표기가 어긋났다")
    bare = ans.replace("　", "")
    if bare not in body.replace("　", ""):
        bad.append(f"{k}: 본문 대사에 '{ans}' 표기가 없다 — 먼저 본문을 맞춰라")

if bad:
    print(f"검사 실패 {len(bad)}건")
    for b in bad:
        print("  " + b)
    raise SystemExit(1)

for k, ko in KO.items():
    by[k]["text"]["ko"] = ko
for k, why in ASK.items():
    by[k]["ask"] = [{"why": why, "state": "open"}]

io.open(DST, "w", encoding="utf-8").write(
    json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
print(f"검사 통과 — 선택지 {len(KO)}줄 기록, 검토 요청 {len(ASK)}건")
