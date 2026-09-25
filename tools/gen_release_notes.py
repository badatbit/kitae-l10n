# -*- coding: utf-8 -*-
"""릴리즈 노트를 만든다 — GitHub 용 마크다운과, 설치 프로그램에 넣을 평문.

    python tools/gen_release_notes.py --text     # dist/릴리즈 노트.txt (설치 프로그램용)
    python tools/gen_release_notes.py            # dist/release/RELEASE-NOTES.md (GitHub 용)

**순서가 있다.** 평문판은 `make_installer.py` 가 설치 프로그램에 집어넣으므로 **그 앞에**,
마크다운판은 세 에셋(.exe 포함)의 sha256 을 적으므로 **그 뒤에** 돌린다.

    make_release.py → gen_release_notes.py --text → make_installer.py → gen_release_notes.py

평문판에 sha256 표가 없는 것은 그래서다 — 설치 프로그램 자신의 해시를 자기 안에 적을 수
없다(적는 순간 해시가 바뀐다). 대신 릴리즈 페이지 주소를 남긴다.
"""
import argparse
import glob
import hashlib
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from kitae.config import Config          # noqa: E402

VER = "v0.90"
BASE = "kitae_white_illumination_ko"

BODY = """## 북으로. White Illumination 한국어 패치 {ver}

드림캐스트 『北へ。White Illumination』(1999, HUDSON) 의 비공식 한국어 패치입니다.
본편 대사부터 가이드북·퀴즈·지도 라벨까지 옮겼고, 이름 입력 화면에서 **한글을 직접 칠 수 있습니다.**

> 원본 디스크 이미지가 있어야 합니다. 이 패치에는 게임 파일이 들어 있지 않습니다.
> 본인이 소유한 디스크의 덤프에만 쓰세요.

---

### 받을 파일

셋 중 **하나만** 받으면 됩니다. 세 파일의 내용은 같습니다.

| 파일 | 크기 | 쓰는 법 |
|---|---|---|
| **`{exe}`** | {exe_mb} | **권장.** 윈도용. 원본 폴더와 저장할 폴더만 고르면 끝입니다. |
| `{xd}` | {xd_mb} | 데이터 트랙 하나에 직접 적용하는 차분. 윈도 밖에서도 됩니다. |
| `{dcp}` | {dcp_mb} | [Universal Dreamcast Patcher](https://github.com/DerekPascarella/UniversalDreamcastPatcher) 용. |

**GDI 와 Redump CUE/BIN 둘 다 됩니다.** 컨테이너 규약만 다를 뿐 데이터 트랙은 같은 파일입니다
(GDI 는 `track03.bin`, CUE/BIN 은 `… (Track 3).bin`). 설치 프로그램은 이름이 아니라 크기로 찾습니다.

<details>
<summary>xdelta 를 직접 쓸 때</summary>

```
xdelta3 -d -s "<원본 데이터 트랙>" "{xd}" "<새 파일>"
```
만들어진 파일을 원래 데이터 트랙 이름으로 바꿔 넣으세요. 나머지 트랙과 `.gdi`/`.cue` 는 그대로 둡니다.
원본 데이터 트랙이 아래와 **바이트까지 같아야** 적용됩니다.

```
크기   {src_size} 바이트
sha256 {src_sha}
```
</details>

---

### 이 판에 들어간 것

| 영역 | 분량 |
|---|---|
| 본편 대사 | 22,652줄 |
| 가이드북 본문 | 2,037줄 |
| 극중 소설 『격돌!!』 | 194줄 |
| 퀴즈 | 292문제 |
| 시스템 UI 문자열 | 26모듈 |
| 지도 라벨 이미지 | 510상자 |

그 밖에

- **이름 입력 한글 입력기** — 두벌식으로 칩니다. 겹받침·복모음·도깨비불까지 됩니다.
- **동적 조사** — 이름 받침에 따라 은/는·이/가·을/를·과/와·아/야 를 런타임에 고릅니다.
- **가변폭 글꼴** — 글자마다 폭을 달리해 한 줄에 더 들어갑니다.
- 이름 입력 화면 아이콘(한자·한글·가나·영숫자·결정), 미니게임 이미지, 인트로 텍스트 카드.

### 아직 안 된 것

- 타이틀 로고와 저작권 이미지
- 동영상 자막, 텍스트가 안 나오는 이벤트 장면의 대사
- 노래방 가사 (싱크가 필요해 손대지 않았습니다)
- 커맨드 메뉴의 날짜·시각 한자 조각 (어디서 나오는지 못 찾았습니다)

### 알려진 문제

- **가라오케에서 곡을 고를 때 무작위로 리셋됩니다.** 패치하지 않은 원본 디스크에서도 같은 증상이
  나와 패치 탓인지 에뮬레이터 탓인지 가르지 못했습니다. 이 게임은 SH4 MMU 를 쓰는 Windows CE
  타이틀이라 에뮬레이터 지원이 덜 여문 편입니다. 자세한 내용은 저장소의 `docs/EMULATOR-BUGS.md`.
- **다음 판으로 올리면 세이브에 저장된 이름이 깨질 수 있습니다.** 글꼴 칸 배정이 바뀌면 옛 세이브가
  그 이름을 다른 글자로 읽습니다. 진행도와 플래그는 멀쩡합니다.

### 확인한 환경

Flycast 2.6 에서 만들고 확인했습니다. redream 에서도 돌아갑니다.

### 문의와 새 판

- **문의·버그 신고** — https://github.com/badatbit/kitae-l10n/
- **새 판 받기** — https://github.com/badatbit/kitae-l10n/releases

---

### 권리

원작의 권리는 SEGA Enterprises · HUDSON SOFT · RED / 広井王子事務所 에 있습니다.
이 패치는 권리자와 무관한 비공식 팬 번역입니다. 도구와 문서는 MIT 이고, **번역문과 레터링은
모든 권리를 유보합니다** — 원작의 2차적저작물이라 자유 이용을 허락할 권한이 저희에게 없습니다.
본인이 소유한 디스크에 적용하는 개인적 이용만 허용하며, 재배포와 상업적 이용은 할 수 없습니다.
"""

