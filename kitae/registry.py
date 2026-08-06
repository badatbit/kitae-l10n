# -*- coding: utf-8 -*-
"""커맨드 모듈 자동 수집.

`kitae/commands/*.py` 안의 모듈이 그대로 서브커맨드가 된다. 각 모듈은
`GROUP`, `HELP`, `configure(parser)`, `run(args)` 를 노출하면 된다.
"""
import importlib
import os
import pkgutil

GROUPS = ["setup", "inspect", "work", "build"]
GROUP_TITLES = {
    "setup": "설정",
    "inspect": "조사",
    "work": "번역 작업",
    "build": "빌드",
}


def load_commands():
    import kitae.commands as pkg
    cmds = {}
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        m = importlib.import_module(f"kitae.commands.{mod.name}")
        if not hasattr(m, "run"):
            continue
        m.GROUP = getattr(m, "GROUP", "inspect")
        m.HELP = getattr(m, "HELP", (m.__doc__ or "").strip().splitlines()[0]
                         if m.__doc__ else "")
        if not hasattr(m, "configure"):
            m.configure = lambda p: None
        cmds[mod.name.replace("_", "-")] = m
    return cmds
