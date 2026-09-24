# 가변폭(프로포셔널) — 확정 사항

구현은 `kitae/build/vwstub.py`(훅·스텁·폭표), `kitae/build/widths.py`(폭의 단일 소스), `kitae/build/runner.py`(모듈별 적용).
옵션은 `kitae.config.json` 의 `font_variable`(true = 정식 rec.x2 방식) · `vw_txout`(HOOK5/6) · `vw_menu`(HOOK7 계열) ·
`vw_extension`(>25자 확장, 접음, 기본 false) · `vw_diag`(진단 링, flycast 전용, `vw_menu` 와 동시 불가).
라이브 조사 환경은 `tools/lualink.py` + Flycast `flycast.lua`(메모리 읽기·입력만; 코드 인젝션은 리셋을 낸다).

## 얻는 것

한 줄 25글자 상한은 **레코드 수 제한**이라 폭과 무관하다(줄당 아틀라스 128×128 = 5×5칸). 가변폭으로 얻는 건
미관뿐이다 — 한글 음절은 전부 24 라 한 픽셀도 안 줄고, 공백(9)·EN(12)·문장부호·라틴·숫자에서 차이가 난다.

## 폭의 단일 소스 — `widths.py`

- 한글 24, 어절 공백 9, EN 12, EM 24, U+2004 8, U+2005 6, 숫자 고정폭(advance+1), ASCII 는 IBM Plex 의 advance(`/` 는 12),
  `・` 22(가운데), `／`·`－`·`．` 24(`／`·`－` 가운데, `．` 은 왼쪽 정렬·오른쪽 여백), 합자는 구성 글자 합, 게임 자체
  글리프(전각 기호 등) 24.
- 글리프는 **펜 원점(왼쪽) 정렬**로 굽는다. 잉크가 폭을 넘는 셀은 `(`·`)` 1px 뿐.
- 폭표(`build_table`) = 페이지맵 256B(0x80|폭 직접값 또는 하위표 번호) + 하위표 256B×2 = 768B. 하위표 두 장은
  **공백이 든 페이지와 전각 숫자·라틴 페이지**에 준다(URL 용 ASCII 페이지에 주면 공백이 대표값으로 뭉개진다).
  1바이트 ASCII(보호 항목)는 12, 전각 공백 0x8140 은 12.

## 엔진 구조(확정)

글자 엔진은 **TRFSTRINGS.DLL** 이다. 모든 DLL 이 ImageBase 0x10000000 이라 주소만으로 모듈을 못 가른다.

| 클래스 | 역할 | 핵심 주소 |
|---|---|---|
| CTRFMessage (vt 0x1000d3c4) | 대사·안내문·본편 선택지(EB 0x73/0x74) | SetText 레코드 빌드 0x100038D0, 그리기 0x100034FC |
| CTRFMsgput (vt 0x1000d48c) | CTRFMessage 파생. +40 비트1 = **표면 모드**(한 번 굽고 캐시) | vt[27]=0x10002e80 줄 목록(표면·글자수·크기) |
| CTRFTXOut → 내부 CTRFTextOut (vt 0x1001c9c8) | UI 텍스트 12모듈(타이틀 VMS 안내·가이드북 도시 설명·옵션·저장 안내·스탭롤 첫 20줄 …) | vt[3]=0x1000970c 토크나이즈(≤25코드)+사설 SquareStr 굽기+사각형 복사, vt[5]=0x10009bec 그리기 |
| CTRFCharout (TRFNCHAR.DLL) | 스탭롤 스크롤 재사용 줄 | 항목 {x,y,w,h}, w=24 상수 0x100016fe |
| CTRFSquareStr (vt 0x1000dd3c/+4 0x1000dd9c) | 문자열 아틀라스 128×128, 한 행 5칸×24, 행 높이 24, 최대 25글자 | SetString 0x100076cc(노드 리스트 this+0x260), 굽기 vt[4]=0x10007c64, 사각형 배열 this+132(16B {x1,y1,x2,y2}) |
| CTRFFont (vt 0x1000de9c 단독 / 0x1000de60 집합) | 글리프 비트맵 | vt[13]=DrawChar(code, rect) 0x10008bac → @(12,font) vt[5] 블릿 |
| CGeneralMenu (MENUSELECT.DLL, vt 0x1000a16c) | 메뉴 팝업(미니게임 선택 등) | 팝업 빌더 vt[8]=0x10001678 |