HASHES = """
### sha256

```
{hashes}
```
"""

TEXT_TAIL = """
파일 해시(sha256)는 릴리즈 페이지에 적어 두었습니다.
https://github.com/badatbit/kitae-l10n/releases
"""


def sha256(path):
    m = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            m.update(chunk)
    return m.hexdigest()


# ── 마크다운 → 평문 ────────────────────────────────────────────────────────
# 우리 릴리즈 노트 한 장만 읽기 좋게 옮기면 된다. 범용 변환기가 아니다.
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_CODE = re.compile(r"`([^`]+)`")


def _inline(s):
    s = _LINK.sub(lambda m: f"{m.group(1)} ({m.group(2)})", s)
    return _CODE.sub(r"\1", _BOLD.sub(r"\1", s))


def to_text(md):
    """표는 두 칸 들여쓴 `항목 — 값` 으로, 제목은 밑줄로 편다."""
    out, rows, fence = [], [], False
    for raw in md.split("\n"):
        line = raw.rstrip()
        if line.startswith("```"):
            fence = not fence
            continue
        if fence:
            out.append("    " + line)
            continue
        if line.startswith("<details>") or line.startswith("</details>"):
            continue
        if line.startswith("<summary>"):
            out.append("")
            out.append(_inline(re.sub(r"</?summary>", "", line)))
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):     # 표 구분선
                continue
            rows.append([_inline(c) for c in cells])
            continue
        if rows:                                            # 표가 끝났다
            head, body = rows[0], rows[1:]
            for r in body:
                out.append("  " + " — ".join(x for x in r if x))
            if not body:                                    # 머리만 있는 표는 없다
                out.extend("  " + " — ".join(head) for _ in (0,))
            out.append("")
            rows = []
        if line.startswith("#"):
            t = _inline(line.lstrip("#").strip())
            out.extend(["", t, "-" * sum(2 if ord(c) > 0x2000 else 1 for c in t)])
            continue
        if line.startswith(">"):                            # 인용은 들여쓰기로
            out.append("  " + _inline(line.lstrip("> ")))
            continue
        if line.strip() == "---":
            out.append("")
            continue
        out.append(_inline(line))
    return "\n".join(out)


def _tidy(text):
    """빈 줄 세 개 이상은 둘로 줄이고, 줄을 넘어가 정규식이 못 잡은 굵은 표시를 턴다."""
    return re.sub(r"\n{3,}", "\n\n", text.replace("**", "")).strip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", action="store_true",
                    help="설치 프로그램에 넣을 평문판을 dist/ 에 쓴다 (해시 표 없음)")
    a = ap.parse_args()

    cfg = Config.load()
    out_dir = os.path.join(ROOT, cfg["out_dir"])
    rel_dir = os.path.join(out_dir, "release")
    src = glob.glob(os.path.join(cfg.dir("orig_dir"), "*track03.bin"))[0]

    def asset(ext, where):
        p = os.path.join(where, f"{BASE}_{VER}{ext}")
        if not os.path.exists(p):
            sys.exit(f"에셋 없음: {p}")
        return p

    where = out_dir if a.text else rel_dir
    xd, dcp = asset(".xdelta", where), asset(".dcp", where)
    exe = None if a.text else asset(".exe", where)
    mb = lambda p: f"{os.path.getsize(p) / 1048576:.1f} MB"   # noqa: E731

    text = BODY.format(
        ver=VER,
        exe=f"{BASE}_{VER}.exe", exe_mb=mb(exe) if exe else "",
        xd=os.path.basename(xd), xd_mb=mb(xd),
        dcp=os.path.basename(dcp), dcp_mb=mb(dcp),
        src_size=f"{os.path.getsize(src):,}", src_sha=sha256(src))

    if a.text:
        out = os.path.join(out_dir, "릴리즈 노트.txt")
        body = _tidy(to_text(text) + TEXT_TAIL)
        # NSIS(유니코드)는 BOM 이 있어야 UTF-8 로 읽는다 — 없으면 ANSI 로 봐서 깨진다
        with io.open(out, "w", encoding="utf-8-sig", newline="\r\n") as fh:
            fh.write(body)
    else:
        rows = sorted((os.path.basename(p), sha256(p)) for p in (exe, dcp, xd))
        text += HASHES.format(hashes="\n".join(f"{h}  {n}" for n, h in rows))
        out = os.path.join(rel_dir, "RELEASE-NOTES.md")
        with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    print(f"  {os.path.relpath(out, ROOT)}  {os.path.getsize(out):,}B")
    return 0


if __name__ == "__main__":
    sys.exit(main())
