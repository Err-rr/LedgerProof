"""In-memory fakes for api.repository.Repository and api.storage.Storage.

Used to test the FastAPI endpoints end-to-end (via TestClient) without a
real Postgres connection or S3 bucket -- overridden onto the app via
app.dependency_overrides, the same pattern CLAUDE.md's CI-safety rules
already require for the Anthropic client (see agent/resolve.py).
"""

from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any


class FakeRepository:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}
        self.match_records: dict[str, list[dict[str, Any]]] = {}
        self.exceptions: dict[str, dict[str, Any]] = {}

    def create_run(self, run_id: str, *, uploaded_files: dict[str, str], status: str, created_at: datetime) -> None:
        self.runs[run_id] = {
            "run_id": run_id,
            "status": status,
            "uploaded_files": uploaded_files,
            "summary": None,
            "error": None,
            "created_at": created_at,
            "completed_at": None,
        }
        self.match_records[run_id] = []

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        row = self.runs.get(run_id)
        return deepcopy(row) if row is not None else None

    def update_run_status(self, run_id: str, *, status: str, summary=None, error=None, completed_at=None) -> None:
        row = self.runs[run_id]
        row["status"] = status
        if summary is not None:
            row["summary"] = summary
        row["error"] = error
        row["completed_at"] = completed_at

    def insert_match_records(self, run_id: str, records: list[dict[str, Any]]) -> None:
        self.match_records.setdefault(run_id, []).extend(deepcopy(records))

    def insert_exceptions(self, run_id: str, records: list[dict[str, Any]]) -> None:
        for record in records:
            row = deepcopy(record)
            row["run_id"] = run_id
            row["status"] = "open"
            row["resolution"] = None
            row["resolved_at"] = None
            self.exceptions[row["id"]] = row

    def insert_journal_lines(self, run_id: str, lines: list[dict[str, Any]]) -> None:
        self.match_records.setdefault(f"{run_id}:journal", []).extend(deepcopy(lines))

    def list_exceptions(self, run_id: str) -> list[dict[str, Any]]:
        rows = [deepcopy(r) for r in self.exceptions.values() if r["run_id"] == run_id]
        rows.sort(key=lambda r: (-r["rupee_at_risk_paisa"], r["created_at"]))
        return rows

    def get_exception(self, exception_id: str) -> dict[str, Any] | None:
        row = self.exceptions.get(exception_id)
        return deepcopy(row) if row is not None else None

    def resolve_exception(self, exception_id: str, *, resolved_by: str, resolution_notes: str, proposal, approved: bool, resolved_at) -> dict[str, Any] | None:
        row = self.exceptions.get(exception_id)
        if row is None:
            return None
        row["status"] = "resolved"
        row["resolution"] = {"resolved_by": resolved_by, "resolution_notes": resolution_notes, "proposal": proposal, "approved": approved}
        row["resolved_at"] = resolved_at
        return deepcopy(row)

    def get_ledger_bundle(self, run_id: str, *, exception_limit: int = 50, journal_line_limit: int = 200) -> dict[str, Any]:
        return {
            "run": self.get_run(run_id),
            "exceptions": self.list_exceptions(run_id)[:exception_limit],
            "journal_lines": deepcopy(self.match_records.get(f"{run_id}:journal", []))[:journal_line_limit],
        }

    def list_match_records(self, run_id: str) -> list[dict[str, Any]]:
        return [deepcopy(r) for r in self.match_records.get(run_id, [])]

    def list_match_records_for_record(self, run_id: str, record_id: str) -> list[dict[str, Any]]:
        return [
            deepcopy(r)
            for r in self.match_records.get(run_id, [])
            if r.get("left_id") == record_id or r.get("right_id") == record_id
        ]


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, content: bytes, *, content_type: str = "application/octet-stream") -> str:
        self.objects[key] = content
        return f"fake://{key}"

    def get(self, key: str) -> bytes:
        return self.objects[key]


class FakeLLMClient:
    """Records the last prompt it was given and returns a canned answer."""

    def __init__(self, answer: str = "The ledger shows one exception worth reviewing.") -> None:
        self.answer = answer
        self.last_call: dict[str, Any] | None = None

        outer = self

        class _Messages:
            @staticmethod
            def create(*args: Any, **kwargs: Any) -> Any:
                outer.last_call = kwargs
                return type("Resp", (), {"content": [type("Block", (), {"text": outer.answer})()]})()

        self.messages = _Messages()
