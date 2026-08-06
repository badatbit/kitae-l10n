# -*- coding: utf-8 -*-
"""원본 디스크에서 파일을 꺼낸다."""
import os

from kitae.config import Config
from kitae.core.gdfs import GdFs

GROUP = "inspect"
HELP = "디스크 이미지의 파일을 나열하거나 꺼낸다"


def configure(p):
    p.add_argument("path", nargs="?",
                   help="꺼낼 디스크 경로 (예: RESOURCE/PLOT.CB). 없으면 목록만")
    p.add_argument("-o", "--out", help="저장 위치 (기본 work/unpack)")
    p.add_argument("--all", action="store_true", help="전부 꺼낸다")
    p.add_argument("--filter", help="이름에 이 문자열이 든 것만")


def run(args):
    cfg = Config.load()
    track = cfg.track(3)
    if not track:
        print("원본 데이터 트랙을 찾을 수 없습니다. kitae check 를 확인하세요")
        return 1
    fs = GdFs(track=track)
    out = cfg.path(args.out or os.path.join(cfg["work_dir"], "unpack"))

    if args.path:
        lba, size = fs.find(args.path)
        dst = os.path.join(out, args.path.strip("/").replace("/", os.sep))
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        with open(dst, "wb") as f:
            f.write(fs.read(lba, size))
        print(f"{args.path} → {dst} ({size:,} bytes)")
        return 0

    n = total = 0
    for full, lba, size, is_dir in fs.walk():
        if is_dir:
            continue
        if args.filter and args.filter.lower() not in full.lower():
            continue
        n += 1
        total += size
        if args.all:
            dst = os.path.join(out, full.strip("/").replace("/", os.sep))
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            with open(dst, "wb") as f:
                f.write(fs.read(lba, size))
        else:
            print(f"  {size:>11,}  {full}")
    print(f"\n{n}개 파일, {total:,} bytes" + (f" → {out}" if args.all else ""))
    return 0
