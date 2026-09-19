# -*- coding: utf-8 -*-
"""디버그 부팅 — 타이틀 씬(P00S052)이 띄우는 태스크를 씬 셀렉터로 바꾼다.

제품판에도 개발용 씬 셀렉터(TRF/TRFSCENELAUNCH.DLL, `CTRFSceneLaunch`)와 사운드
테스트(KITASOUNDTEST.DLL)가 남아 있지만 거기로 가는 분기가 없다(2026-09-19 조사:
저장 변수·타이틀 패드·EB 스크립트 48개·레지스트리 키 전부 없음). 유일한 입구는
씬 파일(SCV)의 `CTRFTaskCut` 이 띄우는 클래스 이름이다.

    RESOURCE/SCN/SCV.CB :: P00S052.SCV (○タイトル)
      CTRFDataSet
        CTRFCutLink
        CTRFTaskCut  payload = u32 cut_id | u32 5 | u32 len(4배수 패딩) | 클래스명
                                       'CKitaTitle'  →  'CTRFSceneLaunch'

클래스명이 4바이트 길어지므로 CTRFTaskCut 과 그 부모 레코드의 payload 길이를 같이
올린다(CLSS 레코드: FF FF FF FF | u32 id | u16 cls_len | cls | u32 payload_len).
P42S007.SCV(○シーンセレクト起動)의 태스크 컷과 바이트 단위로 같은 모양이 된다.

옵션 `debug_boot`(kitae.config.json, 기본 false)가 참일 때만 runner 가 부른다.
결과: VMS 확인 → 오프닝 뒤 타이틀 자리에 플롯/씬 목록 상자가 뜬다. 거기서
P42S024(サウンドテスト)·P42S020(めぐみテスト) 등 어떤 씬이든 띄울 수 있다.
"""
import os
import struct

from kitae.core.cab import Cab
from kitae.core.clss import MARK

SCV_DISC = "/RESOURCE/SCN/SCV.CB"
TITLE_SCENE = "P00S052.SCV"
OLD_CLS = b"CKitaTitle"
NEW_CLS = b"CTRFSceneLaunch"


def _pad4(n):
    return (n + 3) & ~3


def _read(buf, pos, end):
    """clss._read_record 와 같은 검증. (start, oid, cls, payload_start, payload_len) 또는 None."""
    if pos + 14 > end or buf[pos:pos + 4] != MARK:
        return None
    cl = struct.unpack_from("<H", buf, pos + 8)[0]
    p0 = pos + 10 + cl
    if cl == 0 or cl > 64 or p0 + 4 > end:
        return None
    cls = bytes(buf[pos + 10:p0])
    if not all(32 <= b < 127 for b in cls):
        return None
    plen = struct.unpack_from("<I", buf, p0)[0]
    if p0 + 4 + plen > end:
        return None
    return (pos, struct.unpack_from("<I", buf, pos + 4)[0], cls, p0 + 4, plen)


def _records(buf, pos, end):
    """한 단계의 레코드들. 검증에 실패한 자리는 다음 MARK 로 건너뛴다(clss._records)."""
    out = []
    while pos < end:
        got = _read(buf, pos, end)
        if got is None:
            nxt = buf.find(MARK, pos + 1, end)
            if nxt < 0:
                break
            pos = nxt
            continue
        out.append(got)
        pos = got[3] + got[4]
    return out


def _find_path(buf, pos, end, target_cls, path=()):
    """target_cls 레코드까지의 (레코드 시작, payload_len 필드 위치) 경로 — 조상 순."""
    for start, oid, cls, ps, plen in _records(buf, pos, end):
        here = path + ((start, ps - 4),)
        if cls == target_cls:
            return here, (start, ps, plen)
        if plen >= 14:                                   # clss.parse_children 과 같은 조건
            first = buf.find(MARK, ps, ps + plen)
            if first >= 0 and _read(buf, first, ps + plen) is not None:
                got = _find_path(buf, first, ps + plen, target_cls, here)
                if got:
                    return got
    return None


def patch_scene(scv, old_cls=OLD_CLS, new_cls=NEW_CLS):
    """SCV(CLSS 평문)의 CTRFTaskCut 클래스명을 바꾼 바이트를 돌려준다."""
    buf = bytearray(scv)
    assert buf[:4] == b"CLSS", "CLSS 아님"
    nlen = struct.unpack_from("<I", buf, 4)[0]
    got = _find_path(buf, 8 + nlen, len(buf), b"CTRFTaskCut")
    if not got:
        raise ValueError("CTRFTaskCut 없음")
    path, (start, ps, plen) = got
    # payload = u32 cut_id(0x4001) | u32 5 | u32 len(4배수 패딩) | 클래스명
    cut_id, five, ln = struct.unpack_from("<III", buf, ps)
    name = bytes(buf[ps + 12:ps + 12 + ln]).rstrip(b"\0")
    if name != old_cls:
        raise ValueError(f"태스크 클래스가 {name!r} (기대 {old_cls!r})")
    new_ln = _pad4(len(new_cls) + 1)
    new_field = struct.pack("<I", new_ln) + new_cls.ljust(new_ln, b"\0")
    delta = (4 + new_ln) - (4 + ln)
    buf[ps + 8:ps + 12 + ln] = new_field
    for _rec_start, len_pos in path:                     # 조상 전부 + 자기 자신
        struct.pack_into("<I", buf, len_pos, struct.unpack_from("<I", buf, len_pos)[0] + delta)
    return bytes(buf)


def build(cfg, original, out_path):
    """원본 SCV.CB(`original`)에서 타이틀 씬만 바꿔 `out_path` 로 재포장한다."""
    from kitae.build import smf as smf_mod
    cab = Cab(original)
    name = cab.resolve(TITLE_SCENE)
    patched = patch_scene(cab.read(name))
    smf_mod.repack_cab(original, {name: patched}, out_path)
    return out_path
