# -*- coding: utf-8 -*-
"""PE 모듈 끝에 데이터 섹션을 하나 붙인다.

번역문이 원문보다 길어져 재배치로도 자리가 모자랄 때 쓴다. 지명이 많은
모듈(TRFGUIDEMAP)은 한자를 한글로 옮기면서 총량이 소유 공간을 넘어섰다.

붙이는 방식은 표준 PE 그대로다 —
  * 섹션 테이블에 40바이트 항목을 하나 더하고 (헤더에 자리가 있어야 한다)
  * NumberOfSections 와 SizeOfImage 를 올리고
  * 파일 끝에 FileAlignment 로 맞춘 raw 를 덧붙인다

**파일이 커진다.** 디스크에 넣을 때 `replace_same_size` 로는 안 되고 `patch`
로 자리를 다시 잡아야 하며, ISO 에 여유 섹터가 있어야 한다.

로더가 이걸 받아 줄지는 이 게임에서 확인된 바 없다. 실패하면 모듈이 안 올라와
게임이 죽으므로, 다른 수단이 없을 때만 쓴다.
"""
import struct


def _up(v, a):
    return (v + a - 1) // a * a


def info(blob):
    """(pe_off, opt_size, nsec, section_align, file_align, size_of_headers)"""
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    if blob[pe:pe + 4] != b"PE\0\0":
        raise ValueError("PE 헤더가 아니다")
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    sa = struct.unpack_from("<I", blob, pe + 24 + 32)[0]
    fa = struct.unpack_from("<I", blob, pe + 24 + 36)[0]
    soh = struct.unpack_from("<I", blob, pe + 24 + 60)[0]
    return pe, opt, nsec, sa, fa, soh


def room_for_header(blob):
    """섹션 테이블에 항목을 하나 더 넣을 자리가 있는가."""
    pe, opt, nsec, _sa, _fa, soh = info(blob)
    table_end = pe + 24 + opt + nsec * 40
    first_raw = min(struct.unpack_from("<I", blob, pe + 24 + opt + i * 40 + 20)[0]
                    for i in range(nsec))
    return table_end + 40 <= min(soh, first_raw)


def add(blob, name, nbytes, characteristics=0x40000040):
    """섹션을 붙이고 (새 blob, 파일오프셋, 크기) 를 돌려준다.

    characteristics 기본값은 초기화된 데이터 + 읽기 전용이다.
    """
    if not room_for_header(blob):
        raise ValueError("섹션 헤더를 넣을 자리가 없다")
    pe, opt, nsec, sa, fa, _soh = info(blob)
    base = pe + 24 + opt

    end_va = 0
    for i in range(nsec):
        o = base + i * 40
        vsz, va = struct.unpack_from("<II", blob, o + 8)
        end_va = max(end_va, va + vsz)
    new_va = _up(end_va, sa)
    new_raw = _up(len(blob), fa)
    raw_size = _up(nbytes, fa)

    out = bytearray(blob)
    out += b"\x00" * (new_raw - len(out))       # 파일 정렬까지 채우고
    out += b"\x00" * raw_size                   # 새 섹션 본문

    o = base + nsec * 40
    struct.pack_into("<8sIIII", out, o,
                     name.encode("ascii")[:8], nbytes, new_va, raw_size, new_raw)
    struct.pack_into("<IIHHI", out, o + 24, 0, 0, 0, 0, characteristics)
    struct.pack_into("<H", out, pe + 6, nsec + 1)
    struct.pack_into("<I", out, pe + 24 + 56, _up(new_va + nbytes, sa))
    return bytes(out), new_raw, raw_size
