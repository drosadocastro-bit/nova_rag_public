#!/usr/bin/env python3
"""Offline audit integrity checker for NIC.

Reads the tamper-evident audit chain and prints a JSON summary suitable for
human review or CI/CD gate checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from governance.audit_trail_system import AuditTrailSystem, get_audit_system


def run_check(
    *,
    db_path: str | None,
    limit: int,
    include_details: bool,
    strict_unhashed: bool,
) -> tuple[dict, int]:
    """
    Run an integrity check of the audit trail and compute an exit code representing the result.
    
    Parameters:
        db_path (str | None): Filesystem path to a local audit database; if None, the global audit system is used.
        limit (int): Maximum number of events to verify; 0 means verify the entire trail.
        include_details (bool): If False, remove mismatch details from the returned report.
        strict_unhashed (bool): If True, treat the presence of legacy unhashed events as a failure condition.
    
    Returns:
        tuple[dict, int]: A pair where the first element is the integrity report (a dictionary with keys such as
        `valid` and `unhashed_events`), and the second element is the exit code: `0` for success,
        `2` when the report is invalid, and `3` when `strict_unhashed` is enabled and unhashed events were found.
    """
    if db_path:
        audit = AuditTrailSystem(db_path)
    else:
        audit = get_audit_system()

    report = audit.verify_integrity(limit=limit if limit > 0 else None)

    if not include_details and "mismatches" in report:
        report = dict(report)
        report.pop("mismatches", None)

    valid = bool(report.get("valid", False))
    unhashed_events = int(report.get("unhashed_events", 0) or 0)

    exit_code = 0
    if not valid:
        exit_code = 2
    elif strict_unhashed and unhashed_events > 0:
        exit_code = 3

    return report, exit_code


def main() -> int:
    """
    Parse command-line arguments, run the audit integrity check, print the resulting report as pretty-printed JSON to stdout, and return an appropriate exit code.
    
    Returns:
        int: 0 if the audit is valid; 2 if integrity verification failed; 3 if `--strict-unhashed` is set and unhashed events were found.
    """
    parser = argparse.ArgumentParser(description="Check tamper-evident NIC audit chain integrity.")
    parser.add_argument("--db-path", default=None, help="Path to audit DB (defaults to AUDIT_DB_PATH/global config)")
    parser.add_argument("--limit", type=int, default=0, help="Optional max events to verify (0 = full scan)")
    parser.add_argument("--include-details", action="store_true", help="Include mismatch details in output")
    parser.add_argument(
        "--strict-unhashed",
        action="store_true",
        help="Treat legacy unhashed events as failure",
    )
    args = parser.parse_args()

    report, exit_code = run_check(
        db_path=args.db_path,
        limit=args.limit,
        include_details=args.include_details,
        strict_unhashed=args.strict_unhashed,
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())