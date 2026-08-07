# -*- coding: utf-8 -*-
"""자리가 모자란 문자열을 다른 빈 곳으로 옮기고 포인터를 고쳐 쓴다.

한자를 한글로 옮기면 대개 길어져서(`平岸駅` 6바이트 → `히라기시역` 10바이트)
제자리 덮어쓰기만으로는 안 되는 것들이 나온다.

새 섹션을 붙이거나 파일을 늘리기 전에, **이미 우리가 소유한 공간**부터 쓴다.
번역이 짧아진 문자열이 남긴 꼬리와 정렬 패딩을 모아 자유 목록을 만들고 거기에
넣는다. 파일 크기도 PE 헤더도 그대로라 위험이 거의 없다.

포인터는 모듈 전체에서 4바이트 정렬된 리틀엔디언 VA 를 찾아 바꾼다. `.reloc`
엔트리는 값에 델타를 더하는 방식이라 그대로 둬도 된다 — 우리는 선호 베이스
기준의 VA 를 쓰므로 재배치돼도 똑같이 따라온다.
"""
import struct

BASE = 0x10000000


def _va_map(secs):
    return [(raw, raw + rsz, BASE + va - raw) for _n, va, raw, rsz in secs]


def off_to_va(vm, off):
    for lo, hi, delta in vm:
        if lo <= off < hi:
            return off + delta
    return None


def reloc_slots(blob, secs):
    """`.reloc` 이 '여기 32비트 주소가 있다'고 표시한 파일 오프셋 집합.

    이게 없으면 바이트열이 우연히 일치하는 곳까지 포인터로 착각해 엉뚱한
    데이터를 덮어쓴다(`平岸駅` 을 찾을 때 실제로 3곳이 나왔다). 모듈이 다른
    베이스로 올라갈 수 있으므로 **진짜 포인터는 반드시 여기 등록돼 있다.**
    """
    sec = next((s for s in secs if s[0] == ".reloc"), None)
    if sec is None:
        return None
    _n, _va, raw, rsz = sec
    vm = _va_map(secs)
    va2off = {}
    for lo, hi, delta in vm:
        va2off[(lo + delta, hi + delta)] = lo - (lo + delta)

    def to_off(va):
        for (a, b), d in va2off.items():
            if a <= va < b:
                return va + d
        return None

    out, pos, end = set(), raw, min(raw + rsz, len(blob))
    while pos + 8 <= end:
        page, size = struct.unpack_from("<II", blob, pos)
        if size < 8 or pos + size > end:
            break
        for k in range(pos + 8, pos + size, 2):
            ent = struct.unpack_from("<H", blob, k)[0]
            if ent >> 12 == 3:                    # IMAGE_REL_BASED_HIGHLOW
                off = to_off(BASE + page + (ent & 0xFFF))
                if off is not None:
                    out.add(off)
        pos += size
    return out


def find_refs(blob, va, slots=None):
    """이 VA 를 가리키는 곳들. slots 가 있으면 재배치 테이블에 등록된 것만."""
    key = struct.pack("<I", va)
    out, i = [], 0
    while True:
        i = blob.find(key, i)
        if i < 0:
            break
        if i % 4 == 0 and (slots is None or i in slots):
            out.append(i)
        i += 1
    return out


def _merge(spans):
    """[(off, len)] 을 정렬·병합."""
    out = []
    for off, n in sorted(spans):
        if out and out[-1][0] + out[-1][1] == off:
            out[-1] = (out[-1][0], out[-1][1] + n)
        else:
            out.append((off, n))
    return out


def apply(blob, entries, encode, extra_free=()):
    """entries: [{offset, size, avail, text}] — text 는 번역문.

    반환은 (새 blob, 보고서). 보고서에는 제자리/이사/실패 목록이 담긴다.
    extra_free 는 추가로 써도 되는 [(offset, length)] (섹션 끝의 빈 공간 등).
    """
    from kitae.core import pestr

    secs = pestr.sections(blob)
    vm = _va_map(secs)
    slots = reloc_slots(blob, secs)
    out = bytearray(blob)

    keep, move, fail = [], [], []
    for e in entries:
        raw = encode(e["text"])
        (keep if len(raw) <= e["avail"] else move).append((e, raw))

    # 참조는 **손대기 전 원본**에서 찾는다. 패치한 바이트가 우연히 VA 와 같아지면
    # 없던 참조가 생긴 것처럼 보인다.
    refs_of = {}
    for e, _raw in move:
        va = off_to_va(vm, e["offset"])
        refs_of[e["offset"]] = find_refs(blob, va, slots) if va else []

    # 자유 목록 — 제자리 문자열이 남긴 꼬리 + 이사 가는 문자열의 옛 자리
    free = list(extra_free)
    for e, raw in keep:
        left = e["avail"] - len(raw)
        if left > 0:
            free.append((e["offset"] + len(raw) + 1, left))
    for e, _raw in move:
        free.append((e["offset"], e["avail"] + 1))
    free = _merge(free)

    # 제자리 것부터 쓴다
    for e, raw in keep:
        out[e["offset"]:e["offset"] + e["avail"]] = \
            raw + b"\x00" * (e["avail"] - len(raw))

    # 이사 — 큰 것부터, 가장 작은 빈칸에 (조각남을 줄인다)
    for e, raw in sorted(move, key=lambda x: -len(x[1])):
        need = len(raw) + 1                      # NUL 포함
        cand = [(n, off) for off, n in free if n >= need]
        if not cand:
            fail.append((e, len(raw)))
            continue
        _n, off = min(cand)
        free = [(o, n) for o, n in free if o != off]
        rest = _n - need
        if rest > 0:
            free.append((off + need, rest))
            free = _merge(free)

        new_va = off_to_va(vm, off)
        refs = refs_of[e["offset"]]
        if not refs:
            fail.append((e, "참조를 못 찾음"))
            free.append((off, _n))
            free = _merge(free)
            continue
        out[off:off + need] = raw + b"\x00"
        for r in refs:
            struct.pack_into("<I", out, r, new_va)
        e["_moved"] = (e, off, new_va, len(refs))

    moved = [e for e, _r in move if e.get("_moved")]
    return bytes(out), {
        "kept": len(keep),
        "moved": [(e["offset"], e["_moved"][1], e["_moved"][3], e["text"])
                  for e in moved],
        "failed": fail,
        "free_left": sum(n for _o, n in free),
    }
