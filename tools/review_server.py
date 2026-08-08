# -*- coding: utf-8 -*-
"""번역 리뷰 GUI (로컬 웹).

    kitae gui                    # 브라우저가 자동으로 열린다
    python tools/review_server.py --port 8766 --no-open

## 왜 웹인가
볼 게 2만 6천 줄이고 한·일 문자가 섞인다. 무한 스크롤·즉시 검색·글꼴 폴백을
브라우저가 공짜로 해 준다. **새 의존성은 없다** — stdlib `http.server` 와 인라인
HTML 뿐이라 `pyproject.toml` 을 건드리지 않는다.

## ★ 번역 원장은 건드리지 않는다
`translation/**.json` 은 **읽기만** 한다. 판정과 메모는 `data/review.json` 에 따로
쌓는다. 같은 레포에서 `translation/src/*.py` 를 돌려 원장을 다시 쓰는 일이 잦은데,
GUI 가 원장을 쓰면 서로 덮어쓴다.

    data/review.json = {"rows": {"<키>": {"verdict": "ok|hold|fix",
                                          "note": "...", "at": "..."}}}

키는 **`<원장>:<창>:<줄>`** 이다. 창·줄은 엔진이 정한 값이라 번역을 고쳐도 안 변한다.
원문(ja)은 같은 게 수백 개라 키가 될 수 없다 — `風呂` 의 「あれ？そんな名前だっけ？」
하나만 해도 １４일치가 있다.

시스템 문자열(`translation/ui/*.json`)에는 창·줄이 없어 **전부 `0:0`** 이다. 그대로
쓰면 한 모듈의 판정이 서로 덮어쓴다. 이쪽은 PE 안의 바이트 오프셋을 써서
`<원장>:@<오프셋>` 으로 잡는다.

## 날짜·이벤트 순으로 낸다
번역 정책 4번이다. 창 번호 순서는 곧 이야기 순서가 아니다 — `風呂` 는 １４일치가
한 파일에 섞여 있고 스크립트 ３３개 중 １８개가 어긋난다. 그래서 정렬 열쇠는

    날짜 → 시간대(朝·午前·昼·午後·夕方·夜) → 씬 → 창 → 줄

이고, 이건 `kitae.core.scenemap.order_key` 와 같은 규칙이다([[scenemap]]).
날짜가 없는 것(노래·선택지·공용 스크립트)은 뒤로 몰린다.

## 질의(ask)
옮긴 쪽이 판단을 미룬 자리다. 항목에 `ask:[{why, state}]` 로 붙어 있고 `state` 가
`open` 이면 대기다. **리뷰에서 가장 먼저 볼 곳**이라 따로 세고 거를 수 있게 했다.
`kitae review out/apply` 와 같은 원장을 본다 — 여기서 판정만 하고 문구 수정은
`review apply` 로 돌리는 게 안전하다.

## 폭 검사
대사·가이드는 메시지 창이라 한 줄이 **전각 ２５칸**이다(엔진이 ２５번째에서
자른다). 반각은 반 칸, 마크업(`@S@` `&主人公&`)은 그려지지 않으므로 빼고 센다.

시스템 문자열은 화면마다 상자 폭이 달라 고정값을 못 쓴다. 대신 **원문보다
길어졌는가**로 본다 — 원문이 그 상자에 들어갔다는 것만은 확실하다. 또 한
항목에 `\\n` 으로 여러 줄이 들어 있으므로 **가장 긴 줄**로 잰다. 통째로 세면
멀쩡한 안내문이 전부 넘친 것으로 나온다(처음에 ４１건이 그렇게 잡혔다).
"""
import argparse
import datetime
import io
import json
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANS = os.path.join(ROOT, "translation")
STORE = os.path.join(ROOT, "data", "review.json")
MARKUP = re.compile(r"@[^@]{0,8}@|&[^&]{0,16}&")
SLOTS = ("朝", "午前", "昼", "午後", "夕方", "夜")
MAX_CELLS = 25

_lock = threading.Lock()
ROWS = []
META = {}


# ── 폭 ────────────────────────────────────────────────────────────────
def _cells1(s):
    n = 0.0
    for c in MARKUP.sub("", s or ""):
        try:
            n += 0.5 if len(c.encode("cp932")) == 1 else 1
        except UnicodeEncodeError:
            n += 1
    return n