- **코드의 원천은 토크나이저 노드 리스트** `*(*r9)+0x6C`(r9 = &글꼴 전역 0x1001D16C): 노드 +0 next · +8 code
  (lead<<8|trail, 반각은 바이트) · +12 len(2/1/0). 이름 토큰(`&主人公名前&`) 등 치환문도 같은 리스트에 emit 된다.
  대사 obj 의 `+0x1FFC` 는 코드 배열이 아니라 공유 표다.
- 대사 레코드 `rec = obj+84 + 글자×128(원본 320, 0x10003542 패치) + 줄×16` = 아틀라스 소스 사각형. 줄마다 아틀라스
  한 장이라 >25자 확장은 접었다(`vw_extension`).
- **DrawRect(ctx vt[13])(rect, w, h) = 소스 사각형을 화면 w×h 로 늘려 그린다.** 상자는 끝 포함(`x2 = x1+폭−1`).
  대사 경로는 엔진이 w=h=줄 크기(24)를 넘긴다(원본 전각뿐이라 숨어 있던 규약).
- **굽기 블릿은 24·12 폭 사각형만 제대로 굽는다** — 폭 16·8 사각형을 주면 비트가 밀린 잡음이 된다.
- 반각(1바이트) 글리프는 아틀라스 칸의 왼쪽 12px 에만 그려지고 오른쪽 12px 은 이전 찌꺼기가 남는다.
- **메뉴 팝업**: CTRFMsgput 표면 모드 → 사설 SquareStr 아틀라스 → `$MSGsurface$` 표면 → MENUSELECT 빌더가
  **아틀라스 한 행(24px) = 화면 120px 타일**로 이어 붙인다(u 0..120/128, v = 행×24/128, 단위 k=0x3907BAC1/px,
  마지막 타일 pad 다듬기). 폭표는 어디서도 안 읽는다. 전처리기 0x10001b6c 는 ASCII 공백·탭을 제거한다.
- CTRFTXOut 을 만드는 모듈: ITEMMENU, KITACMDMENU, KITATITLE, SOUNDROOM, TRFFRUITION, TRFGUIDEMAP, TRFOPTIONGAME,
  TRFROLL, TRFSCENELAUNCH, TRFSYSCONFIG, TRFVMSVIEW. 구현·등록은 TRFSTRINGS 하나뿐.

## 훅 목록

