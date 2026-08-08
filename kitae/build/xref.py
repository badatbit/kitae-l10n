# -*- coding: utf-8 -*-
"""문자열이 **조회 키**인지 **화면 표시**인지 코드 참조로 가른다.

엔진은 EDL 전역변수를 이름으로 찾는다. 그 이름을 번역하면 조회가 조용히
실패하고 기능이 티 안 나게 죽는다(이동 목록이 그랬다 — build/symbols.py 참고).
그런데 `north01.sym` 에 같은 단어가 있다고 다 키는 아니다. 우연히 이름이 겹칠
뿐 화면에만 나오는 것도 많다.

가르는 방법은 하나뿐이다 — **그 문자열의 주소가 코드에서 어떻게 쓰이는가.**

  키   : 주소가 리터럴 풀에서 레지스터로 실려 조회 함수로 넘어간다.
         또는 `{char* 이름, u32 값}` 표에 들어 있고 코드가 그 표를 돌며 비교한다.
  표시 : 라벨 배열이나 구조체의 이름 칸에만 있고 코드가 주소를 직접 안 만진다.

여기서는 두 가지를 본다:
  1. `.text` 안 리터럴 풀에 그 VA 가 있는가  → 코드가 주소를 만진다
  2. `.rdata`/`.data` 에서 그 VA 바로 뒤 4바이트가 **작은 정수/비트값**인가
     → `{이름, 비트}` 표일 가능성. 이 표는 이름으로 찾으므로 키다.

둘 다 아니면 표시용으로 본다. 확신이 안 서면 키로 취급한다 — 잘못 번역하면
증상이 조용해서 찾기가 어렵다.
"""
import struct


def _refs(blob, secs, va):
    """이 VA 를 담은 4바이트 슬롯: [(섹션, 파일오프셋)]"""
    key = struct.pack("<I", va)
    out = []
    for name, _sva, raw, rsz in secs:
        end = min(raw + rsz, len(blob))
        i = raw
        while True:
            i = blob.find(key, i, end)
            if i < 0:
                break
            if i % 4 == 0:
                out.append((name, i))
            i += 1
    return out


def _looks_like_pair_table(blob, off):
    """VA 바로 뒤가 작은 정수면 `{이름, 값}` 표로 본다."""
    if off + 8 > len(blob):
        return False
    nxt = struct.unpack_from("<I", blob, off + 4)[0]
    # 비트마스크나 작은 인덱스. 주소(0x1000xxxx)면 이름만 늘어선 표다.
    return nxt < 0x10000


def classify(blob, secs, va):
    """'key' | 'display' | 'unknown'"""
    refs = _refs(blob, secs, va)
    if not refs:
        return "unknown"
    for sec, off in refs:
        if sec == ".text":
            return "key"
        if _looks_like_pair_table(blob, off):
            return "key"
    return "display"


def scan(cfg, module, doc, lang, only=None):
    """[(offset, ja, ko, 판정)] — only 가 있으면 그 원문들만 본다."""
    from kitae.core import pestr
    from kitae.build import relocate, uipatch

    blob = open(uipatch.original(cfg, doc["path"]), "rb").read()
    secs = pestr.sections(blob)
    vm = relocate._va_map(secs)
    out = []
    for e in doc["entries"]:
        ja = e["text"]["ja"]
        ko = (e["text"].get(lang) or "").strip()
        if not ko or (only is not None and ja not in only):
            continue
        va = relocate.off_to_va(vm, e["offset"])
        out.append((e["offset"], ja, ko,
                    classify(blob, secs, va) if va else "unknown"))
    return out
