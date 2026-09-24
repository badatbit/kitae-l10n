# -*- coding: utf-8 -*-
"""IME 스텁 대조 시험 — SH4 미니 에뮬레이터로 패치된 TRFNAMEIN 의 PutChar 를 실제로 돌려
`ime.Composer`(파이썬 참조)와 이름 칸·커서를 대조한다. 빌드 없이 돈다.

    python tools/ime_emu_test.py

에뮬레이터는 스텁·훅·PutChar 원본이 쓰는 명령만 안다. 게임 함수 0x10003afc·0x100018dc 는
들어가는 순간 rts 로 친다(둘 다 r8~r14 를 보존하고 여기선 부수 효과가 상관없다).
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from kitae.build import ime, imestub                     # noqa: E402
from kitae.build.hangul import _read_codepage            # noqa: E402

BASE = 0x10000000
MEMSZ = 0x40000
THIS = 0x10030000
STACK = 0x1003F000
STUBBED = (0x10003AFC, 0x100018DC)


def sx8(v):
    return v - 256 if v & 0x80 else v


def sx16(v):
    return v - 0x10000 if v & 0x8000 else v


class SH4:
    def __init__(self, mem):
        self.mem = mem
        self.r = [0] * 16
        self.pr = self.pc = 0
        self.t = 0
        self.steps = 0

    # 메모리
    def _o(self, a):
        o = a - BASE
        if not 0 <= o < MEMSZ:
            raise RuntimeError(f"주소 밖 {a:#x} (pc {self.pc:#x})")
        return o

    def r8(self, a):  return self.mem[self._o(a)]
    def r16(self, a): return struct.unpack_from("<H", self.mem, self._o(a))[0]
    def r32(self, a): return struct.unpack_from("<I", self.mem, self._o(a))[0]
    def w8(self, a, v):  self.mem[self._o(a)] = v & 0xFF
    def w16(self, a, v): struct.pack_into("<H", self.mem, self._o(a), v & 0xFFFF)
    def w32(self, a, v): struct.pack_into("<I", self.mem, self._o(a), v & 0xFFFFFFFF)

    def _set(self, n, v):
        self.r[n] = v & 0xFFFFFFFF

    def run(self, until, limit=200000):
        while self.pc != until:
            if self.pc in STUBBED:                 # 게임 함수 → 즉시 rts
                self.pc = self.pr
                continue
            self.pc = self.exec(self.pc)
            self.steps += 1
            if self.steps > limit:
                raise RuntimeError("무한 루프?")

    def exec(self, pc):
        """pc 의 명령 하나를 실행하고 다음 pc 를 돌려준다. 지연 분기는 슬롯까지 여기서 처리."""
        w = self.r16(pc)
        r, R = self.r, self._set
        op, n, m = w >> 12, (w >> 8) & 15, (w >> 4) & 15
        lo, d4, imm = w & 15, w & 15, w & 0xFF
        nxt = pc + 2

        def delay(target):
            self.exec(pc + 2)
            return target

        if op == 0x0:
            if lo == 0xC:  R(n, sx8(self.r8(r[0] + r[m])) & 0xFFFFFFFF); return nxt
            if lo == 0xD:  R(n, sx16(self.r16(r[0] + r[m])) & 0xFFFFFFFF); return nxt
            if lo == 0xE:  R(n, self.r32(r[0] + r[m])); return nxt
            if lo == 0x4:  self.w8(r[0] + r[n], r[m]); return nxt
            if lo == 0x5:  self.w16(r[0] + r[n], r[m]); return nxt
            if lo == 0x6:  self.w32(r[0] + r[n], r[m]); return nxt
            if w == 0x0009: return nxt
            if w == 0x000B: return delay(self.pr)                        # rts
            if (w & 0xFF) == 0x03: self.pr = pc + 4; return delay((pc + 4 + r[n]) & 0xFFFFFFFF)   # bsrf
            if (w & 0xFF) == 0x23: return delay((pc + 4 + r[n]) & 0xFFFFFFFF)                    # braf
        elif op == 0x1: self.w32(r[n] + d4 * 4, r[m]); return nxt
        elif op == 0x2:
            if lo == 0x0: self.w8(r[n], r[m]); return nxt
            if lo == 0x1: self.w16(r[n], r[m]); return nxt
            if lo == 0x2: self.w32(r[n], r[m]); return nxt
            if lo == 0x6: R(n, r[n] - 4); self.w32(r[n], r[m]); return nxt
            if lo == 0x8: self.t = int((r[n] & r[m]) == 0); return nxt
            if lo == 0x9: R(n, r[n] & r[m]); return nxt
            if lo == 0xB: R(n, r[n] | r[m]); return nxt
        elif op == 0x3:
            a, b = r[n], r[m]
            sa, sb = a - (1 << 32) if a & 0x80000000 else a, b - (1 << 32) if b & 0x80000000 else b
            if lo == 0x0: self.t = int(a == b); return nxt
            if lo == 0x2: self.t = int(a >= b); return nxt                  # cmp/hs
            if lo == 0x6: self.t = int(a > b); return nxt                   # cmp/hi
            if lo == 0x3: self.t = int(sa >= sb); return nxt                # cmp/ge
            if lo == 0x7: self.t = int(sa > sb); return nxt                 # cmp/gt
            if lo == 0x8: R(n, a - b); return nxt
            if lo == 0xC: R(n, a + b); return nxt
        elif op == 0x4:
            k = w & 0xFF
            if k == 0x00: R(n, r[n] << 1); return nxt
            if k == 0x01: R(n, r[n] >> 1); return nxt
            if k == 0x08: R(n, r[n] << 2); return nxt
            if k == 0x09: R(n, r[n] >> 2); return nxt
            if k == 0x18: R(n, r[n] << 8); return nxt
            if k == 0x19: R(n, r[n] >> 8); return nxt
            if k == 0x0B: self.pr = pc + 4; return delay(r[n])             # jsr
            if k == 0x2B: return delay(r[n])                               # jmp
            if k == 0x15: self.t = int(0 < r[n] < 0x80000000); return nxt  # cmp/pl
            if k == 0x22: R(15, r[15] - 4); self.w32(r[15], self.pr); return nxt
            if k == 0x26: self.pr = self.r32(r[15]); R(15, r[15] + 4); return nxt
        elif op == 0x5: R(n, self.r32(r[m] + d4 * 4)); return nxt
        elif op == 0x6:
            if lo == 0x0: R(n, sx8(self.r8(r[m]))); return nxt
            if lo == 0x1: R(n, sx16(self.r16(r[m]))); return nxt
            if lo == 0x2: R(n, self.r32(r[m])); return nxt
            if lo == 0x3: R(n, r[m]); return nxt
            if lo == 0x5: R(n, sx16(self.r16(r[m]))); R(m, r[m] + 2); return nxt
            if lo == 0x6: v = self.r32(r[m]); R(m, r[m] + 4); R(n, v); return nxt
            if lo == 0x7: R(n, ~r[m]); return nxt
            if lo == 0xC: R(n, r[m] & 0xFF); return nxt
            if lo == 0xD: R(n, r[m] & 0xFFFF); return nxt
            if lo == 0xE: R(n, sx8(r[m] & 0xFF)); return nxt
        elif op == 0x7: R(n, r[n] + sx8(imm)); return nxt
        elif op == 0x8:
            k = (w >> 8) & 15
            if k == 0x0: self.w8(r[m] + d4, r[0]); return nxt
            if k == 0x1: self.w16(r[m] + d4 * 2, r[0]); return nxt
            if k == 0x4: R(0, sx8(self.r8(r[m] + d4))); return nxt
            if k == 0x5: R(0, sx16(self.r16(r[m] + d4 * 2))); return nxt
            if k == 0x8: self.t = int(r[0] == (sx8(imm) & 0xFFFFFFFF)); return nxt
            tgt = pc + 4 + sx8(imm) * 2
            if k == 0x9: return tgt if self.t else nxt
            if k == 0xB: return nxt if self.t else tgt
            if k == 0xD: return delay(tgt) if self.t else pc + 4
            if k == 0xF: return pc + 4 if self.t else delay(tgt)
        elif op == 0x9: R(n, sx16(self.r16(pc + 4 + imm * 2))); return nxt
        elif op == 0xA: d = w & 0xFFF; d = d - 0x1000 if d & 0x800 else d; return delay(pc + 4 + d * 2)
        elif op == 0xB: d = w & 0xFFF; d = d - 0x1000 if d & 0x800 else d; self.pr = pc + 4; return delay(pc + 4 + d * 2)
        elif op == 0xC:
            k = (w >> 8) & 15
            if k == 0x7: R(0, ((pc + 4) & ~3) + imm * 4); return nxt
            if k == 0x8: self.t = int((r[0] & imm) == 0); return nxt
            if k == 0x9: R(0, r[0] & imm); return nxt
            if k == 0xB: R(0, r[0] | imm); return nxt
        elif op == 0xD: R(n, self.r32(((pc + 4) & ~3) + imm * 4)); return nxt
        elif op == 0xE: R(n, sx8(imm)); return nxt
        raise RuntimeError(f"모르는 명령 {w:#06x} @ {pc:#x}")


class Game:
    """패치된 TRFNAMEIN 을 올린 에뮬레이터 + 이름 화면 호출자 흉내."""

    def __init__(self, blob, cp):
        mem = bytearray(MEMSZ)
        for nm, s in imestub._headers(blob).items():
            mem[s["va"] - BASE: s["va"] - BASE + s["rs"]] = blob[s["raw"]: s["raw"] + s["rs"]]
        self.cpu = SH4(mem)
        self.cp = cp
        # codepage 에 없는 글자(가나·한자)는 cp932 셀 그대로 — 게임 カナ/漢字 모드가 넣는 값
        self.cell = lambda ch: ((cp[ch][0] << 8) | cp[ch][1]) if ch in cp else int.from_bytes(ch.encode("cp932"), "big")
        self.inv = {self.cell(ch): ch for ch in cp if len(ch) == 1}
        self.inv[ime.BLANK] = " "
        self.decode = lambda v: self.inv.get(v) or v.to_bytes(2, "big").decode("cp932", "replace")

    def putchar(self, code, adv, pr):
        c = self.cpu
        c.r[4], c.r[5], c.r[6], c.pr, c.r[15], c.pc = THIS, code, adv, pr, STACK, imestub.PUTCHAR
        c.run(until=pr)

    @property
    def cursor(self):
        return self.cpu.r32(THIS + 0x118)

    @cursor.setter
    def cursor(self, v):
        self.cpu.w32(THIS + 0x118, v)

    def cells(self):
        return [self.cpu.r16(THIS + 0x158 + 2 * i) for i in range(10)]

    def text(self):
        return "".join(self.decode(v) for v in self.cells()).rstrip()

    def press_a(self, ch):
        self.putchar(self.cell(ch), 1, imestub.A_PR)

    def press_x(self):                              # 0x10002c10 의 호출자 논리
        if self.cells()[self.cursor] == ime.BLANK:
            if self.cursor > 0:
                self.cursor -= 1
            self.putchar(ime.BLANK, 0, imestub.X_PR[1])
        else:
            self.putchar(ime.BLANK, 0, imestub.X_PR[0])

    def reset(self):
        for i in range(10):
            self.cpu.w16(THIS + 0x158 + 2 * i, ime.BLANK)
        self.cursor = 0
        self.cpu.w32(imestub.STATE_VA, 0)


class Ref:
    """참조 모델: Composer + 같은 호출자 논리."""

    def __init__(self, baked):
        self.baked = baked
        self.reset()

    def reset(self):
        self.cells = [" "] * 10
        self.cursor = 0
        self.comp = ime.Composer(baked=self.baked)

    def _put(self, ch, adv):
        self.cells[self.cursor] = ch if ch is not None else " "
        if adv and self.cursor < 9:
            self.cursor += 1

    def press_a(self, ch):
        if ch in ime.JAMO:
            for _k, c, adv in self.comp.feed(self.cursor, ch):
                self._put(c, adv)
        else:
            self.comp._reset()
            self._put(ch, True)

    def press_x(self):
        if self.cells[self.cursor] == " ":
            if self.cursor > 0:
                self.cursor -= 1
            self.comp._reset()
            self._put(None, False)
        else:
            acts = self.comp.delete(self.cursor)
            if acts is None:
                self._put(None, False)
            else:
                for _k, c, adv in acts:
                    self._put(c, adv)

    def text(self):
        return "".join(self.cells).rstrip()


def build_patched():
    class Cfg:
        def path(self, *p):
            return os.path.join(ROOT, *p)
    cp = _read_codepage(os.path.join(ROOT, "data", "codepage.json"))
    blob = open(os.path.join(ROOT, "work", "orig", "TRF", "TRFNAMEIN.DLL"), "rb").read()
    blob, _ = ime.patch(Cfg(), blob)
    blob, note = imestub.apply(blob, cp)
    return blob, cp, note


CASES = [
    "ㄱㅏㅁㅏ", "ㅎㅏㄴㄱㅡㄹ", "ㄱㅗㅏ", "ㅂㅏㄹㄱ", "ㅂㅏㄹㄱㅡㄴ", "ㅇㅣㅆㅏ", "ㄱㄱㅏ", "ㅏㄱ", "ㅇㅜㅣ",
    "ㄷㅏㄹㄱ", "ㅅㅓㅜㄹ", "ㄱㅣㅁㅊㅓㄹㅅㅜ", "ㄴㅏㄹㄱㅡㄹ", "ㅇㅏㄴㅎㅏ", "ㄱㅏㅂㅅㅇㅣ",
    "ㅇㅗㅐ", "ㅈㅓㅇㅎㅗㅏㄴㄱㅣ", "ㅋㅏㅁㅁㅏ",
    # 삭제
    "ㄷㅏㄹㄱX", "ㄷㅏㄹㄱXX", "ㄷㅏㄹㄱXXX", "ㄷㅏㄹㄱXXXX", "ㄱㅏㅁXXXX", "ㄱㅗㅏX", "ㄱㅏㅁㅏXX",
    "ㅎㅏㄴXㄱㅡㄹ", "ㅎㅏㄴㄱㅡㄹXXXXXXX",
    # 자모 아닌 글자(가나·한자) 사이에 끼는 경우, 칸 끝(9)
    "ㄱㅏあㅁㅏ", "あㅏ", "ㄱㅏㄴあ", "ㄱㅏㄴあX", "ㄱㅏㄴあXX",
    "ㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏ", "ㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㄱㅏㅁㅏ",
]


def main():
    blob, cp, note = build_patched()
    print(note)
    game, ref = Game(blob, cp), Ref(baked=lambda ch: ch in cp)
    bad = 0
    for keys in CASES:
        game.reset(); ref.reset()
        for k in keys:
            if k == "X":
                game.press_x(); ref.press_x()
            else:
                game.press_a(k); ref.press_a(k)
        g, r = (game.text(), game.cursor), (ref.text(), ref.cursor)
        ok = g == r
        bad += not ok
        print(("OK  " if ok else "FAIL") + f" {keys:<28} 스텁 {g!r:<20} 참조 {r!r}")
    print(f"명령 {game.cpu.steps}개 실행 · 실패 {bad}")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
