"""Persistence layer: a Repository protocol plus a psycopg-backed impl.

Raw parameterized SQL, no ORM in the app layer -- Alembic (which does need
SQLAlchemy Core to describe tables) is the only place SQLAlchemy appears.
Route handlers depend on the Repository protocol, not on PostgresRepository
directly, so tests can substitute an in-memory fake without a real database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class Repository(Protocol):
    def create_run(self, run_id: str, *, uploaded_files: dict[str, str], status: str, created_at: datetime) -> None: ...

    def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    def update_run_status(
        self,
        run_id: str,
        *,
        status: str,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
        completed_at: datetime | None = None,
    ) -> None: ...

    def insert_match_records(self, run_id: str, records: list[dict[str, Any]]) -> None: ...

    def insert_exceptions(self, run_id: str, records: list[dict[str, Any]]) -> None: ...

    def insert_journal_lines(self, run_id: str, lines: list[dict[str, Any]]) -> None: ...

    def list_exceptions(self, run_id: str) -> list[dict[str, Any]]: ...

    def get_exception(self, exception_id: str) -> dict[str, Any] | None: ...

    def resolve_exception(
        self,
        exception_id: str,
        *,
        resolved_by: str,
        resolution_notes: str,
        proposal: dict[str, Any] | None,
        approved: bool,
        resolved_at: datetime,
    ) -> dict[str, Any] | None: ...

    def get_ledger_bundle(self, run_id: str, *, exception_limit: int = 50, journal_line_limit: int = 200) -> dict[str, Any]: ...


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PostgresRepository:
    """Repository backed by a live psycopg connection (Neon Postgres)."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def create_run(self, run_id: str, *, uploaded_files: dict[str, str], status: str, created_at: datetime) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs (id, status, uploaded_files, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (run_id, status, Jsonb(uploaded_files), created_at),
            )
        self._conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id AS run_id, status, uploaded_files, summary, error, created_at, completed_at
                FROM runs WHERE id = %s
                """,
                (run_id,),
            )
            return cur.fetchone()

    def update_run_status(
        self,
        run_id: str,
        *,
        status: str,
        summary: dict[str, Any] | None = None,
        error: str | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE runs
                SET status = %s,
                    summary = COALESCE(%s, summary),
                    error = %s,
                    completed_at = %s
                WHERE id = %s
                """,
                (status, Jsonb(summary) if summary is not None else None, error, completed_at, run_id),
            )
        self._conn.commit()

    def insert_match_records(self, run_id: str, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        with self._conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO match_records
                    (id, run_id, pass_number, method, confidence, evidence, matched_at, record_type, left_id, right_id, created_at)
                VALUES (%(id)s, %(run_id)s, %(pass_number)s, %(method)s, %(confidence)s, %(evidence)s, %(matched_at)s, %(record_type)s, %(left_id)s, %(right_id)s, %(created_at)s)
                """,
                [
                    {
                        "id": r["id"],
                        "run_id": run_id,
                        "pass_number": r["pass_number"],
                        "method": r["method"],
                        "confidence": r["confidence"],
                        "evidence": Jsonb(r["evidence"]),
                        "matched_at": r["matched_at"],
                        "record_type": r["record_type"],
                        "left_id": r["left_id"],
                        "right_id": r["right_id"],
                        "created_at": r.get("created_at", _now()),
                    }
                    for r in records
                ],
            )
        self._conn.commit()

    def insert_exceptions(self, run_id: str, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        with self._conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO exceptions
                    (id, run_id, code, severity, record_type, record_id, amount_paisa, rupee_at_risk_paisa, details, status, created_at)
                VALUES (%(id)s, %(run_id)s, %(code)s, %(severity)s, %(record_type)s, %(record_id)s, %(amount_paisa)s, %(rupee_at_risk_paisa)s, %(details)s, 'open', %(created_at)s)
                """,
                [
                    {
                        "id": r["id"],
                        "run_id": run_id,
                        "code": r["code"],
                        "severity": r["severity"],
                        "record_type": r["record_type"],
                        "record_id": r["record_id"],
                        "amount_paisa": r["amount_paisa"],
                        "rupee_at_risk_paisa": r["rupee_at_risk_paisa"],
                        "details": Jsonb(r["details"]),
                        "created_at": r.get("created_at", _now()),
                    }
                    for r in records
                ],
            )
        self._conn.commit()

    def insert_journal_lines(self, run_id: str, lines: list[dict[str, Any]]) -> None:
        if not lines:
            return
        with self._conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO journal_lines (id, run_id, order_id, account, direction, amount_paisa, created_at)
                VALUES (%(id)s, %(run_id)s, %(order_id)s, %(account)s, %(direction)s, %(amount_paisa)s, %(created_at)s)
                """,
                [
                    {
                        "id": line["id"],
                        "run_id": run_id,
                        "order_id": line["order_id"],
                        "account": line["account"],
                        "direction": line["direction"],
                        "amount_paisa": line["amount_paisa"],
                        "created_at": line.get("created_at", _now()),
                    }
                    for line in lines
                ],
            )
        self._conn.commit()

    def list_exceptions(self, run_id: str) -> list[dict[str, Any]]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, run_id, code, severity, record_type, record_id, amount_paisa,
                       rupee_at_risk_paisa, details, status, resolution, created_at, resolved_at
                FROM exceptions
                WHERE run_id = %s
                ORDER BY rupee_at_risk_paisa DESC, created_at ASC
                """,
                (run_id,),
            )
            return list(cur.fetchall())

    def get_exception(self, exception_id: str) -> dict[str, Any] | None:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, run_id, code, severity, record_type, record_id, amount_paisa,
                       rupee_at_risk_paisa, details, status, resolution, created_at, resolved_at
                FROM exceptions WHERE id = %s
                """,
                (exception_id,),
            )
            return cur.fetchone()

    def resolve_exception(
        self,
        exception_id: str,
        *,
        resolved_by: str,
        resolution_notes: str,
        proposal: dict[str, Any] | None,
        approved: bool,
        resolved_at: datetime,
    ) -> dict[str, Any] | None:
        resolution = {
            "resolved_by": resolved_by,
            "resolution_notes": resolution_notes,
            "proposal": proposal,
            "approved": approved,
        }
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE exceptions
                SET status = 'resolved', resolution = %s, resolved_at = %s
                WHERE id = %s
                RETURNING id, run_id, code, severity, record_type, record_id, amount_paisa,
                          rupee_at_risk_paisa, details, status, resolution, created_at, resolved_at
                """,
                (Jsonb(resolution), resolved_at, exception_id),
            )
            row = cur.fetchone()
        self._conn.commit()
        return row

    def get_ledger_bundle(self, run_id: str, *, exception_limit: int = 50, journal_line_limit: int = 200) -> dict[str, Any]:
        run = self.get_run(run_id)
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT code, severity, record_type, record_id, amount_paisa, rupee_at_risk_paisa, details, status
                FROM exceptions WHERE run_id = %s
                ORDER BY rupee_at_risk_paisa DESC
                LIMIT %s
                """,
                (run_id, exception_limit),
            )
            exceptions = list(cur.fetchall())
            cur.execute(
                """
                SELECT order_id, account, direction, amount_paisa
                FROM journal_lines WHERE run_id = %s
                ORDER BY order_id
                LIMIT %s
                """,
                (run_id, journal_line_limit),
            )
            journal_lines = list(cur.fetchall())
        return {"run": run, "exceptions": exceptions, "journal_lines": journal_lines}

