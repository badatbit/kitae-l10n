# -*- coding: utf-8 -*-
"""설정 조회/변경."""
import json

from kitae.config import Config

GROUP = "setup"
HELP = "설정을 보거나 바꾼다"


def configure(p):
    sub = p.add_subparsers(dest="action")
    sub.add_parser("show", help="전체 설정 출력")
    g = sub.add_parser("get", help="값 하나 출력")
    g.add_argument("key")
    s = sub.add_parser("set", help="값 설정 (점 표기 지원: font.ttf)")
    s.add_argument("key")
    s.add_argument("value")
    la = sub.add_parser("lang", help="언어 추가/제거/지정")
    la.add_argument("--add", action="append")
    la.add_argument("--remove", action="append")
    la.add_argument("--target")
    la.add_argument("--source")


def _dig(d, key, value=None, set_=False):
    parts = key.split(".")
    cur = d
    for k in parts[:-1]:
        cur = cur.setdefault(k, {})
    if set_:
        old = cur.get(parts[-1])
        # 원래 타입을 최대한 유지한다 (숫자/불리언 설정이 문자열로 바뀌면 곤란)
        if isinstance(old, bool):
            value = value.lower() in ("1", "true", "yes", "on")
        elif isinstance(old, int) and not isinstance(old, bool):
            value = int(value)
        elif isinstance(old, list):
            value = [v.strip() for v in value.split(",") if v.strip()]
        cur[parts[-1]] = value
        return value
    return cur.get(parts[-1])


def run(args):
    cfg = Config.load()
    action = getattr(args, "action", None) or "show"

    if action == "show":
        print(json.dumps(dict(cfg), ensure_ascii=False, indent=2))
        return 0
    if action == "get":
        print(_dig(cfg, args.key))
        return 0
    if action == "set":
        v = _dig(cfg, args.key, args.value, set_=True)
        cfg.save()
        print(f"{args.key} = {v!r}")
        return 0
    if action == "lang":
        langs = list(cfg["languages"])
        for l in (args.add or []):
            if l not in langs:
                langs.append(l)
        for l in (args.remove or []):
            if l in langs:
                langs.remove(l)
        cfg["languages"] = langs
        if args.source:
            cfg["source"] = cfg.check_lang(args.source)
        if args.target:
            cfg["target"] = cfg.check_lang(args.target)
        cfg.save()
        print(f"languages={cfg['languages']}  source={cfg['source']}  "
              f"target={cfg['target']}")
        return 0
    print("kitae config {show|get|set|lang} …")
    return 1
