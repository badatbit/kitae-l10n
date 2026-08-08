# -*- coding: utf-8 -*-
"""가이드북 관광지 — **이미 옮긴 문장 가져오기**.

가이드북 본문과 대사·협력 소개는 같은 문장을 여럿 공유한다. 시계탑 설명은
[[kotori_02]] 의 독백과 글자까지 같고, 자동차 회사 소개는 [[guide4]] 와 같다.
같은 문장을 두 번 옮기면 표기가 갈리므로 있는 것을 그대로 가져온다.

## ★ 줄 경계를 옮긴 번역은 못 가져온다

대사에서는 한 창(２~４줄)을 통째로 다시 끊어 옮겼다. 그래서 **일본어 한 줄과
한국어 한 줄이 １:１로 맞지 않는 곳이 있다.**

    ja  もちろんこれは架空の設定。
    ko  일하지만　물론　이건　가공의　설정이다。   ← 앞줄의 `일하지만` 이 붙어 있다

    ja  防火線として明治４年に設けられた逍遙地だった。
    ko  본래는　메이지４년의　방화선　겸　산책지였다。 ← 앞줄의 `본래는` 이 붙어 있다

기계로 가려낼 수 없어 ６８개를 눈으로 보고 １３개를 뺐다. 뺀 것은
`SKIP` 에 이유와 함께 남긴다 — 나중에 손으로 옮길 몫이다.
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
GUIDE = os.path.join(HERE, os.pardir, "guide")
TRANS = os.path.join(HERE, os.pardir)
MAX = 25

# 줄 경계가 어긋나 가져오면 안 되는 문장
SKIP = {
 "「コンタックスＧ１」と「コンタックスＴｉｘ」を": "앞줄의 `이 회사의` 가 붙어 있다",
 "もちろんこれは架空の設定。": "앞줄의 `일하지만` 이 붙어 있다",
 "グリーンベルト。もともとは市街地が火災になった際の": "뒷줄 내용으로 바뀌어 있다",
 "ノートパソコン「リブレット」を使っている。": "앞줄의 `이 회사의` 가 붙어 있다",
 "始業・就業の時間を学生に報せると共に　札幌市民にも": "`삿포로 시민` 을 뒷줄로 넘겼다",
 "当時と変わらぬ澄んだ鐘の音を響かせている。": "앞줄 내용이 섞여 있다",
 "時を伝えていたといい現在も都会の雑踏に紛れながらも": "줄을 다시 끊었다",
 "現在はライラックやアカシアの並木　大小６０ほどの": "`６０여 개` 를 뒷줄로 넘겼다",
 "花壇　涼味を演出する噴水　数々の彫刻作品などが": "앞줄의 `６０여 개` 가 붙어 있다",
 "西１丁目から西１２丁目まで　札幌中心部を貫く巨大な": "줄을 다시 끊었다",
 "防火線として明治４年に設けられた逍遙地だった。": "앞줄의 `본래는` 이 붙어 있다",
 "露店が立ち　いっそうの活気を見せる。": "앞줄의 `노점이` 가 붙어 있다",
 "５月からは名物のトウキビ（トウモロコシ）の": "`노점이` 를 이 줄로 당겼다",
}


def cells(t):
    return sum(0.5 if len(c.encode("cp932", "replace")) == 1 else 1 for c in t)


def main():
    # 이미 번역된 모든 원장에서 ja→ko 를 모은다
    done = {}
    for sub in (None, "ui", "quiz"):
        d = TRANS if sub is None else os.path.join(TRANS, sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".json"):
                continue
            with io.open(os.path.join(d, f), encoding="utf-8") as fh:
                doc = json.load(fh)
            if not isinstance(doc, dict) or not doc.get("entries"):
                continue
            for e in doc["entries"]:
                ko = (e["text"].get("ko") or "").strip()
                if ko:
                    done.setdefault(e["text"]["ja"], ko)

    n, used = 0, set()
    for f in ("guide.json", "guide2.json", "guides.json"):
        p = os.path.join(GUIDE, f)
        with io.open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        for e in doc["entries"]:
            ja = e["text"]["ja"]
            if (e["text"].get("ko") or "").strip():
                continue
            if ja in SKIP or ja not in done:
                continue
            ko = done[ja]
            if cells(ko) > MAX or "\n" in ko:
                continue
            e["text"]["ko"] = ko
            used.add(ja)
            n += 1
        with io.open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

    left = set()
    for f in ("guide.json", "guide2.json", "guides.json"):
        with io.open(os.path.join(GUIDE, f), encoding="utf-8") as fh:
            for e in json.load(fh)["entries"]:
                if not (e["text"].get("ko") or "").strip():
                    left.add(e["text"]["ja"])
    print(f"가져온 문장 {len(used)}개 → {n}줄 반영 (건너뛴 것 {len(SKIP)}개)")
    print(f"손으로 옮길 문장 {len(left)}개 남음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
