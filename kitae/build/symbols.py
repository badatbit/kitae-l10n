# -*- coding: utf-8 -*-
"""`north01.sym` 의 심볼 이름 — **절대 번역하면 안 되는 문자열**들이다.

엔진은 EDL 가상머신의 전역변수를 **이름으로** 찾는다. 예를 들어 커맨드 메뉴가
열릴 때 `CTRFCmdMenu::Start`(KITACMDMENU 0x10002560)가

    IGelFlexible::GetVarByName("移動表示", &this->moveMask)

를 부르고, 그 이름을 SYMBOL.DLL 이 `north01.sym` 의 해시 표에서 찾는다
(해시 0x10001100, 버킷 순회 0x10001170, 마지막에 strcmp). 못 찾으면 1을 돌려주고
**출력 인자를 건드리지 않아** 마스크가 초기값 0으로 남는다. 그러면 방 목록 대신
3D 시내 지도가 열린다 — ８월１일 밤에 목욕이 안 뜨던 게 이것이었다.

그래서 DLL 안의 문자열이라도 **심볼 이름과 같으면 손대면 안 된다.** 이름은
north01.sym 안에 그대로 있고 우리는 그걸 안 바꾸므로, 한쪽만 한글이 되면
영영 못 만난다.

같은 함정에 걸리는 것들: 「メニュー表示」「セーブ場所」(커맨드 메뉴),
「ナレスキップ」「メッセージ速度」「メッセージボーダー」(설정),
「…の夏編終了」「ＵＦＯできる」… (달성·해금 플래그), 아이템 이름(소지 플래그).

방 이름(風呂, 書斎 …)은 심볼이 아니라 표시용 라벨이라 번역해도 된다.
"""
import struct

import io
import json
import os

CACHE = {}
FILE = "symbols.json"          # data/ 에 그룹별로 남긴다


def read(cfg):
    """north01.sym 을 파싱해 [그룹][이름] 으로 돌려준다."""
    from kitae.core.cab import Cab
    from kitae.build import uipatch
    plot = Cab(uipatch.original(cfg, "/RESOURCE/PLOT.CB"))
    blob = plot.read("north01.sym")
    if blob[:4] != b".STR":
        raise ValueError("north01.sym 이 .STR 로 시작하지 않는다")
    counts = struct.unpack_from("<IIII", blob, 8)
    pos, groups = 0x18, []
    for n in counts:
        g = []
        for _ in range(n):
            e = blob.find(b"\x00", pos)
            if e < 0:
                break
            g.append(blob[pos:e].decode("cp932", "replace"))
            pos = e + 1
        groups.append(g)
    return groups


def save(cfg):
    """data/symbols.json 으로 남긴다. 이름 순서가 곧 EB 가 쓰는 번호다."""
    groups = read(cfg)
    doc = {
        "source": "RESOURCE/PLOT.CB :: north01.sym",
        "note": "EDL 전역변수·화자 이름표. 이 이름들은 번역하면 안 된다 — "
                "엔진이 이름으로 조회하고, 실패해도 조용히 기본값이 남는다. "
                "자세한 건 docs/UI-TEXT.md",
        "groups": [{"index": i, "count": len(g), "names": g}
                   for i, g in enumerate(groups)],
    }
    p = os.path.join(cfg.data_dir, FILE)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with io.open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
    return p, groups


def names(cfg):
    """모든 심볼 이름의 집합. data/symbols.json 이 있으면 그걸 읽는다."""
    key = id(cfg)
    if key in CACHE:
        return CACHE[key]
    out = set()
    p = os.path.join(cfg.data_dir, FILE)
    try:
        if os.path.exists(p):
            with io.open(p, encoding="utf-8") as fh:
                for g in json.load(fh)["groups"]:
                    out.update(g["names"])
        else:
            _p, groups = save(cfg)
            for g in groups:
                out.update(g)
    except Exception:
        pass
    CACHE[key] = out
    return out
