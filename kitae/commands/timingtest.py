# -*- coding: utf-8 -*-
"""타이밍 검증용 웹페이지를 만든다.

`.SET` 의 값(글자별 지속시간 ms + 입 모양)을 그대로 재생해, 음성과 맞는지
에뮬레이터 없이 눈과 귀로 확인한다. 자세한 형식은 docs/MTG-TIMING.md.

음성은 페이지에 넣지 않고 `work/voice/` 에 WAV 로 풀어 상대 경로로 건다.
스크립트 하나가 34MB / 16분이라 base64 로 심으면 페이지가 열리지 않는다.
"""
import base64
import io
import json
import os
import struct

from kitae.config import Config

GROUP = "inspect"
HELP = "타이밍 값과 음성을 브라우저에서 맞춰 보는 테스트 페이지를 만든다"

TEXT_SPEED = 100        # 타이밍이 없는 창의 기본 글자 속도(ms/자)


def configure(p):
    p.add_argument("script", nargs="?", default=None)
    p.add_argument("-w", "--windows", default="all",
                   help="창 번호 — all, 0-60, 1,2,5-9 (기본 all)")
    p.add_argument("--rate", type=int, default=18000, help="음성 재생 주파수")
    p.add_argument("--built", action="store_true",
                   help="원본 대신 빌드 산출물(work/build)의 번역문과 타이밍을 본다")
    p.add_argument("--text-speed", type=int, default=TEXT_SPEED,
                   help="타이밍이 없는 창의 글자 속도(ms/자)")
    p.add_argument("--embed", action="store_true",
                   help="음성을 페이지 안에 넣는다 (창 몇 개만 볼 때)")
    p.add_argument("-o", "--out", help="출력 HTML 경로")


def _voice_cabs(cfg):
    from kitae.core.cab import Cab
    out = {}
    for i in range(10):
        p = cfg.path(cfg["work_dir"], "cb", "RESOURCE", "WAV", f"{i}.CB")
        if os.path.exists(p):
            out[i] = Cab(p)
    return out


def _pick(spec, n):
    """'all' / '0-60' / '1,2,5-9' -> 창 번호 목록."""
    if not spec or spec.strip().lower() in ("all", "*"):
        return list(range(n))
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part[1:]:
            a, b = part.split("-", 1)
            out += list(range(int(a), min(int(b), n - 1) + 1))
        elif int(part) < n:
            out.append(int(part))
    return sorted(set(out))


def _chunks(lines):
    """줄 목록 -> (글자별 조각, 꼬리).

    인라인 마크업은 그려지지도, 타이밍 항목을 먹지도 않는다. 그래서 빼고 세야
    글자 수와 항목 수가 맞는다(display_len 과 같은 기준). 다만 그냥 지우면
    `&主人公名前&。東京に…` 이 `。東京に…` 가 되어 읽을 수 없으므로, 마크업을
    바로 뒤 글자에 붙여 둔다 — 그 글자가 찍힐 때 함께 나타난다.
    """
    from kitae.core.windows import MARKUP
    out, pending = [], ""
    for li, t in enumerate(lines):
        if li:
            pending += "\n"
        pos = 0
        for m in MARKUP.finditer(t):
            for ch in t[pos:m.start()]:
                out.append(pending + ch)
                pending = ""
            pending += m.group(0)
            pos = m.end()
        for ch in t[pos:]:
            out.append(pending + ch)
            pending = ""
    return out, pending


