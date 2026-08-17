# -*- coding: utf-8 -*-
"""이름 입력 화면 힌트 한글 렌더 — 폰트 텍스처 베이크 소스에 한글 글자 주입.

이름화면(TRFNAMEIN)은 힌트 텍스트를 CTRFFontTex(글꼴 텍스처)로 그린다. 그 텍스처는
런타임에 **"굽기용 문자열"**의 글자만 구워진다. 그런데 굽기용 문자열(원본 일본어,
.data `0x1001564c+`)과 **표시용 문자열**(`0x10015864+`, uipatch 가 번역함)이 **별개**다
(원문에선 같은 텍스트의 복사본 2벌). 그래서 번역한 한글이 텍스처에 구워지지 않아 화면에
안 나온다 — 굽기용에 없는 글자(あ·仮·한글)는 전부 빈칸.

이 패치는 번역 힌트의 **유니크 글자**를 굽기용 블록(`0x1564c..0x15848`)에 써 넣어 한글
글리프가 텍스처에 구워지게 한다. 소스 폰트(CTRFFont)는 TRFSTRINGS 공유폰트라 한글 글리프
데이터가 이미 있다([[kitahe-korean-localization]] 폰트 주입).

구조 근거: CTRFFont::DrawChar 매핑 = lead 테이블→페이지배열→(trail-0x40)×72 (24×24 1bpp).
베이크 = `TRFNAMEIN` 함수(끝 `0x100039c0`)가 `0x1564c` 등을 `0x10005c64`(char-add)로 넘김.
굽기용≠표시용은 진단으로 확정(번역문에 넣은 仮/あ 안 나옴 = 원본 굽기셋에 없던 글자).
"""
import json, os, struct

DATA_VA = 0x10015000
DATA_RAW = 0x14000
BAKE_VA = 0x1001564C          # 굽기용 힌트 문자열(idx6) 시작
BAKE_END_VA = 0x100157C8      # idx7(히라가나) 앞까지 = idx6 힌트 굽기 전용.
#   ★ idx7(히라가나 0x157c8)·idx8(名字名前 라벨 0x15828)·idx9/10(샘플이름)은
#     건드리면 안 된다 — 각자 다른 텍스처의 굽기/표시 소스라, 덮으면 그 화면이 빈칸.
#     그것들은 uipatch 가 제자리 번역한다(한글이 더 짧아 in-place 로 들어감).
JA_MARK = b"\x95\xfb\x8c\xfc"  # cp932 "方向" — 원본 확인용


def _foff(va):
    return DATA_RAW + (va - DATA_VA)


def patch(cfg, lang, encode, dll):
    """번역 이름화면 힌트의 유니크 글자를 굽기 블록에 주입한 새 DLL 바이트.

    손댈 게 없거나 원본 서명이 안 맞으면 (원본 그대로, 0) 을 준다.
    """
    off, end = _foff(BAKE_VA), _foff(BAKE_END_VA)
    if not (0 <= off < end <= len(dll)):
        return dll, 0
    if dll[off:off + 4] != JA_MARK:       # 원본 "方向…" 이 아니면 건너뛴다(레이아웃 변동)
        return dll, 0

    doc = os.path.join(cfg.root, "translation", "ui", "TRFNAMEIN.json")
    if not os.path.exists(doc):
        return dll, 0
    j = json.load(open(doc, encoding="utf-8"))
    chars = []
    seen = set()
    for e in j.get("entries", []):
        for c in e.get("text", {}).get(lang, ""):
            if c in ("　", "\n", " ") or c in seen:
                continue
            seen.add(c)
            chars.append(c)
    if not chars:
        return dll, 0

    payload = b"".join(encode(c) for c in chars) + b"\x00"
    budget = end - off
    if len(payload) > budget:
        # 예산 초과 — 들어가는 만큼만(글자 단위로 자른다)
        acc = bytearray()
        for c in chars:
            b = encode(c)
            if len(acc) + len(b) + 1 > budget:
                break
            acc += b
        payload = bytes(acc) + b"\x00"

    out = bytearray(dll)
    out[off:end] = payload + b"\x00" * (budget - len(payload))
    return bytes(out), len(chars)
