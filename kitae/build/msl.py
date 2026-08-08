# -*- coding: utf-8 -*-
""".msl — 가이드북 본문이 들어 있는 문자열 목록.

관광지·도시·협력사 설명은 대사 스크립트가 아니라 **`/RESOURCE/SOZ.CB` 안의
`guide*.msl`** 에 있다. 오래 못 찾은 이유는 두 가지다 — `.CB` 안에 압축되어
있어서 디스크를 그대로 훑어서는 안 걸리고, `TRFGUIDEMAP.DLL` 에는 **지명만**
있고 설명문은 한 줄도 없다.

    guide.msl    387줄 / 창 148   관광지 설명
    guide2.msl   522줄 / 창 197   관광지 설명
    guide3.msl   112줄 / 창  28   도시 설명 (지도 화면에서 Ａ)
    guide4.msl    57줄 / 창  24   협력 (스폰서 소개 + 홈페이지 주소)
    guides.msl   959줄 / 창 359   관광지 설명 (계절 변형)
    gekitotu.msl 194줄            극중 소설 『激突！！』 — 가이드북이 아니다

## 형식은 .SMF 와 같다

    "CLSS" u32 nlen  name("CTRFMessageList")     ← 이 껍데기만 다르다
    ".STR" u32 size  u32 count   count 개의 NUL 종단 cp932 문자열
    ".MSG" u32 size  size/8 개의 (u32 줄수, u32 바이트오프셋)

그래서 껍데기를 떼고 [[smf]] 의 `rebuild_smf` 를 그대로 쓴다. **창 표가 있으니
줄 수도 그대로 지켜야 한다** — 한 창이 화면 한 페이지고, 줄 수가 바뀌면 다음
설명의 첫 줄을 삼킨다.

`.STR` 위치는 파일마다 다르다. `guide4.msl` 은 이름 길이가 달라 ２１ 바이트째다.
고정값으로 두지 말 것.
"""

ENCODING = "cp932"


def split(blob):
    """(CLSS 껍데기, .STR 부터의 본문). 못 찾으면 ValueError."""
    i = blob.find(b".STR")
    if i < 0:
        raise ValueError("no .STR chunk")
    return blob[:i], blob[i:]


def parse(blob):
    """(껍데기, [문자열], [(줄수, 첫문자열)]) — 읽기 전용."""
    from kitae.core.cab import smf_strings
    from kitae.core.windows import msg_table
    head, body = split(blob)
    return head, smf_strings(body), msg_table(body)


def rebuild(blob, rows, encode=None):
    """번역을 얹은 새 .msl 바이트.

    `rows` 는 `{(창, 줄): {"source":…, "target":…}}` — 대사 빌드와 같은 모양이다.
    반환값은 (바이트, 경고, 인코딩 실패).
    """
    from kitae.build.smf import rebuild_smf
    head, body = split(blob)
    out, warns, bad = rebuild_smf("msl", rows, body, encode=encode)
    return head + out, warns, bad
