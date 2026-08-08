# -*- coding: utf-8 -*-
"""화자별 말투가 흔들리는 곳을 찾는다.

## 왜 화자로 재는가

창마다 화자가 EB 의 `0x6A` 로 지정돼 있고([EB-FORMAT.md](../../docs/EB-FORMAT.md)),
`translation/*.json` 의 `speaker` 는 거기서 뽑은 것이다(전 대본 대조 결과 어긋난
곳 ０). 그래서 **화자는 믿을 수 있는 기준**이고, 같은 화자의 말투가 갈리는 곳만
보면 된다.

## 두 가지를 본다

  * **채널 규칙** — `独白` 은 속마음이라 존댓말이 될 수 없다. `システム`·`説明`·
    `アナウンス` 는 반대로 늘 존댓말이다.
  * **소수쪽** — 사람 화자는 듣는 상대에 따라 갈리는 게 정상이다(`主人公` 은
    양코 씨에겐 존대, 코토리에겐 반말). 그래서 어느 쪽이 틀렸다고 할 수 없고,
    **적은 쪽을 눈으로 보라고 뽑아만 준다.**

## ★ `니다` 로 존댓말을 가리면 안 된다

`아주머니다` 가 `습니다` 와 같이 걸린다. 존댓말 `ㅂ니다` 는 **앞 음절의 종성이
ㅂ**(습·입·립·냅·합·옵)이라는 점으로 갈린다 — 한글 음절을 분해해 종성을 본다.
`드립니다`·`합니다` 를 반말로 잘못 잡아 본 뒤에 알았다.
"""
import collections
import glob
import io
import json
import os
import re

GROUP = "review"
HELP = "화자별 말투가 흔들리는 곳을 찾는다"

SENT = re.compile(r"[^。！？]*[。！？]")
MARKUP = re.compile(r"@[^@]*@|&[^&]*&")
QUOTED = re.compile(r"[『「“\"'].+[』」”\"']")

# 종성 ㅂ 의 인덱스. `ㅂ니다`·`ㅂ니까` 를 `아주머니다` 와 가르는 열쇠다
JONG_B = 17
POLITE_TAIL = re.compile(
    r"(세요|셔요|어요|아요|에요|예요|지요|죠|나요|가요|까요|군요|네요|데요|"
    r"시오|십시오|요)$")
PLAIN_TAIL = re.compile(r"(다|까|군|지|나|자|어|아|야|래|걸|텐데|는데|은데|구나|니)$")

CHANNEL_PLAIN = ("独白",)                      # 늘 반말(속마음)
CHANNEL_POLITE = ("システム", "説明", "アナウンス")   # 늘 존댓말


def _jong(ch):
    o = ord(ch)
    return (o - 0xAC00) % 28 if 0xAC00 <= o <= 0xD7A3 else -1


def polite(body):
    """존댓말로 끝나는가."""
    if POLITE_TAIL.search(body):
        return True
    m = re.search(r"(.)(니다|니까)$", body)
    return bool(m) and _jong(m.group(1)) == JONG_B


def plain(body):
    return bool(PLAIN_TAIL.search(body)) and not polite(body)


def sentences(lines):
    t = MARKUP.sub("", "".join(lines)).replace("　", " ")
    return [s.strip() for s in SENT.findall(t) if s.strip()]


def collect(root, lang="ko"):
    """{화자: {'존대'|'반말': [(대본, 창, 문장)]}}"""
    per = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in sorted(glob.glob(os.path.join(root, "*.json"))):
        if os.path.basename(p) == "glossary.json":
            continue
        with io.open(p, encoding="utf-8") as fh:
            try:
                doc = json.load(fh)
            except ValueError:
                continue
        if not isinstance(doc, dict) or "entries" not in doc:
            continue
        wins, spk = collections.defaultdict(list), {}
        for e in doc["entries"]:
            ko = (e["text"].get(lang) or "").strip()
            if ko:
                wins[e["window"]].append(ko)
                spk[e["window"]] = e.get("speaker")
        name = os.path.basename(p)[:-5]
        for w, lines in wins.items():
            for s in sentences(lines):
                body = s[:-1].strip()
                # 인용부호 안은 남의 말이나 글이다 — 화자의 말투가 아니다
                if len(body) < 3 or QUOTED.search(body):
                    continue
                if polite(body):
                    per[spk[w]]["존대"].append((name, w, s))
                elif plain(body):
                    per[spk[w]]["반말"].append((name, w, s))
    return per


def ignored(cfg):
    """채널 규칙에서 뺄 (대본, 창). 주문·의성어처럼 말이 아닌 창만이다."""
    p = os.path.join(cfg.data_dir, "tone_ignore.json")
    if not os.path.exists(p):
        return set()
    with io.open(p, encoding="utf-8") as fh:
        return {(r["script"], r["window"]) for r in json.load(fh)["windows"]}


def configure(p):
    p.add_argument("--speaker", help="이 화자만 본다")
    p.add_argument("--all", action="store_true", help="소수쪽 문장을 전부 나열한다")


def run(args):
    from kitae.config import Config
    cfg = Config.load()
    per = collect(cfg.path("translation"), cfg["target"])

    skip = ignored(cfg)
    bad = []
    for who in CHANNEL_PLAIN:
        bad += [("독백인데 존댓말", who) + r for r in per[who]["존대"]]
    for who in CHANNEL_POLITE:
        bad += [("안내인데 반말", who) + r for r in per[who]["반말"]]
    bad = [b for b in bad if (b[2], b[3]) not in skip]

    print("채널 규칙")
    if not bad:
        print(f"  어긋난 곳 없음  (규칙에서 뺀 창 {len(skip)}개)")
    for why, who, f, w, s in bad:
        print(f"  {f:10} 창{w:<5} {who:6} {why}\n        {s}")

    print("\n인물별 존대/반말  (소수쪽은 눈으로 확인할 자리)")
    print(f"  {'화자':<10} {'존대':>5} {'반말':>5}  소수쪽")
    rows = sorted(per.items(),
                  key=lambda x: -(len(x[1]["존대"]) + len(x[1]["반말"])))
    for who, d in rows:
        a, b = len(d["존대"]), len(d["반말"])
        if a + b < 4 or (args.speaker and who != args.speaker):
            continue
        minor = "존대" if a <= b else "반말"
        print(f"  {who!s:<10} {a:>5} {b:>5}  {minor} "
              f"{min(a, b) * 100 // (a + b)}%  ({min(a, b)}문장)")
        if args.all or args.speaker:
            for f, w, s in d[minor]:
                print(f"        {f:10} 창{w:<5} {s}")
    return 1 if bad else 0
