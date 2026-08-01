#!/usr/bin/env python3
"""Fail if a publishable file resembles a secret or a user-specific path."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+|xox[baprs]-[A-Za-z0-9-]+)\b"),
    re.compile(r"(?i)authorization:\s*bearer\s+\S+"),
)
PATH_PATTERNS = (
    re.compile(r"/Users/", re.IGNORECASE),
    re.compile(r"https?://127\.0\.0\.1:\d+"),
)
TEXT_SUFFIXES = {".md", ".py", ".sh", ".svg", ".zsh", ".txt"}


def publishable_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.resolve() == THIS_FILE:
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in {"Makefile", ".gitignore", "LICENSE"}:
            files.append(path)
    return files


def main() -> int:
    findings: list[str] = []
    for path in publishable_files():
        content = path.read_text(encoding="utf-8")
        for pattern in (*SECRET_PATTERNS, *PATH_PATTERNS):
            if pattern.search(content):
                findings.append(f"{path.relative_to(ROOT)} matches {pattern.pattern}")
    if findings:
        print("Public-tree audit failed:", file=sys.stderr)
        print("\n".join(findings), file=sys.stderr)
        return 1
    print("public-tree audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
