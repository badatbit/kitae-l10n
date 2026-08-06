# kitahe-l10n

드림캐스트 **北へ。White Illumination** (Hudson, 1999) 한국어화 도구 모음.

개인 소장 디스크를 직접 덤프해 분석·재빌드하기 위한 리버스 엔지니어링 도구와 문서입니다.
**게임 데이터는 이 저장소에 포함되지 않습니다.** 모든 산출물은 본인 디스크 덤프에서
아래 도구로 재생성합니다.

## 준비

- Python 3.11+ / `pillow` (이미지), `capstone` (SH-4 역어셈블, 선택)
- GDI 덤프 (`track01.bin`, `track02.raw`, `track03.bin`, `.gdi`)
- 경로는 `tools/gdfs.py`의 `TRACK` 상수에서 지정

## 빌드 순서

```
python tools/workbook.py  KOTORI_01     # 번역 작업대 TSV 생성 → dump/translate/
#   TSV의 target 칸을 채운다
python tools/hangul.py    build KOTORI_01   # 쓰인 한글만 폰트에 주입 → dump/build/TRF/
python tools/build_smf.py KOTORI_01 --cab   # .MSG 재계산 + CAB 재포장
python tools/disc.py      patch RESOURCE/PLOT.CB dump/build/PLOT.CB dump/build/track03.bin
python tools/package.py                     # 실행 가능한 dist/ 조립 + 검증
```

번역 시 제약은 둘뿐이며 빌드 도구가 자동 검사합니다.

1. **창별 줄 수를 바꿀 수 없다** — `.MSG` 테이블이 창마다 줄 수를 고정한다
2. **인라인 마크업 보존** — `@S@`/`@P@`(재생 제어), `&主人公&`(이름 치환)

## 도구

| 분류 | 파일 |
|---|---|
| 디스크 | `gdfs.py` (GD-ROM/ISO9660), `disc.py` (제자리 패치 + EDC/RS 패리티) |
| 아카이브 | `cab.py` (`/CAB`), `enc2.py` (CTRFLzss 압축/해제) |
| 데이터 | `clss.py` (객체 직렬화), `image.py` (CTRFImageBuffer→PNG), `font.py` (글리프) |
| 스크립트 | `ebdis.py` (EDL 바이트코드), `windows.py` (창↔문자열), `script.py` (통합 대본) |
| 번역 | `workbook.py`, `hangul.py` (코드페이지+글리프), `build_smf.py` |
| 조사 | `findtext.py`, `plotmap.py`, `dump_plot.py`, `dump_scn.py`, `extract_p01.py` |

## 문서

- [ANALYSIS.md](docs/ANALYSIS.md) — 디스크·아카이브 전체 구조
- [ENC2-FORMAT.md](docs/ENC2-FORMAT.md) — CTRFLzss 압축 명세
- [EB-FORMAT.md](docs/EB-FORMAT.md) — EDL 바이트코드와 옵코드표
- [SCRIPT-SYSTEM.md](docs/SCRIPT-SYSTEM.md) — 시나리오 엔진 구조
- [PLOT-MAP.md](docs/PLOT-MAP.md) — 플롯/씬/메시지 창 매핑

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
