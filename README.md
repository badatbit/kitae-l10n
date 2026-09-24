# 북으로. White Illumination 한국어화 도구

드림캐스트 **北へ。White Illumination** (Hudson, 1999) 한국어로 즐기기 위한 도구입니다.

개인 소장 디스크를 직접 덤프해 분석·재빌드하기 위한 리버스 엔지니어링 도구와 문서입니다.
**게임 실행 파일·이미지·음성은 이 저장소에 포함되지 않습니다.** 모든 산출물은 본인
디스크 덤프에서 아래 도구로 재생성합니다.

## 번역 현황 (2026-09-24)

### 된 것

| 영역 | 분량 | 상태 |
|---|---|---|
| 본편 대사 (`PLOT.CB` `*.SMF` 48개) | 22,652줄 | **100%** |
| 가이드북 본문 (`SOZ.CB` `guide*.msl` 5개) | 2,037줄 | 100% |
| 극중 소설 『격돌!!』 (`gekitotu.msl`) | 194줄 | 100% |
| 퀴즈 (`M05.CB`) | 292문제 | 100% |
| 시스템 UI 문자열 (`/TRF/*.DLL` 26모듈) | — | 99%? (제어코드 제외) |
| 지도 라벨 이미지 (`SOZ.CB` 510상자) | — | 100% |
| 미니게임 이미지 `M05`·`M08` (지우기 전용 + 헛간 이름표) | — | 100% |
| 이름 입력 화면 라벨·안내문·샘플 이름 74개 | — | 문자판 빼고 100% |
| 글꼴 출력 | — | 가변폭 적용 |

### 안 된 것

- **이미지**
  - **타이틀 로고·저작권 이미지** `SOZ soz_008/009`, **인트로 텍스트 카드** `soz_001_00~03`
  - **커맨드 메뉴 날짜·시각 조각** 朝/午前/午後/夕/夜/日/月 등의 문자가 뜨는 곳을 확인하지 못해 남겨 둠
  - 전수 검사는 하였으나 의도적 또는 비의도적으로 누락된 이미지가 있을 수 있음
- **이름 입력 문자판**: 설명만 번역함. 이름을 입력하지 않을 시 자동으로 한글 이름 부여
- **동영상**: 동영상 및 텍스트가 출력되지 않는 이벤트 장면에서의 자막
- **노래방**: 가사와 싱크가 필요하여 가사는 번역하지 않음. 일부 텍스트가 번역되지 않은 부분 존재함

### 알려진 문제

- **가라오케에서 곡을 고르면 랜덤하게 리셋됨**: 패치하지 않은 원본 디스크에서도 같은 증상이 나와
  패치 탓인지 에뮬레이터 탓인지 가를 수 없어 분석을 멈춤 → [EMULATOR-BUGS.md](docs/EMULATOR-BUGS.md)

## 디버그 패치 (한국어 패치와 별개)

번역과 무관하게 게임 동작을 바꾸는 편의 패치입니다. 전부 `kitae.config.json` 의 불리언 옵션이고,
끄면 그 자리는 원본 바이트 그대로 나갑니다. 배포용 패치에서는 꺼져 있으므로 이를 켜고 싶으시면
직접 환경을 꾸며 패치해 주세요.

| 옵션 | 하는 일 | 구현 |
|---|---|---|
| `cbs_bypass` | **C.B.S(커뮤니케이션 브레이크 시스템) 우회.** 원작은 상대방이 대화할 때 적절한 타이밍에 끼어들어 대화하는 시스템입니다. 이 옵션을 켜면 개입 없이도 대화창이 뜹니다. | `kitae/build/ebgate.py` |
| `minigame_unlock` | **미니게임 목록 띄우기.** 미니게임은 특정 조건을 클리어해야 타이틀 메뉴에 등록됩니다. 이 패치를 켜면 모든 미니 게임이 타이틀에 뜹니다. | `data/dllpatch.json` |
| `soundroom_unlock` | **사운드 룸 띄우기.** 특정 조건을 만족하면 타이틀에 사운드 룸이 뜹니다. 이 패치를 켜면 조건에 관계없이 게임 내의 다양한 음악을 들을 수 있습니다. | `data/dllpatch.json` |
| `debug_boot` | **디버그 화면 띄우기.** 부팅 직후 디버깅 화면으로 넘어갑니다. 원하는 장면으로 바로 넘어가서 게임을 진행할 수 있습니다. | `kitae/build/debugboot.py`, [SCRIPT-SYSTEM.md](docs/SCRIPT-SYSTEM.md) |

