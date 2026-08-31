"""Pydantic v2 request/response models for the API layer.

All money fields are integer paisa, per CLAUDE.md rule 1 -- never float.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RunSummary(BaseModel):
    total_orders: int
    total_matches: int
    total_exceptions: int
    match_rate: float
    auto_resolve_rate: float
    money_at_rest_paisa: int
    exceptions_by_code: dict[str, int] = Field(default_factory=dict)


class RunCreateResponse(BaseModel):
    run_id: str
    status: RunStatus


class RunOut(BaseModel):
    run_id: str
    status: RunStatus
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    summary: RunSummary | None = None


class ExceptionOut(BaseModel):
    id: str
    run_id: str
    code: str
    severity: str
    record_type: str
    record_id: str
    amount_paisa: int
    rupee_at_risk_paisa: int
    details: dict[str, Any] = Field(default_factory=dict)
    status: str
    resolution: dict[str, Any] | None = None
    created_at: datetime
    resolved_at: datetime | None = None


class ResolveExceptionRequest(BaseModel):
    approved: bool = Field(..., description="Explicit human approval flag. Required to be true -- see CLAUDE.md rule 5.")
    resolved_by: str = Field(..., min_length=1, description="Identifier of the human approving this resolution.")
    resolution_notes: str = Field(..., min_length=1)
    proposal: dict[str, Any] | None = Field(
        default=None, description="Optional LLM-proposed resolution (e.g. from agent.resolve.resolve_exception) being approved or overridden here."
    )


class ResolveExceptionResponse(BaseModel):
    exception: ExceptionOut


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    run_id: str
    question: str
    answer: str
    grounded_in: dict[str, int] = Field(
        default_factory=dict, description="Counts of the records the answer was grounded in, e.g. {'exceptions': 12, 'journal_lines': 40}."
    )
