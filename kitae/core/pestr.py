# -*- coding: utf-8 -*-
"""PE(SH-4) 모듈 안에 박혀 있는 화면 표시 문자열을 찾고 제자리에서 바꾼다.

메뉴·안내문 같은 시스템 텍스트는 `.SMF` 처럼 따로 리소스로 빠져 있지 않고
DLL 의 `.data` 에 NUL 로 끝나는 cp932 문자열로 박혀 있다. 그래서 대사와 달리
**길이를 늘릴 수 없다** — 문자열 테이블을 재작성하는 게 아니라 있던 자리를
덮어써야 하므로, 번역문의 바이트 길이가 원문 이하여야 한다.

`.text` 에도 NUL 로 끊어 읽으면 cp932 로 해석되는 바이트열이 잔뜩 나오지만
전부 명령어다. 그래서 데이터 구간만 보고, 글자 구성으로 한 번 더 거른다.
"""
import struct

# 화면에 나올 수 있는 글자만 통과시킨다. 반각 가타카나(U+FF61~FF9F)는 이 게임
# UI 가 쓰지 않으며, 코드 바이트가 우연히 그렇게 읽히는 경우가 많아 제외한다.
def _ok(ch):
    o = ord(ch)
    return (ch in "\n\t"
            or 0x20 <= o <= 0x7E                  # 반각 영숫자·기호
            or 0x3000 <= o <= 0x30FF              # 구두점·히라가나·가타카나
            or 0x4E00 <= o <= 0x9FFF              # 한자
            or 0x3400 <= o <= 0x4DBF
            or 0xFF01 <= o <= 0xFF5E              # 전각 영숫자·기호
            or 0xFFE0 <= o <= 0xFFE5
            or o in (0x2015, 0x2026, 0x203B, 0x2192, 0x2190))


def sections(blob):
    """[(name, va, raw_off, raw_size)]"""
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    if blob[pe:pe + 4] != b"PE\0\0":
        return []
    nsec = struct.unpack_from("<H", blob, pe + 6)[0]
    opt = struct.unpack_from("<H", blob, pe + 20)[0]
    out = []
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        name = blob[o:o + 8].rstrip(b"\x00").decode("ascii", "replace")
        _vsz, va, rsz, raw = struct.unpack_from("<IIII", blob, o + 8)
        out.append((name, va, raw, rsz))
    return out


MAX_PAD = 7             # 정렬 패딩으로 인정할 최대 바이트 (8바이트 정렬)


def strings(blob, where=(".data", ".rdata"), min_wide=2):
    """표시 문자열 목록. [{offset, size, avail, section, text}]

    min_wide 는 '전각 글자가 최소 몇 개는 있어야 한다'는 조건이다. 이게 없으면
    `ﾞ9ｪA` 같은 이진 쓰레기가 걸려 든다.

    `avail` 은 실제로 쓸 수 있는 바이트 수다. 문자열들이 4~8바이트로 정렬돼 있어
    NUL 뒤에 0 패딩이 남는데, 거기까지 쓸 수 있다. 다만 0 이 길게 이어지는 건
    패딩이 아니라 0 으로 초기화된 버퍼일 수 있으므로 MAX_PAD 까지만 인정한다.
    """
    secs = [s for s in sections(blob) if s[0] in where]
    out = []
    for name, _va, raw, rsz in secs:
        end = min(raw + rsz, len(blob))
        i = raw
        while i < end:
            j = blob.find(b"\x00", i, end)
            if j < 0:
                break
            s = blob[i:j]
            if 2 <= len(s) <= 1024:
                try:
                    t = s.decode("cp932")
                except UnicodeDecodeError:
                    t = None
                if t and all(_ok(c) for c in t) and \
                        sum(1 for c in t if ord(c) > 0x7F) >= min_wide:
                    pad = 0
                    k = j + 1                    # NUL 다음부터
                    while pad < MAX_PAD and k + pad < end and blob[k + pad] == 0:
                        pad += 1
                    out.append({"offset": i, "size": len(s), "avail": len(s) + pad,
                                "section": name, "text": t})
            i = j + 1
    return out


def encode_fits(text, limit, encode=None):
    """번역문을 게임 바이트로. 자리를 넘으면 (None, 필요한 크기)."""
    enc = encode or (lambda s: s.encode("cp932"))
    b = enc(text)
    return (b, len(b)) if len(b) <= limit else (None, len(b))


def patch(blob, offset, size, raw):
    """제자리 덮어쓰기. 남는 자리는 0 으로 채워 NUL 종단을 보장한다."""
    if len(raw) > size:
        raise ValueError(f"{len(raw)} > {size} bytes at {offset:#x}")
    out = bytearray(blob)
    out[offset:offset + size] = raw + b"\x00" * (size - len(raw))
    return bytes(out)
