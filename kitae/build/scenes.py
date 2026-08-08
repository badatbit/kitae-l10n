# -*- coding: utf-8 -*-
"""씬 제목(`SCN/INIS.CB`)의 장소 이름을 번역문과 맞춘다.

씬 제목이 곧 트리거 조건이다:

    P02S000=○８月２日／朝／ローズヒル南平岸／春野家／書斎

엔진은 이동 목적지를 고를 때 이 제목의 **장소 필드**를 커맨드 메뉴의 장소
이름과 대조하는 것으로 보인다. 그래서 UI 만 번역하면 짝이 안 맞아 엉뚱한
목록이 뜬다(８월１일 밤에 목욕 대신 시내가 나왔다).

여기서는 **UI 번역과 똑같은 문자열**로 씬 제목을 바꿔 양쪽을 다시 맞춘다.
치환 대상은 아래 목록에 적힌 것만이다 — 날짜·시간대 필드와 분기 조건
(（琴梨と一緒の場合）등)은 건드리지 않는다.

날짜 필드를 건드리면 날짜 파싱이 깨질 수 있고, 시간대는 KITAE 쪽을 번역해도
멀쩡했으므로 대조에 안 쓰이는 것으로 보인다. 둘 다 손대지 않는다.
"""
import io
import json
import os
import re

# 집 안 장소 9종만 바꿔 봤더니 소용이 없었다. 바깥 장소(ローズヒル南平岸)를
# 안 바꿔서 그 단계에서 이미 짝이 어긋났기 때문이다. **한쪽만 바꾸면 거기서
# 끊긴다** — UI 에서 번역한 이름은 씬 제목에서도 전부 같이 바꿔야 한다.
# 역어셈블 결과: INIS.CB 의 .INI 는 제작진 문서일 뿐이고 어떤 코드도
# 씬 제목의 장소 필드를 대조하지 않는다(여는 곳은 디버그 씬 선택기뿐).
# 즉 이 치환은 무해하지만 아무 효과도 없다. 껐다.
ONLY = []           # [] = 아무것도 바꾸지 않음

# 씬 제목의 필드와 대조되는 이름이 든 모듈. 시간대·날짜(朝/夜/月/日)는 KITAE 에,
# 장소는 KITACMDMENU 에 있다.
FROM = ("KITACMDMENU", "KITAE")

TITLE = re.compile(r"^(\w+=○)(.*)$", re.M)
INIS = "/RESOURCE/SCN/INIS.CB"


def wanted(cfg, lang, names=None):
    """{일본어 이름: 번역}. 여러 모듈에서 모으되 표기가 하나여야 한다."""
    out = {}
    for mod in FROM:
        p = cfg.path("translation", "ui", mod + ".json")
        if not os.path.exists(p):
            continue
        with io.open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        # ONLY 가 None 이면 전부, 목록이면 그 안의 것만(빈 목록 = 아무것도 안 함)
        only = set(names) if names else (None if ONLY is None else set(ONLY))
        for e in doc["entries"]:
            ja = e["text"]["ja"]
            ko = (e["text"].get(lang) or "").strip()
            if ko and (only is None or ja in only):
                out.setdefault(ja, ko)
    return out


def retitle(text, table):
    """씬 제목의 장소 필드만 바꾼다. (새 텍스트, 바꾼 횟수)"""
    n = 0

    # 날짜는 `８月１日` 처럼 한 필드 안에 숫자와 섞여 있어 통째 비교가 안 된다.
    # 첫 필드에 한해 月/日 만 글자 단위로 바꾼다. 다른 필드에서 하면 지명 속
    # 같은 글자까지 건드린다.
    date_map = {k: v for k, v in table.items() if k in ("月", "日")}

    def fix(m):
        nonlocal n
        head, title = m.group(1), m.group(2)
        out = []
        for i, f in enumerate(title.split("／")):
            k = f.strip()
            if k in table:
                out.append(f.replace(k, table[k]))
                n += 1
            elif i == 0 and date_map and ("月" in f or "日" in f):
                for a, b in date_map.items():
                    f = f.replace(a, b)
                out.append(f)
                n += 1
            else:
                out.append(f)
        return head + "／".join(out)

    return TITLE.sub(fix, text), n


def rebuild(cfg, lang, encode, names=None):
    """(새 INIS.CB 바이트, 바꾼 필드 수). 바꿀 게 없으면 (None, 0)."""
    from kitae.core.cab import Cab
    from kitae.build import uipatch

    table = wanted(cfg, lang, names)
    if not table:
        return None, 0
    src = uipatch.original(cfg, INIS)
    cab = Cab(src)
    new, total = {}, 0
    for name in cab.names:
        try:
            raw = cab.read(name)
            txt = raw.decode("cp932")
        except Exception:
            continue
        out, n = retitle(txt, table)
        if n:
            new[name] = encode(out)
            total += n
    if not total:
        return None, 0
    from kitae.build.smf import repack_cab
    dst = cfg.path(cfg["work_dir"], "build", "INIS.CB")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    repack_cab(src, new, dst)
    with open(dst, "rb") as fh:
        return fh.read(), total
