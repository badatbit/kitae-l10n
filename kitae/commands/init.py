# -*- coding: utf-8 -*-
"""저장소 초기화 — kitae.config.json 과 작업 디렉터리 생성."""
import os

from kitae.config import CONFIG_NAME, Config, repo_root

GROUP = "setup"
HELP = "설정 파일과 작업 디렉터리를 만든다"


def configure(p):
    p.add_argument("--orig", help="원본 GDI 덤프 디렉터리")
    p.add_argument("--ttf", help="한글 글리프를 뽑을 폰트 파일")
    p.add_argument("--lang", action="append",
                   help="관리할 언어 키 (여러 번 지정 가능; 기본 ja,ko)")
    p.add_argument("--force", action="store_true", help="이미 있어도 덮어쓴다")


def run(args):
    root = repo_root()
    cfg = Config.load(root)
    if cfg.exists and not args.force:
        print(f"{CONFIG_NAME} 이 이미 있습니다 ({root}). 덮어쓰려면 --force")
        return 1

    if args.orig:
        cfg["orig_dir"] = args.orig
    if args.ttf:
        cfg["font"]["ttf"] = args.ttf
    if args.lang:
        cfg["languages"] = list(dict.fromkeys(args.lang))
        if cfg["source"] not in cfg["languages"]:
            cfg["source"] = cfg["languages"][0]
        if cfg["target"] not in cfg["languages"]:
            cfg["target"] = cfg["languages"][-1]

    for d in ("data", "translation", cfg["work_dir"], cfg["out_dir"]):
        os.makedirs(cfg.path(d), exist_ok=True)
    p = cfg.save()
    print(f"생성: {p}")
    print(f"  언어    : {cfg['languages']}  (원문 {cfg['source']} → {cfg['target']})")
    print(f"  원본    : {cfg['orig_dir'] or '(미설정 — kitae config set orig_dir …)'}")
    print(f"  디렉터리: data/ translation/ {cfg['work_dir']}/ {cfg['out_dir']}/")
    print("\n다음: kitae check")
