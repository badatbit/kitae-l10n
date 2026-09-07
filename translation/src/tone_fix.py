# -*- coding: utf-8 -*-
"""`kitae tone` 이 잡아낸 말투 어긋남을 고친다.

## 椎名薫 — 창 ２７·４１ 만 반말이었다

카오루의 원문은 처음 만난 사람에게 쓰는 차분한 존대다.

    〜みたいなんですけど / 〜てますよ / ・・何か？ / 頂ける？ / 〜のよね / 〜わ

우리 번역도 １４문장이 `~요`체인데 이 두 창만 반말이었다. 원문
`付けてたのよ。覚えてないの？` 는 창 ５５ 의 `苦手なの`(→ 못　타요)、창 ６５ 의
`三つあるの`(→ 있어요) 와 **같은 어투**다. 즉 여기만 우리가 반말로 옮긴 것이다.

창 ２７ 과 ４１ 은 글자가 똑같다(같은 대사가 두 갈래로 갈려 있다).

## `그` 를 덜어 냈다

`있었어` → `있었어요` 로 두 칸이 늘어 ２７칸이 된다. 앞 줄이 `이미` 로 끝나므로
`그` 없이도 무엇을 가리키는지 흐려지지 않는다.

## 春野琴梨 — `나 ・・ 입니다` 가 어색했다

    ガイドは私　春野琴梨です！ → 가이드는　나　하루노　코토리입니다！

원문은 `行こ！`(반말) 뒤에 `です`(존대)를 붙여 짓궂게 자기를 소개하는 대목이다.
일본어 `私` 는 어느 쪽에도 쓰이지만 한국어 `나 … 입니다` 는 한 문장 안에서
부딪친다. `저` 로 바꿔 소개하는 말투를 살린다 — 두 글자 다 한 칸이라 자리도 같다.
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
MAX = 25

FIX = {
 ("KOTORI_01", 27, 0): "네？　그게　무슨　소리죠・・",
 ("KOTORI_01", 27, 2): "엉뚱한　버클　채우고　있었어요。기억　안　나요？",
 ("KOTORI_01", 41, 0): "네？　그게　무슨　소리죠・・",
 ("KOTORI_01", 41, 2): "엉뚱한　버클　채우고　있었어요。기억　안　나요？",
 ("KOTORI_02", 9, 2): "가이드는　저　하루노　코토리입니다！",
 ("KOTORI_02", 21, 2): "가이드는　저　하루노　코토리입니다！",
}


def cells(t):
    return sum(0.5 if len(c.encode("cp932", "replace")) == 1 else 1 for c in t)


def main():
    docs, bad, n = {}, [], 0
    for name in sorted({k[0] for k in FIX}):
        p = os.path.join(ROOT, name + ".json")
        with io.open(p, encoding="utf-8") as fh:
            docs[name] = json.load(fh)
    idx = {(name, e["window"], e["line"]): e
           for name, d in docs.items() for e in d["entries"]}

    for k, ko in FIX.items():
        e = idx.get(k)
        if e is None:
            bad.append(f"{k}: 그런 자리가 없다")
        elif cells(ko) > MAX:
            bad.append(f"{k}: {cells(ko):g}칸 > {MAX}  {ko}")
    if bad:
        print(f"검사 실패 {len(bad)}건")
        for b in bad:
            print("  " + b)
        return 1

    for k, ko in FIX.items():
        old = idx[k]["text"].get("ko") or ""
        if old != ko:
            print(f"  {k[0]} 창{k[1]}.{k[2]}  {cells(ko):g}칸")
            print(f"      전 {old}")
            print(f"      후 {ko}")
            idx[k]["text"]["ko"] = ko
            n += 1

    for name, d in docs.items():
        p = os.path.join(ROOT, name + ".json")
        with io.open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    print(f"검사 통과 — {n}줄 고침")
    return 0


if __name__ == "__main__":
    sys.exit(main())
