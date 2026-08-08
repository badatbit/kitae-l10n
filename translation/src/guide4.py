# -*- coding: utf-8 -*-
"""가이드북 『협력』 — 스폰서 소개 (`SOZ.CB::guide4.msl`, 24창 57줄).

목차의 마지막 항목이다. 회사 소개 세 줄 + 홈페이지 주소 두 줄이 한 쌍으로
２４창을 이룬다. 홈페이지 주소 창은 Ａ 버튼으로 ＶＭＳ에 등록할 수 있다.

## 대사와 다른 두 가지

1. **반각을 써도 된다.** 가이드북에는 음성이 없어서 MTG 타이밍을 소비하지
   않는다([[mtg-timing]]). ＵＲＬ은 반각 그대로 두는 게 읽기 좋고, 애초에
   건드리면 안 되는 값이다. 폭은 반각 두 글자를 한 칸으로 세어 재면 된다.
2. **회사 이름은 옮긴다.** 앞서 스폰서 이름을 일본어로 두기로 했는데, 목록의
   절반만 한국어라 화면이 깨져 보였다. `TRFGUIDEMAP` 의 목록 쪽도 같이 맞춘다
   ([[guide4_names]]).

제품명은 한국에 들어온 표기를 쓴다 — `그랜드체로키`, `바르케타`, `콘탁스`.
`リブレット` 는 도시바 `리브레토` 가 정식 표기다.
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
DST = os.path.join(HERE, os.pardir, "guide", "guide4.json")
MARKUP = re.compile(r"@[^@]{0,8}@|&[^&]{0,16}&")
MAX = 25

KO = {
 (0, 0): "독일의　대형　자동차　회사。",
 (0, 1): "본편에서는　메르세데스벤츠　ＣＬ６００이",
 (0, 2): "사토나카　집의　자가용으로　나온다。",
 (1, 0): "메르세데스벤츠　일본의　홈페이지　주소。",
 (1, 1): "http://www.mbj.mercedes-benz.com/",
 (2, 0): "스웨덴의　대형　자동차　회사。",
 (2, 1): "본편에서는　볼보　８５０　에스테이트가",
 (2, 2): "아이다　집의　자가용으로　나온다。",
 (3, 0): "볼보　카즈　재팬의　홈페이지　주소。",
 (3, 1): "http://www.volvocars.co.jp/pages/default.asp",
 (4, 0): "본편에서　주인공이　떠나는　공항。",
 (4, 1): "매일　３０편　이상　하네다ー치토세를　오간다。",
 (5, 0): "하네다　공항의　홈페이지　주소。",
 (5, 1): "http://www.tokyo-airport-bldg.co.jp/index2.html",
 (6, 0): "현지에서는　「마루이　씨」라　불리며　사랑받는",
 (6, 1): "오래된　백화점。　여름편　코즈에　편에　나온다。",
 (6, 2): "도쿄의　「빨간　카드　마루이」와는　다른　가게다。",
 (7, 0): "마루이이마이의　홈페이지　주소。",
 (7, 1): "http://www.marui-imai.co.jp/",
 (8, 0): "본편에서　주인공이　내리는　공항。",
 (8, 1): "홋카이도의　하늘　관문으로　업무와　관광에",
 (8, 2): "널리　쓰인다。",
 (9, 0): "신치토세　공항의　홈페이지　주소。",
 (9, 1): "http://www.iacnet.or.jp/aero/link6.html",
 (10, 0): "항공자위대　치토세　기지。　본편에서　유코가",
 (10, 1): "일하지만　물론　이건　가공의　설정이다。",
 (11, 0): "항공자위대의　홈페이지　주소。",
 (11, 1): "http://www.jda.go.jp/jasdf/",
 (12, 0): "대형　가전　회사。　본편에서　사토나카　코즈에가",
 (12, 1): "이　회사의　노트북　「리브레토」를　쓴다。",
 (13, 0): "도시바의　홈페이지　주소。",
 (13, 1): "http://www.toshiba.co.jp/",
 (14, 0): "대형　카메라　회사。　본편에서　유코가",
 (14, 1): "이　회사의　「콘탁스Ｇ１」과　「콘탁스Ｔｉｘ」를",
 (14, 2): "즐겨　쓴다。",
 (15, 0): "교세라의　홈페이지　주소。",
 (15, 1): "http://www.kyocera.co.jp/index-j.html",
 (16, 0): "미국의　대형　자동차　회사。",
 (16, 1): "본편에서는　그랜드체로키　리미티드ＬＸ가",
 (16, 2): "하루노　집의　자가용으로　나온다。",
 (17, 0): "크라이슬러의　홈페이지　주소。",
 (17, 1): "http://www.chrysler.co.jp/japanese/",
 (18, 0): "이탈리아의　대형　자동차　회사。",
 (18, 1): "본편에서는　피아트　바르케타가",
 (18, 2): "시이나　카오루의　애차로　나온다。",
 (19, 0): "피아트의　홈페이지　주소。",
 (19, 1): "http://www.fiat-auto.co.jp/",
 (20, 0): "주식회사　루크가　해마다　내는　가이드북。",
 (20, 1): "게임　속　가이드북은　이　책의　글　일부를",
 (20, 2): "쓰고　있다。　봄　발행에　정가는　１９２０엔。",
 (21, 0): "빅런　홋카이도의　홈페이지　주소。",
 (21, 1): "http://nexus.earthcape.or.jp/BIGRUN/",
 (22, 0): "대형　전화　서비스　회사。　본편에서　주인공이",
 (22, 1): "이　회사의　ＰＨＳ　파워캐럿　ＤＬ－Ｓ２８Ｐ를",
 (22, 2): "쓰고　있다。",
 (23, 0): "ＤＤＩ　포켓의　홈페이지　주소。",
 (23, 1): "http://www.j-plaza.or.jp/ddi-pocket/",
}

ASK = {
 (20, 0): "`株式会社ルック` 가 내는 가이드북 『ビッグラン北海道』 가 게임 내 "
          "가이드북의 원전이라는 설명이다. 회사명을 `루크` 로 음차했는데 "
          "실재 회사라 표기를 확인해 두면 좋겠다.",
 (6, 2): "`赤いカードの丸井` 는 도쿄 마루이의 광고 문구(빨간 카드)를 가리킨다. "
         "한국 독자에게는 통하지 않아 직역만 해 두었다. 각주 없이 그대로 둘지.",
 (22, 1): "`パワーキャロットＤＬ－Ｓ２８Ｐ` 는 실제 ＰＨＳ 기종명이라 그대로 음차했다.",
}


def cells(s):
    """전각 １칸, 반각 ０.５칸. 가이드북 상자는 대사와 폭이 같다."""
    n = 0.0
    for c in MARKUP.sub("", s):
        try:
            n += 0.5 if len(c.encode("cp932")) == 1 else 1
        except UnicodeEncodeError:
            n += 1
    return n


doc = json.load(io.open(DST, encoding="utf-8"))
by = {(e["window"], e["line"]): e for e in doc["entries"]}

bad = []
for k, ko in KO.items():
    e = by.get(k)
    if e is None:
        bad.append(f"{k}: 원문에 없는 자리")
        continue
    if cells(ko) > MAX:
        bad.append(f"{k}: {cells(ko)}칸 > {MAX}  {ko}")
    ja = e["text"]["ja"]
    # ＵＲＬ은 한 글자도 바뀌면 안 된다
    u_ja = re.findall(r"https?://\S+", ja)
    if u_ja and u_ja != re.findall(r"https?://\S+", ko):
        bad.append(f"{k}: 주소가 바뀌었다  {ja}")

missing = [(e["window"], e["line"]) for e in doc["entries"]
           if (e["window"], e["line"]) not in KO]
if missing:
    bad.append(f"빠진 줄 {len(missing)}개: {missing[:12]}")

if bad:
    print(f"검사 실패 {len(bad)}건")
    for b in bad:
        print("  " + b)
    raise SystemExit(1)

for k, ko in KO.items():
    by[k]["text"]["ko"] = ko
for k, why in ASK.items():
    by[k]["ask"] = [{"why": why, "state": "open"}]

io.open(DST, "w", encoding="utf-8").write(
    json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
print(f"검사 통과 — 협력 {len(KO)}줄 기록, 검토 요청 {len(ASK)}건")