def cells(s):
    """가장 긴 줄의 칸 수. 전각 １, 반각 ０.５.

    시스템 문자열 하나에 `\\n` 으로 여러 줄이 들어 있다(안내문·아이템 설명).
    폭 제한은 **줄마다** 걸리므로 통째로 세면 멀쩡한 것이 넘친 것으로 보인다.
    """
    return max((_cells1(x) for x in (s or "").split("\n")), default=0.0)


def over(cat, ja, ko):
    """이 줄이 넘쳤는가.

    대사·가이드는 메시지 창이라 **전각 ２５칸**이 한 줄이다. 시스템 문자열은
    화면마다 상자 폭이 달라서 고정값을 쓸 수 없다 — 대신 **원문보다 길어졌는가**
    로 본다. 원문이 그 상자에 들어갔다는 건 확실하니까. 한두 칸 차이는 흔하므로
    ２칸 넘게 길어진 것만 잡는다.
    """
    if not (ko or "").strip():
        return False
    if cat == "시스템":
        # 한두 칸 길어지는 건 흔하고 상자에도 여유가 있다. 눈에 띄게
        # 길어진 것만 잡는다 — 아니면 224건이 떠서 아무도 안 본다.
        return cells(ko) > cells(ja) + 2
    return cells(ko) > MAX_CELLS


def halfwidth(s):
    out = []
    for c in MARKUP.sub("", s or ""):
        try:
            if len(c.encode("cp932")) == 1:
                out.append(c)
        except UnicodeEncodeError:
            pass
    return out


# ── 원장 읽기 ─────────────────────────────────────────────────────────
def _docs():
    """(분류, 원장이름, 경로) — 대사·가이드·시스템 셋으로 나눈다."""
    out = []
    for f in sorted(os.listdir(TRANS)):
        if f.endswith(".json"):
            out.append(("대사", f[:-5], os.path.join(TRANS, f)))
    for cat, sub in (("가이드", "guide"), ("시스템", "ui")):
        d = os.path.join(TRANS, sub)
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith(".json"):
                    out.append((cat, f[:-5], os.path.join(d, f)))
    return out


def _asks(e):
    a = e.get("ask")
    if isinstance(a, dict):
        return [a]
    return a or []


def order_key(r):
    """날짜 → 시간대 → 씬 → 창 → 줄. 날짜 없는 것은 뒤로."""
    return (r["date"] or "99-99",
            SLOTS.index(r["slot"]) if r["slot"] in SLOTS else 9,
            r["scene"] if r["scene"] is not None else 9999,
            r["window"], r["line"])


def load_rows():
    rows = []
    for cat, name, path in _docs():
        try:
            with io.open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except Exception:
            continue
        if not isinstance(doc, dict) or not doc.get("entries"):
            continue
        for e in doc["entries"]:
            t = e.get("text") or {}
            ja, ko = t.get("ja", ""), (t.get("ko") or "")
            w = e.get("window", 0)
            ln = e.get("line", 0)
            asks = _asks(e)
            # 시스템 문자열은 창·줄이 없다 — 전부 0:0 이라 키가 겹친다.
            # PE 안의 바이트 오프셋이 그 항목의 불변 식별자다.
            off = e.get("offset")
            ident = f"@{off}" if off is not None else f"{w}:{ln}"
            rows.append({
                "key": f"{name}:{ident}", "at": ident,
                "cat": cat, "doc": name, "window": w, "line": ln,
                "who": e.get("speaker") or "", "kind": e.get("kind") or "",
                "date": e.get("date"), "slot": e.get("slot"),
                "place": e.get("place") or "", "scene": e.get("scene"),
                "ja": ja, "ko": ko,
                "cells": cells(ko), "jacells": cells(ja),
                "over": over(cat, ja, ko),
                "half": "".join(halfwidth(ko)),
                "ask": asks,
                "open": sum(1 for a in asks if a.get("state", "open") == "open"),
            })
    rows.sort(key=order_key)
    return rows