def run(args):
    from kitae.core.cab import Cab
    from kitae.core.windows import clss_objects, msg_table, MARKUP
    from kitae.core import adpcm
    from kitae.build import mtg as mtg_mod, hangul
    from kitae import translation

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

    # 화자·구분은 번역 작업 파일에 이미 있다 — 통독할 때 이게 있어야 읽힌다
    who = {}
    try:
        for e in translation.load(cfg, script)["entries"]:
            who.setdefault(e["window"], (e.get("speaker") or "",
                                         e.get("kind") or ""))
    except Exception:
        pass

    def wave_name(p):
        if len(p) < 2:
            return ""
        n = struct.unpack("<H", p[:2])[0]
        return p[2:2 + n].decode("ascii", "replace")

    voice_dir = os.path.join(work, "voice")
    if not args.embed:
        os.makedirs(voice_dir, exist_ok=True)

    items, wrote, reused = [], 0, 0
    for w in _pick(args.windows, len(sets)):
        lines, start = (table[w] if w < len(table) else (0, None))
        if start is None:
            continue
        rawtext = [strs[start + k] for k in range(lines)]
        marks = [m for t in rawtext for m in MARKUP.findall(t)]
        chunks, tail = _chunks(rawtext)
        nchars = len(chunks)
        if not nchars:
            continue

        got = mtg_mod.parse(sets[w]) if w < len(sets) else None
        if got:
            ticks, shapes = got
            synth = False
        else:
            # 타이밍이 없으면 엔진은 설정된 글자 속도로 균등하게 찍는다
            ticks = [args.text_speed] * nchars + [0]
            shapes = [0] * (nchars + 1)
            synth = True

        wav, name = "", wave_name(wsts[w]) if w < len(wsts) else ""
        if name:
            base = name.lower().replace(".wav", ".p04")
            idx = int(base[1]) if len(base) > 1 and base[1].isdigit() else None
            cab = cabs.get(idx)
            if cab:
                try:
                    pcm = adpcm.p04_to_wav(cab.read(base), args.rate)
                    if args.embed:
                        wav = "data:audio/wav;base64," + \
                            base64.b64encode(pcm).decode("ascii")
                    else:
                        fn = base.replace(".p04", ".wav")
                        dst = os.path.join(voice_dir, fn)
                        if os.path.exists(dst) and \
                                os.path.getsize(dst) == len(pcm):
                            reused += 1
                        else:
                            with open(dst, "wb") as fh:
                                fh.write(pcm)
                            wrote += 1
                        wav = "voice/" + fn
                except Exception:
                    pass

        sp, kind = who.get(w, ("", ""))
        items.append({"window": w, "voice": name, "ticks": ticks,
                      "shapes": shapes, "chunks": chunks, "tail": tail,
                      "chars": nchars, "wav": wav, "synth": synth,
                      "who": sp, "kind": kind, "mk": marks})

    name = "timing-built.html" if args.built else "timing.html"
    out = cfg.path(args.out or os.path.join(cfg["work_dir"], name))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(_HTML.replace("__DATA__", json.dumps(items, ensure_ascii=False))
                     .replace("__RATE__", str(args.rate))
                     .replace("__SCRIPT__", script)
                     .replace("__SPEED__", str(args.text_speed))
                     .replace("__MODE__", "빌드" if args.built else "원문"))

    voiced = sum(1 for i in items if i["wav"])
    ms = sum(sum(i["ticks"]) for i in items)
    print(f"{os.path.relpath(out, cfg.root)}  창 {len(items)}개 "
          f"(유성 {voiced} · 무성 {len(items) - voiced}), "
          f"총 {ms // 60000}분 {ms % 60000 // 1000}초")
    if not args.embed and (wrote or reused):
        print(f"음성 → work/voice/  새로 {wrote}개, 그대로 {reused}개")
    print("전체 재생을 누르면 창이 이어서 재생됩니다")
    return 0


