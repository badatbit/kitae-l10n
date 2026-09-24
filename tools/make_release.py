# -*- coding: utf-8 -*-
"""배포 파일 두 벌을 만든다 — xdelta(우리 GDI 기준)와 DCP.

    python tools/make_release.py [-v v0.9]

**1) `.xdelta`** — 원본 `track03.bin` → 패치본 `track03.bin` 차분.
   track01(오디오)·track02·`.gdi` 는 안 바뀌므로 데이터 트랙 하나만 낸다.
   받는 쪽 원본이 **바이트까지 같아야** 적용된다. 그래서 원본 sha256 을 같이 적어 둔다.

**2) `.dcp`** — [Universal Dreamcast Patcher](https://github.com/DerekPascarella/UniversalDreamcastPatcher)
   형식. 확장자만 바꾼 ZIP 으로, 뿌리에 바뀐 파일을 디스크 폴더 구조 그대로 담는다
   (`RESOURCE/…`, `TRF/…`). 매니페스트는 없다. 부트섹터를 바꾸려면 뿌리에
   `bootsector/IP.BIN` 을 두는데 이 패치는 IP.BIN 을 안 건드리므로 넣지 않는다.
   파일을 통째로 담아 xdelta 보다 크지만, 원본이 조금 달라도 덮어쓰므로 너그럽다.

담을 파일은 `work/build/` 가 아니라 **빌드된 디스크와 원본 디스크를 직접 비교**해 고른다 —
SOZ 처럼 디스크에 넣는 단계에서 한 번 더 손대는 것이 있어, 배포될 바이트는 디스크 쪽이 정답이다.
"""
import argparse
import glob
import hashlib
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from kitae.config import Config          # noqa: E402
from kitae.core.gdfs import GdFs         # noqa: E402

TITLE = "Kita He - White Illumination (KO)"


def sha256(path):
    m = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            m.update(chunk)
    return m.hexdigest()


def disc_files(track):
    fs = GdFs(track=track)
    return fs, {p.lstrip("/"): (lba, size)
                for p, lba, size, is_dir in fs.walk() if not is_dir}


def changed(orig_track, built_track):
    """[(경로, 빌드 바이트)] — 달라졌거나 새로 생긴 파일."""
    fo, mo = disc_files(orig_track)
    fb, mb = disc_files(built_track)
    out, gone = [], sorted(set(mo) - set(mb))
    for path, (lba, size) in sorted(mb.items()):
        data = fb.read(lba, size)
        if path not in mo:
            out.append((path, data)); continue
        olba, osize = mo[path]
        if size != osize or data != fo.read(olba, osize):
            out.append((path, data))
    return out, gone


def make_dcp(rows, out):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path, data in rows:
            z.writestr(path, data)          # 뿌리에 원래 폴더 구조 그대로
    return os.path.getsize(out)


def make_xdelta(src, dst, out):
    """pyxdelta 로 차분을 뜨고, **되적용해 결과가 같은지 반드시 확인한다**."""
    import pyxdelta
    if not pyxdelta.run(src, dst, out):
        raise RuntimeError("xdelta 생성 실패")
    check = out + ".check"
    try:
        if not pyxdelta.decode(src, out, check):
            raise RuntimeError("xdelta 되적용 실패")
        if sha256(check) != sha256(dst):
            raise RuntimeError("되적용 결과가 빌드본과 다르다")
    finally:
        if os.path.exists(check):
            os.remove(check)
    return os.path.getsize(out)


HOWTO = """북으로. White Illumination 한국어 패치 {ver}

원본 디스크 이미지(GDI)가 있어야 합니다. 아래 둘 중 편한 쪽을 쓰세요.

[1] {dcp}
    Universal Dreamcast Patcher 로 적용합니다.
    https://github.com/DerekPascarella/UniversalDreamcastPatcher
    원본 GDI(또는 CDI)와 이 .dcp 를 넣으면 패치된 이미지가 나옵니다.
    원본이 우리 것과 조금 달라도 적용됩니다.

[2] {xd}
    원본의 데이터 트랙 하나에만 적용하는 xdelta 차분입니다.
    xdelta3 -d -s track03.bin "{xd}" track03_patched.bin
    만들어진 track03_patched.bin 을 track03.bin 으로 바꿔 넣으면 됩니다.
    .gdi 와 track01.bin, track02.raw 는 그대로 두세요 (바뀌지 않습니다).
    ★ 원본 track03.bin 이 아래와 정확히 같아야 적용됩니다.
      크기   {src_size:,} 바이트
      sha256 {src_sha}

패치된 track03.bin
  크기   {dst_size:,} 바이트
  sha256 {dst_sha}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--version", default="", help="파일 이름에 붙일 판 번호 (예: v0.9)")
    a = ap.parse_args()

    cfg = Config.load()
    orig = glob.glob(os.path.join(cfg.dir("orig_dir"), "*track03.bin"))[0]
    built = os.path.join(ROOT, cfg["out_dir"], "track03.bin")
    out_dir = os.path.join(ROOT, cfg["out_dir"])
    tag = f"{TITLE} {a.version}".strip()

    rows, gone = changed(orig, built)
    print(f"바뀐 파일 {len(rows)}개" + (f" · 사라진 파일 {len(gone)}개 ★" if gone else ""))
    for p in gone:
        print(f"   ★ 빌드에 없음: {p} — DCP 는 파일 삭제를 표현 못 한다")

    dcp = os.path.join(out_dir, tag + ".dcp")
    n_dcp = make_dcp(rows, dcp)
    raw = sum(len(d) for _, d in rows)
    print(f"\n  {os.path.basename(dcp)}\n    {n_dcp:,}B ({n_dcp/1048576:.1f} MB) "
          f"· 원자료 {raw:,}B 의 {n_dcp*100//max(raw,1)}%")

    xd = os.path.join(out_dir, tag + ".xdelta")
    n_xd = make_xdelta(orig, built, xd)
    print(f"  {os.path.basename(xd)}\n    {n_xd:,}B ({n_xd/1048576:.1f} MB) · 되적용 확인됨")

    howto = os.path.join(out_dir, "읽어주세요.txt")
    with open(howto, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(HOWTO.format(ver=a.version or "", dcp=os.path.basename(dcp),
                              xd=os.path.basename(xd),
                              src_size=os.path.getsize(orig), src_sha=sha256(orig),
                              dst_size=os.path.getsize(built), dst_sha=sha256(built)))
    print(f"  {os.path.basename(howto)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
