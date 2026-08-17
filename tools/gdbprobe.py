# -*- coding: utf-8 -*-
"""flycast GDB 스텁으로 글자 그리기 루프를 실측한다.

화면 눈금자(폭으로 값을 부호화해 읽기)는 한 판에 2비트씩이라 비쌌다. 여기서는
중단점 한 번으로 다 잰다.

  1. RAM 을 훑어 TRFSTRINGS.DLL 이 어디 로드됐는지 찾는다 (훅 원본 12바이트)
  2. 글자 루프 RVA 0x35B4 에 중단점을 걸고
  3. 글자마다 레코드 16B 와 레지스터를 받아 적는다 — 연속 60글자
  4. 첫 글자에서 객체 창·스택·한 단계 역참조를 덤프한다
  5. 알려진 대사의 코드열을 RAM 전체에서 찾는다 (cp932 순 · u16 LE 두 가지)

쓰는 법: flycast 로 dist GDI 를 띄워 대사창이 보이는 상태로 두고

    python -X utf8 tools/gdbprobe.py

결과: work/gdb-dump.txt · work/gdb-dump.json
"""
import io
import json
import os
import socket
import struct
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

HOST, PORT = "127.0.0.1", 3263
HOOK_RVA = 0x35B4                       # 0x100035B4 − ImageBase 0x10000000
PAT = struct.pack("<6H", 0x6492, 0x7B01, 0x51AD, 0x341C, 0x52AC, 0x3428)
RAM_LO, RAM_HI = 0x8C000000, 0x8D000000
LINE = "로즈힐　미나미히라기시　응접실이다。"
HITS = 60
REGN = [f"r{i}" for i in range(16)] + ["pc", "pr", "gbr", "vbr", "mach", "macl", "sr"]


class Rsp:
    def __init__(self):
        self.s = None
        self.buf = b""
        self.chunk = 512

    def connect(self, wait):
        t0 = time.time()
        note = 0
        while True:
            try:
                self.s = socket.create_connection((HOST, PORT), timeout=3)
                return True
            except OSError:
                el = time.time() - t0
                if el > wait:
                    return False
                if el > note:
                    print(f"  flycast 대기 중... ({int(el)}초)")
                    note += 30
                time.sleep(2)

    def _pump(self, timeout):
        self.s.settimeout(max(timeout, 0.05))
        try:
            d = self.s.recv(65536)
        except socket.timeout:
            return False
        if not d:
            raise ConnectionError("flycast 가 연결을 끊었다")
        self.buf += d
        return True

    def recv_pkt(self, timeout=10):
        end = time.time() + timeout
        while True:
            i = self.buf.find(b"$")
            if i >= 0:
                j = self.buf.find(b"#", i)
                if j >= 0 and len(self.buf) >= j + 3:
                    data = self.buf[i + 1:j]
                    self.buf = self.buf[j + 3:]
                    try:
                        self.s.send(b"+")
                    except OSError:
                        pass
                    return data.decode("ascii", "replace")
            left = end - time.time()
            if left <= 0:
                return None
            self._pump(min(left, 2))

    def send_pkt(self, c):
        b = c.encode()
        self.s.send(b"$" + b + (b"#%02x" % (sum(b) & 0xFF)))

    def cmd(self, c, timeout=10):
        self.send_pkt(c)
        return self.recv_pkt(timeout)

    def interrupt(self, timeout=10):
        self.s.send(b"\x03")
        return self.recv_pkt(timeout)


def mem(r, addr, ln):
    out = b""
    while ln > 0:
        n = min(r.chunk, ln)
        rep = r.cmd(f"m{addr:x},{n:x}", 15)
        if rep is None or rep == "" or (rep.startswith("E") and len(rep) <= 3):
            if r.chunk > 128 and not out:       # 패킷이 크면 줄여서 한 번 더
                r.chunk //= 2
                continue
            return out or None
        try:
            d = bytes.fromhex(rep)
        except ValueError:
            return out or None
        if not d:
            return out or None
        out += d
        addr += len(d)
        ln -= len(d)
    return out


def read_regs(r):
    rep = r.cmd("g", 15)
    if not rep or rep.startswith("E"):
        return None
    try:
        raw = bytes.fromhex(rep)
    except ValueError:
        return None
    n = len(raw) // 4
    return ([int.from_bytes(raw[i*4:i*4+4], "little") for i in range(n)],
            [int.from_bytes(raw[i*4:i*4+4], "big") for i in range(n)])


