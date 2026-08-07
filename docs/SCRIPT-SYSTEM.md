# 스크립트 시스템 분석 (EDL / Plot / Scene)

분석일: 2026-08-05 · 선행 문서: [ANALYSIS.md](ANALYSIS.md), [EB-FORMAT.md](EB-FORMAT.md)

## 1. 저작 파이프라인 (개발 당시)

Hudson 내제 툴 **SWiz V1.05**로 시나리오 프로젝트 `north01.spf`를 컴파일:

```
north01.spf (SWiz 프로젝트)
 ├─→ *.SMF   대사 문자열 테이블 (.STR)          — 파일 ID 0~44
 ├─→ *.EB    이벤트 바이트코드 = "EDL" 컴파일 산물 — 파일 ID 0~44 (SMF와 1:1)
 ├─→ north01.sym  심볼 테이블 (화자명 89종 등)
 └─→ north01.msd  음성 번호 공간 매핑 (9그룹 분할)
```

- 파일 ID 매핑 근거: `RESOURCE/MISSION/PLOT.TAB`의 `#SMF`/`#EDLP` 섹션 (0=hanyou,
  1~6=kotori, 7~9=ayu, … 42=game, 43=風呂, 44=歌詞).
- "EDL"이라는 이름은 KITAE.DLL/SCENE0.EXE .data의 리소스명 문자열로 확인.

## 2. 런타임 아키텍처 (모듈별 역할)

| 모듈 | 클래스 (RTTI 확인) | 역할 |
|---|---|---|
| KITAE.DLL | **CKitaEvent**, IKitaTrap2/Core/TimeAction/Location/Telephone | **EDL(EB) 인터프리터**. north01.sym/msd 로드. 시간대(午前/午後/夕方/夜)·날짜 표시 문자열 보유 |
| SCENE0.EXE | (호스트) | 장면 프로세스. "EDL"·"KitaEvent"·"VSC"·"Pad"·"CLIP" 리소스 연결 |
| TRFPLOTMANAGER.DLL | CTRFPlotManager | PLOT.CB 로드 — 그룹 "EDLS"/"SMFS"/"GEL.SET" + **MTG.CB**(.set/.wst) |
| TRFSCENELAUNCH.DLL | CTRFSceneLaunch | `SCN/Plots.Ini`(=INIS.CB), `Plots.scn`, P##.INI/scn으로 장면 기동 |
| MESSAGEOUT.DLL | CTRFMsgput | 메시지 출력 |
| TRFMSGTIMING.DLL | CTRFMsgTiming, ITRFStrTimingImport | 음성 동기 문자 타이밍 |
| TRFSTRINGS.DLL | CTRFResourceMessage?/폰트 데이터 | .STR 리소스 + 내장 비트맵 폰트 |

엔진은 COM 스타일(TRFDllGetClassObject)이라 익스포트명 없음 — 클래스명은 .rdata의
인터페이스 이름 테이블(0x100 간격 배치)에서 확인.

## 3. 시나리오 계층 구조

```
Plot (P00~P47, 49개)               ← PLOTS.CB/P##.scn + INIS.CB/P##.INI
 └─ Scene (P##S###, 총 1104개)      ← SCV.CB/P##S###.SCV
     └─ Event (P##S###E##)          ← INI에 이름 정의, EB 바이트코드가 구현
```

- 예: `P06.INI` → `[P06]` 섹션에 장면 목록(제목 포함), `[P06S001]`에 이벤트
  `P06S001E00=＠プレゼント処理` 식으로 정의.
- P06은 개발용 테스트 플롯(동시발음/인터럽트 테스트 등 제목이 남아있음).

## 4. SCV = CLSS 직렬화 포맷 (해독 완료)

```
"CLSS" u32 rootname_len, rootname("CTRFVisualScene")
반복: FF FF FF FF | u32 obj_id | u16 classname_len | classname | u32 payload_len | payload
```

등장 클래스: CTRFResourceList, CTRFDataSet(키="NAME" 등), CTRFCutScheduler,
CTRFCutResource, CTRFMasterResource, **ElmScript**(장면 내 컷 스크립트, 바이너리).
MTG의 WST도 같은 포맷: `CTRFDataSet` 루트 아래 `CTRFWaveName` 객체 나열
(예: CF23.WST = "s2001.wav", "s2002.wav"…) — **문자열 인덱스 순 음성 파일 목록**.

## 5. 음성 시스템

- 음성 파일: `RESOURCE/WAV/0~9.CB`의 `aNNNN.p04`, **5,716개** (a0013~a9629),
  천 단위 블록별로 CB 분할 (0.CB=a0xxx, 1.CB=a1xxx, …).
- `north01.msd`: 음성 번호 공간을 9그룹으로 연속 분할하는 테이블
  (0~3849 / 3850~5022 / … / 8658~9264; 뒤 2그룹은 예약에 가까움) + 부속 데이터.
- 대사↔음성 매핑: **MTG.CB**의 스크립트 파일별 `.WST`(CTRFWaveName 목록)가 담당.
  `.SET`은 글자별 표시 시각(밀리초)과 입 모양을 담은 CTRFMsgTiming — → [MTG-TIMING.md](MTG-TIMING.md)
- 음성은 18000Hz Yamaha ADPCM (효과음만 22050Hz).

## 6. EB 내부 구조 (추가 해독)

- 헤더(12B) 뒤: 장면별 블록. 각 블록에 `(id u16, EB내부오프셋 u16)` 점프 테이블 —
  **id는 장면마다 0x20부터 재시작**(메시지/이벤트 슬롯), 0xE8~0xEC는 고정 핸들러 5종.
- 22바이트 고정 레코드 배열 발견 (KOTORI_01: 0x0A98~0x0F22 = 정확히 53개).
  필드에 2의 거듭제곱(1,1,2,2,4,4,8…) 마스크 + 짝 값 — 플래그 분기/선택지 테이블 추정.
- 옵코드 의미 확정은 CKitaEvent(KITAE.DLL .text, SH-4) 디스어셈블 필요.
  capstone 5.0.7(SH4 지원) 사용 가능 확인됨.

## 7. 번역 관점 요약

- **분절 단위**: SMF 문자열 1개 = 화면 1줄. 창 단위 묶음/화자/음성은 EB·MTG가 결정.
- **화자 표시**: north01.sym의 89개 심볼 중 하나를 EB가 지정(추정) — 심볼만 번역하면 전 대사 적용.
- **선택지**: EB 내 분기 레코드(§6)로 표현 — 해당 문자열이 어떤 것인지는 옵코드 해석 후 확정.
- ~~**최대 병목 = ENC2 압축**~~ → **해소 (2026-08-05)**: ENC2 = `CTRFLzss` 해독 완료,
  INIS/SCV/MTG 전량 판독 가능. 상세: [ENC2-FORMAT.md](ENC2-FORMAT.md).
  이제 §6의 EB 옵코드 해석과 화자·선택지·음성 매핑 자동 추출이 다음 과제.
