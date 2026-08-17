# -*- coding: utf-8 -*-
"""Flycast GDB 스텁(RSP) 클라이언트 — SH4 메모리 포렌식용.

가변폭 조사([PROPORTIONAL-WIDTH.md](../docs/PROPORTIONAL-WIDTH.md))에서
"굽고-보고" 반복을 끊으려고 만들었다. emu.cfg 에 `Debug.GDBEnabled = yes`
(포트 3263)를 켜고 게임을 띄운 뒤 쓴다.

    python tools/dcgdb.py probe                       스텁 능력·레지스터 확인
    python tools/dcgdb.py regs                        레지스터 덤프 (멈췄다 재개)
    python tools/dcgdb.py read  0x8C000000 0x100      메모리 읽기 (hex 덤프)
    python tools/dcgdb.py scan  0x8C000000 0x1000000 92640B7B  패턴 검색
    python tools/dcgdb.py catch 0x????????            중단점 → 잡히면 레지스터 덤프
    python tools/dcgdb.py catch 0x???????? --deref r10+0x1FE4 --deref r8+0
                                                      잡힌 자리에서 역참조도 찍는다

주의
----
  * 연결만으로는 안 멈춘다. 각 명령이 0x03(인터럽트)으로 멈추고 끝나면 `c` 로
    되살린다 (`--halt` 를 주면 멈춘 채로 둔다).
  * `m`(읽기)은 **가상 주소**다. WinCE 는 MMU 를 쓰므로 어느 주소가 읽히는지는
    스텁 구현에 달렸다 — `probe` 로 0x8C000000(P1)·0x0C000000(물리)·
    0x10000000(DLL 선호 베이스) 세 군데를 찔러 본다.
  * 중단점(Z0)은 다이나렉에서 안 걸릴 수 있다. 그때는 emu.cfg 에서
    `Dynarec.Enabled = no` 로 바꾸고 다시 부팅한다 (느리다).
"""
import argparse
import binascii
import re
import socket
import struct
import sys
import time

PORT = 3263

# GDB SH 아키텍처 레지스터 순서
REGS = ([f"r{i}" for i in range(16)] +
        ["pc", "pr", "gbr", "vbr", "mach", "macl", "sr", "fpul", "fpscr"] +
        [f"fr{i}" for i in range(16)])


class Rsp:
    def __init__(self, port=PORT, timeout=5.0):
        self.s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
        self.s.settimeout(timeout)
        self.buf = b""

    # ---------------------------------------------------------- 패킷 계층
    def _send(self, payload):
        raw = b"$" + payload + b"#" + b"%02x" % (sum(payload) & 0xFF)
        self.s.sendall(raw)

    def _recv_packet(self, timeout=None):
        """다음 $...# 패킷 하나. '+'/'-' ack 은 소비한다."""
        if timeout is not None:
            self.s.settimeout(timeout)
        while True:
            m = re.search(rb"\$([^#]*)#[0-9a-fA-F]{2}", self.buf)
            if m:
                self.buf = self.buf[m.end():]
                self.s.sendall(b"+")
                return m.group(1)
            chunk = self.s.recv(4096)
            if not chunk:
                raise ConnectionError("스텁이 연결을 끊었다")
            self.buf += chunk

    def cmd(self, payload, timeout=None):
        if isinstance(payload, str):
            payload = payload.encode()
        self._send(payload)
        return self._recv_packet(timeout)

    # ---------------------------------------------------------- 동작 계층
    def interrupt(self):
        """0x03 → 멈춤 응답(S/T 패킷)."""
        self.s.sendall(b"\x03")
        return self._recv_packet()

    def read_mem(self, addr, length):
        r = self.cmd(f"m{addr:x},{length:x}")
        if r.startswith(b"E") and len(r) <= 3:
            raise IOError(f"m {addr:#x},{length:#x} → {r.decode()}")
        return binascii.unhexlify(r)

    def write_mem(self, addr, data):
        r = self.cmd(b"M%x,%x:%s" % (addr, len(data), binascii.hexlify(data)))
        if r != b"OK":
            raise IOError(f"M {addr:#x} → {r.decode()}")

    def regs(self):
        r = self.cmd("g")
        if r.startswith(b"E"):
            raise IOError(f"g → {r.decode()}")
        raw = binascii.unhexlify(r)
        vals = {}
        for i, name in enumerate(REGS):
            if (i + 1) * 4 <= len(raw):
                # 타깃(리틀엔디언) 바이트 순서
                vals[name] = struct.unpack_from("<I", raw, i * 4)[0]
        return vals

    def cont(self):
        self._send(b"c")            # 응답은 멈출 때까지 안 온다

    def wait_stop(self, timeout):
        return self._recv_packet(timeout)

    def set_bp(self, addr):
        r = self.cmd(f"Z0,{addr:x},2")
        if r != b"OK":
            raise IOError(f"Z0 {addr:#x} → {r.decode() or '(빈 응답 — 미지원)'}")

    def clear_bp(self, addr):
        self.cmd(f"z0,{addr:x},2")

    def detach(self):
        try:
            self._send(b"D")
            self.s.close()
        except OSError:
            pass