def build_meta(rows):
    docs, whos, dates = {}, {}, {}
    for r in rows:
        docs[r["doc"]] = docs.get(r["doc"], 0) + 1
        if r["who"]:
            whos[r["who"]] = whos.get(r["who"], 0) + 1
        d = r["date"] or "-"
        dates[d] = dates.get(d, 0) + 1
    done = sum(1 for r in rows if r["ko"].strip())
    return {
        "total": len(rows), "done": done,
        "open": sum(r["open"] for r in rows),
        "over": sum(1 for r in rows if r["over"]),
        "docs": sorted(docs.items()),
        "whos": sorted(whos.items(), key=lambda kv: -kv[1])[:40],
        "dates": sorted(dates.items()),
        "cats": sorted({r["cat"] for r in rows}),
        "max": MAX_CELLS,
    }


def reload_all():
    global ROWS, META, _STAMP
    with _lock:
        ROWS = load_rows()
        META = build_meta(ROWS)
        _STAMP = _mtime()
    return META


_STAMP = None


def _mtime():
    """원장 전체의 최신 수정 시각. 파일 목록이 바뀌어도 값이 달라진다."""
    t = 0.0
    n = 0
    for _cat, _name, path in _docs():
        try:
            t = max(t, os.path.getmtime(path))
            n += 1
        except OSError:
            pass
    return (t, n)


def ensure_fresh():
    """원장이 바뀌었으면 다시 읽는다.

    `translation/src/*.py` 를 돌려 원장을 갱신하는 일이 잦은데, 켜 둔 GUI 가
    시작 때 읽은 것만 들고 있으면 **방금 넣은 번역이 검색에 안 걸린다.**
    실제로 `도립문서관` 을 못 찾아 한참 헤맸다. 요청마다 mtime 만 훑어
    (파일 ３６개, 수 ms) 달라졌을 때만 다시 읽는다.
    """
    if _STAMP != _mtime():
        reload_all()
        return True
    return False


