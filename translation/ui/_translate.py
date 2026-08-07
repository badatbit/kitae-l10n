# -*- coding: utf-8 -*-
"""시스템 UI 번역을 translation/ui/<모듈>.json 에 채운다.

DLL 안 문자열은 자리에 덮어쓰므로 **바이트 길이가 원문 자리 이하**여야 한다.
정렬 패딩까지 쓸 수 있어 `avail` 이 실제 한도다. 한글·전각은 2바이트,
반각 영숫자는 1바이트다(타이틀 메뉴의 가운데 맞춤 공백이 반각이라 그대로 쓴다).

들어가지 않는 문자열은 채우지 않고 목록으로 보고한다 — 억지로 줄이는 것보다
남겨 두고 나중에 포인터 재배치로 푸는 편이 낫다.
"""
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))

# 번역하면 안 되는 것 — 화면 표시가 아니라 대사 마크업의 키/값이다.
SKIP_MODULES = {"KITAE"}

KO = {
 "KITATITLE": {
  0x010940: "   처음부터",
  0x01094c: "  이어하기",
  0x01095c: " 시스템 설정",
  0x01096c: "   달성도",
  0x010978: "  미니게임",
  0x010988: "사운드룸",
  0x010998: "메모리 카드에 접근 중입니다.\n"
            "메모리 카드를 뺐다 꽂았다 하지 마세요.",
  0x010a34: "해설 건너뛰기",
  0x010a44: "메시지 속도",
  0x010a54: "메시지 테두리",
 },
 "TRFSYSCONFIG": {
  0x010988: "시스템 변경",
  0x010998: "한 번 들은 해설",
  0x0109b0: "건너뛰지 않음／건너뛰기",
  0x0109d0: "메시지 표시 속도",
  0x0109ec: "표준／고속",
  0x0109f8: "메시지 창 색",
  0x010a14: "빨／보／파／초／노／흰／검",
  0x010a30: "메시지 창 투명도",
  # ０／１／２／３／４／５／６ 는 숫자라 그대로 둔다
  0x010a6c: "방향 버튼 위아래로 항목을 고르고 좌우로 바꿉니다.\n"
            "스타트 버튼으로 설정하고 나갑니다.\n"
            "Ｂ 버튼으로 반영하지 않고 나갑니다.",
  0x010af4: "이 설정으로 괜찮습니까？\n　 예　／　아니요",
  0x010b74: "해설 건너뛰기",
  0x010b84: "메시지 속도",
  0x010b94: "메시지 테두리",
 },
 "COMMONSAVE": {
  0x0104c4: "클리어 데이터를 저장할까요？\n　　예　／　아니요",
  0x0104f8: "데이터를 제대로 저장하지 못했습니다.",
  0x010520: "포트Ａ 확장 소켓１의 메모리 카드에 저장 중\n"
            "입니다. 메모리 카드를 빼지 마세요.",
  0x010584: "저장이 끝났습니다.",
  0x0105a0: "코토리 여름편",
  0x0105b0: "아유 여름편",
  0x0105c0: "타냐 여름편",
  0x0105d4: "유코 여름편",
  0x0105e4: "카오루 여름편",
  0x0105f4: "하노카 여름편",
  0x010608: "코즈에 여름편",
  0x010618: "메구미 여름편",
  0x01062c: "ＵＦＯ 가능",
  0x01063c: "퀴즈 가능",
  0x01064c: "테니스 가능",
  0x01065c: "테크노 미로 가능",
  0x010670: "해바라기 가능",
  0x010680: "노래방 가능",
  0x010690: "슈팅 가능",
  0x0106a8: "졌습니다",
 },
 "KITACMDMENU": {
  # 커맨드 메뉴 (화면에 늘 보이는 것)
  0x01b048: "이동합니다",
  0x01b054: "소지품",
  0x01b05c: "시간 보내기",
  0x01b06c: "가이드북",
  0x01b07c: "격돌 읽기",
  0x01b088: "ＰＨＳ",
  0x01b090: "잔다",
  0x01b098: "메뉴에서 나가기",
  0x01b0ac: "저장, 불러오기",
  0x01b0bc: "시스템",
  # 안내문
  0x01a944: "방향 버튼으로 거점 선택, Ａ 버튼으로 결정\n"
            "Ｌ／Ｒ 트리거로 맵 회전\n"
            "Ｂ 버튼으로 커맨드 메뉴로 돌아갑니다.",
  0x01ac1c: "방향 버튼 위아래로 상대를 고르고\n"
            "Ａ 버튼으로 그 상대에게 전화를 겁니다.\n"
            "Ｂ 버튼으로 메뉴로 돌아갑니다.",
  0x01af0c: "방향 버튼 좌우로 선택, Ａ 버튼으로 결정",
  0x01ac88: "님으로 괜찮습니까？",
  0x01ac9c: "　　　예　／　아니요",
  # 이동 메뉴
  0x01aa8c: "메뉴 표시",
  0x01aa9c: "이동 표시",
  0x01aaa8: "응접실",
  0x01aab0: "서재",
  0x01aab8: "현관",
  0x01aac0: "욕실",
  0x01aac8: "하루노 집 나감",
  0x01aad8: "거실",
  0x01aae4: "손님방",
  0x01aaec: "축사",
  0x01aaf4: "아이다 집 나감",
  0x01ab04: "코토리 방",
  0x01ab10: "온천",
  0x01ab18: "호텔 방",
  0x01ab28: "하루노",
  0x01ab30: "아이다",
  0x01ab38: "레스토랑",
  0x01ab44: "저장 장소",
  # PHS 상대
  0x01abb4: "코토리",
  0x01abc0: "카오루",
  0x01abcc: "아유",
  0x01abd8: "하노카",
  0x01abe8: "유코",
  0x01abf4: "코즈에",
  0x01ac00: "타냐",
  0x01ac0c: "메구미",
 },
}


def blen(s):
    """게임 바이트 수. 한글·전각 2바이트, 반각 1바이트."""
    return sum(1 if ord(c) < 0x80 and c != "\n" else
               (1 if c == "\n" else 2) for c in s)


tgt = "ko"
fits = skipped = 0
too_long = []
for name, table in KO.items():
    p = os.path.join(HERE, name + ".json")
    doc = json.load(io.open(p, encoding="utf-8"))
    by = {e["offset"]: e for e in doc["entries"]}
    for off, ko in table.items():
        e = by.get(off)
        if e is None:
            too_long.append((name, off, "원문에 없는 오프셋", ko))
            continue
        n = blen(ko)
        if n > e["avail"]:
            too_long.append((name, off, f"{n}B > {e['avail']}B", ko))
            continue
        e["text"][tgt] = ko
        fits += 1
    io.open(p, "w", encoding="utf-8").write(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n")

print(f"채움 {fits}개")
if too_long:
    print(f"\n자리에 안 들어감 {len(too_long)}개")
    for name, off, why, ko in too_long:
        print(f"  {name} {off:#08x}  {why}  {ko!r}")

# 아직 번역이 없는 것 요약
print()
for name in sorted(os.listdir(HERE)):
    if not name.endswith(".json"):
        continue
    doc = json.load(io.open(os.path.join(HERE, name), encoding="utf-8"))
    n = len(doc["entries"])
    d = sum(1 for e in doc["entries"] if (e["text"].get(tgt) or "").strip())
    mark = "  (마크업 키 — 건드리지 않음)" if doc["module"] in SKIP_MODULES else ""
    print(f"  {doc['module']:<14} {d:>3}/{n:<4}{mark}")
