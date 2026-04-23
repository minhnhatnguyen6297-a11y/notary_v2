from __future__ import annotations

import argparse
from pathlib import Path


TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".ini",
    ".cfg",
}

SKIP_DIRS = {
    ".git",
    ".claude",
    ".agent",
    ".vscode",
    "venv",
    "__pycache__",
    "runtime",
    "logs",
    "tmp",
    ".tmp_enotary",
}

# Common codepoints produced when UTF-8 bytes are decoded as CP1252.
MOJIBAKE_CODEPOINTS = {
    0x00C2,
    0x00C3,
    0x00C4,
    0x00D0,
    0x00F0,
    0x2018,
    0x2019,
    0x201C,
    0x201D,
    0x2039,
    0x203A,
    0x2022,
    0x2026,
    0x2013,
    0x2014,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fix mojibake caused by CP1252-decoded UTF-8 text."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repo root to scan. Defaults to current directory.",
    )
    return parser.parse_args()


def should_scan(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    return not any(part in SKIP_DIRS for part in path.parts)


def mojibake_score(text: str) -> int:
    score = 0
    for ch in text:
        code = ord(ch)
        if 0x80 <= code <= 0x9F:
            score += 5
        elif code in MOJIBAKE_CODEPOINTS:
            score += 2
    return score


def decode_cp1252_mojibake_once(text: str) -> str:
    raw = bytearray()
    for ch in text:
        code = ord(ch)
        if code <= 0xFF:
            raw.append(code)
        else:
            raw.extend(ch.encode("cp1252"))
    return raw.decode("utf-8")


def fix_file(path: Path) -> int:
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 0

    fixed_lines: list[str] = []
    changed_lines = 0

    for line in original.splitlines(keepends=True):
        try:
            repaired = decode_cp1252_mojibake_once(line)
        except (UnicodeEncodeError, UnicodeDecodeError):
            fixed_lines.append(line)
            continue

        if repaired != line and mojibake_score(repaired) < mojibake_score(line):
            fixed_lines.append(repaired)
            changed_lines += 1
        else:
            fixed_lines.append(line)

    if not changed_lines:
        return 0

    path.write_text("".join(fixed_lines), encoding="utf-8", newline="")
    return changed_lines


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    total_files = 0
    total_lines = 0

    for path in root.rglob("*"):
        if not should_scan(path):
            continue
        changed_lines = fix_file(path)
        if not changed_lines:
            continue
        total_files += 1
        total_lines += changed_lines
        print(f"fixed {path.relative_to(root)} ({changed_lines} line(s))")

    print(f"done: {total_files} file(s), {total_lines} line(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
