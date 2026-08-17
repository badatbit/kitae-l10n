# -*- coding: utf-8 -*-
"""flycast Lua 명령 서버(flycast.lua)와 파일로 대화한다.

flycast 쪽은 매 6프레임 `lua_cmd.txt` 를 실행하고 결과를 `lua_out.txt` 에 쓴다.
이 스크립트는 그 파일 왕복을 감싼다.

    python tools/lualink.py "return hexdump(0x8CCAB5B4, 16)"
    python tools/lualink.py --file probe.lua
"""
import argparse
import io
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
DIR = r"C:\Users\me\Downloads\flycast-win64-2.6"
CMD = os.path.join(DIR, "lua_cmd.txt")
OUT = os.path.join(DIR, "lua_out.txt")


def run(src, timeout=12):
    try:
        os.remove(OUT)
    except OSError:
        pass
    with io.open(CMD, "w", encoding="utf-8") as fh:
        fh.write(src)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if os.path.exists(OUT):
            time.sleep(0.2)                      # 서버가 쓰는 중일 수 있다
            with io.open(OUT, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        time.sleep(0.1)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", help="Lua 조각")
    ap.add_argument("--file", help="Lua 파일 경로")
    ap.add_argument("--timeout", type=float, default=12)
    a = ap.parse_args()
    src = io.open(a.file, encoding="utf-8").read() if a.file else a.src
    if not src:
        ap.error("Lua 조각이나 --file 이 필요하다")
    out = run(src, a.timeout)
    if out is None:
        print("!! 응답 없음 — flycast/Lua 서버가 안 도는 듯")
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
