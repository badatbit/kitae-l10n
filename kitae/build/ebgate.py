# -*- coding: utf-8 -*-
"""**에뮬레이터 버그 우회** — 선택지 앞의 `0x6E`/`0x6F` 게이트를 지운다.

번역이 아니다. 게임 바이트코드를 고치는 우회 패치이므로
[docs/EMULATOR-BUGS.md](../../docs/EMULATOR-BUGS.md) 의 규칙을 따른다 —
**원본 디스크와 다른 에뮬레이터에서 먼저 재현을 확인하고**, 설정으로 끌 수 있고,
끄면 원본과 같은 바이트가 나가야 한다.

## ★ 왜 지우나 — 에뮬레이터에서 선택 상자가 안 그려진다

선택지를 여는 `0x73`/`0x74` 앞에는 두 갈래가 있다.

    (가)                    0x2E · 0x46 · 0x73     524곳 — 잘 뜬다
    (나)  0x6E|0x6F · 0x24 · 0x42 · 0x2E · 0x46 · 0x73   508곳 — 상자가 안 그려진다

`(나)` 에서는 상자가 화면에 나오지 않는데 **시간은 흐른다.** ２~３초 멈췄다가
기본값이 고른 것처럼 진행된다. 안 되는 것은 그리기뿐이다. redream·Flycast 둘 다,
**패치하지 않은 원본 디스크에서도** 같다(2026-08-08 확인). 우리 번역과는
무관하고 에뮬레이션 쪽 구멍이다.

## ★ 게이트가 정확히 무엇인지는 모른다

옵코드는 `<u16 A> <u16 B>` 를 받는다. `A` 는 ９０·１２０·１８０·２４０·２６０ 다섯 값뿐이라
타임아웃으로 보인다(１２０ 이 ６５%, ６０fps 로 ２초 = 관찰된 멈춤 시간). 하지만
**`B` 가 무엇인지 모른다** — 창 번호도, 화자도, 앞 창 글자 수도 아니다.

그래서 "제한 시간이 있는 선택지가 안 그려진 것" 이라고 **단정할 수 없다.**
남은 가설과 갈라 볼 방법은 docs/EMULATOR-BUGS.md 의 미해결 항목에 적었다.

다만 게이트를 통째로 지우면 `(가)` 와 같은 형태가 되므로 **원인이 어느 쪽이든
우회는 유효하다.**

## 지워도 되는 근거

  * `0x00` 은 전 대본에 ２１,００３곳 나오는 **문장 구분자**다. `0x6B` 뒤에만
    ６,９７６곳이다. 다섯 바이트를 `00` 으로 덮으면 빈 문장 다섯 개가 된다.
  * 게이트만 빠진 형태(`0x24 0x42 0x00 0x2E 0x46 0x73`)가 **원본에 이미 ９곳**
    있다(KAORU 창９, KOZUE 창２７９ 등). 엔진이 처리하는 형태다.
  * 길이가 그대로라 점프 목적지도 `tail_off` 도 움직이지 않는다.

## 잃는 것

시간 제한이 사라지므로 **제한 시간 안에 못 고르면 벌어지던 연출**이 없어진다.
원래 그 자리에서 뜸을 들이면 기본값으로 넘어갔을 텐데, 이제는 고를 때까지
기다린다. 진행이 막히는 것보다 낫다고 보고 켜 두지만, 원작과 다른 동작이다.

    "emulator_fixes": { "choice_gate": false }

로 끄면 EB 는 원본 바이트 그대로 나간다.
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
