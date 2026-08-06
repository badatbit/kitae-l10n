# -*- coding: utf-8 -*-
"""kitae CLI 진입점. 모든 커맨드가 이 파서 하나로 만들어진다."""
import argparse
import sys

from kitae import __version__
from kitae.registry import GROUP_TITLES, GROUPS, load_commands


def build_parser(cmds):
    grouped = {g: [] for g in GROUPS}
    for name in sorted(cmds):
        grouped.setdefault(cmds[name].GROUP, []).append((name, cmds[name].HELP))

    lines = []
    for g in GROUPS:
        if not grouped.get(g):
            continue
        lines.append(f"{GROUP_TITLES[g]}:")
        for name, help_ in grouped[g]:
            lines.append(f"  {name:<12} {help_}")
        lines.append("")

    parser = argparse.ArgumentParser(
        prog="kitae",
        description="北へ。White Illumination 다국어화 파이프라인",
        epilog="\n".join(lines),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version",
                        version=f"kitae {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, c in sorted(cmds.items()):
        p = sub.add_parser(name, description=c.HELP)
        c.configure(p)
        p.set_defaults(_run=c.run)
    return parser


def main(argv=None):
    # 일본어 원문을 그대로 찍는 일이 많다 — 콘솔 코드페이지와 무관하게 UTF-8로.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)
    parser = build_parser(load_commands())
    args = parser.parse_args(argv)
    if not getattr(args, "_run", None):
        parser.print_help()
        return 1
    return args._run(args) or 0


if __name__ == "__main__":
    sys.exit(main())
