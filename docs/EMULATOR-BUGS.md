# 에뮬레이터 버그와 우회 패치

이 게임은 SH4 의 MMU 를 쓰는 **Windows CE 타이틀**이며, 개발 과정에서는 Flycast
에뮬레이터로 동작을 확인하였다.

MMU 를 흉내 내려면 메모리 접근마다 주소 변환이 붙어 비용이 크다. 그런데 드림캐스트
게임 다수는 MMU 를 쓰지 않는 Katana SDK 로 만들어졌기에 에뮬레이터들도 이 지원을
뒤로 미뤘고, 그래서 WinCE 타이틀에는 아직 고쳐지지 않은 버그가 남아 있을 수 있다.

여기에는 **원본 디스크를 Flycast 로 돌렸을 때에도 나는 버그**만 적는다. 번역 탓에
생긴 문제나 원작 본래의 동작도 증상은 똑같이 보이므로, 원본에서 먼저 재현해 보고
나서 싣는다. 제한 시간이 있는 선택지(C.B.S)를 에뮬레이터 버그로 오해해 한참 쫓은
적이 있다.

---

## 해결

둘 다 Flycast 쪽 버그였고, 수정을 [badatbit/flycast](https://github.com/badatbit/flycast) 포크에
넣어 [Flycast KitaHe 1](https://github.com/badatbit/flycast/releases/tag/kitahe-1) 로 배포했다(2026-10-04).
분석은 [flyinghead/flycast#1058](https://github.com/flyinghead/flycast/issues/1058) 에 올렸다.
공식 Flycast 에는 아직 들어가지 않았다.

### 오프닝 동영상이 20초 멈춤 — SH4 사이클 계산

**증상.** 오프닝(`RESOURCE/MOVIE/KITAHE.AVI`) 6초쯤에서 그림이 멈추고 음악만 나오다가 26초쯤 돌아온다.

**원인.** Flycast 의 사이클 모델(`Sh4Cycles::countCycles`)이 MMU 를 켠 게임의 메모리 접근에 5사이클
(평소 2)을 매겨 WinCE 코드가 1.7배 느려진다. 동영상 디코더(DXLVFW.DLL)가 프레임당 8.33ms 를 넘기면
QUARTZ 의 AVI 디컴프레서가 "따라잡을 수 없다"고 보고 다음 키프레임까지 프레임을 버리는데, 이 영상은
5.2~26.2초 사이에 키프레임이 없다. 수정 커밋
[`699483f`](https://github.com/badatbit/flycast/commit/699483fae49f59d37bf44c14530a1c762318ee83).

### 가라오케에서 BIOS 로 리셋됨 — FPSCR cause 필드

**증상.** 곡을 고르거나 부르는 중에 **랜덤하게** 드림캐스트 BIOS 화면으로 돌아간다. 원본 디스크에서도 난다.

**원인.** 에뮬레이터가 죽는 것이 아니라 게임의 예외 처리기가 재부팅한다. KITAMAIN.EXE 의 `WinMain` 은
`__try { 게임 } __except { ResetToFirmware(); }` 구조다. 예외는 TRFDRAW.DLL 의 4×4 행렬 LU 분해
(`ludcmp`, +0xc064)에서 나는 접근 위반이다. 피벗 비교 보조함수가 `fcmp/gt` 뒤 FPSCR 의 cause.V 를
"NaN 비교" 신호로 읽는데, Flycast 는 FPU 명령에서 cause 필드를 지우지 않아 한 번 켜진 V 가 계속 남는다.
그러면 모든 비교가 거짓이 되어 피벗이 안 골라지고, 초기화되지 않은 피벗 번호가 엉뚱한 주소를
가리킨다. 그 번호가 스택에 남은 우연한 값이라 리셋이 랜덤해 보인다. 수정 커밋
[`c148add`](https://github.com/badatbit/flycast/commit/c148add68329ce1bfe7401edcf9364719c254296).

### 참고 — SH4 오버클럭과 사운드 멈춤

SH4 가 사운드 CPU(ARM7)보다 지나치게 빨라지면 게임이 멈춘 적이 있다. 프롤로그
「あっ！もうこんな時間！」 뒤 암전에서 음성이 반복되며 더 진행되지 않는다. 확인한 조합은 둘이다.

| Flycast | `Sh4Clock` | 결과 |
|---|---|---|
| 동영상 패치(사이클 수정) 적용 | 300 MHz | 멈춤 (2번 중 2번) |
| 순정(패치 없음) | 500 MHz | 멈춤 |
| 동영상 패치 적용 | 200 MHz (기본) | 정상 |
| 순정 | 300 MHz | 정상 |

동영상 패치는 WinCE 코드를 약 1.7배 빠르게 돌리므로, 패치 + 300 MHz 는 순정 + 500 MHz 와 비슷한
속도가 된다. 멈춘 동안 SH4 쪽 DSOUND.DLL 은 음성 버퍼가 멈췄다는 보고를 기다리고, ARM7 사운드
드라이버는 살아 있지만 SH4 로 인터럽트를 보내지 않는다 — 둘 사이가 어긋난 교착이다.
**SH4 클럭은 기본값(200 MHz)으로 둔다.**

## 미해결

없음.

---

## 에뮬레이터 설정

디스크는 `대응 지역 J` 다. 큰 영향은 없을지도 모르지만, 원인 모를 증상을 쫓기 전에
에뮬레이터 설정을 아래와 맞춰 두기를 권한다.

| | 맞춰야 할 값 |
|---|---|
| 지역 | Japan |
| 언어 | Japanese |
| BIOS | 실기 `dc_boot.bin` (HLE 아님) |
| Flycast `aica.DSPEnabled` | `yes` |
| Flycast `Dynarec.Enabled` | `yes` (기본) |
| Flycast `Sh4Clock` | `200` MHz (기본 — 올리면 사운드가 멈출 수 있음) |
| redream `frameskip` | 끔 |
