"""Map message windows to SMF strings.

The mapping is stored in the game data: every `.SMF` ends with a `.MSG` chunk

    ".MSG" u32 size            size == 8 * window_count
    then one record per window: u32 line_count, u32 byte_offset

where `byte_offset` is the offset of the window's first string inside the
string block (which starts right after the 12-byte `.STR` header). So a window
shows `line_count` consecutive strings beginning at that offset -- no guessing.

Everything below is a straight read of that table; the MTG timing data is only
used as a cross-check (a voiced window's characters must match its timing).

The cross-check: for a window that has voice, `MTG/<script>.SET` holds a
CTRFMsgTiming record with one u16 entry per *drawn* character plus a
terminator (see `kitae.build.mtg`). Inline markup
(`@S@`, `@P@`, `&主人公&`) is not drawn, so it is stripped before comparing --
see `display_len`. Unvoiced windows (narration, monologue, the silent
protagonist) carry an empty timing record and cannot be cross-checked.

Usage:
    python windows.py                 # verify over every script
    python windows.py KOTORI_01       # dump one script's windows
"""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))

from kitae.core.cab import Cab, smf_strings

PLOT_CB = os.path.join(HERE, "..", "dump", "plot", "PLOT.CB")
MTG_CB = os.path.join(HERE, "..", "dump", "scn", "MTG.CB")

import re

# Inline markup inside a message line, none of which is a displayed character:
#   @S@ @P@ ...  playback control (speed / pause)
#   &主人公& &主人公名前& ...  runtime name substitution
MARKUP = re.compile(r"@[^@]{0,8}@|&[^&]{0,16}&")
# 인코더·변환기·검사기가 쓰는 전체 마크업 — 선택지 `%N%`, 자간 `*N`, `$N` 까지.
# display_len 은 게임의 타이밍 셈과 같게 위의 MARKUP 만 뺀다(%N% 은 예전처럼 글자로 센다).
MARKUP_ALL = re.compile(r"@[^@]{0,8}@|&[^&]{0,16}&|%[0-9０-９]{1,2}%|\*[0-9]|\$[0-9]")


def display_len(s):
    """Characters actually drawn, i.e. what the MTG timing table counts."""
    return len(MARKUP.sub("", s))


def clss_objects(buf):
    if buf[:4] != b"CLSS":
        return
    nlen = struct.unpack("<I", buf[4:8])[0]
    pos = 8 + nlen
    while pos + 14 <= len(buf):
        if buf[pos:pos + 4] != b"\xff\xff\xff\xff":
            pos += 1
            continue
        oid = struct.unpack("<I", buf[pos + 4:pos + 8])[0]
        cl = struct.unpack("<H", buf[pos + 8:pos + 10])[0]
        nm = buf[pos + 10:pos + 10 + cl].decode("ascii", "replace")
        plen = struct.unpack("<I", buf[pos + 10 + cl:pos + 14 + cl])[0]
        yield oid, nm, buf[pos + 14 + cl:pos + 14 + cl + plen]
        pos += 14 + cl + plen


def timing_chars(payload):
    """Characters this timing record covers, or None when there is no timing.

    The payload is `u16 count` + `count` u16 entries, and the last entry is a
    terminator that no character consumes -- so it covers `count - 1` glyphs.
    """
    if len(payload) < 4:
        return None
    count = struct.unpack_from("<H", payload, 0)[0]
    return count - 1 if count >= 2 else None


def wave_name(payload):
    if len(payload) < 2:
        return ""
    ln = struct.unpack("<H", payload[:2])[0]
    return payload[2:2 + ln].decode("ascii", "replace")




def msg_table(smf):
    """Parse the `.MSG` chunk: [(line_count, first_string_index)] per window."""
    i = smf.find(b".MSG")
    if i < 0:
        return None
    size = struct.unpack_from("<I", smf, i + 4)[0]
    body = smf[i + 8:i + 8 + size]

    # byte offset of every string inside the string block (starts at 12)
    off_to_idx, pos, n = {}, 12, 0
    total_count = struct.unpack_from("<I", smf, 8)[0]
    while n < total_count and pos < len(smf):
        off_to_idx[pos - 12] = n
        end = smf.find(b"\x00", pos)
        if end < 0:
            break
        pos = end + 1
        n += 1

    out = []
    for r in range(size // 8):
        lines, byte_off = struct.unpack_from("<II", body, r * 8)
        out.append((lines, off_to_idx.get(byte_off)))
    return out


def script_windows(script, plot_cab, mtg_cab):
    """Return (list of window dicts, list of SMF strings).

    타이밍이 아예 없는 스크립트도 있다 — 風呂/風呂冬/風呂冬2/歌詞/URANAI 는
    MTG 에 `.SET` 자체가 없다. 전부 무성이라는 뜻이므로 창 수를 `.MSG` 에서
    가져오고 타이밍·음성은 비운다.
    """
    smf = plot_cab.read(script.upper() + ".SMF")
    strs = smf_strings(smf)
    table = msg_table(smf)

    def _objs(name):
        try:
            return [p for _, _, p in clss_objects(mtg_cab.read(name))]
        except Exception:
            return []

    sets = _objs(script.lower() + ".SET")
    wavs = _objs(script.lower() + ".WST")
    nwin = len(sets) or len(table or [])
    want = [timing_chars(p) for p in sets] + [None] * (nwin - len(sets))

    out = []
    for wi in range(nwin):
        lines, start = (table[wi] if table and wi < len(table) else (0, None))
        idx = ([] if start is None
               else [i for i in range(start, min(start + lines, len(strs)))])
        chars = sum(display_len(strs[i]) for i in idx)
        out.append(dict(window=wi, strings=idx, chars=chars, want=want[wi],
                        wave=wave_name(wavs[wi]) if wi < len(wavs) else "",
                        ok=(want[wi] is None or chars == want[wi])))
    return out, strs


def main():
    plot_cab, mtg_cab = Cab(PLOT_CB), Cab(MTG_CB)
    scripts = sorted({n[:-4] for n in mtg_cab.names if n.lower().endswith(".set")})
    scripts = [s for s in scripts
               if (s.upper() + ".SMF") in plot_cab.names
               and (s.lower() + ".WST") in mtg_cab.names]

    if len(sys.argv) > 1:
        s = sys.argv[1]
        wins, strs = script_windows(s, plot_cab, mtg_cab)
        for w in wins[:40]:
            txt = " / ".join(strs[i] for i in w["strings"])
            flag = "" if w["ok"] else "  <-- MISMATCH"
            print(f"[{w['window']:>4}] str{w['strings']} "
                  f"chars={w['chars']}/{w['want']} {w['wave']:<11} {txt}{flag}")
        return

    tot = bad = infeasible = 0
    for s in scripts:
        try:
            wins, strs = script_windows(s, plot_cab, mtg_cab)
        except Exception as e:
            print(f"{s}: ERROR {e}")
            continue
        n = sum(1 for w in wins if not w["ok"])
        used = sum(len(w["strings"]) for w in wins)
        tot += len(wins); bad += n
        if used != len(strs):
            infeasible += 1
        print(f"{s:<16} windows={len(wins):>5} bad={n:>4} "
              f"strings {used}/{len(strs)}"
              f"{'  <-- INFEASIBLE' if used != len(strs) else ''}")
    print(f"\nTOTAL windows={tot} constraint-violations={bad} "
          f"scripts-infeasible={infeasible}")


if __name__ == "__main__":
    main()
