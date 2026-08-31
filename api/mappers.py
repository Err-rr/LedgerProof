"""DB-row -> response-schema mappers shared across routers."""

from __future__ import annotations

from typing import Any

from api.schemas import ExceptionOut, MatchRecordOut, RunOut, RunStatus, RunSummary


def run_row_to_out(row: dict[str, Any]) -> RunOut:
    summary = RunSummary(**row["summary"]) if row.get("summary") else None
    return RunOut(
        run_id=row["run_id"],
        status=RunStatus(row["status"]),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
        error=row.get("error"),
        summary=summary,
    )


def exception_row_to_out(row: dict[str, Any]) -> ExceptionOut:
    return ExceptionOut(
        id=row["id"],
        run_id=row["run_id"],
        code=row["code"],
        severity=row["severity"],
        record_type=row["record_type"],
        record_id=row["record_id"],
        amount_paisa=row["amount_paisa"],
        rupee_at_risk_paisa=row["rupee_at_risk_paisa"],
        details=row.get("details") or {},
        status=row["status"],
        resolution=row.get("resolution"),
        created_at=row["created_at"],
        resolved_at=row.get("resolved_at"),
    )


def match_record_row_to_out(row: dict[str, Any]) -> MatchRecordOut:
    return MatchRecordOut(
        id=row["id"],
        pass_number=row["pass_number"],
        method=row["method"],
        confidence=row["confidence"],
        evidence=row.get("evidence") or {},
        matched_at=row["matched_at"],
        record_type=row["record_type"],
        left_id=row["left_id"],
        right_id=row["right_id"],
    )