_HTML = """<!doctype html>
<meta charset="utf-8">
<title>__SCRIPT__ 타이밍 · 입 모양 (__MODE__)</title>
<style>
 body{background:#20222a;color:#dfe3ea;font:14px/1.6 system-ui,sans-serif;
      margin:0;padding:24px 24px 60vh}
 h1{font-size:18px;margin:0 0 4px}
 .hint{color:#8b93a3;margin-bottom:10px;max-width:920px}
 .bar{position:sticky;top:0;z-index:9;background:#20222acc;backdrop-filter:blur(6px);
      padding:10px 0 12px;margin-bottom:14px;border-bottom:1px solid #333744}
 .ctl{background:#262932;border-radius:6px;padding:8px 12px;display:inline-block}
 .win{background:#2a2d37;border-radius:8px;padding:12px 14px;margin-bottom:10px;
      border-left:3px solid transparent}
 .win.on{border-left-color:#3d6fd8;background:#31353f}
 .win.mute{opacity:.62}
 .head{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
 .tag{color:#8b93a3;font-size:12px}
 .who{color:#f0c674;font-weight:600}
 .mk{font-size:11px;color:#20222a;background:#8b93a3;border-radius:3px;
     padding:1px 6px}
 button{background:#3d6fd8;color:#fff;border:0;border-radius:5px;
        padding:6px 14px;font-size:13px;cursor:pointer}
 button.sm{padding:4px 10px;font-size:12px}
 button.alt{background:#4a4f5c}
 button:disabled{background:#4a4f5c;cursor:default}
 .row{display:flex;gap:12px;align-items:stretch}
 .stage{background:#767a83;border-radius:5px;padding:9px 12px;min-height:70px;
        font-size:22px;letter-spacing:.04em;white-space:pre-wrap;flex:1;
        text-shadow:3px 3px 0 rgba(0,0,0,.8)}
 .face{width:84px;background:#1b1d24;border-radius:5px;display:flex;
       flex-direction:column;align-items:center;justify-content:center;gap:6px}
 .mouth{width:40px;height:4px;background:#6b3540;
        border-radius:0 0 20px 20px/0 0 16px 16px;
        transition:height .05s linear,background .05s linear}
 .lipnum{font-size:11px;color:#8b93a3;font-variant-numeric:tabular-nums}
 .strip{position:relative;height:22px;margin-top:8px;border-radius:4px;
        overflow:hidden;background:#1b1d24;display:flex}
 .seg{height:100%;border-right:1px solid #20222a;box-sizing:border-box}
 .ph{position:absolute;top:0;bottom:0;width:2px;background:#fff;left:0;
     box-shadow:0 0 6px #fff;display:none}
 .legend{font-size:11px;color:#8b93a3;margin:8px 0 0}
 .sw{display:inline-block;width:10px;height:10px;border-radius:2px;
     vertical-align:-1px;margin:0 3px 0 10px}
 code{color:#9fb4e0}
 input[type=number]{background:#1b1d24;color:#dfe3ea;border:1px solid #3c4150;
                    border-radius:4px;padding:2px 5px}
</style>
<h1>__SCRIPT__ — 타이밍과 입 모양 (__MODE__)</h1>
<div class="hint">
 <code>.SET</code> 의 <b>u16</b> 항목을 그대로 재생합니다 —
 하위 12비트가 그 글자를 찍기 <i>전에</i> 기다리는 <b>밀리초</b>,
 상위 4비트가 <b>입 모양(0~8)</b>입니다.
 엔진은 입 모양을 표 <code>{0,2,1,0,1,2,2,1,1}</code> 로 3단계로 줄이고, 글자를 찍은 뒤
 90ms 까지 유지하다 90~110ms 는 1단계, 그 뒤엔 다뭅니다.
 흐린 창은 타이밍이 없어 <b>__SPEED__ms/자</b> 기본값으로 찍는 창입니다.
</div>
<div class="bar"><div class="ctl">
 <button id="all">▶ 전체 재생</button>
 <button id="stop" class="alt" disabled>■ 정지</button>
 <span class="tag" id="pos"></span>
 · 창 간격 <input id="gap" type="number" value="600" step="100" min="0" style="width:64px">ms
 · 배속 <input id="speed" type="number" value="1" step="0.1" min="0.1" style="width:52px">
 · 음성 <input id="vrate" type="range" min="0.25" max="1.5" step="0.05" value="1"
   style="vertical-align:middle;width:120px"> <b id="vhz">__RATE__</b> Hz
</div></div>
<div id="root"></div>
<script>
const DATA = __DATA__;
const BASE_RATE = __RATE__;
const LIP = [0, 2, 1, 0, 1, 2, 2, 1, 1];   // 엔진의 9바이트 축약표
const H = [4, 13, 24];                     // 3단계 입 높이(px)
const COL = ['#4a4f5c', '#3d6fd8', '#d8a13d'];
const PAUSE = 250;

const root = document.getElementById('root');
const speedEl = document.getElementById('speed');
const gapEl = document.getElementById('gap');
const vrateEl = document.getElementById('vrate');
const vhzEl = document.getElementById('vhz');
const posEl = document.getElementById('pos');
const allBtn = document.getElementById('all');
const stopBtn = document.getElementById('stop');
vrateEl.oninput = () => {
  vhzEl.textContent = Math.round(BASE_RATE * parseFloat(vrateEl.value));
};

let token = 0;                 // 재생 세대. 정지하면 올려서 진행 중인 것을 버린다
const sleep = ms => new Promise(r => setTimeout(r, ms));

const players = DATA.map(d => {
  // 조각 하나가 타이밍 항목 하나에 대응한다. 마크업은 뒤 글자에 붙어 있다.
  const chars = d.chunks;
  const total = d.ticks.reduce((a, b) => a + b, 0);
  // 글자 i 가 나타나는 누적 시각. ticks[i] 는 '찍기 전 대기'이므로 앞부터 더한다.
  const cum = [];
  let acc = 0;
  d.ticks.forEach(t => { acc += t; cum.push(acc); });

  const el = document.createElement('div');
  el.className = 'win' + (d.synth ? ' mute' : '');
  el.innerHTML = `<div class="head">
      <button class="sm">재생</button>
      <b>창 ${d.window}</b>
      ${d.who ? `<span class="who">${d.who}</span>` : ''}
      <span class="tag">${d.kind || ''} ${d.voice || (d.synth ? '· 타이밍 없음' : '· 무성')}
        · 글자 ${d.chars} · ${(total / 1000).toFixed(1)}초</span>
      ${d.mk.length ? `<span class="mk">${d.mk.join(' ')}</span>` : ''}
    </div>
    <div class="row">
      <div class="face"><div class="mouth"></div><div class="lipnum">입 –</div></div>
      <div class="stage"></div>
    </div>
    <div class="strip"><div class="ph"></div></div>`;
  root.appendChild(el);

  const strip = el.querySelector('.strip');
  const ph = el.querySelector('.ph');
  if (!d.synth) {
    d.ticks.forEach((t, i) => {
      const s = document.createElement('div');
      s.className = 'seg';
      s.style.width = (t / total * 100) + '%';
      const lv = LIP[Math.min(8, d.shapes[i])];
      // 250ms 넘는 구간은 전부 '긴 구간'이지만, 입이 0 인 것만 진짜 무음이다.
      s.style.background = (t >= PAUSE && d.shapes[i] === 0) ? '#e2556a' : COL[lv];
      if (t >= PAUSE && d.shapes[i] !== 0) s.style.borderTop = '3px solid #e2556a';
      const ch = i < chars.length ? chars[i] : '«끝»';
      s.title = `[${i}] ${ch} · ${t}ms · 입${d.shapes[i]}(${lv}단계)`
              + ` · 누적 ${cum[i]}ms`;
      strip.insertBefore(s, ph);
    });
  }

  const btn = el.querySelector('button');
  const stage = el.querySelector('.stage');
  const mouth = el.querySelector('.mouth');
  const lipnum = el.querySelector('.lipnum');
  let audio = null;            // 창이 349개라 필요할 때 만든다

  const setMouth = (lv, raw) => {
    mouth.style.height = H[lv] + 'px';
    mouth.style.background = lv ? '#e2556a' : '#6b3540';
    lipnum.textContent = raw === null ? '입 –' : `입 ${raw} → ${lv}단계`;
  };

  function play(myToken, scroll) {
    return new Promise(resolve => {
      const per = 1 / (parseFloat(speedEl.value) || 1);
      stage.textContent = '';
      ph.style.display = 'block';
      el.classList.add('on');
      if (scroll) el.scrollIntoView({block: 'center', behavior: 'smooth'});
      if (d.wav) {
        if (!audio) { audio = new Audio(d.wav); audio.preload = 'none'; }
        audio.currentTime = 0;
        audio.playbackRate = parseFloat(vrateEl.value) || 1;
        audio.play().catch(() => {});
      }
      const t0 = performance.now();
      let shown = -1;
      const frame = () => {
        if (myToken !== token) {            // 정지됨
          if (audio) audio.pause();
          el.classList.remove('on');
          ph.style.display = 'none';
          setMouth(0, null);
          return resolve(false);
        }
        // 데이터 시각. 실제 경과를 배속으로 나눠 쓰므로 오차가 쌓이지 않는다.
        const now = (performance.now() - t0) / per;
        let i = shown;
        while (i + 1 < cum.length && cum[i + 1] <= now) i++;
        if (i !== shown) {
          shown = i;
          stage.textContent =
            chars.slice(0, Math.min(shown + 1, chars.length)).join('');
        }
        if (shown >= 0) {
          // 마지막으로 찍은 글자로부터 얼마나 지났는지로 입을 닫아 간다
          const age = now - cum[shown];
          const rawLip = d.shapes[shown];
          setMouth(age < 90 ? LIP[Math.min(8, rawLip)] : age < 110 ? 1 : 0, rawLip);
        }
        ph.style.left = Math.min(100, now / total * 100) + '%';
        if (now < total) return requestAnimationFrame(frame);
        stage.textContent = chars.join('') + d.tail;
        setMouth(0, null);
        el.classList.remove('on');
        resolve(true);
      };
      requestAnimationFrame(frame);
    });
  }

  btn.onclick = async () => {
    token++;
    const my = token;
    btn.disabled = true;
    await play(my, false);
    btn.disabled = false;
  };
  setMouth(0, null);
  return {d, play};
});

const legend = document.createElement('div');
legend.className = 'legend';
legend.innerHTML = `막대 하나가 항목 하나, 너비가 지속시간입니다.
  <span class="sw" style="background:${COL[0]}"></span>다뭄
  <span class="sw" style="background:${COL[1]}"></span>조금
  <span class="sw" style="background:${COL[2]}"></span>크게
  <span class="sw" style="background:#e2556a"></span>무음 쉼(${PAUSE}ms↑·입0)
  <span class="sw" style="background:${COL[2]};border-top:3px solid #e2556a"></span>긴 구간(입 열림)`;
document.querySelector('.bar').appendChild(legend);

allBtn.onclick = async () => {
  token++;
  const my = token;
  allBtn.disabled = true;
  stopBtn.disabled = false;
  for (let n = 0; n < players.length; n++) {
    if (my !== token) break;
    posEl.textContent = `${n + 1} / ${players.length}  (창 ${players[n].d.window})`;
    const ok = await players[n].play(my, true);
    if (!ok) break;
    // 실제 게임은 여기서 입력을 기다린다. 통독용으로 고정 간격을 준다.
    await sleep(parseInt(gapEl.value) || 0);
  }
  if (my === token) posEl.textContent = '끝';
  allBtn.disabled = false;
  stopBtn.disabled = true;
};

stopBtn.onclick = () => {
  token++;
  posEl.textContent = '정지';
  allBtn.disabled = false;
  stopBtn.disabled = true;
};
</script>
"""
