#!/usr/bin/env python3
"""Backfill/rewrite audit hash chain for legacy events.

This utility is intended for controlled maintenance windows where legacy
unhashed rows must be upgraded for strict integrity mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from governance.audit_trail_system import AuditTrailSystem, get_audit_system  # noqa: E402


def main() -> int:
    """
    CLI entry point to backfill or rewrite the NIC audit hash chain and optionally verify integrity.
    
    Parses command-line arguments (--db-path, --limit, --rewrite-all, --apply), initializes the audit system (from the provided DB path or the global audit system), runs backfill_hash_chain with the requested options, and prints the backfill result as JSON. If --apply is used, runs verify_integrity afterward and prints a post-verify JSON object.
    
    Returns:
        int: Process exit code: 0 on success; 2 if backfill returned an "error"; 3 if post-apply verification reports invalid integrity.
    """
    parser = argparse.ArgumentParser(description="Backfill or rewrite NIC audit hash chain.")
    parser.add_argument("--db-path", default=None, help="Path to audit DB (defaults to AUDIT_DB_PATH/global config)")
    parser.add_argument("--limit", type=int, default=0, help="Optional max events to process (0 = full scan)")
    parser.add_argument("--rewrite-all", action="store_true", help="Rewrite full chain from oldest event")
    parser.add_argument("--apply", action="store_true", help="Apply updates (default is dry-run)")
    args = parser.parse_args()

    if args.db_path:
        audit = AuditTrailSystem(args.db_path)
    else:
        audit = get_audit_system()

    result = audit.backfill_hash_chain(
        rewrite_all=bool(args.rewrite_all),
        dry_run=not bool(args.apply),
        limit=args.limit if args.limit > 0 else None,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result.get("error"):
        return 2

    if args.apply:
        verification = audit.verify_integrity(limit=args.limit if args.limit > 0 else None)
        print(json.dumps({"post_verify": verification}, indent=2, ensure_ascii=False))
        if not verification.get("valid", False):
            return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())