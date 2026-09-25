# -*- coding: utf-8 -*-
"""NSIS 설치 프로그램 스크립트를 만든다 (dist/installer.nsi).

흐름은 사용자 요청대로다 — **원본 해시가 맞으면 xdelta 로 바로 패치하고, 아니면 DCP 로 넘긴다.**

  1. 원본 `track03.bin` 이 있는 폴더를 고른다
  2. `certutil -hashfile … SHA256` 으로 해시를 잰다 (윈도 기본 도구, 추가 의존성 없음)
  3. 해시가 같으면 → 같이 넣은 `xdelta3.exe` 로 차분을 적용하고 **끝**
  4. 다르면 → 다른 덤프본이다. `.dcp` 와 안내문을 출력 폴더에 풀고 패처 내려받기 쪽을 띄운다

★ 4번이 자동이 아닌 이유: Universal Dreamcast Patcher 는 **GUI 전용**이라(Avalonia .NET)
  명령줄 인자로 조용히 적용할 방법이 없다. DCP 를 코드로 직접 적용하려면 ISO9660 파일 교체와
  Mode1 섹터 EDC/ECC 재계산이 필요한데(우리 `kitae/build/disc.py` 가 하는 일) NSIS 로는 못 한다.

해시를 스크립트에 박아 두므로 **빌드할 때마다 이 생성기를 다시 돌려야** 한다.

    python tools/make_installer.py -v v0.9
    makensis dist/installer.nsi          # NSIS 3 (유니코드) 필요
"""
import argparse
import glob
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")

from kitae.config import Config          # noqa: E402

BASE = "kitae_white_illumination_ko"        # 파일 이름 어간(ASCII)
TITLE = "북으로. White Illumination 한국어 패치"   # 설치 창에 보이는 이름
UDP_URL = "https://github.com/DerekPascarella/UniversalDreamcastPatcher/releases"