저장소 기본값은 넷 다 꺼져 있습니다. 켜려면 원하는 것만 `true` 로 바꾸고 다시 빌드하세요.

```
python -m kitae config set cbs_bypass true
python -m kitae config set minigame_unlock true
python -m kitae config set soundroom_unlock true
python -m kitae config set debug_boot true
python -m kitae build
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

번역 파일은 `translation/` 아래 JSON 하나가 단일 소스입니다 — 대사 `translation/<SCRIPT>.json`,
가이드·소설 `translation/guide/*.json`, UI `translation/ui/<모듈>.json`, 이미지 텍스트
`translation/images/`. 규칙(전각·마크업·공백·문장부호)은 [KO-TEXT-RULES.md](docs/KO-TEXT-RULES.md)에
있고 `kitae check` 가 기계 검사합니다.

1. **창별 줄 수를 바꿀 수 없다** — `.MSG` 테이블이 창마다 줄 수를 고정합니다.
2. **인라인 마크업 보존** — `@S@`/`@P@`(재생 제어), `&主人公&`(이름 치환)

## 배포용 패치

```
python tools/make_release.py -v v0.9     # dist/*.dcp · *.xdelta · 읽어주세요.txt
```

두 벌을 냅니다.

| 파일 | 크기 | 적용 | 원본 요구 |
|---|---|---|---|
| `.dcp` | 10.6MB | Universal Dreamcast Patcher | 조금 달라도 됨 |
| `.xdelta` | 5.3MB | `xdelta3 -d -s track03.bin …` | 바이트까지 같아야 함 |

`.xdelta` 는 **데이터 트랙 `track03.bin` 하나**의 차분입니다 — track01(오디오)·track02·`.gdi` 는
바뀌지 않습니다. 만든 뒤 되적용해 빌드본과 sha256 이 같은지 확인합니다. 원본 해시는
`읽어주세요.txt` 에 적힙니다.

[Universal Dreamcast Patcher](https://github.com/DerekPascarella/UniversalDreamcastPatcher) 가 읽는
**DCP** 로 냅니다. DCP 는 확장자만 바꾼 ZIP 이고, 뿌리에 바뀐 파일을 디스크의 폴더 구조 그대로
(`RESOURCE/…`, `TRF/…`) 담습니다. 매니페스트는 없습니다. 부트섹터를 바꿔야 하면 뿌리에
`bootsector/IP.BIN` 을 두는데, 이 패치는 IP.BIN 을 안 건드리므로 넣지 않습니다.

담을 파일은 `work/build/` 가 아니라 **빌드된 디스크와 원본 디스크를 직접 비교**해 고릅니다 —
SOZ 처럼 디스크에 넣는 단계에서 한 번 더 손대는 것이 있어, 배포될 바이트는 디스크 쪽이 정답입니다.
현재 39개 파일입니다(원자료 16.7MB). 사용자는 원본 GDI/CDI 와 이 `.dcp` 를 패처에 넣으면
패치된 이미지가 나옵니다.

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
  본체/안티에일리어스 2중 평면이라 둘 다 패치해야 함.
- **이미지** = `CTRFImageBuffer`/`IBUF`, RGB565(배경)·ARGB1555(스프라이트),
  픽셀은 같은 LZSS. `.SET`의 `CTRFPictures`가 640×480 블릿 좌표를 가짐.

## 라이선스 / 범위

- **코드와 문서** (`kitae/`, `tools/`, `docs/`, `README.md`): MIT. [LICENSE](LICENSE) 참고.
- **번역문과 레터링** (`translation/`, `images/`): 모든 권리를 유보합니다. 번역은 원작의
  2차적저작물이라 자유 이용을 허락할 권한이 저희에게 없습니다. 본인이 소유한 디스크에
  적용하는 개인적 이용만 허용하며, 재배포와 상업적 이용은 허락 없이 할 수 없습니다.
- **원작의 권리**는 타이틀 화면 표기대로 SEGA Enterprises, HUDSON SOFT,
  RED / 広井王子事務所 에 있습니다. 이 저장소는 권리자와 무관한 비공식 팬 번역입니다.

게임 실행 파일·이미지·음성은 포함하지 않으며, 모든 산출물은 본인 디스크 덤프에서
재생성합니다. 다만 번역 작업에 필요한 **원문 대사는 `translation/` 안에 대조용으로
들어 있습니다.**
