# 디스크 지도 — 원본 파일에 무엇이 들어 있나

`track03.bin`(ISO9660, BASE_LBA 45000) 안의 **파일 287개 · 898MB** 전부에 대한
목록이다. 번역할 글이 어디에 있는지 **키워드가 나올 때마다 찾지 않으려고** 만들었다.
실제로 가이드북 본문(`SOZ.CB` 안)을 못 찾아 한참 헤맸다.

## 스스로 확인하는 법 — `MISSION/*.TAB`

제작진이 남긴 **자산 점검표**다. 엑셀에서 뽑은 CSV이고 파일마다 설명이 붙어 있다.
새 자산이 궁금하면 코드를 읽기 전에 여기부터 본다.

```
;	その他素材リスト.xls
%Feld 番号 更新 ダミー 完了 check ファイル 説明0 説明1 内容 内容補足 形式
#Mission
1,●,,99/01/03,,soz-001,イントロダクション１,,,大晦日の夜･･,psd
```

`PLOT.TAB` 은 스크립트 번호 ↔ 파일 이름 표라서 특히 쓸모 있다.

```python
from kitae.core.gdfs import GdFs
g = GdFs(cfg.track(3))
lba, size = g.find("/RESOURCE/MISSION/SOZ.TAB")
print(g.read(lba, size).decode("cp932"))
```

## 번역 대상이 있는 파일

여기 없는 파일에는 화면에 나오는 글이 없다.

| 파일 | 무엇 | 분량 |
|---|---|---|
| `/RESOURCE/PLOT.CB` | 대사 스크립트 `*.SMF` 48개 + 바이트코드 `*.EB` | **23,030줄** |
| `/RESOURCE/SOZ.CB` | 가이드북 본문 `guide*.msl` | **2,037줄** |
| `/RESOURCE/SOZ.CB` | 극중 소설 『激突！！』 `gekitotu.msl` | 194줄 |
| `/RESOURCE/SCN/INIS.CB` | 씬 제목 `P##.INI` (날짜·시간대·장소) | 49개 |
| `/RESOURCE/MTG.CB` | 대사 타이밍 `*.SET` — 글자 수가 바뀌면 같이 고쳐야 한다 | — |
| `/TRF/*.DLL` | 시스템 UI 문자열 (PE 안에 cp932 로 박혀 있다) | 26개 모듈 |
| `/RESOURCE/PLOT.CB::north01.sym` | 심볼 이름 623개 — **번역하면 안 된다** | — |

가이드북 본문의 구조는 [MSL 형식](../kitae/build/msl.py), 대사는
[SMF 형식](../kitae/build/smf.py), UI 는 [UI-TEXT.md](UI-TEXT.md) 를 본다.

### 가이드북이 `SOZ.CB` 에 있는 이유

`SOZ` 는 **その他素材**(기타 소재)의 약자다(`SOZ.TAB` 머리말). `TRFGUIDEMAP.DLL`
에는 지명 210개만 있고 설명문은 한 줄도 없다 — 지명만 보고 "가이드북은 다
번역했다"고 판단하면 틀린다.

| 멤버 | 줄 | 창 | 내용 |
|---|---|---|---|
| `guide.msl` | 387 | 147 | 관광지 설명 |
| `guide2.msl` | 522 | 201 | 관광지 설명 |
| `guide3.msl` | 112 | 44 | 도시 설명 (지도 화면에서 Ａ) |
| `guide4.msl` | 57 | 24 | 협력 (스폰서 소개 + 홈페이지 주소) |
| `guides.msl` | 959 | 368 | 관광지 설명 (계절 변형) |

## 아카이브 이름 규칙

`/CAB` 아카이브의 이름은 **`[S]코드[N|F]`** 로 읽는다.

- 뒤의 **`N`=夏(여름편)**, **`F`=冬(겨울편)**. 같은 캐릭터가 두 벌씩 있다.
- 앞의 **`S`= 特殊絵**(특수 컷). `SHKN` 은 `S`+`HK`+`N` 이다.
- 가운데가 캐릭터 코드다. **이름의 로마자 머리글자**에서 왔다.

| 코드 | 캐릭터 | 아카이브 |
|---|---|---|
| `HK` | 春野琴梨 (하루노 코토리) | `HKN/HKF` · 특수 `SHKN/SHKF` |
| `KA` | 川原鮎 (카와하라 아유) | `KAN/KAF` · 특수 `SKAN/SKAF` |
| `SH` | 左京葉野香 (사쿄 하노카) | `SHN/SHF` · 특수 `SSHN/SSHF` |
| `KZ` | 里中梢 (사토나카 코즈에) | `KZN/KZF` · 특수 `SKZN/SKZF` |
| `SK` | 椎名薫 (시이나 카오루) | `SKN/SKF` · 특수 `SSKN/SSKF` |
| `SY` | 桜町由子 (사쿠라마치 유코) | `SYN/SYF` · 특수 `SSYN/SSYF` |
| `TL` | ターニャ・リピンスキー (타냐) | `TLN/TLF` · 특수 `STLN/STLF` |
| `AM` | 愛田めぐみ (아이다 메구미) | `AMN/AMF` · 특수 `SAMN/SAMF` |
| `SC` | サブキャラ (조연 — 春野陽子 등) | `SC.CB` |
| `BG` | 背景 (배경) | `BGN` 97MB · `BGF` 53MB |

