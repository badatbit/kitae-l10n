"""Re-encode dumped Shift-JIS (cp932) text files as UTF-8, in place.

The game stores all text as cp932; these dumps are byte-for-byte copies, so most
editors show them as mojibake. This rewrites them as UTF-8 for reading and
translating. The rebuild path must encode back to cp932 — UTF-8 is a working
convenience, not the on-disc format.

Usage:  python sjis2utf8.py <dir-or-file> [...]
"""
import os, sys


def is_text(data):
    """True if the blob decodes cleanly as cp932 and looks like text."""
    if b"\x00" in data:
        return False
    try:
        s = data.decode("cp932")
    except UnicodeDecodeError:
        return False
    ctrl = sum(1 for c in s if ord(c) < 0x20 and c not in "\r\n\t")
    return ctrl == 0


def convert(path):
    with open(path, "rb") as f:
        data = f.read()
    if data.startswith(b"\xef\xbb\xbf"):
        return "already-utf8"
    try:
        data.decode("utf-8")
        if any(b > 0x7F for b in data):
            return "already-utf8"
    except UnicodeDecodeError:
        pass
    if not is_text(data):
        return "binary-skip"
    text = data.decode("cp932")
    if not any(ord(c) > 0x7F for c in text):
        return "ascii-only"
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))
    return "converted"


def main():
    targets = sys.argv[1:] or ["."]
    files = []
    for t in targets:
        if os.path.isdir(t):
            for root, _, names in os.walk(t):
                files += [os.path.join(root, n) for n in names]
        else:
            files.append(t)
    tally = {}
    for p in sorted(files):
        r = convert(p)
        tally[r] = tally.get(r, 0) + 1
        if r == "converted":
            print(f"  {os.path.relpath(p)}")
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(tally.items())))


if __name__ == "__main__":
    main()
