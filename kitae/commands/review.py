# -*- coding: utf-8 -*-
"""옮긴 쪽이 봐 달라고 남긴 곳을 사람에게 낸다.

  kitae review out            → 검토할 곳을 md 로 (translation/review.md)
  kitae review apply          → 사람이 고친 것을 번역 파일로 되돌린다
  kitae review list           → 대기 중인 곳을 세어만 본다

## 기계 검사와 다른 것이다
길이가 넘쳤다거나 마크업이 빠졌다는 건 빌드가 잡는다. **뜻이 애매하다는 것은
옮긴 쪽만 안다.** 그래서 옮기면서 그 자리에 `ask` 를 남기고 여기서 겨눠 준다.

## 번역 파일이 원본이다
대기 목록을 따로 관리하지 않는다. 항목에 `ask` 가 붙어 있으면 그게 곧 대기열이다 —
목록을 따로 적으면 원장과 조용히 어긋난다.

## 항목에 붙는 모양

    {"window": 12, "line": 0, "speaker": "琴梨",
     "text": {"ja": "...", "ko": "..."},
     "ask": [{"why": "「お兄ちゃん」을 오빠로 옮겼는데 사촌이라 어색할 수 있다",
              "state": "open"}]}

`state` 는 `open`(대기) · `done`(반영됨) · `held`(보류).
"""
import io
import json
import os
import re

from kitae.config import Config

GROUP = "process"
HELP = "번역자가 봐 달라고 남긴 곳 내기·되돌리기 (out · apply · list)"
DEFAULT = os.path.join("translation", "review.md")


def configure(p):
    p.add_argument("action", choices=["out", "apply", "list"])
    p.add_argument("file", nargs="?", help=f"md 경로 (기본 {DEFAULT})")
    p.add_argument("-l", "--lang", help="대상 언어 (기본 설정의 target)")
    p.add_argument("--dry", action="store_true", help="쓰지 않고 결과만")


def _docs(cfg):
    """[(스크립트, 경로, 문서)] — translation/*.json 전부."""
    d = cfg.path("translation")
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        p = os.path.join(d, f)
        with io.open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        if isinstance(doc, dict) and doc.get("entries"):
            out.append((f[:-5], p, doc))
    return out


def _asks(e):
    a = e.get("ask")
    return [a] if isinstance(a, dict) else (a or [])


def _open(e):
    return [a for a in _asks(e) if a.get("state", "open") == "open"]


def run(args):
    cfg = Config.load()
    lang = args.lang or cfg["target"]
    src = cfg["source"]
    path = cfg.path(args.file or DEFAULT)
    docs = _docs(cfg)

    if args.action == "list":
        tot = 0
        for name, _p, doc in docs:
            n = sum(len(_open(e)) for e in doc["entries"])
            if n:
                print(f"  {name:<16} {n}곳")
                tot += n
        print(f"봐 달라고 남긴 곳 {tot}곳" if tot else "대기 중인 곳이 없다.")
        return 0

    if args.action == "out":
        L = ["# 번역 검토", "",
             "옮긴 쪽이 봐 달라고 남긴 곳이다. `kitae review out` 이 만든다.", "",
             "`->` 아래에 고쳐 쓴다. **비우면 원안 그대로 확정**, `-` 하나면 보류.",
             "다 보셨으면 `kitae review apply`.", ""]
        n = 0
        for name, _p, doc in docs:
            hit = [e for e in doc["entries"] if _open(e)]
            if not hit:
                continue
            L += [f"## {name}", ""]
            for e in hit:
                n += 1
                who = e.get("speaker") or ""
                L += [f"### {name} 창{e['window']} 줄{e['line']}"
                      + (f"  ·  {who}" if who else ""), "",
                      "```",
                      f"원문  {e['text'].get(src, '')}",
                      f"번역  {e['text'].get(lang, '')}",
                      "```", ""]
                for a in _open(e):
                    L.append(f"- **?** {a['why']}")
                L += ["", "```", "->", "```", ""]
        if not n:
            print("봐 달라고 남긴 곳이 없다.")
            return 0
        os.makedirs(os.path.dirname(path), exist_ok=True)
        io.open(path, "w", encoding="utf-8").write("\n".join(L) + "\n")
        print(f"검토할 곳 {n}곳 → {os.path.relpath(path, cfg.root)}")
        return 0

    # apply
    if not os.path.exists(path):
        print(f"{os.path.relpath(path, cfg.root)} 가 없다 — 먼저 kitae review out")
        return 2
    txt = io.open(path, encoding="utf-8").read()
    edits = {}
    for m in re.finditer(r"^### (\S+) 창(\d+) 줄(\d+).*?```\n->(.*?)```",
                         txt, re.S | re.M):
        edits[(m.group(1), int(m.group(2)), int(m.group(3)))] = m.group(4).strip()

    fixed = kept = held = 0
    for name, p, doc in docs:
        dirty = False
        for e in doc["entries"]:
            v = edits.get((name, e["window"], e["line"]))
            if v is None or not _open(e):
                continue
            if v == "-":
                held += 1
                continue
            if v:
                e["text"][lang] = v
                fixed += 1
            else:
                kept += 1
            for a in _asks(e):
                a["state"] = "done"
            dirty = True
        if dirty and not args.dry:
            io.open(p, "w", encoding="utf-8").write(
                json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    print(f"고침 {fixed} · 원안 확정 {kept} · 보류 {held}"
          + ("  (dry)" if args.dry else ""))
    return 0