`FSN.TAB` 은 藤崎栞 인데 짝이 되는 `.CB` 가 없다 — 쓰이지 않은 자산이다.

## 디렉터리별

### `/RESOURCE` — 게임 데이터

| 파일 | 크기 | 내용 |
|---|---|---|
| `PLOT.CB` | 1.3MB | 대사·바이트코드·심볼 (99멤버) |
| `SOZ.CB` | 6.6MB | 기타 소재 — **가이드북 본문**·연출 컷 (274멤버) |
| `MTG.CB` | 551KB | 대사 타이밍 |
| `BGN/BGF.CB` | 97+53MB | 배경 그림 |
| 캐릭터 `.CB` 16개 | 2.4~10MB | 입 모양·표정별 컷 (`.SET` + `.dds`) |
| `MAIN.CB` | 392KB | 이름 입력 화면 글자판 |
| `MENU.CB` · `CI.CB` · `DEBUG.CB` | 작음 | 메뉴 부품·오리 커서·디버그 |
| `M.CB` | 3MB | MIDI 159곡 + 내장음원 파형 |
| `MP4/6/7/9/10.CB` | 0.1~18MB | 미니게임 그림 |
| `SONG.CB` | 56MB | 카라오케 음원 |
| `WAV/0~9.CB` | 각 ~35MB | 음성 (`aNNNN.p04`, ADPCM 18000Hz) |
| `A/P04.CB` · `SE/P04.CB` | 35+3.5MB | 환경음·효과음 (22050Hz) |
| `SC.CB` | 5.6MB | 조연 컷 |
| `SCN/INIS.CB` | 144KB | **씬 제목** — 날짜·시간대·장소 |
| `SCN/PLOTS.CB` | 16KB | 플롯 정의 |
| `SCN/SCV.CB` | 1.4MB | 씬별 자원 목록 (그림만, 글 없음) |
| `MISSION/*.TAB` | 각 2~26KB | **제작진 자산 점검표** (위 참고) |
| `MENU/*.TMD/.MOT/.3DP` | | 지도·ＰＨＳ 3D 모델 |
| `MOVIE/*.AVI` | 9~80MB | TrueMotion2 동영상 6편 |
| `ALIAS.INI` | 1.4KB | 자원 별칭 |

### `/TRF` — 엔진 모듈 (WinCE SH-4 PE, image base 0x10000000)

글이 든 모듈은 26개다. 나머지(`TRFDRAW*`, `TRF3D`, `TRFCAMERA` …)는 그리기·
입력 담당이라 손대지 않는다. 어느 모듈에 무엇이 있는지는
[UI-TEXT.md](UI-TEXT.md) 에 있다.

미니게임 모듈은 아직 작업대가 없다 — `TRFROLL`(122) · `TRFTECHNOMAZE`(72) ·
`TRFSUNFLOWERMAZE`(68) · `SOUNDROOM`(35) · `TRFMILKING`(27) · `TRFSHOTING`(19) ·
`TRFSCORE`(15) · `TRFQUIZ`(12) · `TRFTENNIS`(10) · `TRFUFO`(5) · `TRFKARAOKE`(4).

### 그 밖

`/0GDTEX.PVR` 로고 · `/0WINCEOS.BIN` WinCE 커널 · `/TRF/*.EXE` 진입점 ·
`/WINCE/*.DLL` 시스템 DLL. 전부 손대지 않는다.

## 새 텍스트를 찾는 절차

지명이나 문구가 화면에 보이는데 어디 있는지 모를 때:

1. **`MISSION/*.TAB`** 을 먼저 읽는다 — 자산 설명이 일본어로 적혀 있다.
2. 디스크를 그대로 훑지 말 것. `.CB` 안은 **압축**(ENC2)이라 안 걸린다.
   반드시 CAB 멤버를 풀어서 찾는다.
3. 그래도 없으면 `/TRF/*.DLL` 을 cp932 로 훑는다 — PE 안에 박힌 UI 문자열이다.

```python
# 압축까지 풀어서 찾는 예 — 이 방법으로 guide*.msl 을 찾았다
for full, lba, size, is_dir in g.walk():
    if is_dir or not full.upper().endswith(".CB"):
        continue
    open(tmp, "wb").write(g.read(lba, size))
    for n in Cab(tmp).names:
        if needle in Cab(tmp).read(n):
            print(full, "::", n)
```
