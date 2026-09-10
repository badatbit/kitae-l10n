# -*- coding: utf-8 -*-
"""u16 글리프-코드 와이드 문자열 패치 (CTRF 서술자의 텍스트).

이 게임의 일부 UI 텍스트(환영 패널 등)는 cp932 바이트 문자열이 아니라,
**글자마다 폰트 셀 코드를 u16 로 담은 배열**로 CTRF 서술자에 박혀 있다.
예: `歓迎様` = [0x8abd, 0x8c7d, 0x976c] (LE). 셀 코드 = (lead<<8)|trail 이라
폰트 주소지정과 같다(kitae.core.font). cp932 바이트 추출기(uipatch)는 이 형식을
못 잡으므로 여기서 따로 처리한다.

data/wide_strings.json 에 {module, offset, ja, ko} 를 등록하면, ko 를 한글
인코더로 셀 코드화해 원본 길이(널 전까지) 이하로 제자리 교체한다. 한글 글리프는
번역문에 이미 쓰여 폰트에 주입돼 있어야 한다(안 그러면 빈칸).
"""
import io
import json
import os


def _entries(cfg):
    p = os.path.join(cfg.data_dir, "wide_strings.json")
    if not os.path.exists(p):
        return []
    return json.load(io.open(p, encoding="utf-8")).get("entries", [])


def apply(cfg, ui, encode):
    """ui[disc_path] 블롭들(및 원본)에 등록된 와이드 문자열을 패치. 개수 반환."""
    from kitae.build import uipatch
    n = 0
    for e in _entries(cfg):
        disc = f"/TRF/{e['module']}.DLL"
        blob = bytearray(ui.get(disc) or open(uipatch.original(cfg, disc), "rb").read())
        off = int(e["offset"], 16)

        # ko → 셀코드 u16 LE. 각 글자 = 2바이트 셀(lead,trail) → 저장은 (trail,lead).
        codes = bytearray()
        for ch in e["ko"]:
            cb = encode(ch)
            if len(cb) != 2:
                raise ValueError(f"{e['module']} {ch!r}: 2바이트 셀이 아니다 ({cb.hex()})")
            codes += bytes((cb[1], cb[0]))

        # 원본 와이드 문자열 길이 = 널(u16 0) 전까지
        end = off
        while end + 1 < len(blob) and blob[end:end + 2] != b"\x00\x00":
            end += 2
        avail = end - off
        if len(codes) > avail:
            raise ValueError(f"{e['module']} {off:#x}: {e['ko']!r} {len(codes)}B > 자리 {avail}B")

        blob[off:off + len(codes)] = codes
        for i in range(off + len(codes), end):     # 남는 자리 널
            blob[i] = 0
        ui[disc] = bytes(blob)
        n += 1
    return n