# ── 판정 저장 ─────────────────────────────────────────────────────────
def load_review():
    try:
        with io.open(STORE, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:
        d = {}
    d.setdefault("rows", {})
    return d


def save_one(key, verdict=None, note=None):
    with _lock:
        d = load_review()
        cur = d["rows"].get(key) or {}
        if verdict is not None:
            cur["verdict"] = verdict or None
        if note is not None:
            cur["note"] = note
        cur["at"] = datetime.datetime.now().isoformat(timespec="seconds")
        if not cur.get("verdict") and not (cur.get("note") or "").strip():
            d["rows"].pop(key, None)
        else:
            d["rows"][key] = cur
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        tmp = STORE + ".tmp"
        with io.open(tmp, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(d, ensure_ascii=False, indent=1) + "\n")
        os.replace(tmp, STORE)
    return True


# ── 질의 ──────────────────────────────────────────────────────────────
def query(q, cat, doc, who, date, status, verdict, ask, limit, offset):
    rv = load_review()["rows"]
    ql = (q or "").strip().lower()
    out, total = [], 0
    for r in ROWS:
        if cat and r["cat"] != cat:
            continue
        if doc and r["doc"] != doc:
            continue
        if who and r["who"] != who:
            continue
        if date and (r["date"] or "-") != date:
            continue
        if status == "todo" and r["ko"].strip():
            continue
        if status == "done" and not r["ko"].strip():
            continue
        if status == "over" and not r["over"]:
            continue
        if status == "half" and not r["half"]:
            continue
        if ask == "open" and not r["open"]:
            continue
        rr = rv.get(r["key"]) or {}
        if verdict and (rr.get("verdict") or "") != verdict:
            continue
        if ql and ql not in r["ja"].lower() and ql not in r["ko"].lower():
            continue
        total += 1
        if total <= offset:
            continue
        if len(out) >= limit:
            continue
        out.append(dict(r, review=rr))
    return {"total": total, "rows": out, "meta": META}


def doc_list(cat):
    """원장(스크립트) 단위 진행률. 번역 단위를 스크립트 전체로 바꾼 뒤로
    이쪽이 실제 작업 단위다 — 날짜로 자르면 구멍이 생긴다([[scenemap]])."""
    out, by = [], {}
    for r in ROWS:
        if cat and r["cat"] != cat:
            continue
        d = by.get(r["doc"])
        if d is None:
            d = by[r["doc"]] = {"doc": r["doc"], "cat": r["cat"], "n": 0,
                                "done": 0, "open": 0, "over": 0,
                                "date": r["date"], "date2": r["date"]}
            out.append(d)
        d["n"] += 1
        d["done"] += 1 if r["ko"].strip() else 0
        d["open"] += r["open"]
        d["over"] += 1 if r["over"] else 0
        if r["date"]:
            d["date"] = min(d["date"] or r["date"], r["date"])
            d["date2"] = max(d["date2"] or r["date"], r["date"])
    out.sort(key=lambda d: (d["done"] == d["n"], d["date"] or "99-99", d["doc"]))
    return out


def scene_list(cat, doc):
    """날짜·시간대·장소로 묶은 목차. 정책 4번의 '이벤트 순'이 이것이다."""
    seen, out = {}, []
    for r in ROWS:
        if cat and r["cat"] != cat:
            continue
        if doc and r["doc"] != doc:
            continue
        k = (r["doc"], r["date"], r["slot"], r["scene"])
        s = seen.get(k)
        if s is None:
            s = seen[k] = {"doc": r["doc"], "date": r["date"], "slot": r["slot"],
                           "scene": r["scene"], "place": r["place"],
                           "n": 0, "done": 0, "open": 0, "over": 0,
                           "w0": r["window"]}
            out.append(s)
        s["n"] += 1
        s["done"] += 1 if r["ko"].strip() else 0
        s["open"] += r["open"]
        s["over"] += 1 if r["over"] else 0
    return out


PAGE = r"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>北へ。 번역 리뷰</title><style>
:root{--bg:#15171c;--fg:#e6e8ee;--dim:#8b93a3;--line:#2a2e38;--acc:#5aa9ff;
 --ok:#4ec97a;--hold:#e8b84b;--fix:#ef6b6b;--warn:#ff8a5c}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:13px/1.55 "Malgun Gothic",system-ui,sans-serif}
header{display:flex;gap:6px;align-items:center;padding:7px 10px;
 border-bottom:1px solid var(--line);flex-wrap:wrap}
button,select,input{background:#1e222b;color:var(--fg);border:1px solid var(--line);
 border-radius:5px;padding:5px 9px;font:inherit}
button{cursor:pointer}button:hover{border-color:var(--acc)}
button.on{background:var(--acc);color:#0b0d11;border-color:var(--acc)}
input[type=text]{min-width:200px}
#bar{margin-left:auto;color:var(--dim);font-size:12px}
#wrap{display:grid;grid-template-columns:260px 1fr 420px;height:calc(100vh - 46px)}
#toc,#list,#side{overflow:auto}
#toc{border-right:1px solid var(--line);padding:6px}
#list{border-right:1px solid var(--line)}
#side{padding:12px}
table{border-collapse:collapse;width:100%}
td{padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}
tr.sel td{background:#1d2430;box-shadow:inset 2px 0 0 var(--acc)}
tr:hover td{background:#191d25}
.ja{color:var(--dim)}
.who{color:var(--acc);font-size:11px;white-space:nowrap}
.meta{color:var(--dim);font-size:11px;white-space:nowrap}
.over{color:var(--warn);font-weight:bold}
.badge{display:inline-block;min-width:16px;text-align:center;border-radius:8px;
 padding:0 5px;font-size:11px;background:#33261a;color:var(--hold)}
.v-ok{color:var(--ok)}.v-hold{color:var(--hold)}.v-fix{color:var(--fix)}
.scene{padding:4px 6px;border-radius:5px;cursor:pointer;font-size:12px}
.scene:hover{background:#1d2430}
.scene.on{background:#1d2430;box-shadow:inset 2px 0 0 var(--acc)}
.scene .p{color:var(--dim)}
h4{margin:12px 0 5px;font-size:12px;color:var(--dim);
 border-bottom:1px solid var(--line);padding-bottom:3px}
pre{white-space:pre-wrap;word-break:break-all;margin:4px 0;font:inherit}
.ask{background:#1c1f27;border-left:2px solid var(--hold);padding:6px 8px;margin:6px 0}
textarea{width:100%;min-height:60px;background:#1e222b;color:var(--fg);
 border:1px solid var(--line);border-radius:5px;padding:6px;font:inherit}
.ruler{font-family:"MS Gothic",monospace;color:var(--dim);font-size:11px}
</style></head><body>
<header>
 <input type="text" id="q" placeholder="원문·번역 검색">
 <select id="cat"></select><select id="doc"></select>
 <select id="who"></select><select id="date"></select>
 <select id="status">
  <option value="">전체</option><option value="todo">미번역</option>
  <option value="done">번역됨</option><option value="over">폭 넘침</option>
  <option value="half">반각 섞임</option></select>
 <select id="verdict">
  <option value="">판정 전체</option><option value="ok">확인</option>
  <option value="hold">보류</option><option value="fix">고칠 것</option></select>
 <button id="askbtn">질의만</button>
 <button id="tocmode">목차: 원장</button>
 <span id="bar"></span>
</header>
<div id="wrap"><div id="toc"></div><div id="list"></div><div id="side"></div></div>
<script>
let rows=[],meta=null,sel=null,off=0,total=0,askOnly=false,scene=null;
let tocDoc=true,tocList=[],pick0=null;
const $=s=>document.querySelector(s);
const esc=s=>(s||"").replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
async function getJSON(u){try{const r=await fetch(u,{cache:'no-store'});
 return r.ok?await r.json():null}catch(e){return null}}
async function post(u,b){try{const r=await fetch(u,{method:'POST',
 headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
 return r.ok}catch(e){return false}}

function opts(el,list,all){el.innerHTML='<option value="">'+all+'</option>'+
 list.map(([k,n])=>'<option value="'+esc(k)+'">'+esc(k)+' ('+n+')</option>').join('')}

function params(){const p=new URLSearchParams();
 for(const k of ['q','cat','doc','who','date','status','verdict']){
   const v=$('#'+k).value; if(v) p.set(k,v)}
 if(askOnly) p.set('ask','open');
 if(scene){p.set('doc',scene.doc); if(scene.scene!==null)p.set('scene',scene.scene)}
 return p}

async function load(reset){
 if(reset){off=0}
 const p=params(); p.set('limit',300); p.set('offset',off);
 const d=await getJSON('/api/rows?'+p); if(!d) return;
 meta=d.meta; total=d.total; rows=d.rows; draw(); bar()}

function bar(){if(!meta)return;
 $('#bar').textContent=`보임 ${rows.length} / 걸린 ${total} · 전체 ${meta.total} · `
  +`번역 ${meta.done} · 질의 ${meta.open} · 폭넘침 ${meta.over}`}

function draw(){
 $('#list').innerHTML='<table>'+rows.map((r,i)=>{
  const v=(r.review&&r.review.verdict)||'';
  const mark=v?'<span class="v-'+v+'">●</span> ':'';
  const over=r.over?' class="over"':'';
  return '<tr data-i="'+i+'"'+(sel&&sel.key===r.key?' class="sel"':'')+'>'
   +'<td class="meta">'+mark+esc(r.doc)+' '+esc(r.at)
     +(r.date?'<br>'+esc(r.date)+(r.slot?' '+esc(r.slot):''):'')+'</td>'
   +'<td class="who">'+esc(r.who)+'</td>'
   +'<td><div class="ja">'+esc(r.ja)+'</div><div'+over+'>'+esc(r.ko||'—')+'</div></td>'
   +'<td class="meta">'+(r.ko?r.cells:'')+(r.open?' <span class="badge">?'+r.open+'</span>':'')+'</td>'
   +'</tr>'}).join('')+'</table>'
 $('#list').querySelectorAll('tr').forEach(tr=>tr.onclick=()=>pick(+tr.dataset.i))}

function ruler(n){let s='';for(let i=1;i<=meta.max;i++)s+=(i%5===0?'|':'·');
 return '<div class="ruler">'+s+'  '+n+'/'+meta.max+'</div>'}

function pick(i){sel=rows[i];draw();
 const r=sel,v=(r.review&&r.review.verdict)||'';
 $('#side').innerHTML=
  '<h4>자리</h4><div class="meta">'+esc(r.cat)+' · '+esc(r.doc)
   +' · '+esc(r.at)
   +(r.scene!==null?' · 씬 '+r.scene:'')+'</div>'
  +'<div class="meta">'+(r.date?esc(r.date):'날짜 없음')
   +(r.slot?' '+esc(r.slot):'')+(r.place?' · '+esc(r.place):'')+'</div>'
  +(r.who?'<div class="who">'+esc(r.who)+(r.kind?' ('+esc(r.kind)+')':'')+'</div>':'')
  +'<h4>원문</h4><pre>'+esc(r.ja)+'</pre>'
  +'<h4>번역</h4><pre'+(r.cells>meta.max?' class="over"':'')+'>'+esc(r.ko||'—')+'</pre>'
  +ruler(r.cells)+(r.over?'<div class="over">원문 '+r.jacells+'칸보다 길다</div>':'')
  +(r.half?'<div class="over">반각 '+esc(r.half)+'</div>':'')
  +(r.ask.length?'<h4>질의</h4>'+r.ask.map(a=>'<div class="ask">['
     +esc(a.state||'open')+'] '+esc(a.why)+'</div>').join(''):'')
  +'<h4>판정</h4><div>'
   +['ok:확인','hold:보류','fix:고칠 것'].map(x=>{const[k,t]=x.split(':');
     return '<button class="vb'+(v===k?' on':'')+'" data-v="'+k+'">'+t+'</button>'}).join(' ')
   +' <button class="vb" data-v="">지움</button></div>'
  +'<h4>메모</h4><textarea id="note">'+esc((r.review&&r.review.note)||'')+'</textarea>'
  +'<div class="meta">'+((r.review&&r.review.at)||'')+'</div>';
 $('#side').querySelectorAll('.vb').forEach(b=>b.onclick=async()=>{
   r.review=r.review||{}; r.review.verdict=b.dataset.v||null;
   await post('/api/review/rows',{key:r.key,verdict:b.dataset.v}); pick(i)});
 $('#note').onchange=async e=>{r.review=r.review||{};r.review.note=e.target.value;
   await post('/api/review/rows',{key:r.key,note:e.target.value})}}

async function toc(){
 const p=new URLSearchParams();
 for(const k of ['cat','doc']){const v=$('#'+k).value; if(v)p.set(k,v)}
 if(tocDoc){
   const list=await getJSON('/api/docs?'+p); if(!list)return; tocList=list;
   $('#toc').innerHTML='<div class="scene'+(pick0?'':' on')+'" data-i="-1">전체</div>'
    +list.map((d,i)=>{const pct=d.n?Math.round(d.done*100/d.n):0;
     const cls=pct===100?'v-ok':(pct?'v-hold':'');
     return '<div class="scene'+(pick0&&pick0.doc===d.doc&&!pick0.scene0?' on':'')
      +'" data-i="'+i+'"><b class="'+cls+'">'+esc(d.doc)+'</b> '
      +'<span class="p">'+pct+'% '+d.done+'/'+d.n
      +(d.open?' ?'+d.open:'')+(d.over?' ⚠'+d.over:'')+'</span>'
      +'<br><span class="p">'+esc(d.cat)+(d.date?' · '+d.date+(d.date2!==d.date?'~'+d.date2:''):'')
      +'</span></div>'}).join('');
 }else{
   const list=await getJSON('/api/scenes?'+p); if(!list)return; tocList=list;
   $('#toc').innerHTML='<div class="scene'+(pick0?'':' on')+'" data-i="-1">전체</div>'
    +list.map((s,i)=>{const pct=s.n?Math.round(s.done*100/s.n):0;
     return '<div class="scene'+(pick0&&pick0.doc===s.doc&&pick0.scene===s.scene?' on':'')
      +'" data-i="'+i+'"><b>'+(s.date||'—')+'</b> '+esc(s.slot||'')
      +' <span class="p">'+pct+'% '+s.n+'줄'
      +(s.open?' ?'+s.open:'')+(s.over?' ⚠'+s.over:'')+'</span>'
      +'<br><span class="p">'+esc(s.doc)+(s.place?' · '+esc(s.place):'')+'</span></div>'}).join('');
 }
 $('#toc').querySelectorAll('.scene').forEach(d=>d.onclick=()=>{
   const i=+d.dataset.i;
   if(i<0){pick0=null; scene=null}
   else if(tocDoc){pick0=tocList[i]; pick0.scene0=true; scene=null;
                   $('#doc').value=tocList[i].doc}
   else {pick0=tocList[i]; scene=tocList[i]}
   toc(); load(true)})}

$('#tocmode').onclick=()=>{tocDoc=!tocDoc; pick0=null; scene=null;
 $('#tocmode').textContent='목차: '+(tocDoc?'원장':'날짜'); toc(); load(true)};

for(const k of ['cat','doc','who','date','status','verdict'])
  $('#'+k).onchange=()=>{if(k==='cat'||k==='doc'){scene=null;toc()}load(true)};
$('#q').oninput=()=>{clearTimeout(window._t);window._t=setTimeout(()=>load(true),200)};
$('#askbtn').onclick=e=>{askOnly=!askOnly;e.target.classList.toggle('on',askOnly);load(true)};
$('#list').onscroll=e=>{const el=e.target;
 if(el.scrollTop+el.clientHeight>el.scrollHeight-80&&rows.length<total){
   off=rows.length; const p=params(); p.set('limit',300); p.set('offset',off);
   getJSON('/api/rows?'+p).then(d=>{if(d){rows=rows.concat(d.rows);draw();bar()}})}};
document.onkeydown=e=>{if(e.target.tagName==='TEXTAREA'||e.target.tagName==='INPUT')return;
 const i=sel?rows.findIndex(r=>r.key===sel.key):-1;
 if(e.key==='j'&&i<rows.length-1)pick(i+1);
 if(e.key==='k'&&i>0)pick(i-1);
 if('123'.includes(e.key)&&sel){const v=['ok','hold','fix'][+e.key-1];
  post('/api/review/rows',{key:sel.key,verdict:v}).then(()=>{
   sel.review=sel.review||{};sel.review.verdict=v;pick(i)})}};

(async()=>{const m=await getJSON('/api/meta'); if(!m)return; meta=m;
 opts($('#cat'),m.cats.map(c=>[c,0]),'분류 전체');
 $('#cat').innerHTML='<option value="">분류 전체</option>'
   +m.cats.map(c=>'<option value="'+c+'">'+c+'</option>').join('');
 opts($('#doc'),m.docs,'원장 전체');
 opts($('#who'),m.whos,'화자 전체');
 opts($('#date'),m.dates,'날짜 전체');
 await toc(); await load(true)})();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)

        def g(k, d=""):
            return (qs.get(k) or [d])[0]

        if u.path in ("/", "/index.html"):
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if u.path.startswith("/api/"):
            ensure_fresh()
        if u.path == "/api/meta":
            return self._send(200, json.dumps(META, ensure_ascii=False))
        if u.path == "/api/rows":
            d = query(g("q"), g("cat"), g("doc"), g("who"), g("date"),
                      g("status"), g("verdict"), g("ask"),
                      int(g("limit", "300")), int(g("offset", "0")))
            sc = g("scene")
            if sc != "":
                s = int(sc)
                d["rows"] = [r for r in d["rows"] if r["scene"] == s]
                d["total"] = len(d["rows"])
            return self._send(200, json.dumps(d, ensure_ascii=False))
        if u.path == "/api/docs":
            return self._send(200, json.dumps(doc_list(g("cat")),
                                              ensure_ascii=False))
        if u.path == "/api/scenes":
            return self._send(200, json.dumps(
                scene_list(g("cat"), g("doc")), ensure_ascii=False))
        if u.path == "/api/reload":
            return self._send(200, json.dumps(reload_all(), ensure_ascii=False))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, json.dumps({"error": "bad json"}))
        if u.path == "/api/review/rows":
            key = body.get("key")
            if not key:
                return self._send(400, json.dumps({"error": "no key"}))
            save_one(key, body.get("verdict") if "verdict" in body else None,
                     body.get("note") if "note" in body else None)
            return self._send(200, json.dumps({"ok": True}))
        return self._send(404, json.dumps({"error": "not found"}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--no-open", action="store_true", dest="no_open")
    a = ap.parse_args()
    m = reload_all()
    print(f"줄 {m['total']:,} · 번역 {m['done']:,} · 질의 {m['open']} · "
          f"폭 넘침 {m['over']}")
    url = f"http://127.0.0.1:{a.port}/"
    print(f"리뷰 GUI  {url}   (Ctrl+C 로 종료)")
    if not a.no_open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
