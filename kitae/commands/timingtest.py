# -*- coding: utf-8 -*-
"""타이밍 검증용 웹페이지를 만든다."""
import base64
import io
import json
import os
import struct

from kitae.config import Config

GROUP = "inspect"
HELP = "타이밍 값과 음성을 브라우저에서 맞춰 보는 테스트 페이지를 만든다"


def configure(p):
    p.add_argument("script", nargs="?", default=None)
    p.add_argument("-w", "--windows", default="1,2,3,4",
                   help="검사할 창 번호 (쉼표 구분)")
    p.add_argument("--rate", type=int, default=18000, help="음성 재생 주파수")
    p.add_argument("--built", action="store_true",
                   help="원본 대신 빌드 산출물(work/build)의 번역문과 타이밍을 본다")
    p.add_argument("-o", "--out", help="출력 HTML 경로")


def _voice_cabs(cfg):
    from kitae.core.cab import Cab
    out = {}
    for i in range(10):
        p = cfg.path(cfg["work_dir"], "cb", "RESOURCE", "WAV", f"{i}.CB")
        if os.path.exists(p):
            out[i] = Cab(p)
    return out


def run(args):
    from kitae.core.cab import Cab
    from kitae.core.windows import clss_objects, msg_table
    from kitae.core import adpcm
    from kitae.build import mtg as mtg_mod, hangul

    cfg = Config.load()
    script = (args.script or cfg["scripts"][0]).upper()
    work = cfg.path(cfg["work_dir"])
    src = os.path.join(work, "build") if args.built \
        else os.path.join(work, "cb", "RESOURCE")
    plot = Cab(os.path.join(src, "PLOT.CB"))
    mtg = Cab(os.path.join(src, "MTG.CB"))     # 음성은 늘 원본에서 온다

    smf = plot.read(script + ".SMF")
    table = msg_table(smf)
    cnt = struct.unpack_from("<I", smf, 8)[0]
    dec = hangul.decoder(cfg) if args.built else \
        (lambda b: b.decode("cp932", "replace"))
    raw, strs, pos = smf[12:], [], 0
    while len(strs) < cnt:
        e = raw.find(b"\x00", pos)
        if e < 0:
            break
        strs.append(dec(raw[pos:e]))
        pos = e + 1

    sets = [p for _, _, p in clss_objects(mtg.read(script.lower() + ".SET"))]
    wsts = [p for _, _, p in clss_objects(mtg.read(script.lower() + ".WST"))]
    cabs = _voice_cabs(cfg)

    def wave_name(p):
        if len(p) < 2:
            return ""
        n = struct.unpack("<H", p[:2])[0]
        return p[2:2 + n].decode("ascii", "replace")

    items = []
    for w in [int(x) for x in args.windows.split(",") if x.strip()]:
        if w >= len(sets) or len(sets[w]) <= 4:
            continue
        got = mtg_mod.parse(sets[w])
        if not got:
            continue
        ticks, shapes = got
        lines, start = table[w]
        text = [strs[start + k] for k in range(lines)]

        wav_b64 = ""
        name = wave_name(wsts[w]) if w < len(wsts) else ""
        if name:
            base = name.lower().replace(".wav", ".p04")
            idx = int(base[1]) if len(base) > 1 and base[1].isdigit() else None
            cab = cabs.get(idx)
            if cab:
                try:
                    pcm = adpcm.p04_to_wav(cab.read(base), args.rate)
                    wav_b64 = base64.b64encode(pcm).decode("ascii")
                except Exception:
                    pass
        items.append({"window": w, "voice": name, "ticks": ticks,
                      "shapes": shapes, "lines": text,
                      "chars": sum(len(t) for t in text), "wav": wav_b64})

    name = "timing-built.html" if args.built else "timing.html"
    out = cfg.path(args.out or os.path.join(cfg["work_dir"], name))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(_HTML.replace("__DATA__", json.dumps(items, ensure_ascii=False))
                     .replace("__RATE__", str(args.rate))
                     .replace("__SCRIPT__", script))
    total = sum(len(i["wav"]) for i in items)
    print(f"{os.path.relpath(out, cfg.root)}  창 {len(items)}개, "
          f"음성 {total // 1024}KB 내장")
    print("브라우저로 열어 재생하면 타이밍 값대로 글자가 찍힙니다")
    return 0


