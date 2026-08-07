# -*- coding: utf-8 -*-
"""번역 길이에 맞춰 MTG 타이밍(CTRFMsgTiming)을 다시 만든다.

형식 (TRFMSGTIMING.DLL / TRFSTRINGS.DLL 역어셈블로 확인)

    payload = u16 count + count개의 u16 entry        count == 표시 글자 수 + 1
    entry   = (lip << 12) | duration_ms              duration 0..4095, lip 0..8

`duration` 은 **밀리초**다. 스케일도 프레임도 아니다 — CTRFMsgput 의 갱신
루프(TRFSTRINGS.DLL 0x10002F20)가 `GetTickCount()` 에 이 값을 누적해 마감
시각을 만든다. `entry[i]` 는 *글자 i 를 찍기 전에* 기다리는 시간이므로 글자
i 는 시작 후 `sum(d[0..i])` ms 에 나타난다. 첫 항목은 보통 0 이고, 마지막
항목은 글자가 없는 종결자로 마지막 글자 뒤의 여운이다.

`lip` 은 입 모양 0..8 로 ITRFLipControll 에 넘어간다. 0 은 다문 입 = 무음
구간이라, 성우가 쉬는 자리에는 긴 duration 과 lip 0 이 함께 온다.

음성은 이 배열에 묶여 있지 않다. 재생을 한 번 걸어 놓고 이후로는 재생 위치를
묻지 않으므로, 싱크는 순전히 이 숫자들이 녹음에 맞게 찍혀 있어서 유지된다.
따라서 배열 길이가 글자 수와 어긋나면 죽지는 않아도 싱크가 완전히 망가진다.

재생성 원칙
    창의 **줄 경계**는 원문과 번역이 같으므로(번역도 줄 단위로 관리한다)
    줄마다 원본이 쓰던 시간을 그대로 물려받는다. 줄 안에서는 250ms 이상의
    쉼을 길이째로 보존해 위치만 비례 이동시키고, 나머지 발화 시간만 새 글자
    수에 고르게 나눈다. 그래서 줄 시작·끝 시각과 쉼의 위치가 원본과 같다.
"""
import os
import struct
import sys

MAX_MS = 0x0FFF         # duration 은 12비트
PAUSE_MS = 250          # 이 이상은 '쉼'으로 보고 길이를 보존한다


