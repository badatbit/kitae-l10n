# -*- coding: utf-8 -*-
"""배포용 DCP 패치 만들기 — Universal Dreamcast Patcher(DerekPascarella) 형식.

DCP 는 **확장자만 바꾼 ZIP** 이다. 압축 파일 뿌리에 바뀐·새로 생긴 파일을 게임 디스크의
폴더 구조 그대로 넣는다(`RESOURCE/PLOT.CB`, `TRF/TRFNAMEIN.DLL` …). 부트섹터를 바꾸려면
뿌리에 `bootsector/IP.BIN` 을 둔다(그 폴더는 결과 디스크의 파일시스템에는 안 들어간다).
매니페스트 같은 건 필요 없다.

여기서는 **빌드 산출 디스크(dist/track03.bin)와 원본 디스크를 직접 비교**해 달라진 파일만
뽑는다. `work/build/` 를 쓰지 않는 이유: SOZ 처럼 디스크에 넣는 단계에서 한 번 더 손대는
것이 있어, 실제로 배포될 바이트는 디스크 쪽이 정답이기 때문이다.

    python tools/make_dcp.py [-o 출력.dcp]
"""
import argparse
import hashlib
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from kitae.config import Config          # noqa: E402
from kitae.core.gdfs import GdFs         # noqa: E402


def files(track):
    """디스크의 {경로(앞 / 없음): (lba, size)}."""
    fs = GdFs(track=track)
    return fs, {p.lstrip("/"): (lba, size)
                for p, lba, size, is_dir in fs.walk() if not is_dir}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", help="출력 .dcp 경로")
    ap.add_argument("--orig", help="원본 track03.bin (기본: 설정의 orig_dir)")
    ap.add_argument("--built", help="빌드 track03.bin (기본: dist/track03.bin)")
    a = ap.parse_args()

    cfg = Config.load()
    import glob
    orig = a.orig or glob.glob(os.path.join(cfg.dir("orig_dir"), "*track03.bin"))[0]
    built = a.built or os.path.join(ROOT, cfg["out_dir"], "track03.bin")
    out = a.out or os.path.join(ROOT, cfg["out_dir"], "Kita He - White Illumination (KO).dcp")

    fo, mo = files(orig)
    fb, mb = files(built)
    changed, added = [], []
    for path, (lba, size) in sorted(mb.items()):
        data = fb.read(lba, size)
        if path not in mo:
            added.append((path, data)); continue
        olba, osize = mo[path]
        if size != osize or data != fo.read(olba, osize):
            changed.append((path, data))
    gone = sorted(set(mo) - set(mb))

    print(f"원본 {len(mo)}개 · 빌드 {len(mb)}개 파일")
    print(f"바뀐 파일 {len(changed)}개 · 새 파일 {len(added)}개"
          + (f" · 사라진 파일 {len(gone)}개 ★" if gone else ""))
    for p in gone:
        print(f"   ★ 빌드에 없음: {p} — DCP 는 파일 삭제를 표현 못 한다")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    total = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path, data in changed + added:
            z.writestr(path, data)          # 뿌리에 원래 폴더 구조 그대로
            total += len(data)
    size = os.path.getsize(out)
    print(f"\n{out}")
    print(f"  담은 파일 {len(changed) + len(added)}개 · 원자료 {total:,}B → 패치 {size:,}B "
          f"({size * 100 // max(total, 1)}%)")
    print("  sha256", hashlib.sha256(open(out, "rb").read()).hexdigest()[:32])
    for path, data in changed + added:
        print(f"    {path:34} {len(data):>10,}B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
