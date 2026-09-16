# -*- coding: utf-8 -*-
"""風呂 8월 1일 밤 — 삿포로 첫날 밤의 목욕 독백.

구조: 그날 만난 사람·장소의 이름을 하나씩 떠올리는 퀴즈다. 틀리면
「あれ？そんな名前だっけ？」, 맞히면 「そうそう！…だ。」 로 갈린다.
그래서 같은 뒷줄이 두 창에 반복된다 — 두 쪽 다 같은 문장을 써야 자연스럽다.

전부 독백이라 문어체(~다/~지)로 옮긴다. 대사와 문체를 갈라야 화면에서 구분된다.
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
MAX = 25

# 틀렸을 때 / 맞혔을 때 되풀이되는 뒷줄 — 한 곳에서 관리해 표기를 맞춘다
KAORU_2 = "좀　차가운　느낌이지만　예쁜　사람이었지・・"
KOTORI_A = "『오빠』라고　불리면　진짜　여동생처럼"
KOTORI_B = "느껴진단　말이지・・"
AGE = "딱　한　살　아래구나・・"
LUCKY = "삿포로에　친척이　있어　다행이었지・・"
MISS = "어라？　그런　이름이었나？　・・뭐　됐다・・"

KO = {
 (0, 0): "삿포로에　온　첫　밤이다。",
 (0, 1): "・・오늘　하루도　참　많은　일이　있었다・・",
 (0, 2): "먼저　비행기에서　만난　사람이・・",
 (2, 0): MISS,
 (2, 1): KAORU_2,
 (3, 0): "맞다！　시이나　카오루　씨다。",
 (3, 1): KAORU_2,
 (4, 0): "삿포로에　온　첫　밤이다。",
 (4, 1): "・・오늘　하루도　참　많은　일이　있었다・・",
 (4, 2): "먼저　비행기에서　만난　사람이・・",
 (5, 0): "・・・생각해　보니　이름도　못　들었구나・・",
 (6, 0): "그리고　그　뒤에　공항에　마중　나온　건・・",
 (8, 0): MISS,
 (8, 1): KOTORI_A,
 (8, 2): KOTORI_B,
 (9, 0): "맞다！　하루노　코토리다。",
 (9, 1): "친척인데　잊을　리가　없지。",
 (10, 0): KOTORI_A,
 (10, 1): KOTORI_B,
 (11, 0): "그　애는　고등학교　１학년이었지・・",
 (11, 1): "분명・・학교　이름이・・・",
 (13, 0): MISS,
 (13, 1): AGE,
 (14, 0): "맞다！　오오사토고교다。",
 (14, 1): AGE,
 (15, 0): "그리고　오늘부터　신세를　지는",
 (15, 1): "이　아파트　이름이・・분명・・・",
 (17, 0): MISS,
 (17, 1): LUCKY,
 (18, 0): "맞다！　로즈힐이다。",
 (18, 1): LUCKY,
 (19, 0): "오늘　하루　알찼고・・",
 (19, 1): "좋은　여행이　될　것　같은　예감이　든다・・",
 (19, 2): "자！　슬슬　나가자！",
}

# 옮긴 쪽이 봐 달라고 남기는 곳 — kitae review out 으로 나온다
ASK = {
 (9, 0): "원문은 `春野琴梨ちゃん`. `ちゃん`을 살리면 어색해서 뺐다. "
         "주인공이 사촌 동생을 떠올리는 자리인데 이대로 괜찮은지.",
 (14, 0): "`大里高校` 를 `오오사토고교` 로 옮겼다. 선택지 상자(창 12)가 좁아 "
          "`오오사토고등학교` 는 넘칠 위험이 있어 줄인 것이고, 정답 대사인 이 줄과 "
          "선택지·[[kotori_02]] 창 80 을 같은 표기로 맞췄다. 셋을 함께 바꿔야 한다.",
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
    if e.get("date") != "08-01":
        bad.append(f"{k}: 8월 1일이 아니다 ({e.get('date')})")
    if cells(ko) > MAX:
        bad.append(f"{k}: {cells(ko)}칸 > {MAX}  {ko}")
    h = halfwidth(ko)
    if h:
        bad.append(f"{k}: 반각 {h}  {ko}")
    ja, kk = e["text"]["ja"], ko
    if sorted(MARKUP.findall(ja)) != sorted(MARKUP.findall(kk)):
        bad.append(f"{k}: 마크업 불일치")

# 그 날짜의 모든 줄을 다 채웠는가
missing = [(e["window"], e["line"]) for e in doc["entries"]
           if e.get("date") == "08-01" and (e["window"], e["line"]) not in KO]
if missing:
    bad.append(f"빠진 줄 {len(missing)}개: {missing[:8]}")

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
print(f"검사 통과 — 8월 1일 {len(KO)}줄 기록, 검토 요청 {len(ASK)}건")