NSI = r"""; 북으로. White Illumination 한국어 패치 설치 프로그램
; tools/make_installer.py 가 생성합니다 — 손으로 고치지 마세요(해시가 박혀 있습니다).
Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"

Name "{title} {ver}"
OutFile "{out_exe}"
RequestExecutionLevel user
ShowInstDetails show

Var SrcDir          ; 원본 이미지가 있는 폴더
Var DestDir         ; 결과를 쓸 폴더
Var DataTrack       ; 데이터 트랙 파일 이름 (경로 없음)
Var SrcHash

!define EXPECT "{src_sha}"
!define DATASIZE {data_size}
!define XDELTA "{xdelta_name}"
!define DCP    "{dcp_name}"

!define MUI_WELCOMEPAGE_TITLE "{title} {ver}"
!define MUI_WELCOMEPAGE_TEXT "원본 디스크 이미지에 한국어 패치를 적용합니다.$\r$\n$\r$\n\
GDI(track03.bin) 와 CUE/BIN(… (Track 3).bin) 둘 다 됩니다 — 데이터 트랙은 어느 덤프본이든 같습니다.$\r$\n$\r$\n\
원본은 그대로 두고 패치본을 새 폴더에 만듭니다. 약 1.2GB 의 빈 공간이 필요합니다."
!insertmacro MUI_PAGE_WELCOME

; ── 릴리즈 노트 (MUI 의 라이선스 페이지를 읽기 전용 안내문으로 쓴다 — 동의 체크는 없앤다)
!define MUI_PAGE_HEADER_TEXT "이 패치에 대하여"
!define MUI_PAGE_HEADER_SUBTEXT "무엇이 들어 있고 무엇이 아직 안 되는지"
!define MUI_LICENSEPAGE_TEXT_TOP " "
!define MUI_LICENSEPAGE_TEXT_BOTTOM "계속하려면 [다음] 을 누르세요."
!define MUI_LICENSEPAGE_BUTTON "다음(&N)"
!insertmacro MUI_PAGE_LICENSE "{notes_path}"

; ── 원본 폴더
!define MUI_PAGE_HEADER_TEXT "원본 디스크 이미지"
!define MUI_PAGE_HEADER_SUBTEXT "트랙 파일들이 들어 있는 폴더"
!define MUI_DIRECTORYPAGE_TEXT_TOP "원본 폴더를 고르세요. 이 폴더는 바뀌지 않습니다."
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "원본 폴더"
!define MUI_DIRECTORYPAGE_VARIABLE $SrcDir
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE CheckSrc
!insertmacro MUI_PAGE_DIRECTORY

; ── 출력 폴더
!define MUI_PAGE_HEADER_TEXT "패치본을 만들 곳"
!define MUI_PAGE_HEADER_SUBTEXT "빈 폴더를 권합니다"
!define MUI_DIRECTORYPAGE_TEXT_TOP "패치된 이미지를 쓸 폴더입니다. 약 1.2GB 가 필요합니다."
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "출력 폴더"
!define MUI_DIRECTORYPAGE_VARIABLE $DestDir
!insertmacro MUI_PAGE_DIRECTORY

!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Korean"

Function .onInit
  StrCpy $SrcDir "$DOCUMENTS"
  StrCpy $DestDir "$DESKTOP\{base} {ver}"
FunctionEnd

; 데이터 트랙 찾기 — 이름이 덤프본마다 다르므로 **크기로** 고른다.
; GDI 는 track03.bin, Redump CUE/BIN 은 "… (Track 3).bin" 이지만 내용은 같다.
Function FindDataTrack
  StrCpy $DataTrack ""
  FindFirst $0 $1 "$SrcDir\*.bin"
  ${{Do}}
    ${{If}} $1 == ""
      ${{Break}}
    ${{EndIf}}
    ClearErrors
    FileOpen $2 "$SrcDir\$1" r
    ${{IfNot}} ${{Errors}}
      FileSeek $2 0 END $3
      FileClose $2
      ${{If}} $3 == ${{DATASIZE}}
        StrCpy $DataTrack $1
        ${{Break}}
      ${{EndIf}}
    ${{EndIf}}
    FindNext $0 $1
  ${{Loop}}
  FindClose $0
FunctionEnd

Function CheckSrc
  Call FindDataTrack
  ${{If}} $DataTrack == ""
    MessageBox MB_ICONSTOP "이 폴더에서 데이터 트랙을 찾지 못했습니다.$\r$\n\
크기가 ${{DATASIZE}} 바이트인 .bin 파일이 있어야 합니다.$\r$\n\
(GDI 는 track03.bin, CUE/BIN 은 '… (Track 3).bin')"
    Abort
  ${{EndIf}}
FunctionEnd

; certutil 로 SHA256 → $SrcHash. 출력을 파일로 받아 둘째 줄을 읽는다
; (StrFunc·플러그인 없이 처리하려고 파일 경유. certutil 은 윈도 기본 도구다.)
Function HashSrc
  StrCpy $SrcHash ""
  Delete "$PLUGINSDIR\hash.txt"
  nsExec::ExecToLog 'cmd /c ""$SYSDIR\certutil.exe" -hashfile "$SrcDir\$DataTrack" SHA256 > "$PLUGINSDIR\hash.txt""'
  Pop $0
  ${{IfNot}} ${{FileExists}} "$PLUGINSDIR\hash.txt"
    Return
  ${{EndIf}}
  ClearErrors
  FileOpen $1 "$PLUGINSDIR\hash.txt" r
  ${{If}} ${{Errors}}
    Return
  ${{EndIf}}
  FileRead $1 $2          ; 1행: 안내(언어별로 다름)
  FileRead $1 $2          ; 2행: 해시
  FileClose $1
  ; 공백·탭·개행 제거 (옛 certutil 은 바이트마다 띄운다)
  StrCpy $3 ""
  StrLen $4 $2
  ${{If}} $4 > 0
    IntOp $4 $4 - 1
    ${{For}} $5 0 $4
      StrCpy $6 $2 1 $5
      ${{If}} $6 != " "
      ${{AndIf}} $6 != "$\r"
      ${{AndIf}} $6 != "$\n"
      ${{AndIf}} $6 != "$\t"
        StrCpy $3 "$3$6"
      ${{EndIf}}
    ${{Next}}
  ${{EndIf}}
  StrCpy $SrcHash $3
FunctionEnd

; 데이터 트랙 말고 나머지 파일(.gdi/.cue/오디오 트랙)을 그대로 옮긴다
Function CopyRest
  FindFirst $0 $1 "$SrcDir\*.*"
  ${{Do}}
    ${{If}} $1 == ""
      ${{Break}}
    ${{EndIf}}
    ${{If}} $1 != "."
    ${{AndIf}} $1 != ".."
    ${{AndIf}} $1 S!= $DataTrack
      ${{IfNot}} ${{FileExists}} "$SrcDir\$1\*.*"
        DetailPrint "  $1"
        CopyFiles /SILENT "$SrcDir\$1" "$DestDir\$1"
      ${{EndIf}}
    ${{EndIf}}
    FindNext $0 $1
  ${{Loop}}
  FindClose $0
FunctionEnd

Section "패치"
  ; $PLUGINSDIR 은 첫 플러그인 호출이나 InitPluginsDir 전에는 비어 있다 —
  ; 먼저 부르지 않으면 SetOutPath 가 빈 경로를 받아 설치가 그대로 중단된다.
  InitPluginsDir
  CreateDirectory "$DestDir"
  SetOutPath "$PLUGINSDIR"
  File "{xdelta_exe}"
  File "{xdelta_path}"
  File "{dcp_path}"
  File "{readme_path}"
  File "{notes_path}"

  Call FindDataTrack
  DetailPrint "데이터 트랙: $DataTrack"
  DetailPrint "원본 확인 중… (1.2GB, 몇십 초 걸립니다)"
  Call HashSrc
  ${{If}} $SrcHash == ""
    DetailPrint "해시를 재지 못했습니다 — DCP 쪽으로 넘어갑니다."
    Goto Fallback
  ${{EndIf}}
  DetailPrint "원본 sha256: $SrcHash"

  ; LogicLib 의 == 는 대소문자를 가리지 않는다 — certutil 이 대문자로 내도 맞는다
  ${{If}} $SrcHash == "${{EXPECT}}"
    DetailPrint "우리가 쓴 덤프본과 같습니다. xdelta 로 적용합니다."
    nsExec::ExecToLog '"$PLUGINSDIR\xdelta3.exe" -d -f -s "$SrcDir\$DataTrack" "$PLUGINSDIR\${{XDELTA}}" "$DestDir\$DataTrack"'
    Pop $0
    ${{If}} $0 != 0
      MessageBox MB_ICONSTOP "차분 적용에 실패했습니다 (코드 $0).$\r$\n빈 공간이 모자라지 않은지 보세요."
      Abort
    ${{EndIf}}
    DetailPrint "나머지 파일 복사 중…"
    Call CopyRest
    CopyFiles /SILENT "$PLUGINSDIR\{notes_name}" "$DestDir\{notes_name}"
    DetailPrint "완료."
    MessageBox MB_ICONINFORMATION "패치가 끝났습니다.$\r$\n$\r$\n$DestDir$\r$\n$\r$\n이 폴더의 .gdi 또는 .cue 를 에뮬레이터로 여세요."
    ExecShell "open" "$DestDir"
    Return
  ${{EndIf}}

  Fallback:
  DetailPrint "원본이 우리 덤프본과 다릅니다 — 범용 패처용 파일을 꺼냅니다."
  CopyFiles /SILENT "$PLUGINSDIR\${{DCP}}" "$DestDir\${{DCP}}"
  CopyFiles /SILENT "$PLUGINSDIR\읽어주세요.txt" "$DestDir\읽어주세요.txt"
  CopyFiles /SILENT "$PLUGINSDIR\{notes_name}" "$DestDir\{notes_name}"
  MessageBox MB_ICONEXCLAMATION "원본 데이터 트랙이 우리가 쓴 덤프본과 다릅니다.$\r$\n\
xdelta 차분은 바이트까지 같아야 하므로 쓸 수 없습니다.$\r$\n$\r$\n\
대신 $DestDir 에 패치 파일(.dcp)을 꺼내 두었습니다.$\r$\n\
Universal Dreamcast Patcher 로 적용하세요. 이어서 내려받기 쪽을 엽니다."
  ExecShell "open" "{udp_url}"
  ExecShell "open" "$DestDir"
SectionEnd
"""


