# 북으로. White Illumination 한국어 패치

드림캐스트 **北へ。White Illumination** (Hudson, 1999) 한국어화 도구 모음.

개인 소장 디스크를 직접 덤프해 분석·재빌드하기 위한 리버스 엔지니어링 도구와 문서입니다.
**게임 데이터는 이 저장소에 포함되지 않습니다.** 모든 산출물은 본인 디스크 덤프에서
아래 도구로 재생성합니다.

## 번역 현황 (2026-09-24)

### 된 것

| 영역 | 분량 | 상태 |
|---|---|---|
| 본편 대사 (여름편·겨울편, 히로인 8명, `PLOT.CB` `*.SMF` 48개) | 22,652줄 | **100%**. 남은 8줄은 `・・・` 만 있는 줄 |
| 가이드북 본문 (`SOZ.CB` `guide*.msl` 5개) | 2,037줄 | 100% |
| 극중 소설 『격돌!!』 (`gekitotu.msl`) | 194줄 | 100% (9/24) |
| 퀴즈 (`M05.CB`) | 292문제 | 100% |
| 시스템 UI 문자열 (`/TRF/*.DLL` 26모듈 — 메뉴·안내·저장·옵션·미니게임·스탭롤 244항목) | — | 완료. 미번역으로 남은 건 이진 잡음·서식 문자열·조회 키뿐 |
| 지도 라벨 이미지 (`SOZ.CB` 510상자) | — | 한글 레터링 주입 완료 |
| 미니게임 이미지 `M05`·`M08` (지우기 전용 + 헛간 이름표) | — | 주입 완료 |
| 이름 입력 화면 라벨·안내문·샘플 이름 74개 | — | 완료 (문자판은 아래) |
| 글꼴 | — | IBM Plex Sans KR 한글을 JIS 2수준 빈 칸에 주입, **가변폭**(대사창·UI·팝업·스탭롤 모두) |

### 안 된 것

- **타이틀 로고·저작권 이미지** `SOZ soz_008/009`, **인트로 텍스트 카드** `soz_001_00~03`(날짜 카드 `005~007` 은 번역·스타일 준비됨, 주입만 남음).
- **이름 입력 문자판**: あいうえお 그리드는 가나 그대로 — 한글 이름은 입력 못 한다(`MAIN.CB` 이미지도 미주입).
- **동영상** `RESOURCE/MOVIE/*.AVI` 7편: 영상에 구워진 글자는 손대지 않았고, `BALLOON.SMF` 자막 4줄은 파이프라인 밖.
  `END.AVI` 엔딩 크레딧도 영상.
- **노래방**: 가사(`歌詞.json` 215줄)는 **번역하지 않기로 함**. 곡 제목 목록·`MP7` 이미지(キタカラ 로고·곡 선택)도 그대로.
- **커맨드 메뉴 날짜·시각 조각** `MENU.CB MSE_H00`(숫자 + 朝/午前/午後/夕/夜/日/月): 어느 화면에 뜨는지 못 짚음.
- **이미지 전수 조사 미완**: 덤프 7,447장 중 글자 유무를 가려낸 건 `SOZ`·`M05`·`M08`·`MENU`·`MAIN`·`MP7`·`M03`. 나머지 미니게임(`MP4/6/9/10`)·조연(`SC`)·캐릭터 아카이브는 미확인.
- 조회 키(`data/untranslatable.json` 163개)는 EDL 변수 이름이라 번역하지 않는다. 화면엔 나오지 않는다(해바라기 미로 6개 확인).

### 알려진 문제

- **가라오케에서 곡을 고르면 랜덤하게 리셋된다.** 패치하지 않은 원본 디스크에서도 같은 증상이 나와
  패치 탓인지 에뮬레이터 탓인지 가를 수 없어 분석을 멈췄다. → [EMULATOR-BUGS.md](docs/EMULATOR-BUGS.md)

## 디버그 패치 (한국어 패치와 별개)

번역과 무관하게 게임 동작을 바꾸는 편의 패치. 전부 `kitae.config.json` 의 불리언 옵션이고,
끄면 그 자리는 원본 바이트 그대로 나간다. **배포용 디스크에서는 끄는 것이 원칙이다.**

| 옵션 | 하는 일 | 구현 |
|---|---|---|
| `cbs_bypass` | **C.B.S(커뮤니케이션 브레이크 시스템) 우회.** 원작은 선택지 508곳에 제한 시간(90~260프레임)이 있어 안 고르면 기본값으로 넘어간다. EB 의 `0x6E/0x6F` 게이트 5바이트를 문장 구분자 `0x00` 으로 덮어 제한 시간을 없앤다(길이 불변, 게이트 없는 형태는 원본에도 9곳). | `kitae/build/ebgate.py` |
| `minigame_unlock` | **미니게임 목록 띄우기.** 타이틀의 미니게임 항목은 세이브 해제 마스크(데이터+0x700 의 `0x7F00` 비트)로 열린다. 그 검사 분기(`KITATITLE 0x10001fa2 bt`)를 nop 으로 바꿔 항상 켠다. | `data/dllpatch.json` |
| `soundroom_unlock` | 타이틀 사운드룸 항목의 달성도 임계값(평균 80 이상)을 0 으로. | `data/dllpatch.json` |
| `debug_boot` | **디버그 화면 띄우기.** 타이틀 씬(`P00S052`)의 태스크를 개발용 씬 셀렉터 `CTRFSceneLaunch` 로 바꿔, VMS 확인·오프닝 뒤 플롯/씬 목록이 뜬다. 거기서 `P42S024` 사운드 테스트 등 어떤 씬이든 띄울 수 있다. | `kitae/build/debugboot.py`, [SCRIPT-SYSTEM.md](docs/SCRIPT-SYSTEM.md) |

