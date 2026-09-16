# -*- coding: utf-8 -*-
"""욕실 회상 — 날짜 있는 창 ①. 되풀이 문장 전체 + ８월３~５일.

[[furo_a]] 가 날짜 없는 창만 채웠기 때문에, 같은 문장이 날짜 있는 창에는
그대로 남아 있었다. 여기서 **날짜 있는 창 전체**에 한 번에 채운다.
문자열이 같으므로 번역도 같아야 한다 — 갈리면 같은 장면이 날마다 다르게
읽힌다.

## 되풀이 문장은 [[furo_a]] 와 글자까지 같아야 한다

`REPEAT` 를 그대로 옮겨 적었다. 한쪽만 고치면 어긋나므로, 고칠 일이 생기면
**두 파일을 같이** 고쳐야 한다.

## ８월５일은 첫 관광 날이다

`旧北海道庁`·`大通公園`·`川原鮎` 처럼 앞서 확정한 이름이 처음 회상되는 날이라,
glossary 와 커맨드 메뉴 표기를 그대로 쓴다. `喫茶エンゼル` 은 [[furo_a]] 에서
`エンジェル` 과 가르려고 `엔제르` 로 정했으므로 여기서도 그렇게 적는다.
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, os.pardir, os.pardir)))
NAME = "風呂"
MAX = 25

# ★ [[furo_a]] 의 REPEAT 과 글자까지 같아야 한다
REPEAT = {
 "ふぅ・・いい湯加減だ。": "후우・・물　온도가　딱　좋다。",
 "まぁ・・色々あったけど　今日も楽しかったな。":
     "뭐・・이런저런　일이　있었지만　오늘도　즐거웠다。",
 "さて！　そろそろ上がろう！": "자！　슬슬　나가자！",
 "あれ？　そうだっけ？　・・まぁいいや・・": "어？　그랬던가？　・・뭐　됐다・・",
 "・・今日も一日　いろんなことがあったな・・":
     "・・오늘도　하루　여러　일이　있었다・・",
 "名前は確か・・・": "이름이　아마・・・",
 "今日一日　充実していたし・・": "오늘　하루　알찼고・・",
 "やっぱりこっちに来て良かったな・・": "역시　여기　오길　잘했다・・",
 "のどかな感じの遊園地だったな・・": "한가로운　느낌의　유원지였지・・",
 "最近は　おかしなものが流行るな・・": "요즘은　희한한　게　유행이구나・・",
 "ちょっと変わった雰囲気の女の子だったな・・": "좀　독특한　분위기의　여자애였지・・",
 "そうそう・・里中梢ちゃんだ。": "맞다・・사토나카　코즈에다。",
 "北海道ならではの食材が　たくさん並んでいたな・・":
     "홋카이도다운　식재료가　잔뜩　있었지・・",
 "あそこで働いていた金髪の店員さん　綺麗だったな・・":
     "거기서　일하던　금발　점원　예뻤지・・",
 "結構　見応えのある水族館だったな・・": "꽤　볼만한　수족관이었지・・",
 "彼女　ベンチに座って　ずっと本を読んでたっけ・・":
     "그녀는　벤치에　앉아　계속　책을　읽었지・・",
 "きっと仕事の忙しい中　時間を作って": "분명　바쁜　일　틈틈이　시간을　내서",
 "あのベンチに来てるんだろうな・・": "그　벤치에　오는　거겠지・・",
}

BRICK = "낡은　붉은　벽돌의　인상적인　건물이었지・・"
PARK = "초록　가득한　넓은　공원이었지・・"
WHITE = ("아마　겨울엔　화이트・일루미네이션",
         "행사장이　된다고　코토리가　말했었지・・",
         "어떤　행사일까？　한번　보고　싶다・・")
AYU = "밝고　씩씩한　여자애였지・・"
TANYA = "금발의・・무척　예쁜　여자애였지・・"
GOAL = "뚜렷한　목표를　갖고　애쓰고　있구나・・"
MASTER = "그　가게　주인　따뜻해　보이는　사람이었지・・"

KO = {
 (49, 1): "먼저　코토리랑　간　곳이・・",
 (51, 1): BRICK,
 (52, 0): "맞다・・옛　홋카이도　도청이다。",
 (52, 1): BRICK,
 (53, 0): "그리고　그　뒤　간　공원　이름은・・・",
 (55, 1): PARK,
 (56, 0): WHITE[0],
 (56, 1): WHITE[1],
 (56, 2): WHITE[2],
 (57, 0): "맞다・・오도리공원이다。",
 (57, 1): PARK,
 (58, 0): WHITE[0],
 (58, 1): WHITE[1],
 (58, 2): WHITE[2],
 (59, 0): "그리고　그　뒤　타누키코지에서　딱　만난　사람이",
 (59, 1): "코토리의　단짝・・・",
 (61, 1): AYU,
 (62, 0): "맞다・・카와하라　아유다。",
 (62, 1): AYU,
 (63, 1): "좋은　여행이　될　것　같은　예감이　든다・・",
 (108, 1): "운하공예관에서　만난　여자애　이름이・・아마・・",
 (110, 1): TANYA,
 (111, 0): "맞다・・타냐다。",
 (111, 1): TANYA,
 (112, 0): "그러고　공원에서　노을을　보는　그녀를　만났지・・",
 (112, 1): "그녀는　노을빛을　유리로　재현하고　싶다고",
 (112, 2): "그랬지・・러시아어로　아마・・",
 (114, 1): GOAL,
 (115, 0): "맞다・・츠베트・자카타다。",
 (115, 1): GOAL,
 (116, 0): "그러고　그녀가　좋아하는　찻집에　갔었지・・",
 (116, 1): "가게　이름이・・아마・・・",
 (118, 1): MASTER,
 (119, 0): "맞다・・찻집　엔제르다。",
 (119, 1): MASTER,
}

ASK = {
 (56, 0): "`ホワイト・イルミネーション` 은 삿포로의 겨울 행사이고 이 게임의 부제이기도 "
          "하다(`北へ。White Illumination`). 음차한 `화이트・일루미네이션` 으로 뒀다.",
 (119, 0): "`喫茶エンゼル` 을 `찻집　엔제르` 로 적었다. [[furo_a]] 창 １１７ 에서 "
           "`エンジェル`(엔젤)과 가르려고 정한 표기다. 한쪽만 고치면 어긋난다.",
}


def cells(t):
    return sum(0.5 if len(c.encode("cp932", "replace")) == 1 else 1 for c in t)


def main():
    from kitae.config import Config
    from kitae.core import scenemap
    cfg = Config.load()
    wi = scenemap.window_info(cfg, NAME)

    p = os.path.join(ROOT, NAME + ".json")
    with io.open(p, encoding="utf-8") as fh:
        doc = json.load(fh)
    idx = {(e["window"], e["line"]): e for e in doc["entries"]}

    bad = []
    for k, ko in KO.items():
        if k not in idx:
            bad.append(f"{k}: 그런 자리가 없다")
        elif cells(ko) > MAX:
            bad.append(f"{k}: {cells(ko):g}칸 > {MAX}  {ko}")
    for ja, ko in REPEAT.items():
        if cells(ko) > MAX:
            bad.append(f"{ja[:18]}: {cells(ko):g}칸 > {MAX}  {ko}")
    if bad:
        print(f"검사 실패 {len(bad)}건")
        for b in bad:
            print("  " + b)
        return 1

    n = r = 0
    for k, ko in KO.items():
        if not (idx[k]["text"].get("ko") or "").strip():
            idx[k]["text"]["ko"] = ko
            n += 1
    # 이번엔 날짜 있는 창에 채운다
    for e in doc["entries"]:
        if wi.get(e["window"], {}).get("date") is None:
            continue
        ja = e["text"]["ja"]
        if ja in REPEAT and not (e["text"].get("ko") or "").strip():
            e["text"]["ko"] = REPEAT[ja]
            r += 1
    for k, why in ASK.items():
        if k in idx:
            idx[k]["ask"] = [{"why": why, "state": "open"}]

    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    tot = len(doc["entries"])
    done = sum(1 for e in doc["entries"] if (e["text"].get("ko") or "").strip())
    print(f"검사 통과 — 지정 {n}줄 + 되풀이 {r}줄 = {n + r}줄 채움. "
          f"{NAME} {done}/{tot}줄 ({done * 100 // tot}%), 검토 요청 {len(ASK)}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
