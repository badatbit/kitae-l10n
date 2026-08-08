# -*- coding: utf-8 -*-
"""다국어 번역 데이터.

한 시나리오 = `translation/<SCRIPT>.json` 하나. 항목마다 언어 키를 갖는 dict를
두어 ja/ko/en/… 을 나란히 관리한다. 원문(`source` 언어)은 게임에서 추출한 값이
그대로 들어가고, 나머지 언어는 비어 있으면 미번역이다.

```json
{
  "script": "KOTORI_01",
  "entries": [
    {"window": 1, "line": 0, "speaker": "琴梨", "kind": "대사",
     "voice": "a0013.WAV", "chars": 7,
     "text": {"ja": "…", "ko": "저기, 엄마!", "en": ""}}
  ]
}
```

창별 줄 수는 게임의 `.MSG` 테이블이 고정하므로 항목을 늘리거나 줄일 수 없다.
번역은 각 줄을 1:1로 대체한다.
"""
import io
import json
import os

KEY = ("window", "line")


def path_for(cfg, script):
    return os.path.join(cfg.translation_dir, f"{script.upper()}.json")


def load(cfg, script):
    p = path_for(cfg, script)
    if not os.path.exists(p):
        return None
    with io.open(p, encoding="utf-8") as f:
        return json.load(f)


def save(cfg, script, doc):
    os.makedirs(cfg.translation_dir, exist_ok=True)
    p = path_for(cfg, script)
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    return p


def index(doc):
    """(window, line) -> entry"""
    return {(e["window"], e["line"]): e for e in doc["entries"]}


def text(entry, lang, fallback=None):
    """해당 언어의 문장. 비어 있으면 fallback 언어로."""
    t = (entry.get("text") or {}).get(lang) or ""
    if t.strip():
        return t
    if fallback:
        return (entry.get("text") or {}).get(fallback) or ""
    return ""


def merge(doc, fresh, languages):
    """게임에서 다시 추출한 `fresh` 위에 기존 번역을 얹는다."""
    old = index(doc) if doc else {}
    for e in fresh["entries"]:
        prev = old.get((e["window"], e["line"]))
        e.setdefault("text", {})
        for lang in languages:
            e["text"].setdefault(lang, "")
        if prev:
            for lang, v in (prev.get("text") or {}).items():
                if lang in e["text"] and v and v.strip():
                    e["text"][lang] = v
            # 봐 달라고 남긴 것은 다시 뽑아도 살아남아야 한다
            if prev.get("ask"):
                e["ask"] = prev["ask"]
    return fresh


def stats(doc, languages):
    """언어별 (번역된 줄, 전체 줄)."""
    out = {}
    entries = doc["entries"]
    for lang in languages:
        done = sum(1 for e in entries
                   if ((e.get("text") or {}).get(lang) or "").strip())
        out[lang] = (done, len(entries))
    return out
