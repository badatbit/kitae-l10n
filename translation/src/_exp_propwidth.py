# -*- coding: utf-8 -*-
"""※ 실험용 — 가변폭 조사. 끝나면 되돌린다.

`HANYOU` 창 ３１２·３１５·３１８·３２１·３２４·３２７(로즈힐 응접실, 같은 대사 여섯 갈래)의
두 줄을 시험 문자열로 바꾼다.

## 무엇을 보려는 것인가

엔진은 **반각(１２×２４)과 전각(２４×２４) 두 폭을 이미 쓴다.** 그런데
`CTRFFont::DrawChar` 는 폭을 돌려주지 않으므로(에필로그에 r0 설정이 없다),
다음 글자의 자리를 정하는 것은 **부르는 쪽**이다. 그 부르는 쪽이

  (가) 글자마다 폭을 더해 가며 미는가        → 가변폭으로 갈 길이 있다
  (나) 열 번호 × 고정 폭으로 좌표를 내는가   → 배치를 다시 써야 한다

ASCII 만으로 된 줄을 그려 보면 **한 화면에 답이 나온다.**

  * 촘촘히 붙어 나오면 → 반각 폭(１２px)이 실제로 반영된다 = (가) 쪽
  * 한 글자씩 띄엄띄엄 나오면 → 고정 격자에 얹는다 = (나) 쪽

둘째 줄은 자尺이다. `i` 와 `m` 과 `W` 를 나란히 놓았으니, 폭이 글자마다
다르면 세 덩어리의 길이가 달라지고 같으면 똑같이 나온다. 게임의 반각 글리프는
３６바이트 고정 칸이라 **글리프 자체는 １２px 고정**이다 — 그러므로 이 줄에서
길이가 갈린다면 그건 엔진이 글리프 잉크 폭을 따로 재고 있다는 뜻이 된다.

## 되돌리기

    python translation/src/_exp_propwidth.py --revert
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
NAME = "HANYOU"
WINS = (312, 315, 318, 321, 324, 327)

LINE0 = "가가가가가가가가나나나나나나나나"
LINE1 = "가나다라마바사아자차카타파하。１２３"

ORIG = {
    0: "로즈힐　미나미히라기시　응접실이다。",
    1: "방에는　아무도　없다。",
}


def main(revert=False):
    p = os.path.join(ROOT, NAME + ".json")
    with io.open(p, encoding="utf-8") as fh:
        doc = json.load(fh)
    idx = {(e["window"], e["line"]): e for e in doc["entries"]}

    n = 0
    for w in WINS:
        for ln, txt in ((0, LINE0), (1, LINE1)):
            e = idx.get((w, ln))
            if e is None:
                continue
            e["text"]["ko"] = ORIG[ln] if revert else txt
            n += 1
    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    print(("되돌림" if revert else "시험 문자열 넣음") + f" — {n}줄")
    if not revert:
        print(f"  줄0  {LINE0}")
        print(f"  줄1  {LINE1}")
    return 0


if __name__ == "__main__":
    sys.exit(main("--revert" in sys.argv))