def pick_endian(pair, hook):
    le, be = pair
    def score(v):
        s = 0
        if len(v) > 16 and v[16] in (hook, hook + 2):
            s += 10
        s += sum(1 for x in v[:16] if RAM_LO <= x < RAM_HI)
        return s
    return le if score(le) >= score(be) else be


def find_module(r):
    for align in (0x10000, 0x1000):
        total = (RAM_HI - RAM_LO) // align
        print(f"  모듈 검색 (정렬 {align:#x}, {total}칸)...")
        for k, base in enumerate(range(RAM_LO, RAM_HI, align)):
            d = mem(r, base + HOOK_RVA, 12)
            if d and d[:12] == PAT:
                return base
            if k % 512 == 511:
                print(f"    {k+1}/{total}")
    return None


def hexdump(addr, data):
    out = []
    for i in range(0, len(data), 16):
        row = data[i:i+16]
        hx = " ".join(f"{b:02x}" for b in row)
        asc = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        out.append(f"    {addr+i:08x}  {hx:<47}  {asc}")
    return "\n".join(out)


def build_patterns():
    with io.open("data/codepage.json", encoding="utf-8") as fh:
        cp = json.load(fh)
    codes = []
    for ch in LINE:
        if ch in cp:
            l, t = cp[ch]
        else:
            b = ch.encode("cp932")
            l, t = b[0], b[1]
        codes.append((l << 8) | t)
    pa = b"".join(bytes(((c >> 8) & 0xFF, c & 0xFF)) for c in codes[:8])
    pb = b"".join(struct.pack("<H", c) for c in codes[:8])
    return codes, {"cp932순": pa, "u16LE": pb}


def ram_search(r, pats):
    hits = {k: [] for k in pats}
    keep = max(len(p) for p in pats.values()) - 1
    tail = b""
    addr = RAM_LO
    while addr < RAM_HI:
        d = mem(r, addr, 1024)
        if d is None:
            addr += 1024
            tail = b""
            continue
        blob = tail + d
        for k, p in pats.items():
            off = 0
            while len(hits[k]) < 40:
                j = blob.find(p, off)
                if j < 0:
                    break
                hits[k].append(addr - len(tail) + j)
                off = j + 1
        tail = blob[-keep:]
        addr += len(d)
        if (addr - RAM_LO) % 0x200000 < 1024:
            print(f"    RAM 검색 {(addr-RAM_LO)>>20}/{(RAM_HI-RAM_LO)>>20}MB")
    return hits


