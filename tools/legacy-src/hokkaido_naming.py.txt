# -*- coding: utf-8 -*-
"""`北海大学`·`北海道庁` 표기를 풀어 쓴다.

    홋카이대학  → 홋카이도　대학
    홋카이도청  → 홋카이도　도청

## 왜 줄이지 않아도 되나

`北海大学` 는 실제로는 홋카이도 대학이고 `北海道庁` 은 홋카이도의 도청이다.
붙여 쓴 `홋카이대학`·`홋카이도청` 은 자리를 아끼려던 것인데, 재어 보니 아낄
필요가 없었다.

  * 대사·가이드북 한 줄은 ２５칸. 가장 빠듯한 곳이 １７칸이 된다
  * 커맨드 메뉴 목적지는 원문 `大通公園・テレビ塔` 이 이미 ９칸이다.
    가장 길어지는 `옛　홋카이도　도청` 이 딱 ９칸이라 상자를 넘지 않는다

## 세 파일이 같은 문자열이어야 한다

목적지 이름은 `KITACMDMENU`·`TRFGUIDEMAP`·`TRFVMSVIEW` 에 따로 들어 있고,
[[scenemap]] 의 씬 제목 장소 필드와 **글자까지 같아야** 대조가 걸린다
(`kitae/build/scenes.py` 의 `wanted`). 그래서 셋을 한꺼번에 바꾼다.

바이트로는 늘어나 제자리에 안 들어가지만(`avail` １１ B), UI 패처가 이사를
시켜 준다 — 지금도 `옛　홋카이도청` 은 이사한 상태다.
"""
import glob
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, os.pardir)
MAX = 25

SUB = [("홋카이대학", "홋카이도　대학"),
       ("홋카이도청", "홋카이도　도청")]


def cells(t):
    return sum(0.5 if len(c.encode("cp932", "replace")) == 1 else 1 for c in t)


def apply(ko):
    for a, b in SUB:
        ko = ko.replace(a, b)
    return ko


def main():
    # 퀴즈는 한 줄이 더 좁다 — 문제 ２０칸, 선택지 １５칸
    groups = [("대사", sorted(glob.glob(os.path.join(ROOT, "*.json"))), MAX),
              ("가이드북", sorted(glob.glob(os.path.join(ROOT, "guide", "*.json"))), MAX),
              ("퀴즈", sorted(glob.glob(os.path.join(ROOT, "quiz", "*.json"))), "quiz"),
              ("UI", sorted(glob.glob(os.path.join(ROOT, "ui", "*.json"))), None)]

    bad, hits, widest = [], [], (0, "")
    for label, paths, width in groups:
        for p in paths:
            with io.open(p, encoding="utf-8") as fh:
                doc = json.load(fh)
            if not isinstance(doc, dict) or "entries" not in doc:
                continue
            n = 0
            for e in doc["entries"]:
                ko = e["text"].get("ko") or ""
                new = apply(ko)
                if new == ko:
                    continue
                lim = width
                if width == "quiz":
                    lim = 20 if e.get("kind") == "문제" else 15
                # UI 는 한 슬롯에 여러 줄이 들어가므로 줄마다 잰다
                if lim and max(cells(l) for l in new.split("\n")) > lim:
                    bad.append(f"{os.path.basename(p)} "
                               f"[{e.get('window')}.{e.get('line')}] "
                               f"{cells(new):g}칸 > {lim}  {new}")
                    continue
                e["text"]["ko"] = new
                widest = max(widest, max((cells(l), l) for l in new.split("\n")))
                n += 1
            if n:
                with io.open(p, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
                hits.append(f"  {label:8} {os.path.basename(p):22} {n}곳")

    if bad:
        print(f"검사 실패 {len(bad)}건 — 줄이 넘친다")
        for b in bad:
            print("  " + b)
        return 1

    # 다시 돌려도 되돌아가지 않도록 원본 대본도 같이 고친다
    for p in ([os.path.join(ROOT, "ui", "_translate.py")]
              + sorted(glob.glob(os.path.join(HERE, "*.py")))):
        if not os.path.exists(p) or os.path.samefile(p, __file__):
            continue
        with io.open(p, encoding="utf-8") as fh:
            txt = fh.read()
        new = apply(txt)
        if new != txt:
            with io.open(p, "w", encoding="utf-8") as fh:
                fh.write(new)
            hits.append(f"  대본     {os.path.basename(p):22} 갱신")

    print("\n".join(hits))
    print(f"검사 통과 — 가장 긴 줄 {widest[0]:g}칸  {widest[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
