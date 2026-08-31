#!/usr/bin/env python3
"""Exercise the real PostgresRepository against a live DATABASE_URL.

Nothing in the automated test suite talks to a real Postgres instance (CI
has no DATABASE_URL, and the repository is unit-tested against an in-memory
fake -- see tests/test_api_*.py). This script is the missing piece: run it
by hand, once, against your own Neon connection string after
`alembic upgrade head`, to confirm the schema and the repository queries
actually work together.

Usage:
    DATABASE_URL=postgresql://... python scripts/db_smoke_test.py

It creates one throwaway run (and its match_record/exception/journal_line),
reads everything back, resolves the exception, then deletes the run
(cascading) so it leaves no residue.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psycopg  # noqa: E402

from api.repository import PostgresRepository  # noqa: E402


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("Set DATABASE_URL first.", file=sys.stderr)
        return 1

    conn = psycopg.connect(database_url)
    repo = PostgresRepository(conn)
    run_id = f"smoke-{uuid.uuid4()}"
    now = datetime.now(timezone.utc)

    try:
        repo.create_run(run_id, uploaded_files={"orders": "s3://smoke/orders.xlsx"}, status="pending", created_at=now)
        check("create_run", repo.get_run(run_id) is not None)

        repo.update_run_status(run_id, status="completed", summary={"total_orders": 1, "total_matches": 1, "total_exceptions": 1, "match_rate": 1.0, "auto_resolve_rate": 0.5, "money_at_rest_paisa": 500, "exceptions_by_code": {"UNMATCHED_BANK_CREDIT": 1}}, completed_at=now)
        run = repo.get_run(run_id)
        check("update_run_status persisted summary", run is not None and run["status"] == "completed" and run["summary"]["total_orders"] == 1)

        match_id = str(uuid.uuid4())
        repo.insert_match_records(run_id, [{
            "id": match_id, "pass_number": 1, "method": "utr", "confidence": 1.0,
            "evidence": {"bank_credit_id": "BC-1"}, "matched_at": now.isoformat(),
            "record_type": "bank_credit", "left_id": "BC-1", "right_id": "SET-1",
        }])

        exception_id = str(uuid.uuid4())
        repo.insert_exceptions(run_id, [{
            "id": exception_id, "code": "UNMATCHED_BANK_CREDIT", "severity": "high",
            "record_type": "bank_credit", "record_id": "BC-2", "amount_paisa": 50000,
            "rupee_at_risk_paisa": 50000, "details": {"narration": "smoke test"},
        }])

        journal_id = str(uuid.uuid4())
        repo.insert_journal_lines(run_id, [{
            "id": journal_id, "order_id": "ORD-1", "account": "Bank", "direction": "Dr", "amount_paisa": 100,
        }])

        exceptions = repo.list_exceptions(run_id)
        check("list_exceptions returns the inserted row", len(exceptions) == 1 and exceptions[0]["id"] == exception_id)

        resolved = repo.resolve_exception(
            exception_id, resolved_by="smoke-test", resolution_notes="smoke test resolution",
            proposal=None, approved=True, resolved_at=now,
        )
        check("resolve_exception", resolved is not None and resolved["status"] == "resolved")

        bundle = repo.get_ledger_bundle(run_id)
        check("get_ledger_bundle returns run + exceptions + journal_lines", bundle["run"] is not None and len(bundle["exceptions"]) == 1 and len(bundle["journal_lines"]) == 1)

        print("\nAll checks passed against a live database.")
        return 0
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM runs WHERE id = %s", (run_id,))
        conn.commit()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
