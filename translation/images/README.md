# translation/images — 이미지 내 텍스트 번역 (jp→ko)

게임 이미지에 **구워진 일본어 텍스트**의 한국어 번역 테이블. 이미지 레터링
(OCR·지우기·렌더·주입)은 외주(`F:\dev-furaiki3\type-lettering`의 **jaguk** +
codex)가 맡고, **여기 있는 JSON은 그 파이프라인의 `terms`(용어표)로 참조**된다.

## 흐름 (역할 분담)

```
[jaguk/codex]  originals/ ← kitahe 이미지 덤프(dump/images/)
               jaguk extract  → OCR 로 각 상자의 jp 씨앗을 data/lettering.json 에
                                                     ↓ jp 목록 전달
[Claude]       이 폴더의 *.json 에 jp→ko 번역 (오독은 원본 이미지 보고 교정)
                                                     ↓ terms 참조
[jaguk/codex]  jaguk erase → inject  → injected/   (ko 를 상자에 렌더)
```

- 번역 방식: **jaguk 의 OCR jp 씨앗을 받아** 번역한다(옵션 1). OCR 오독은
  원본 이미지를 직접 보고 교정한다.
- 최종 목표: **우선 번역/텍스트만.** 게임 재주입은 별개(furaiki3 쪽 raiki 또는
  kitae 이미지 빌드 파이프라인은 나중에).

## 파일 형식

type-lettering `terms` 가 자동 인식하는 형식 중 하나를 쓴다(README of type-lettering 참고):

- **평면 맵** — 같은 원문이 여러 곳에 반복될 때(정석):
  ```json
  { "クイズまるごと北海道": "퀴즈 통째로 홋카이도", "結果発表": "결과 발표" }
  ```
- **레코드 목록**(이름·지명 등, 상태 표시 필요 시) — spot.json 꼴:
  ```json
  { "names": [ { "ja": "宗谷岬", "ko": "소야곶", "status": "ok" } ] }
  ```

파일은 카테고리/아카이브별로 나눈다 (예: `quiz_ko.json`, `menu_ko.json`,
`minigame_ko.json`). type-lettering 원장에서:
```json
"terms": ["../../kitae-l10n/translation/images/quiz_ko.json"]
```
처럼 참조 (경로는 jaguk 프로젝트 위치에 맞춰 조정).

## 번역 규칙 (kitahe 공통)

- **전각**(full-width) 원칙은 대사창 타이밍 규칙이라, 이미지 텍스트엔 강제 아님 —
  레터링은 자유 렌더라 반각/자간을 jaguk 스타일이 정한다.
- 고유명사 **음차**·표기는 대사 번역과 일치시킨다(코토리·아유·소야곶 등).
  글로서리: `translation/glossary.json`, 캐릭터: `docs/CHARACTERS.md`.
- 퀴즈 정답 등 "발음 맞히기"류는 대사 쪽 규칙을 따른다(한자 답을 음차로).
