# 北へ。White Illumination — 한국어화 사전 분석

분석일: 2026-08-05 · 대상: Dreamcast GDI 덤프 v2.002 (Hudson, 1999)

## 1. 플랫폼 개요

- **Windows CE 기반 드림캐스트 게임**이다. 부트 바이너리는 `0WINCEOS.BIN`(WinCE 커널+게임 통합 이미지)이고, `/WINCE/`에 CE 시스템 DLL, `/TRF/`에 게임 엔진(PE 형식, **SH-4** 아키텍처)이 있다.
- 엔진은 Hudson 자체 C++ 프레임워크 "TRF" (`CTRFFont`, `CTRFResourceMessage`, `CTRFVisualScene` 등 RTTI 이름 확인됨).
- 디스크: GDI 3트랙. 게임 데이터는 전부 track03.bin (LBA 45000~, raw 2352B 섹터, ISO9660).
- 에뮬레이터 `redream.exe`가 `kitahe-org/`에 준비되어 있어 테스트 루프 구성 가능.

## 2. 디스크/파일 구조

```
/0GDTEX.PVR          부트 로고 텍스처
/0WINCEOS.BIN        WinCE OS 이미지 (1.37MB)
/RESOURCE/*.CB       게임 리소스 아카이브 (독자 /CAB 포맷)
/RESOURCE/MISSION/*.TAB  리소스 매핑 테이블 (Shift-JIS 텍스트, SWiz 툴 생성)
/RESOURCE/MOVIE/*.AVI    동영상 (Cinepak — ICCVID.DLL 존재)
/RESOURCE/ALIAS.INI  아카이브 별칭 정의 (구조 파악의 열쇠)
/TRF/*.EXE|*.DLL     게임 엔진 모듈 (PE/SH-4, 총 75개)
/WINCE/*.DLL         WinCE 시스템 DLL
```

### .CB 아카이브 (/CAB 컨테이너)

- 청크 구조. **청크 크기는 8바이트 헤더(태그+크기) 제외** 값.
- `"/CAB" u32 | "/FCB" u32 | INFO(엔트리: FILETIME8+크기4+절대오프셋4+인덱스4) | .STR(파일명, cp932)`
- 데이터는 엔트리 오프셋 위치에 `ENC0`(무압축) 또는 `ENC2`(압축, **알고리즘 미해석**) 청크로 저장.
- 파서/추출기: [tools/cab.py](../tools/cab.py), GD-ROM 추출기: [tools/gdfs.py](../tools/gdfs.py)

## 3. 텍스트의 위치 (번역 대상)

| 위치 | 내용 | 분량 | 형식 |
|---|---|---|---|
| `RESOURCE/PLOT.CB` → 48개 `.SMF` | **메인 시나리오 전체** (여름편+겨울편, 8히로인) | **23,030 문자열 / 약 733KB** | `.STR` 테이블, ENC0 무압축, cp932 |
| `RESOURCE/SONG.CB` → 11개 `.smf` | 노래방 가사 | 215 문자열 / 6.6KB | 동일 |
| `PLOT.CB/north01.sym` | 화자명 등 심볼 테이블 (琴梨, 陽子…) | 소량 | `.STR` |
| `TRF/TRFSTRINGS.DLL` .data 선두 | 주인공 기본 이름 (竹下功一) 등 | 극소량 | DLL 내장 |
| `RESOURCE/MISSION/*.TAB` | 리소스 명칭 테이블 (일부 UI 노출 가능성) | 소량 | 평문 SJIS |
| 각종 `.DDS` (CB 내부) | **메뉴/UI가 이미지 텍스트** — MS DDS가 아니라 `CLSS`+`CTRFImage` 직렬화 포맷 | 수백 장 중 텍스트 포함분 | 이미지 편집 필요 |

