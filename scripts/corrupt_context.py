#!/usr/bin/env python3
"""
Corrupt a specific value in vector_db/nic_docs.jsonl without rebuilding FAISS.

Use to simulate stale embeddings vs corrupted source text.
"""

from __future__ import annotations

import argparse
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DOCS_PATH = BASE_DIR / "vector_db" / "nic_docs.jsonl"


def corrupt_docs(docs_path: Path, pattern: str, replacement: str, backup: bool) -> int:
    if backup:
        backup_path = docs_path.with_suffix(docs_path.suffix + ".bak")
        backup_path.write_text(docs_path.read_text(encoding="utf-8"), encoding="utf-8")

    updated_lines = []
    replaced = 0
    for line in docs_path.read_text(encoding="utf-8").splitlines():
        if replaced == 0 and pattern in line:
            line = line.replace(pattern, replacement, 1)
            replaced = 1
        updated_lines.append(line)

    docs_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return replaced


def restore_docs(docs_path: Path) -> bool:
    backup_path = docs_path.with_suffix(docs_path.suffix + ".bak")
    if not backup_path.exists():
        return False
    docs_path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Corrupt nic_docs.jsonl for evaluation.")
    parser.add_argument("--docs-path", default=str(DEFAULT_DOCS_PATH))
    parser.add_argument("--pattern", default="dBZ =10logZ")
    parser.add_argument("--replacement", default="dBZ =20logZ")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()

    docs_path = Path(args.docs_path)
    if not docs_path.exists():
        print("ERROR: docs path not found:", docs_path)
        return 2

    if args.restore:
        ok = restore_docs(docs_path)
        if ok:
            print("Restored:", docs_path)
            return 0
        print("ERROR: backup file not found for restore.")
        return 3

    replaced = corrupt_docs(docs_path, args.pattern, args.replacement, args.backup)
    if replaced == 0:
        print("WARNING: pattern not found; no changes made.")
        return 1
    print("Corruption complete:", args.pattern, "->", args.replacement)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