_HTML = """<!doctype html>
<meta charset="utf-8">
<title>__SCRIPT__ 타이밍 검증</title>
<style>
 body{background:#20222a;color:#dfe3ea;font:14px/1.6 system-ui,sans-serif;margin:24px}
 h1{font-size:18px;margin:0 0 4px}
 .hint{color:#8b93a3;margin-bottom:20px}
 .win{background:#2a2d37;border-radius:8px;padding:14px 16px;margin-bottom:14px}
 .head{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
 .tag{color:#8b93a3;font-size:12px}
 button{background:#3d6fd8;color:#fff;border:0;border-radius:5px;
        padding:6px 14px;font-size:13px;cursor:pointer}
 button:disabled{background:#4a4f5c;cursor:default}
 .stage{background:#767a83;border-radius:5px;padding:10px 12px;min-height:70px;
        font-size:22px;letter-spacing:.04em;white-space:pre-wrap;
        text-shadow:3px 3px 0 rgba(0,0,0,.8)}
 .bar{height:4px;background:#1b1d24;border-radius:2px;margin-top:8px;overflow:hidden}
 .bar i{display:block;height:100%;background:#3d6fd8;width:0}
 code{color:#9fb4e0}
</style>
<h1>__SCRIPT__ — 타이밍 값 검증</h1>
<div class="hint">
 재생을 누르면 <code>.SET</code> 의 <b>밀리초</b> 값 그대로 글자가 찍히고 음성이 함께 납니다.
 값은 손대지 않은 원본이니, 맞으면 발화와 딱 붙어야 합니다.
 배속 <input id="speed" type="number" value="1" step="0.1" min="0.1" style="width:60px">
 · 배율 <input id="ms" type="number" value="1" step="0.1" min="0.1" style="width:60px">
 · 음성 <input id="vrate" type="range" min="0.25" max="1.5" step="0.05" value="1" style="vertical-align:middle;width:160px">
   <b id="vhz">__RATE__</b> Hz
</div>
<div id="root"></div>
<script>
const DATA = __DATA__;
const root = document.getElementById('root');
const speedEl = document.getElementById('speed');
const msEl = document.getElementById('ms');
const vrateEl = document.getElementById('vrate');
const vhzEl = document.getElementById('vhz');
const BASE_RATE = __RATE__;
vrateEl.oninput = function () {
  vhzEl.textContent = Math.round(BASE_RATE * parseFloat(vrateEl.value));
};

DATA.forEach((d, n) => {
  const el = document.createElement('div');
  el.className = 'win';
  const total = d.ticks.reduce((a, b) => a + b, 0);
  el.innerHTML = `<div class="head">
      <button>재생</button>
      <b>창 ${d.window}</b>
      <span class="tag">${d.voice || '무성'} · 글자 ${d.chars} · 항목 ${d.ticks.length} · 총 ${total}ms</span>
    </div>
    <div class="stage"></div><div class="bar"><i></i></div>`;
  root.appendChild(el);

  const btn = el.querySelector('button');
  const stage = el.querySelector('.stage');
  const bar = el.querySelector('.bar i');
  const audio = d.wav ? new Audio('data:audio/wav;base64,' + d.wav) : null;

  btn.onclick = () => {
    const chars = d.lines.join('\\n').split('');
    const perTick = (parseFloat(msEl.value) || 1) / (parseFloat(speedEl.value) || 1);
    stage.textContent = '';
    bar.style.width = '0';
    btn.disabled = true;
    if (audio) {
      audio.currentTime = 0;
      audio.playbackRate = parseFloat(vrateEl.value) || 1;
      audio.play();
    }
    // ticks[i] 는 글자 i 를 찍기 *전에* 기다리는 시간이다. 그러니 기다린 뒤
    // 찍는다 — 순서를 뒤집으면 창 전체가 첫 항목만큼 앞당겨진다.
    const t0 = performance.now();
    let i = 0, due = 0;
    const step = () => {
      if (i >= chars.length) { btn.disabled = false; return; }
      due += (d.ticks[i] || 0) * perTick;
      const tick = () => {
        stage.textContent += chars[i];
        bar.style.width = (due / (total * perTick) * 100) + '%';
        i++;
        step();
      };
      // 누적 마감시각으로 재우므로 setTimeout 오차가 쌓이지 않는다
      const wait = due - (performance.now() - t0);
      if (wait > 1) setTimeout(tick, wait); else tick();
    };
    step();
  };
});
</script>
"""