- SMF `.STR` 형식: `".STR" u32(크기) u32(개수)` + 널 종료 cp932 문자열 나열. **EB(이벤트 바이트코드)와 분리되어 있어** 문자열 교체가 비교적 안전할 것으로 보이나, EB가 문자열을 인덱스로 참조하는지 바이트 오프셋으로 참조하는지 **검증 필요**.
- `&主人公名前&` 같은 치환 태그 존재 → 태그 보존 규칙 필요.

## 4. 폰트 (한글화 최대 관건 — 해결 전망 밝음)

- `TRF/TRFSTRINGS.DLL`의 `.data` 섹션(1.1MB)에 **24×24 1bpp 비트맵 폰트 전체 내장**: 섹션+0x400부터 72바이트/글리프 × **15,978 슬롯** (ASCII, 가나, 그리스/키릴, JIS X 0208 한자 전체).
- 렌더러는 `TRF/TRFFONT.DLL`(`CTRFFont`/`CTRFFontTex`), 문자코드→글리프 매핑 로직 RE 필요.
- **전략**: 사용 빈도 낮은 한자 영역 글리프를 한글 2,350자(KS X 1001 완성형)로 교체하고, 번역 텍스트를 해당 SJIS 코드로 인코딩하는 코드페이지 매핑 방식. 비트맵 24×24 한글 폰트(예: 둥근모꼴 계열) 렌더링해 삽입.
- 이름 입력 화면(`TRFNAMEIN.DLL`, `TANKANJI.DLL` 한자 변환)은 별도 대응 필요.

## 5. 리빌드 경로

1. track03.bin 내 파일들은 ISO9660 표준 배치 → 크기가 변하는 파일은 **디스크 리빌드** 필요. GDI 재생성 도구(예: 자체 스크립트로 섹터 재조립) 작성 가능. 파일 크기를 늘리면 LBA 재배치 필요 → 디렉토리 레코드/`.TAB`은 이름 기반이라 LBA 하드코딩 여부는 확인 필요.
2. `ENC2` 압축 미해석 상태 — 두 가지 우회로:
   - 로더가 태그로 분기한다면 **ENC2 파일을 ENC0(무압축)으로 재포장** (크기 증가 감수). 검증 필요.
   - 또는 `KITAMAIN.EXE`/`TRFKERNEL.DLL`의 SH-4 코드에서 ENC2 디코더 RE.
3. 에뮬레이터(redream) 테스트는 GDI 직접 로드로 가능. 실기 테스트는 GDEMU 등.

## 6. 남은 조사 과제 (우선순위순)

1. ~~**EB↔SMF 참조 방식 확인**~~ → **해결 (2026-08-05)**: EB는 바이트 오프셋을 저장하지 않음.
   문자열 개수·순서만 유지하면 **길이 자유 변경 가능**. 상세: [EB-FORMAT.md](EB-FORMAT.md)
2. ~~**ENC2 압축 해석**~~ → **해결 (2026-08-05)**: 12비트 절대위치 + 4비트 길이 LZSS.
   디스크 전체 3,442개 엔트리 복원 성공, 압축기도 구현. 상세: [ENC2-FORMAT.md](ENC2-FORMAT.md)
3. **폰트 코드→글리프 매핑 RE** (TRFFONT.DLL / TRFSTRINGS.DLL 익스포트 분석).
4. 반각(12×24 추정) 글리프 영역 구조 확인.
5. `CTRFImage` DDS 파싱 → 메뉴 이미지 텍스트 목록화.
6. SCV(장면 스크립트, `CLSS` 직렬화) 내 텍스트 유무 확인 (대부분 ENC2라 2번 선행 필요).
7. 한 글자 폭 전제 UI(문자 수 기반 개행 등) 검증.

## 7. 등장 캐릭터 (ALIAS.INI 기준)

春野琴梨(HK) · 川原鮎(KA) · ターニャ(TL) · 桜町由子(SY) · 椎名薫(SK) · 左京葉野香(SH) · 里中梢(KZ) · 愛田めぐみ(AM), 여름편(n)/겨울편(f) × 통상/특수(S-) 시나리오.
