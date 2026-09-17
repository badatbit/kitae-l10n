# -*- coding: utf-8 -*-
"""DLL 코드/데이터 바이트 직접 패치.

문자열이 아니라 **상수**(레이아웃 좌표·크기 등)를 고칠 때 쓴다. uipatch 는
표시 문자열만 다루므로, `mov #imm` 의 즉시값 같은 코드 상수는 여기서 바꾼다.

근거는 `data/dllpatch.json`. 각 항목은 {module, offset, from, to, why[, option]}:
- option 이 있으면 kitae.config.json 의 그 키(불리언, 기본 true)가 false 일 때 건너뛴다.
- offset 은 모듈(원본 DLL) 기준 파일 오프셋.
- from/to 는 16진 바이트열. **from 이 실제 바이트와 일치할 때만** 적용한다
  (원본이 바뀌면 조용히 엉뚱한 곳을 덮지 않도록).

문자열 재배치는 .text 코드 오프셋을 옮기지 않으므로, uipatch 뒤에 적용해도
좌표는 그대로다.

## 옵션 — `layout_patch`

kitae.config.json 의 `layout_patch`(불리언, 기본 true)로 통째로 켜고 끈다.
가이드북 지역선택·스폿 목록의 흰 선택막대/회색 오버레이/텍스트 X 를 한글
길이에 맞게 넓힌 것이 여기 들어 있어, 원본 레이아웃으로 돌려 보고 싶을 때
`kitae config set layout_patch false` 후 빌드하면 된다.
"""
import io
import json
import os


def apply(cfg, ui):
    """ui({디스크경로: 바이트})에 dllpatch.json 을 적용. 바뀐 곳 수를 돌려준다."""
    from kitae.build import uipatch

    if not cfg.get("layout_patch", True):
        print("  DLL 코드 상수 패치 건너뜀 (layout_patch=false)")
        return 0
    path = os.path.join(cfg.data_dir, "dllpatch.json")
    if not os.path.exists(path):
        return 0
    spec = json.load(io.open(path, encoding="utf-8"))
    n = 0
    for e in spec.get("patches", []):
        opt = e.get("option")
        if opt and not cfg.get(opt, True):
            continue                      # 항목별 옵션(kitae.config.json 불리언)으로 끈 패치
        mod = e["module"]
        blob = bytearray(ui.get(mod) or open(uipatch.original(cfg, mod), "rb").read())
        off = int(e["offset"])
        frm = bytes.fromhex(e["from"])
        to = bytes.fromhex(e["to"])
        if len(frm) != len(to):
            raise ValueError(f"dllpatch {mod} @{off:#x}: from/to 길이 불일치")
        cur = bytes(blob[off:off + len(frm)])
        if cur != frm:
            raise ValueError(
                f"dllpatch {mod} @{off:#x}: from 불일치 "
                f"(실제 {cur.hex()} != 기대 {e['from']})")
        blob[off:off + len(to)] = to
        ui[mod] = bytes(blob)
        n += 1
    return n
