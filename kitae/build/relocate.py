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


def _ref_target_offsets(blob, secs):
    """재배치 슬롯이 **가리키는** 대상 파일 오프셋들 (정렬).

    문자열 뒤 0 패딩 안에 이런 대상이 있으면(정렬 패딩과 구별되지 않는 0 정수
    테이블 필드 등) 그 자리는 비어 보여도 **실제로 참조되는 데이터**다. 거기까지
    avail 로 잡아 덮어쓰면 테이블이 깨진다 — TRFGUIDEMAP 큐빅 설명 인덱스가
    0 에서 쓰레기값으로 바뀌어 선택 즉시 리셋된 사고의 원인이었다.
    """
    slots = reloc_slots(blob, secs)
    if not slots:
        return []
    vm = _va_map(secs)
    out = set()
    for s in slots:
        va = struct.unpack_from("<I", blob, s)[0]
        for lo, hi, delta in vm:
            if lo + delta <= va < hi + delta:
                out.add(va - delta)
                break
    return sorted(out)


def _clamp_avails(entries, ref_offs):
    """각 항목의 avail 을 **문자열 뒤 첫 참조 대상 직전**까지로 줄인다.

    자유 목록은 [offset, offset+avail] 까지를 쓸 수 있는 것으로 보므로
    (apply 의 꼬리/옛자리, compact 의 풀), 참조 대상 바이트가 그 범위에
    들어오면 못 쓰게 avail = 대상오프셋 − offset − 1 로 막는다.
    """
    import bisect
    out = {}
    for e in entries:
        off, av, sz = e["offset"], e["avail"], e.get("size", 0)
        i = bisect.bisect_right(ref_offs, off)      # 문자열 시작 뒤 첫 참조
        nxt = ref_offs[i] if i < len(ref_offs) else None
        if nxt is not None and nxt > off + sz and off + av >= nxt:
            av = nxt - off - 1
        out[id(e)] = av
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

    # avail 은 참조되는 데이터 직전까지로 줄여 쓴다 (테이블 침범 방지).
    avs = _clamp_avails(entries, _ref_target_offsets(blob, secs))

    keep, move, fail = [], [], []
    for e in entries:
        raw = encode(e["text"])
        (keep if len(raw) <= avs[id(e)] else move).append((e, raw))

    # 참조는 **손대기 전 원본**에서 찾는다. 패치한 바이트가 우연히 VA 와 같아지면
    # 없던 참조가 생긴 것처럼 보인다.
    refs_of = {}
    for e, _raw in move:
        va = off_to_va(vm, e["offset"])
        refs_of[e["offset"]] = find_refs(blob, va, slots) if va else []

    # 자유 목록 — 제자리 문자열이 남긴 꼬리 + 이사 가는 문자열의 옛 자리
    free = list(extra_free)
    for e, raw in keep:
        left = avs[id(e)] - len(raw)
        if left > 0:
            free.append((e["offset"] + len(raw) + 1, left))
    for e, _raw in move:
        free.append((e["offset"], avs[id(e)] + 1))
    free = _merge(free)

    # 제자리 것부터 쓴다
    for e, raw in keep:
        out[e["offset"]:e["offset"] + avs[id(e)]] = \
            raw + b"\x00" * (avs[id(e)] - len(raw))

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


def compact(blob, entries, encode):
    """소유한 공간 전체를 비우고 처음부터 촘촘히 다시 배치한다.

    제자리 우선 방식은 문자열이 조금씩만 짧아지면 빈칸이 잘게 흩어져, 정작
    길어진 문자열이 들어갈 자리를 못 찾는다(210바이트가 남았는데도 9바이트를
    못 넣는 일이 생겼다). 여기서는 모든 문자열의 자리를 합쳐 하나의 풀로 보고
    원래 순서대로 다시 깔아, 남는 공간이 뒤쪽에 한 덩어리로 모이게 한다.

    포인터를 전부 다시 쓰므로 참조를 하나라도 못 찾은 문자열이 있으면 손대지
    않고 실패로 돌린다.
    """
    from kitae.core import pestr

    secs = pestr.sections(blob)
    vm = _va_map(secs)
    slots = reloc_slots(blob, secs)
    out = bytearray(blob)

    # avail 은 참조되는 데이터 직전까지로 줄여 쓴다 (테이블 침범 방지).
    avs = _clamp_avails(entries, _ref_target_offsets(blob, secs))

    items, fail = [], []
    for e in entries:
        va = off_to_va(vm, e["offset"])
        refs = find_refs(blob, va, slots) if va else []
        if not refs:
            fail.append((e, "참조를 못 찾음"))
            continue
        items.append((e, encode(e["text"]), refs))
    if fail:
        return blob, {"kept": 0, "moved": [], "failed": fail, "free_left": 0}

    pool = _merge([(e["offset"], avs[id(e)] + 1) for e, _r, _f in items])
    for off, n in pool:                       # 옛 내용을 지운다
        out[off:off + n] = b"\x00" * n

    si, cur, left = 0, pool[0][0], pool[0][1]
    moved, kept = [], 0
    for e, raw, refs in sorted(items, key=lambda x: x[0]["offset"]):
        need = len(raw) + 1
        while need > left:
            si += 1
            if si >= len(pool):
                return blob, {"kept": 0, "moved": [],
                              "failed": [(e, "풀이 모자람")], "free_left": 0}
            cur, left = pool[si]
        out[cur:cur + need] = raw + b"\x00"
        new_va = off_to_va(vm, cur)
        if cur != e["offset"]:
            for r in refs:
                struct.pack_into("<I", out, r, new_va)
            moved.append((e["offset"], cur, len(refs), e["text"]))
        else:
            kept += 1
        cur += need
        left -= need
    free_left = left + sum(n for _o, n in pool[si + 1:])
    return bytes(out), {"kept": kept, "moved": moved, "failed": [],
                        "free_left": free_left}