| 훅 | 자리 | 하는 일 | 옵션 |
|---|---|---|---|
| HOOK2 `stub_rec_x2` | 0x10003AE6 (copy 루프) | 노드 리스트를 순서대로 읽어 `rec.x2 = 폭표 폭 \| len<<16`. 게임의 x2 쓰기 0x10003b12 는 nop | font_variable |
| HOOK3 `stub_drawchar1` | 0x10003582 (그림자 DrawChar) | rec.x2 → `x1 + 상자−1` 로 스왑, 실린 값을 스크래치에 보관, DrawChar 재발행. 상자 = 12×len−1, `vw_menu` 면 폭−1 + **그리기 폭 r6 = 폭** | font_variable |
| HOOK8 | 0x100035A6 (본체 DrawChar) | HOOK3 징검다리로 같은 스텁. PR 하위 16비트(0x358E/0x35B2)로 호출 구분, 스크래치의 폭만 꺼내 r6 | vw_menu |
| HOOK `stub_advance` | 0x100035B4 (전진폭) | rec.x2 를 스크래치 값 그대로 복원, 전진폭 = `값 & 0xFF` + 자간 | font_variable |
| HOOK5 `stub_txout_advance` | 0x10009CE2 (TextOut 전진) | r8==24 면 r11−2/−1 로 코드 되읽어 폭표 조회 → **전진폭**. vw_menu 여도 함께 건다 | vw_txout |
| HOOK5b `stub_txout_rect` | 0x10009C90 (TextOut 사각형 찾기) | 헬퍼 0x10009d1c 호출 뒤 **r8 = 사각형 폭** → **그리기 폭**만. 못 찾으면 0x10009ce2 로 jmp | vw_menu (HOOK5 와 함께) |
| HOOK6 `stub_nchar_width` | TRFNCHAR 0x100016F2 | 항목 w = 폭표(문자열 객체 +38 u16 배열, 색인 @r13−1). 폭표는 폰트 vtable(0x1000de9c/0x1000de60) 거리 | vw_txout |
| HOOK7a `stub_atlas_pack` | 0x10007D6E (아틀라스 굽기) | x1 = 운영 x(@(0,r15)), 폭(@(4,r15)) = 폭표/12. **굽기 사각형은 엔진 24/12 유지**. 행 첫 글자 = rect[i−1].y1≠y1. 스텁은 .pdata 꼬리 | vw_menu |
| HOOK7c `stub_atlas_x2` | 0x10007DA4 (사각형 저장 직전) | x2 = x1+폭−1 → 사각형 배열이 진짜 폭(대사 rec·TextOut 복사 모두 받음). 스텁은 .rdata 꼬리 | vw_menu |
| HOOK7b `stub_menu_tiles` | MENUSELECT 0x100019AA (타일 루프) | 타일 폭·u1·@(48,r15) = 행 t 글자 폭 합(항목 사본 CTRFMenu+152+i*4 를 폭표로, 0x20/0x09 건너뜀) × k × 배율 | vw_menu |
| W 훅 (같은 스텁) | MENUSELECT 0x10001858 | W(선택 막대·정렬 폭) = 글자 폭 합. PR 하위 16비트(0x185E/0x19B0)로 모드, r12 = 모드 | vw_menu |
| pad 끔 | MENUSELECT 0x100018BA/BC | `mov #0,r10` / nop — 마지막 타일 다듬기 제거 | vw_menu |

MENUSELECT 의 FP 는 게임 썽크(itof 0x10005d84·fadd 0x10005f38·fmul 0x10006140)를 mova 거리 리터럴로 부른다 —
거리는 **더하는 r0 의 값 기준**(ITOF 는 +8, FADD/FMUL 은 +12 리터럴 주소). 폭표는 CTRFMenu vtable(0x1000d82c)
거리(vt[3]=SetItems 로 검증, 아니면 24).

## 배치와 제약

- 절대주소는 하나도 없다: PC 상대(mova)·거리 리터럴·vtable 거리만 쓴다 → 재배치 불필요.
- **TRFSTRINGS `.ktrw`**(RWX, 새 섹션, `.reloc` 앞): adv 24 + dc1 68 + 스크래치 4 + cpy 900(코드 132 + 표 768) ≤ 1,024B.
  디스크 익스텐트 여유가 1,024B 뿐이라 못 키운다. **스크래치는 모듈 메모리**여야 한다(물리 RAM 0x8CFE0100 은 redream
  크래시).
- **스텁 자리**(TRFSTRINGS). SH4 MMU 는 실행 비트가 없어 어느 섹션이든 읽기 = 실행이다.
  `hook16`(mov.l/bsrf, 32비트 거리)은 어디든 닿고, `hook_code`(12B, bsrf 16비트 거리)는 64KB 안만 닿는다.

  | 꼬리 | 크기 | 들어간 것 |
  |---|---|---|
  | `.text` 0x1000c31c~0x1000c400 | 228B | 징검다리 3개 36 + HOOK5b 60 + HOOK5 92 (40B 남음) |
  | `.pdata` | 322B | HOOK7a 96 + 조사 훅 80 |
  | `.rdata` | 62B | HOOK7c 32 |

  `.text` 가 좁아 HOOK7a 를 `.pdata` 로 옮겼다(9/24). `vw_diag` 의 DrawChar 진단 스텁은 `.text` 꼬리를
  쓰므로 `vw_menu` 와 함께 못 켠다.