def parse(payload):
    """payload -> (durations, lips). 타이밍이 없는 창이면 None."""
    if len(payload) < 4:
        return None
    count = struct.unpack_from("<H", payload, 0)[0]
    n = min(count, (len(payload) - 2) // 2)
    if n < 2:
        return None
    ent = struct.unpack_from(f"<{n}H", payload, 2)
    return [e & MAX_MS for e in ent], [e >> 12 for e in ent]


def pack(dur, lip):
    """(durations, lips) -> payload."""
    n = len(dur)
    ent = [(min(l, 8) << 12) | max(0, min(MAX_MS, int(d)))
           for d, l in zip(dur, lip)]
    return struct.pack(f"<H{n}H", n, *ent)


def timing_chars(payload):
    """이 타이밍이 감당하는 글자 수. 종결자는 뺀다."""
    p = parse(payload)
    return None if p is None else len(p[0]) - 1


def _retime_line(dur, lip, m):
    """한 줄의 구간들을 글자 m개짜리로 다시 나눈다. 총합은 그대로 둔다."""
    r = len(dur)
    if m == r:
        return list(dur), list(lip), 0
    total = sum(dur)
    # 쉼 구간은 '침묵 + 그 글자를 발음하는 시간'이 합쳐진 값이다. 통째로 옮기면
    # 새 칸이 받는 발화 몫이 덧붙어 쉼이 길어지므로, 보통 음절 시간을 뺀
    # 침묵분(extra)만 보존한다.
    spoken = [d for d in dur if d < PAUSE_MS]
    avg = (sum(spoken) / len(spoken)) if spoken else total / r
    extra = [(i, dur[i] - avg) for i in range(r) if dur[i] >= PAUSE_MS]
    extra = [(i, e) for i, e in extra if e > 0]

    # 침묵을 뺀 나머지를 새 글자 수에 고르게 나누고, 침묵은 비례 위치에 얹는다
    want = [(total - sum(e for _, e in extra)) / m] * m
    for i, e in extra:
        want[min(m - 1, i * m // r)] += e

    # 반올림 오차를 다음 칸으로 넘겨 총합이 흐트러지지 않게 한다
    out, acc = [], 0.0
    for v in want:
        acc += v
        d = int(round(acc))
        acc -= d
        out.append(d)

    new_lip = [lip[min(r - 1, j * r // m)] for j in range(m)]
    for j, d in enumerate(out):
        if d >= PAUSE_MS:
            new_lip[j] = 0          # 쉬는 동안은 입을 다문다

    over = sum(max(0, d - MAX_MS) for d in out)
    return [min(d, MAX_MS) for d in out], new_lip, over


def retime(payload, orig_lines, new_lines):
    """줄 구성이 (orig_lines -> new_lines) 로 바뀐 창의 타이밍을 새로 만든다.

    두 인자 모두 줄별 표시 글자 수 목록이다. 반환은 (payload, 넘친 ms).
    """
    got = parse(payload)
    if got is None:
        return payload, 0
    dur, lip = got
    if sum(orig_lines) != len(dur) - 1 or len(orig_lines) != len(new_lines):
        return payload, 0               # 전제가 깨졌으면 손대지 않는다
    if list(orig_lines) == list(new_lines):
        return payload, 0

    nd, nl, over, a = [], [], 0, 0
    for r, m in zip(orig_lines, new_lines):
        if r == 0 or m == 0:
            nd += dur[a:a + r]
            nl += lip[a:a + r]
        else:
            d, l, o = _retime_line(dur[a:a + r], lip[a:a + r], m)
            nd += d
            nl += l
            over += o
        a += r
    nd.append(dur[-1])                  # 종결자(마지막 글자 뒤 여운)
    nl.append(lip[-1])
    return pack(nd, nl), over


def _records(buf):
    """(payload_off, payload_len, cls, len_off) 전부. 중첩 포함."""
    MARK = b"\xff\xff\xff\xff"
    out, pos, n = [], 0, len(buf)
    while True:
        i = buf.find(MARK, pos)
        if i < 0 or i + 14 > n:
            break
        cl = struct.unpack_from("<H", buf, i + 8)[0]
        p0 = i + 10 + cl
        if cl == 0 or cl > 64 or p0 + 4 > n:
            pos = i + 1
            continue
        name = buf[i + 10:p0]
        if not all(32 <= b < 127 for b in name):
            pos = i + 1
            continue
        plen = struct.unpack_from("<I", buf, p0)[0]
        if p0 + 4 + plen > n:
            pos = i + 1
            continue
        out.append((p0 + 4, plen, name.decode("ascii"), p0))
        pos = i + 1
    return out


def rebuild_set(script, original, specs):
    """창별 타이밍을 새로 쓴다. specs[w] = (원문 줄별 글자수, 번역 줄별 글자수).

    길이가 바뀌면 그 페이로드를 품은 조상 컨테이너의 길이도 함께 고쳐야
    CLSS 트리가 깨지지 않는다.
    """
    out = bytearray(original)
    targets = sorted((r for r in _records(bytes(out)) if r[2] == "CTRFMsgTiming"),
                     key=lambda r: r[0])

    changed, warn = 0, {}
    # 뒤에서부터 바꿔야 앞쪽 오프셋이 유효하게 남는다
    for wi in sorted(range(len(targets)), reverse=True):
        if wi not in specs:
            continue
        off, ln, _cls, lenoff = targets[wi]
        old_payload = bytes(out[off:off + ln])
        orig_lines, new_lines = specs[wi]
        new_payload, over = retime(old_payload, orig_lines, new_lines)
        if over:
            warn[wi] = over
        if new_payload == old_payload:
            continue
        delta = len(new_payload) - ln
        struct.pack_into("<I", out, lenoff, len(new_payload))
        out[off:off + ln] = new_payload
        if delta:
            for a_off, a_len, _c, a_lenoff in _records(bytes(original)):
                if a_off <= off and off + ln <= a_off + a_len and a_off != off:
                    cur = struct.unpack_from("<I", out, a_lenoff)[0]
                    struct.pack_into("<I", out, a_lenoff, cur + delta)
        changed += 1
    return bytes(out), changed, warn