def hexdump(addr, data):
    out = []
    for o in range(0, len(data), 16):
        row = data[o:o + 16]
        h = " ".join(f"{b:02x}" for b in row)
        out.append(f"{addr + o:08x}  {h}")
    return "\n".join(out)


def _resume(g, args):
    if getattr(args, "halt", False):
        print("(멈춘 채로 둔다 — 재개하려면 regs 나 read 를 --halt 없이)")
        g.detach()
    else:
        g.cont()
        g.s.close()


def cmd_probe(args):
    g = Rsp(args.port)
    print("qSupported:", g.cmd("qSupported").decode(errors="replace"))
    print("halt:", g.interrupt().decode(errors="replace"))
    r = g.regs()
    print(" ".join(f"{n}={v:08x}" for n, v in r.items() if not n.startswith("fr")))
    for probe in (0x8C000000, 0x0C000000, 0x10000000, r.get("pc", 0) & ~0xF):
        try:
            d = g.read_mem(probe, 16)
            print(f"m {probe:#010x}: {d.hex()}")
        except IOError as e:
            print(f"m {probe:#010x}: {e}")
    _resume(g, args)


def cmd_regs(args):
    g = Rsp(args.port)
    g.interrupt()
    for n, v in g.regs().items():
        if not n.startswith("fr"):
            print(f"{n:6} {v:08x}")
    _resume(g, args)


def cmd_read(args):
    g = Rsp(args.port)
    g.interrupt()
    addr, length = int(args.addr, 0), int(args.len, 0)
    data = b""
    while len(data) < length:
        n = min(0x400, length - len(data))
        data += g.read_mem(addr + len(data), n)
    print(hexdump(addr, data))
    _resume(g, args)


def cmd_scan(args):
    g = Rsp(args.port)
    g.interrupt()
    base, size = int(args.addr, 0), int(args.len, 0)
    pat = binascii.unhexlify(args.pattern)
    step = 0x800
    hits, errs = [], 0
    t0 = time.time()
    carry = b""
    carry_at = base
    for off in range(0, size, step):
        try:
            chunk = g.read_mem(base + off, min(step, size - off))
        except IOError:
            errs += 1
            carry = b""
            continue
        blob = carry + chunk
        at = carry_at if carry else base + off
        i = blob.find(pat)
        while i >= 0:
            hits.append(at + i)
            i = blob.find(pat, i + 1)
        carry = chunk[-(len(pat) - 1):] if len(pat) > 1 else b""
        carry_at = base + off + len(chunk) - len(carry)
        if args.first and hits:
            break
    dt = time.time() - t0
    for h in hits:
        print(f"hit {h:#010x}")
    print(f"({len(hits)}건 · 읽기 실패 {errs}구간 · {dt:.1f}s)")
    _resume(g, args)


DEREF = re.compile(r"^(r\d+|pc|pr)([+-]0x[0-9a-fA-F]+|[+-]\d+)?$")


def cmd_catch(args):
    g = Rsp(args.port, timeout=10.0)
    g.interrupt()
    addr = int(args.addr, 0)
    g.set_bp(addr)
    g.cont()
    print(f"중단점 {addr:#x} — 대기(최대 {args.wait}s)…")
    try:
        stop = g.wait_stop(args.wait)
    except socket.timeout:
        print("안 잡혔다 — 그 코드가 안 돌거나 다이나렉이 중단점을 무시한다")
        g.interrupt()
        g.clear_bp(addr)
        _resume(g, args)
        return
    print("stop:", stop.decode(errors="replace"))
    r = g.regs()
    print(" ".join(f"{n}={v:08x}" for n, v in r.items() if not n.startswith("fr")))
    for expr in args.deref or []:
        m = DEREF.match(expr)
        if not m:
            print(f"deref '{expr}': 형식은 r10+0x1FE4")
            continue
        v = r[m.group(1)] + (int(m.group(2), 0) if m.group(2) else 0)
        try:
            d = g.read_mem(v & 0xFFFFFFFF, int(args.deref_len, 0))
            print(f"[{expr}] = @{v:#010x}:")
            print(hexdump(v, d))
        except IOError as e:
            print(f"[{expr}] = @{v:#010x}: {e}")
    g.clear_bp(addr)
    _resume(g, args)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=PORT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe"); p.set_defaults(fn=cmd_probe)
    p = sub.add_parser("regs"); p.set_defaults(fn=cmd_regs)
    p = sub.add_parser("read"); p.add_argument("addr"); p.add_argument("len")
    p.set_defaults(fn=cmd_read)
    p = sub.add_parser("scan"); p.add_argument("addr"); p.add_argument("len")
    p.add_argument("pattern", help="hex 바이트열, 예: 92640B7B")
    p.add_argument("--first", action="store_true")
    p.set_defaults(fn=cmd_scan)
    p = sub.add_parser("catch"); p.add_argument("addr")
    p.add_argument("--wait", type=float, default=30.0)
    p.add_argument("--deref", action="append", help="r10+0x1FE4 꼴, 여러 번 가능")
    p.add_argument("--deref-len", default="0x40")
    p.set_defaults(fn=cmd_catch)
    for name, sp in sub.choices.items():
        sp.add_argument("--halt", action="store_true",
                        help="끝나고 재개하지 않는다")
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