- TRFNCHAR `.text` 꼬리(0x10002878, 132B)·MENUSELECT `.text` 꼬리(0x10009a48, 332B/440B).
- 훅 코드는 **r0 을 쓴다** — 스텁이 원래 r0 을 쓰려면 다시 구한다.
- 진단 모드(`font_variable` 값): `flat`(무조건 22)·`len`·`page40`·`swap40`·`ruler6/4/2/0`·`low6`·`cp40`·`diag` — 화면으로 가르려면
  값이 두 가지뿐인 질문을 던진다.

## 반복하지 말 것

- 전진폭 훅은 `width | len<<16` 을 **그대로** 복원한다. width 만 되돌리면 다음 프레임 상자폭이 0(글자 실종).
- 1바이트 글자 상자는 12 를 넘기지 말 것(오른쪽 12px 은 찌꺼기). 상자는 끝 포함(`+폭−1`).
- 폭 상자만 주고 그리기 폭(r6)을 안 바꾸면 DrawRect 가 늘려 그린다 — 대사(HOOK3/8)·TextOut(HOOK5b) 둘 다 r6=폭.
- **TextOut 은 그리기 폭과 전진폭을 갈라야 한다.** HOOK5b 만 두면 r8(사각형 폭) 하나가 둘 다 정하는데,
  아틀라스를 HOOK7 이 안 채우는 화면(TRFNAMEIN 이 직접 만드는 CTRFTextOut 6개)에서는 사각형이 24 라
  전진도 24 로 돌아가 고정폭이 된다(9/24 인게임 A/B 확인). 그리기 = 사각형(HOOK5b), 전진 = 폭표(HOOK5).
- 굽기 사각형을 폭으로 줄이면 블릿이 깨진다 — 굽기는 24/12, 저장 직전에 x2 만 고친다(HOOK7c).
- 코드는 노드 리스트에만 있다. `r11` raw 문자열 파싱(이름 토큰 어긋남), `obj+0x1FFC`(공유 표), 그리기 훅에서 노드
  인덱싱(마크업 토큰이 섞여 노드 idx ≠ 글자 idx) — 전부 틀렸다.
- CTRFSquareStr 의 `this+52`(피치 스칼라)·`$N` 토큰·CTRFMenu 측정은 팝업 가변폭과 무관하다(팝업은 아틀라스 행 = 타일).
- HOOK6 의 폰트 vtable 은 0x1000de9c/0x1000de60 이다(0x1000dc10 은 CTRFSquareStr 표 안쪽).
- 라이브 코드 인젝션(훅을 braf 로 poke)은 다이나렉·인터프리터 모두 리셋. 라이브는 읽기·poke 관찰만. 힙 va→phys 는
  청크마다 델타가 다르다(모듈 이미지도 별도).
- `is_fixed` 는 명시 `fixed: false` 가 자동 판정보다 우선 — 엔진 반각 글리프(`?` 는 12px 를 잉크로 꽉 채움) 대신 우리 셀을
  쓰고 싶은 항목에 단다.
- HOOK5 의 코드 소스는 r11−2/−1 되읽기다. `@(24,r15)` 는 코드가 아니다(타이틀 메뉴가 겹친다).

## 인게임 확인 상태

- 대사·안내문(HOOK/2/3): 확인. 이름 토큰(2026-09-17)·퀴즈 머리글/순위표 1바이트(9/19)·이름 확인창(9/20) 확인.
- TextOut(HOOK5b+HOOK5)·타이틀 VMS 안내: 확인(9/22, 9/24). 스탭롤 스크롤 줄(HOOK6): 정적 검증, 인게임 미확인.
- 메뉴 팝업(HOOK7a/7b/7c/8/W): 확인(9/22, flycast) — `게임 시작`·`순위 보기`·로마자·선택 막대 길이·대사창 로마자·
  마침표 정상.