def main():
    os.makedirs("work", exist_ok=True)
    print("★ flycast GDB 실측 — 대사창이 보이는 상태로 두면 자동으로 잡는다")
    r = Rsp()
    if not r.connect(900):
        print("!! 15분 안에 flycast 에 붙지 못했다. GDB 설정을 다시 봐야 한다")
        return 1
    print("  붙었다. 상태 확인...")

    rep = r.cmd("qSupported", 5)
    if rep:
        for part in rep.split(";"):
            if part.startswith("PacketSize="):
                try:
                    r.chunk = max(128, min(1024, (int(part[11:], 16) - 32) // 2))
                except ValueError:
                    pass
    rep = r.cmd("?", 3)
    if rep is None:
        rep = r.interrupt()
    print(f"  정지: {rep!r} · 패킷 {r.chunk}B")

    base = None
    for attempt in range(40):
        base = find_module(r)
        if base is not None:
            break
        print(f"  아직 없다 — 3초 돌리고 다시 ({attempt+1}/40)")
        r.send_pkt("c")
        time.sleep(3)
        r.interrupt()
    if base is None:
        print("!! TRFSTRINGS 를 RAM 에서 못 찾았다")
        return 1
    hook = base + HOOK_RVA
    print(f"★ TRFSTRINGS @ {base:#x} · 훅 {hook:#x}")

    bp = None
    for kind in ("2", "4", ""):
        c = f"Z0,{hook:x}" + (f",{kind}" if kind else "")
        if r.cmd(c) == "OK":
            bp = c
            break
    if bp is None:
        print("!! 중단점(Z0)을 지원하지 않는다 — RAM 검색만 하고 끝낸다")
    samples, dumps, order = [], {}, None

    if bp:
        print("  중단점 설정. 글자를 기다린다 (대사창이 보이면 즉시)...")
        for i in range(HITS):
            r.send_pkt("c")
            stop = r.recv_pkt(300 if i == 0 else 15)
            if stop is None:
                print(f"  {i}번째에서 더 안 잡힌다 — 여기까지 수집")
                r.interrupt()
                break
            pair = read_regs(r)
            if pair is None:
                print("  레지스터를 못 읽었다")
                break
            if order is None:
                v = pick_endian(pair, hook)
                order = "little" if v == pair[0] else "big"
                print(f"  레지스터 엔디안: {order} · pc={v[16]:#x}")
            v = pair[0] if order == "little" else pair[1]
            g = dict(zip(REGN, v[:23]))
            rec = mem(r, g["r8"], 16) or b""
            wid = mem(r, g["r9"], 4) or b""
            samples.append({"regs": {k: f"{x:#x}" for k, x in g.items()},
                            "rec": rec.hex(), "width": wid.hex()})
            if i == 0:
                print("  첫 글자 — 객체·스택 덤프 중...")
                for name, a, ln in (
                        ("obj_head", g["r10"], 0x40),
                        ("obj_win", g["r10"] + 0x1F80, 0xB0),
                        ("stack", g["r15"], 0xA0),
                        ("renderer", g["r13"], 0x40)):
                    d = mem(r, a, ln)
                    if d:
                        dumps[name] = {"addr": a, "hex": d.hex()}
                ptrs = set()
                for d in dumps.values():
                    raw = bytes.fromhex(d["hex"])
                    for off in range(0, len(raw) - 3, 4):
                        p = struct.unpack_from("<I", raw, off)[0]
                        if RAM_LO <= p < RAM_HI:
                            ptrs.add(p & ~3)
                for k, p in enumerate(sorted(ptrs)[:24]):
                    d = mem(r, p, 0x40)
                    if d:
                        dumps[f"deref_{p:08x}"] = {"addr": p, "hex": d.hex()}
            if (i + 1) % 10 == 0:
                print(f"  {i+1}/{HITS} 글자")
        r.cmd(f"z0,{hook:x},2")
        r.cmd(f"z0,{hook:x}")

    print("  코드열 RAM 검색...")
    codes, pats = build_patterns()
    hits = ram_search(r, pats)

    out = {"base": f"{base:#x}", "hook": f"{hook:#x}", "endian": order,
           "line": LINE, "line_codes": [f"{c:#06x}" for c in codes],
           "samples": samples, "dumps": dumps,
           "text_hits": {k: [f"{a:#x}" for a in v] for k, v in hits.items()}}
    with io.open("work/gdb-dump.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    with io.open("work/gdb-dump.txt", "w", encoding="utf-8") as fh:
        w = fh.write
        w(f"TRFSTRINGS @ {base:#x} · 훅 {hook:#x} · 엔디안 {order}\n")
        w(f"기준 문장: {LINE}\n")
        w("코드열: " + " ".join(f"{c:04x}" for c in codes) + "\n\n")
        w(f"== 글자 샘플 {len(samples)}개 ==\n")
        w("   #   r11(idx)  r8(rec)     rec+0     rec+4     rec+8     rec+12    @r9\n")
        for i, s in enumerate(samples):
            g = s["regs"]
            rec = bytes.fromhex(s["rec"])
            f4 = [struct.unpack_from("<I", rec, o)[0] for o in (0, 4, 8, 12)] \
                if len(rec) == 16 else [0, 0, 0, 0]
            wid = struct.unpack("<I", bytes.fromhex(s["width"]))[0] \
                if s["width"] else -1
            w(f"  {i:>3}  {int(g['r11'],16):>7}  {g['r8']:>10}  "
              + "  ".join(f"{x:08x}" for x in f4) + f"  {wid}\n")
        w("\n== 덤프 ==\n")
        for name, d in dumps.items():
            w(f"\n[{name}] @ {d['addr']:#x}\n")
            w(hexdump(d["addr"], bytes.fromhex(d["hex"])) + "\n")
        w("\n== 코드열 검색 ==\n")
        for k, v in hits.items():
            w(f"  {k}: " + (" ".join(f"{a:#x}" for a in v) if v else "없음") + "\n")

    r.cmd("D", 3)
    print("★ 끝 — work/gdb-dump.txt · 게임은 다시 돌아간다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
