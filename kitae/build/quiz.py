# -*- coding: utf-8 -*-
"""`Quiz.mhd` — 미니게임 『クイズまるごと北海道』의 문제 292개.

`TRFQUIZ.DLL` 에는 `これはテストです。` 같은 자리표시자만 있고 **진짜 문제는
`/RESOURCE/M05.CB` 안의 `Quiz.mhd`** 에 들어 있다. 홋카이도 상식 퀴즈다.

## 형식

`CLSS` 컨테이너에 `CTRFQuizQuestion` 객체가 292개 들어 있다. 객체 하나가
문제 하나이고, 껍데기는 [[windows]] 의 `clss_objects` 로 이미 읽을 수 있다.

    u32               머리값 — 문제마다 다르다(1·13·…). 반드시 그대로 둔다
    문자열            문제 (여러 줄이면 \\n 으로 잇는다)
    u32  1~10         장르 번호 — 줄 수와 무관하다. 그대로 둔다
    문자열 ×3         선택지
    u32  0|1|2        **정답 번호**(０부터). 그대로 둔다

## ★ 정답은 꼬리 u32 가 가리킨다

대부분(269문제)이 ０이라 처음엔 "１번이 늘 정답"으로 잘못 봤다. 아니다 —
`厚岸` 문제는 꼬리가 １이고 정답이 두 번째 `あっけし` 다(１이 14문제, ２가 9문제).

그러니 **선택지 순서를 바꾸면 안 된다.** 보기 좋으라고 재배열하면 그 23문제가
조용히 오답 처리된다. 순서를 지키면 꼬리를 건드릴 일도 없다.

## 문제를 옮길 때

  * **줄 수를 지킨다.** 문제 상자가 ４줄까지고 원문이 그 안에 맞춰져 있다.
  * 선택지는 오답도 **정답과 헷갈릴 만큼 비슷해야** 퀴즈가 성립한다
    (`花咲ガニ／花巻ガニ／花持ガニ`). 뜻만 옮기면 정답이 뻔해진다.
"""
import struct

ENCODING = "cp932"
CLASS = "CTRFQuizQuestion"


def _objects(blob):
    """[(시작, 끝, oid, 이름, payload)] — CLSS 컨테이너를 훑는다.

    객체 사이에 정렬용 여백이 있다. `시작`·`끝`을 함께 돌려주어 다시 쓸 때
    그 여백을 **그대로 베끼게** 한다 — 안 그러면 파일이 ２，５３０바이트 줄고
    엔진이 읽는 자리가 어긋난다.
    """
    assert blob[:4] == b"CLSS", "CLSS 가 아니다"
    nlen = struct.unpack_from("<I", blob, 4)[0]
    pos = 8 + nlen
    out = []
    while pos + 14 <= len(blob):
        if blob[pos:pos + 4] != b"\xff\xff\xff\xff":
            pos += 1
            continue
        oid = struct.unpack_from("<I", blob, pos + 4)[0]
        cl = struct.unpack_from("<H", blob, pos + 8)[0]
        nm = blob[pos + 10:pos + 10 + cl].decode("ascii", "replace")
        plen = struct.unpack_from("<I", blob, pos + 10 + cl)[0]
        body = pos + 14 + cl
        out.append((pos, body + plen, oid, nm, blob[body:body + plen]))
        pos = body + plen
    return out


def parse(blob):
    """[{oid, q, genre, choices, tail}] — 읽기 전용."""
    out = []
    for _a, _b, oid, nm, pay in _objects(blob):
        if nm != CLASS:
            continue
        head = struct.unpack_from("<I", pay, 0)[0]
        p = 4
        e = pay.index(b"\x00", p)
        q = pay[p:e].decode(ENCODING, "replace")
        p = e + 1
        genre = struct.unpack_from("<I", pay, p)[0]
        p += 4
        ch = []
        for _ in range(3):
            e = pay.index(b"\x00", p)
            ch.append(pay[p:e].decode(ENCODING, "replace"))
            p = e + 1
        out.append({"oid": oid, "head": head, "q": q, "genre": genre,
                    "choices": ch, "tail": pay[p:]})
    return out


def _payload(rec, encode):
    out = bytearray(struct.pack("<I", rec["head"]))
    out += encode(rec["q"]) + b"\x00"
    out += struct.pack("<I", rec["genre"])
    for c in rec["choices"]:
        out += encode(c) + b"\x00"
    out += rec["tail"]
    return bytes(out)


def rebuild(blob, rows, encode=None):
    """번역을 얹은 새 Quiz.mhd.

    `rows` 는 `{oid: {"q": …, "choices": [3]}}`. 없는 것은 원문을 쓴다.
    반환값은 (바이트, 인코딩 실패 목록).
    """
    if encode is None:
        from kitae.build import hangul
        cp = hangul.load_codepage()

        def encode(s):
            return hangul.encode(s, cp)

    src = {r["oid"]: r for r in parse(blob)}
    bad = []
    objs = _objects(blob)
    out = bytearray()
    prev = 0
    for pos, end, oid, nm, pay in objs:
        out += blob[prev:pos]          # 머리와 객체 사이 여백을 그대로
        prev = end
        if nm != CLASS or oid not in src:
            out += blob[pos:end]
            continue
        rec = dict(src[oid])
        t = rows.get(oid) or {}
        if (t.get("q") or "").strip():
            rec["q"] = t["q"]
        cs = t.get("choices") or []
        rec["choices"] = [(cs[i] if i < len(cs) and (cs[i] or "").strip()
                           else rec["choices"][i]) for i in range(3)]
        try:
            body = _payload(rec, encode)
        except UnicodeEncodeError as e:
            bad.append((oid, str(e)))
            body = _payload(src[oid], lambda s: s.encode(ENCODING, "replace"))
        out += b"\xff\xff\xff\xff" + struct.pack("<IH", oid, len(nm))
        out += nm.encode("ascii") + struct.pack("<I", len(body)) + body
    out += blob[prev:]                 # 마지막 객체 뒤의 꼬리
    return bytes(out), bad
