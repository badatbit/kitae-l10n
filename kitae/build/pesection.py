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

## ★ `.reloc` 뒤에 놓으면 안 된다

이 게임의 `.reloc` 은 **DISCARDABLE** 이다. WinCE 로더는 재배치를 적용한 뒤
그 페이지를 해제하고, 풀린 메모리는 곧 다른 할당에 재사용된다. 새 섹션을
`.reloc` **뒤**(가장 높은 VA)에 놓으면 같이 풀려 나가고, 모듈은 남의 메모리가
된 자리에서 문자열을 읽게 된다.

처음에 그렇게 만들었더니 **가이드북을 열 때 오디오가 깨졌다.** 화면에 글자는
멀쩡히 나왔는데(아직 재사용 전이라) 그 뒤 잡힌 버퍼가 같은 페이지를 물었다.
찾기 어려운 종류의 고장이라 여기 적어 둔다.

그래서 새 섹션은 **`.reloc` 앞의 VA** 를 받는다. `.reloc` 은 VA 만 뒤로 밀고
파일 안의 raw 는 그대로 둔다 — PE 는 섹션 헤더가 VA 순이기만 하면 되고
raw 순서는 상관하지 않는다. 옮긴 뒤 **데이터 디렉터리 5번(base relocation)의
RVA 도 같이 고쳐야** 로더가 `.reloc` 을 찾는다.
"""
import struct

DIR_BASERELOC = 5           # 데이터 디렉터리에서 .reloc 을 가리키는 자리


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


def _headers(blob):
    """[(이름, vsize, va, rsize, raw, characteristics)] — 파일에 적힌 순서대로."""
    pe, opt, nsec, _sa, _fa, _soh = info(blob)
    base = pe + 24 + opt
    out = []
    for i in range(nsec):
        o = base + i * 40
        nm = blob[o:o + 8]
        vsz, va, rsz, raw = struct.unpack_from("<IIII", blob, o + 8)
        ch = struct.unpack_from("<I", blob, o + 36)[0]
        out.append([nm, vsz, va, rsz, raw, ch])
    return out


def add(blob, name, nbytes, characteristics=0x40000040):
    """섹션을 붙이고 (새 blob, 파일오프셋, 크기) 를 돌려준다.

    characteristics 기본값은 초기화된 데이터 + 읽기 전용이다.

    새 섹션의 VA 는 **DISCARDABLE 섹션 앞**에 잡는다 (머리말 참고).
    그런 섹션이 없으면 예전처럼 맨 뒤에 붙인다.
    """
    if not room_for_header(blob):
        raise ValueError("섹션 헤더를 넣을 자리가 없다")
    pe, opt, nsec, sa, fa, _soh = info(blob)
    base = pe + 24 + opt
    secs = _headers(blob)

    # 풀려 나갈 섹션(.reloc 등)은 뒤로 민다. VA 로 봤을 때 첫 discardable.
    disc = sorted((s for s in secs if s[5] & 0x02000000), key=lambda s: s[2])
    if disc:
        new_va = disc[0][2]
        shift = _up(nbytes, sa)
        for s in disc:
            s[2] += shift                       # VA 만 민다. raw 는 그대로다
    else:
        new_va = _up(max(s[2] + s[1] for s in secs), sa)

    new_raw = _up(len(blob), fa)
    raw_size = _up(nbytes, fa)
    out = bytearray(blob)
    out += b"\x00" * (new_raw - len(out))       # 파일 정렬까지 채우고
    out += b"\x00" * raw_size                   # 새 섹션 본문

    secs.append([name.encode("ascii")[:8].ljust(8, b"\x00"), nbytes, new_va,
                 raw_size, new_raw, characteristics])
    secs.sort(key=lambda s: s[2])               # 섹션 헤더는 VA 오름차순이어야 한다
    for i, s in enumerate(secs):
        o = base + i * 40
        struct.pack_into("<8sIIII", out, o, s[0], s[1], s[2], s[3], s[4])
        struct.pack_into("<IIHHI", out, o + 24, 0, 0, 0, 0, s[5])
    struct.pack_into("<H", out, pe + 6, len(secs))
    struct.pack_into("<I", out, pe + 24 + 56,
                     _up(max(s[2] + s[1] for s in secs), sa))

    # .reloc 을 옮겼으면 로더가 보는 데이터 디렉터리도 같이 고쳐야 한다
    if disc:
        ndir = struct.unpack_from("<I", blob, pe + 24 + 92)[0]
        if ndir > DIR_BASERELOC:
            d = pe + 24 + 96 + DIR_BASERELOC * 8
            rva, sz = struct.unpack_from("<II", blob, d)
            if rva:
                for s in disc:
                    old = s[2] - shift
                    if old <= rva < old + s[1]:
                        struct.pack_into("<I", out, d, rva + shift)
                        break
    return bytes(out), new_raw, raw_size
