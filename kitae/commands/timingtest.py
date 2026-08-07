# -*- coding: utf-8 -*-
"""타이밍 검증용 웹페이지를 만든다.

`.SET` 의 값(글자별 지속시간 ms + 입 모양)을 그대로 재생해, 음성과 맞는지
에뮬레이터 없이 눈과 귀로 확인한다. 자세한 형식은 docs/MTG-TIMING.md.
"""
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
                     .replace("__SCRIPT__", script)
                     .replace("__MODE__", "빌드" if args.built else "원문"))
    total = sum(len(i["wav"]) for i in items)
    print(f"{os.path.relpath(out, cfg.root)}  창 {len(items)}개, "
          f"음성 {total // 1024}KB 내장")
    print("브라우저로 열면 값 그대로 글자가 찍히고 입 모양이 함께 움직입니다")
    return 0


_HTML = """<!doctype html>
<meta charset="utf-8">
<title>__SCRIPT__ 타이밍 · 입 모양 (__MODE__)</title>
<style>
 body{background:#20222a;color:#dfe3ea;font:14px/1.6 system-ui,sans-serif;margin:24px}
 h1{font-size:18px;margin:0 0 4px}
 .hint{color:#8b93a3;margin-bottom:8px;max-width:900px}
 .ctl{background:#262932;border-radius:6px;padding:8px 12px;margin-bottom:18px;
      display:inline-block}
 .win{background:#2a2d37;border-radius:8px;padding:14px 16px;margin-bottom:14px}
 .head{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:10px}
 .tag{color:#8b93a3;font-size:12px}
 button{background:#3d6fd8;color:#fff;border:0;border-radius:5px;
        padding:6px 14px;font-size:13px;cursor:pointer}
 button:disabled{background:#4a4f5c;cursor:default}
 .row{display:flex;gap:14px;align-items:stretch}
 .stage{background:#767a83;border-radius:5px;padding:10px 12px;min-height:74px;
        font-size:22px;letter-spacing:.04em;white-space:pre-wrap;flex:1;
        text-shadow:3px 3px 0 rgba(0,0,0,.8)}
 .face{width:96px;background:#1b1d24;border-radius:5px;display:flex;
       flex-direction:column;align-items:center;justify-content:center;gap:6px}
 .mouth{width:44px;background:#e2556a;border-radius:0 0 22px 22px/0 0 18px 18px;
        transition:height .05s linear,background .05s linear}
 .lipnum{font-size:11px;color:#8b93a3;font-variant-numeric:tabular-nums}
 .strip{position:relative;height:26px;margin-top:10px;border-radius:4px;
        overflow:hidden;background:#1b1d24;display:flex}
 .seg{height:100%;border-right:1px solid #20222a;box-sizing:border-box}
 .ph{position:absolute;top:0;bottom:0;width:2px;background:#fff;left:0;
     box-shadow:0 0 6px #fff;display:none}
 .legend{font-size:11px;color:#8b93a3;margin-top:6px}
 .sw{display:inline-block;width:10px;height:10px;border-radius:2px;
     vertical-align:-1px;margin:0 3px 0 10px}
 code{color:#9fb4e0}
</style>
<h1>__SCRIPT__ — 타이밍과 입 모양 (__MODE__)</h1>
<div class="hint">
 <code>.SET</code> 의 <b>u16</b> 항목을 그대로 재생합니다 —
 하위 12비트가 그 글자를 찍기 <i>전에</i> 기다리는 <b>밀리초</b>,
 상위 4비트가 <b>입 모양(0~8)</b>입니다.
 엔진은 입 모양을 표 <code>{0,2,1,0,1,2,2,1,1}</code> 로 3단계(다뭄·조금·크게)로 줄이고,
 글자를 찍은 뒤 90ms 까지 그 모양을 유지하다 90~110ms 는 1단계, 그 뒤엔 다뭅니다.
 여기서도 같은 규칙으로 그립니다.
</div>
<div class="ctl">
 배속 <input id="speed" type="number" value="1" step="0.1" min="0.1" style="width:56px">
 · 배율 <input id="ms" type="number" value="1" step="0.1" min="0.1" style="width:56px">
 · 음성 <input id="vrate" type="range" min="0.25" max="1.5" step="0.05" value="1"
   style="vertical-align:middle;width:150px"> <b id="vhz">__RATE__</b> Hz
</div>
<div id="root"></div>
<script>
const DATA = __DATA__;
const BASE_RATE = __RATE__;
const LIP = [0, 2, 1, 0, 1, 2, 2, 1, 1];   // 엔진의 9바이트 축약표
const H = [4, 13, 26];                     // 3단계 입 높이(px)
const COL = ['#4a4f5c', '#3d6fd8', '#d8a13d'];
const PAUSE = 250;

const root = document.getElementById('root');
const speedEl = document.getElementById('speed');
const msEl = document.getElementById('ms');
const vrateEl = document.getElementById('vrate');
const vhzEl = document.getElementById('vhz');
vrateEl.oninput = () => {
  vhzEl.textContent = Math.round(BASE_RATE * parseFloat(vrateEl.value));
};

DATA.forEach(d => {
  const chars = d.lines.join('\\n').split('');
  const total = d.ticks.reduce((a, b) => a + b, 0);
  // 글자 i 가 나타나는 누적 시각. ticks[i] 는 '찍기 전 대기'이므로 앞부터 더한다.
  const cum = [];
  let acc = 0;
  d.ticks.forEach(t => { acc += t; cum.push(acc); });

  const el = document.createElement('div');
  el.className = 'win';
  el.innerHTML = `<div class="head">
      <button>재생</button>
      <b>창 ${d.window}</b>
      <span class="tag">${d.voice || '무성'} · 글자 ${d.chars}
        · 항목 ${d.ticks.length} · 총 ${total}ms</span>
    </div>
    <div class="row">
      <div class="face">
        <div class="mouth"></div>
        <div class="lipnum">입 –</div>
      </div>
      <div class="stage"></div>
    </div>
    <div class="strip"><div class="ph"></div></div>
    <div class="legend">막대 하나가 항목 하나, 너비가 지속시간입니다.
      <span class="sw" style="background:${COL[0]}"></span>다뭄
      <span class="sw" style="background:${COL[1]}"></span>조금
      <span class="sw" style="background:${COL[2]}"></span>크게
      <span class="sw" style="background:#e2556a"></span>무음 쉼(${PAUSE}ms↑·입0)
      <span class="sw" style="background:${COL[2]};border-top:3px solid #e2556a"></span>긴 구간(입 열림)</div>`;
  root.appendChild(el);

  const strip = el.querySelector('.strip');
  const ph = el.querySelector('.ph');
  d.ticks.forEach((t, i) => {
    const s = document.createElement('div');
    s.className = 'seg';
    s.style.width = (t / total * 100) + '%';
    const lv = LIP[Math.min(8, d.shapes[i])];
    // 250ms 넘는 구간은 전부 '긴 구간'이지만, 입이 0 인 것만 진짜 무음이다.
    // 입이 열린 채 긴 것은 늘여 빼는 소리라 색을 유지하고 테두리만 준다.
    s.style.background = (t >= PAUSE && d.shapes[i] === 0) ? '#e2556a' : COL[lv];
    if (t >= PAUSE && d.shapes[i] !== 0) s.style.borderTop = '3px solid #e2556a';
    const ch = i < chars.length ? chars[i] : '«끝»';
    s.title = `[${i}] ${ch} · ${t}ms · 입${d.shapes[i]}(${lv}단계) `
            + `· 누적 ${cum[i]}ms`;
    strip.insertBefore(s, ph);
  });

  const btn = el.querySelector('button');
  const stage = el.querySelector('.stage');
  const mouth = el.querySelector('.mouth');
  const lipnum = el.querySelector('.lipnum');
  const audio = d.wav ? new Audio('data:audio/wav;base64,' + d.wav) : null;

  const setMouth = (lv, raw) => {
    mouth.style.height = H[lv] + 'px';
    mouth.style.background = lv ? '#e2556a' : '#6b3540';
    lipnum.textContent = raw === null ? '입 –' : `입 ${raw} → ${lv}단계`;
  };
  setMouth(0, null);

  btn.onclick = () => {
    const per = (parseFloat(msEl.value) || 1) / (parseFloat(speedEl.value) || 1);
    stage.textContent = '';
    ph.style.display = 'block';
    btn.disabled = true;
    if (audio) {
      audio.currentTime = 0;
      audio.playbackRate = parseFloat(vrateEl.value) || 1;
      audio.play();
    }
    const t0 = performance.now();
    let shown = -1;
    const frame = () => {
      // 데이터 시각. 실제 경과를 배속으로 나눠 쓰므로 오차가 쌓이지 않는다.
      const now = (performance.now() - t0) / per;
      let i = shown;
      while (i + 1 < cum.length && cum[i + 1] <= now) i++;
      if (i !== shown) {
        shown = i;
        stage.textContent = chars.slice(0, Math.min(shown + 1, chars.length))
                                 .join('');
      }
      if (shown >= 0) {
        // 마지막으로 찍은 글자로부터 얼마나 지났는지로 입을 닫아 간다
        const age = now - cum[shown];
        const raw = d.shapes[shown];
        setMouth(age < 90 ? LIP[Math.min(8, raw)] : age < 110 ? 1 : 0, raw);
      }
      ph.style.left = Math.min(100, now / total * 100) + '%';
      if (now < total) {
        requestAnimationFrame(frame);
      } else {
        setMouth(0, null);
        btn.disabled = false;
      }
    };
    requestAnimationFrame(frame);
  };
});
</script>
"""
