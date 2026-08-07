# -*- coding: utf-8 -*-
"""DLL 안에 박힌 시스템 텍스트를 뽑아 번역 파일로 만든다."""
import io
import json
import os

from kitae.config import Config

GROUP = "extract"
HELP = "메뉴·안내문 등 DLL 안의 시스템 텍스트를 뽑는다"

# 화면에 늘 보이는 것부터. 미니게임·사운드룸은 뒤로 미룬다.
CORE = ["KITACMDMENU", "ITEMMENU", "TRFSYSCONFIG", "TRFOPTIONGAME",
        "COMMONSAVE", "KITATITLE", "TRFNAMEIN", "TRFGUIDEMAP",
        "TRFVMSVIEW", "KITAE", "TRFSTRINGS"]


def configure(p):
    p.add_argument("modules", nargs="*",
                   help="모듈 이름 (없으면 핵심 모듈, all 이면 전부)")
    p.add_argument("-l", "--list", action="store_true", help="내용을 찍어만 본다")
    # 1 이어야 한다. 2 로 걸렀더니 조립에 쓰이는 한 글자짜리 조각(月, 日,
    # Ａ, １ …)이 통째로 빠져서 날짜와 포트 표시가 깨졌다.
    p.add_argument("--min-wide", type=int, default=1,
                   help="전각 글자가 최소 몇 개는 있어야 표시 문자열로 본다")


def _modules(cfg, want):
    """[(디스크 경로, 이름)] — 요청한 모듈만."""
    from kitae.core.gdfs import GdFs
    fs = GdFs(cfg.track(3))
    out = []
    for row in fs.walk():
        path, is_dir = row[0], row[-1]
        if is_dir or not path.upper().endswith((".DLL", ".EXE")):
            continue
        name = os.path.basename(path).rsplit(".", 1)[0].upper()
        if want is None or name in want:
            out.append((path, name))
    return fs, out


def run(args):
    from kitae.core import pestr

    cfg = Config.load()
    want = None if args.modules == ["all"] else set(
        m.upper() for m in (args.modules or CORE))
    fs, mods = _modules(cfg, want)
    dst_dir = cfg.path("translation", "ui")
    if not args.list:
        os.makedirs(dst_dir, exist_ok=True)

    src, tgt = cfg["source"], cfg["target"]
    total = 0
    for path, name in sorted(mods, key=lambda m: m[1]):
        lba, size = fs.find(path)
        blob = fs.read(lba, size)
        found = pestr.strings(blob, min_wide=args.min_wide)
        if not found:
            continue
        total += len(found)
        print(f"\n=== {name}  ({len(found)}개, "
              f"{sum(s['size'] for s in found):,}B)")
        if args.list:
            for s in found:
                print(f"  {s['offset']:#08x} [{s['section']}] {s['size']:>4}B  "
                      + s["text"].replace("\n", " ⏎ "))
            continue

        # 기존 번역은 지키고 원문 목록만 갱신한다 (오프셋이 열쇠)
        dst = os.path.join(dst_dir, name + ".json")
        old = {}
        if os.path.exists(dst):
            with io.open(dst, encoding="utf-8") as fh:
                for e in json.load(fh)["entries"]:
                    old[e["offset"]] = e.get("text", {})
        entries = []
        for s in found:
            t = dict(old.get(s["offset"], {}))
            t[src] = s["text"]
            t.setdefault(tgt, "")
            entries.append({"offset": s["offset"], "size": s["size"],
                            "avail": s["avail"], "section": s["section"],
                            "text": t})
        doc = {"module": name, "path": path, "entries": entries}
        with io.open(dst, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        done = sum(1 for e in entries if (e["text"].get(tgt) or "").strip())
        print(f"  → translation/ui/{name}.json   번역 {done}/{len(entries)}")

    print(f"\n합계 {total:,}개")
    if not args.list:
        print("바이트 길이가 원문 이하여야 합니다 — 자리에 덮어쓰기 때문입니다")
    return 0