def sha256(path):
    m = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            m.update(chunk)
    return m.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--version", default="", help="판 번호 (예: v0.9)")
    ap.add_argument("--xdelta3", default="xdelta3.exe",
                    help="같이 넣을 xdelta3.exe 경로 (기본: dist/xdelta3.exe)")
    a = ap.parse_args()

    cfg = Config.load()
    out_dir = os.path.join(ROOT, cfg["out_dir"])
    tag = f"{BASE}_{a.version}" if a.version else BASE
    orig = glob.glob(os.path.join(cfg.dir("orig_dir"), "*track03.bin"))[0]

    need = {"xdelta": os.path.join(out_dir, tag + ".xdelta"),
            "dcp": os.path.join(out_dir, tag + ".dcp"),
            "readme": os.path.join(out_dir, "읽어주세요.txt"),
            "notes": os.path.join(out_dir, "릴리즈 노트.txt")}
    missing = [k for k, p in need.items() if not os.path.exists(p)]
    if "notes" in missing:
        sys.exit("먼저 `python tools/gen_release_notes.py --text` 를 돌리세요 "
                 "— 릴리즈 노트 평문판이 설치 프로그램 안내 페이지로 들어갑니다")
    if missing:
        sys.exit(f"먼저 `python tools/make_release.py -v {a.version}` 를 돌리세요 — 없는 것: {missing}")

    xd_exe = a.xdelta3 if os.path.isabs(a.xdelta3) else os.path.join(out_dir, a.xdelta3)
    have_exe = os.path.exists(xd_exe)

    nsi = NSI.format(
        title=TITLE, ver=a.version, udp_url=UDP_URL,
        out_exe=tag + ".exe", base=BASE,        # 세 에셋이 어간을 공유한다: .xdelta · .dcp · .exe
        src_sha=sha256(orig), data_size=os.path.getsize(orig),
        xdelta_name=os.path.basename(need["xdelta"]),
        dcp_name=os.path.basename(need["dcp"]),
        xdelta_exe=xd_exe, xdelta_path=need["xdelta"],
        dcp_path=need["dcp"], readme_path=need["readme"],
        notes_path=need["notes"], notes_name=os.path.basename(need["notes"]))
    nsi_path = os.path.join(out_dir, "installer.nsi")
    with open(nsi_path, "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write(nsi)

    print(f"  {nsi_path}")
    print(f"  원본 sha256 {sha256(orig)}")
    print(f"  담을 것: {os.path.basename(need['xdelta'])} · {os.path.basename(need['dcp'])}"
          f" · 읽어주세요.txt · {os.path.basename(need['notes'])}(안내 페이지 겸용)")
    print(f"  xdelta3.exe: {'있음 ' + xd_exe if have_exe else '★없음 — ' + xd_exe + ' 에 넣어야 컴파일됩니다'}")
    print(f"\n  컴파일:  makensis \"{nsi_path}\"")
    return 0 if have_exe else 1


if __name__ == "__main__":
    sys.exit(main())
