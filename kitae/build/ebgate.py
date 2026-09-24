# -*- coding: utf-8 -*-
"""**C.B.S(커뮤니케이션 브레이크 시스템) 우회** — 디버그·편의 패치. 한국어 패치와 별개다.

선택지를 여는 `0x73`/`0x74` 앞에 `0x6E`/`0x6F <u16 제한시간> <u16 값>` 게이트가 붙은 곳이
508곳 있다(게이트 없는 곳 524곳). 게이트가 있으면 제한 시간(60fps 기준 90·120·180·240·260
프레임) 안에 고르지 않을 때 기본값으로 넘어간다 — 원작의 C.B.S 다. 처음엔 이걸 에뮬레이터
버그로 오해했었다(2026-08). 상자가 안 보였던 것은 사용자 실수였다.

이 패치는 게이트 다섯 바이트를 `0x00`(문장 구분자)으로 덮어 제한 시간을 없앤다.
길이가 그대로라 점프 목적지도 `tail_off` 도 움직이지 않고, 게이트 없는 형태는 원본에도
9곳 있어 엔진이 처리한다. **원작과 다른 동작**이므로 배포 빌드에선 끈다.

    "cbs_bypass": false     ← kitae.config.json (기본 false). true 면 EB 508곳을 덮는다.
"""
from kitae.core import ebdis

GATE = (0x6E, 0x6F)
OPEN = (0x73, 0x74)
SHOW = (0x6B, 0x6C)
NOP = 0x00


def ungate(eb):
    """(새 바이트, 지운 곳 수). 지울 게 없으면 (원본 그대로, 0)."""
    ops = list(ebdis.decode(eb))
    cut = []
    for i, o in enumerate(ops):
        if o[1] not in OPEN:
            continue
        # 바로 앞 창 표시까지만 거슬러 본다 — 그 사이의 게이트가 이 선택지 것이다
        for j in range(i - 1, -1, -1):
            if ops[j][1] in SHOW:
                break
            if ops[j][1] in GATE:
                cut.append((ops[j][0], 1 + len(ops[j][2])))
    if not cut:
        return eb, 0
    out = bytearray(eb)
    for off, n in cut:
        out[off:off + n] = bytes([NOP]) * n
    return bytes(out), len(cut)


def patch_all(plot_cab, scripts=None):
    """{`<대본>.EB`: 새 바이트}. 손댈 게 없는 대본은 넣지 않는다."""
    out, total = {}, 0
    for name in plot_cab.names:
        if not name.endswith(".EB"):
            continue
        if scripts and name[:-3] not in scripts:
            continue
        blob, n = ungate(plot_cab.read(name))
        if n:
            out[name] = blob
            total += n
    return out, total