```
python -m kitae config set cbs_bypass false      # 배포 빌드
python -m kitae config set minigame_unlock false
python -m kitae config set soundroom_unlock false
python -m kitae config set debug_boot false
```

## 준비

- Python 3.11+ / `pillow` (이미지), `capstone` (SH-4 역어셈블)
- GDI 덤프 (`track01.bin`, `track02.raw`, `track03.bin`, `.gdi`) — `kitae.config.json` 의 `orig_dir`
- 글꼴: IBM Plex Sans KR (`kitae.config.json` 의 `font.ttf`)

## 빌드 순서

```
python -m kitae check            # 환경·원본·폰트·번역 파일 규칙 검사
python -m kitae status           # 스크립트별 번역 진행률
python -m kitae build            # 폰트·대사·타이밍·UI·이미지 → dist/*.gdi
python -m kitae build KOTORI_01  # 스크립트 하나만
```

번역 파일은 `translation/` 아래 JSON 하나가 단일 소스다 — 대사 `translation/<SCRIPT>.json`,
가이드·소설 `translation/guide/*.json`, UI `translation/ui/<모듈>.json`, 이미지 텍스트
`translation/images/`. 규칙(전각·마크업·공백·문장부호)은 [KO-TEXT-RULES.md](docs/KO-TEXT-RULES.md)에
있고 `kitae check` 가 기계 검사한다.

1. **창별 줄 수를 바꿀 수 없다** — `.MSG` 테이블이 창마다 줄 수를 고정한다
2. **인라인 마크업 보존** — `@S@`/`@P@`(재생 제어), `&主人公&`(이름 치환)

## 문서

- [ANALYSIS.md](docs/ANALYSIS.md) — 디스크·아카이브 전체 구조
- [DISC-MAP.md](docs/DISC-MAP.md) — 어느 파일에 무슨 글이 있나
- [SCRIPT-SYSTEM.md](docs/SCRIPT-SYSTEM.md) — 시나리오 엔진 구조
- [EB-FORMAT.md](docs/EB-FORMAT.md) — EDL 바이트코드와 옵코드표
- [ENC2-FORMAT.md](docs/ENC2-FORMAT.md) — CTRFLzss 압축 명세
- [PLOT-MAP.md](docs/PLOT-MAP.md) — 플롯/씬/메시지 창 매핑
- [MTG-TIMING.md](docs/MTG-TIMING.md) — 대사 타이밍(입 모양·표시 속도)
- [UI-TEXT.md](docs/UI-TEXT.md) — DLL 안의 UI 문자열 패치
- [KO-TEXT-RULES.md](docs/KO-TEXT-RULES.md) — 한국어 표기 규칙
- [PROPORTIONAL-WIDTH.md](docs/PROPORTIONAL-WIDTH.md) — 가변폭 훅(확정 사항)
- [JOSA-ENGINE.md](docs/JOSA-ENGINE.md) — 이름 치환 뒤 조사 처리
- [CHARACTERS.md](docs/CHARACTERS.md) — 등장인물 표기
- [EMULATOR-BUGS.md](docs/EMULATOR-BUGS.md) — 원본 디스크에서도 나는 에뮬레이터 쪽 증상

## 밝혀진 포맷 요약

- **ENC2** = `CTRFLzss`. 12비트 절대 윈도우 위치 + 4비트 길이, 비트는 바이트 내 LSB-first,
  값은 MSB-first. 쓰기 커서 1에서 시작, `src == 0`이 스트림 종료.
- **EB** = `CKitaheGel`(TRF/KITAHEGEL.DLL) VM. `u8 옵코드 + 길이표대로의 오퍼랜드`.
  `0x6A` 화자 지정, `0x6B/0x6C` 메시지 표시, `0x73` 입력 대기, `0x74` 선택지.
- **창↔문자열** = `.SMF` 끝의 `.MSG` 청크에 창마다 `(줄 수, 바이트 오프셋)`.
- **폰트** = 24×24 1bpp, 주소는 리드바이트 **테이블 조회** 기반(산술식 아님).
  본체/안티에일리어스 2중 평면이라 둘 다 패치해야 한다.
- **이미지** = `CTRFImageBuffer`/`IBUF`, RGB565(배경)·ARGB1555(스프라이트),
  픽셀은 같은 LZSS. `.SET`의 `CTRFPictures`가 640×480 블릿 좌표를 갖는다.

## 라이선스 / 범위

도구와 문서는 자유롭게 쓰셔도 됩니다. 게임 데이터·에셋·대사는 저작권자(Hudson)의 것이며
이 저장소에 포함되지 않습니다. 본인이 소유한 디스크의 개인적 이용을 전제로 합니다.
