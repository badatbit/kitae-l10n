# legacy-src — 초기 번역 저작 스크립트 (퇴역, 실행 금지)

2026-08-08 첫 번역 때 파이썬 dict(`KO = {(창,줄): "…"}`)로 번역을 저작해 `translation/*.json`
에 채워 넣던 스크립트 39개다. **실행하면 JSON 을 통째로 덮어쓴다**(import 만 해도 실행됨).
그 뒤 마침표 `．`화·단어장 반영·날짜 공백·검수 판정 등은 전부 JSON 에만 적용됐고 여기엔 옛
`。` 가 1,507개 남아 있어, 2026-09-16 `guide3.py` 를 돌렸을 때 실제로 회귀가 났다.

**단일 소스는 `translation/**/*.json`** 이다. 이 파일들은 번역 정책 머리말(음차·지청·단위·연호
등)을 참고하려고 `.py.txt` 로 이름을 바꿔 보존만 한다. 다시 실행할 필요가 있다고 생각되면
먼저 `kitae check` 와 `docs/` 를 보고, JSON 을 읽고 쓰는 일회성 스크립트로 대신한다.

| 파일 | 머리말 첫 줄 |
|---|---|
| `_exp_propwidth.py.txt` | ※ 실험용 — 가변폭 조사. 끝나면 되돌린다. |
| `_translate.py.txt` | 시스템 UI 번역을 translation/ui/<모듈>.json 에 채운다(9/13 판, avail 한도 검사). 실행하면 ui JSON 을 덮어쓴다. |
| `furo_0801.py.txt` | 風呂 8월 1일 밤 — 삿포로 첫날 밤의 목욕 독백. |
| `furo_a.py.txt` | 욕실 회상 — `風呂` 날짜 없는 창 첫 배치 (창 32~135). |
| `furo_b.py.txt` | 욕실 회상 — `風呂` 날짜 없는 창 둘째 배치 (창 137~284). |
| `furo_c.py.txt` | 욕실 회상 — `風呂` 날짜 없는 창 셋째 배치 (창 285~328). |
| `furo_d.py.txt` | 욕실 회상 — `風呂` 날짜 없는 창 마지막 배치 (창 329~414). |
| `furo_e.py.txt` | 욕실 회상 — 날짜 있는 창 ①. 되풀이 문장 전체 + ８월３~５일. |
| `furo_f.py.txt` | 욕실 회상 — 날짜 있는 창 ②. ８월６~７일. |
| `furo_quiz.py.txt` | 風呂 8월 1일 밤 — 이름 맞히기 퀴즈의 **선택지**. |
| `guide3.py.txt` | 가이드북 『홋카이도 지도』 — 거점 도시 설명 (`SOZ.CB::guide3.msl`, 44창 112줄). |
| `guide4.py.txt` | 가이드북 『협력』 — 스폰서 소개 (`SOZ.CB::guide4.msl`, 24창 57줄). |
| `guide_data.py.txt` | 가이드북 관광지 — **정형 줄**(전화·주소·영업시간·요금)만 기계로 옮긴다. |
| `guide_doto.py.txt` | 가이드북 관광지 — 도동·무로란·노보리베쓰·시코쓰호 (`guides.msl` 창 164~198). |
| `guide_furano.py.txt` | 가이드북 관광지 — 호쿠류·후라노·샤코탄·루모이·하코다테 앞 (`guides.msl` 창 199~235). |
| `guide_hakodate.py.txt` | 가이드북 관광지 — 하코다테 １차분 (`guides.msl` 창 236~276). |
| `guide_hakodate2.py.txt` | 가이드북 관광지 — 하코다테 ２차분과 협력사 (`guides.msl` 창 276~367). |
| `guide_otaru.py.txt` | 가이드북 관광지 — 오타루·유바리·오비히로·도동 (`guides.msl` 창 128~164). |
| `guide_rest.py.txt` | 가이드북 관광지 — 남은 줄 전부 (`guide.msl` · `guide2.msl`). |
| `guide_reuse.py.txt` | 가이드북 관광지 — **이미 옮긴 문장 가져오기**. |
| `guide_sapporo.py.txt` | 가이드북 관광지 — 삿포로 １차분 (`guides.msl` 창 0~65). |
| `guide_sapporo2.py.txt` | 가이드북 관광지 — 삿포로 ２차분과 오타루 앞부분 (`guides.msl` 창 66~127). |
| `hanyou.py.txt` | HANYOU(汎用) — 어디서나 불리는 공용 스크립트. |
| `hokkaido_naming.py.txt` | `北海大学`·`北海道庁` 표기를 풀어 쓴다. |
| `kotori_02.py.txt` | KOTORI_02 8월 2일 — 삿포로 시내 관광 · 오락실 · 노래방 · 징기스칸. |
| `kotori_02_rest.py.txt` | KOTORI_02 나머지 112줄 — 8월 2일 아침 장면과 선택지 전부. |
| `kotori_03_a.py.txt` | ８월３일 — `KOTORI_03` 첫 배치 (창 0~69). 오타루 나들이. |
| `kotori_03_b.py.txt` | ８월３일 — `KOTORI_03` 둘째 배치 (창 70~135). 운하공예관. |
| `kotori_03_c.py.txt` | ８월３일 — `KOTORI_03` 셋째 배치 (창 136~200). 수족관과 저녁 운하. |
| `kotori_03_d.py.txt` | ８월３일 — `KOTORI_03` 마지막 배치 (창 201~298). 저녁 식사와 비에이 제안. |
| `load.py.txt` | 번역문 텍스트를 translation/<SCRIPT>.json 에 넣는다. |
| `minigames.py.txt` | 미니게임 조작 설명 — 인형뽑기·테니스·슈팅·젖짜기·노래방·퀴즈. |
| `quiz_g4.py.txt` | 퀴즈 장르 ４ — 지청·교통·인물·사투리 (32문제). |
| `quiz_g5.py.txt` | 퀴즈 장르 ５ — 홋카이도 일반·명물·인물 (43문제). |
| `quiz_g6.py.txt` | 퀴즈 장르 ６ — 명소·자연·문화 (39문제). |
| `quiz_g7.py.txt` | 퀴즈 장르 ７ — 상징·명소·인물 (43문제). |
| `quiz_g8.py.txt` | 퀴즈 장르 ８ — 지리·자연·명소 (54문제). |
| `quiz_rest.py.txt` | 퀴즈 나머지 전부 — 장르 ９·２·３·１０·１ (81문제). |
| `tone_fix.py.txt` | `kitae tone` 이 잡아낸 말투 어긋남을 고친다. |
| `uranai.py.txt` | URANAI — ＰＨＳ 전화 스크립트. 『Ｄｒ．다바다 점술 전화 서비스』와 통화 응답. |

`ko_a.txt`~`ko_d.txt` 는 KOTORI_01 첫 번역 초안(창 번호별 평문). 어디서도 읽지 않는다 — 참고 보존.
