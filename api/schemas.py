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


class StageResult(BaseModel):
    """What one matching pass actually did, measured -- not a live progress
    signal (the run is synchronous; there is nothing to poll mid-run), but a
    real, honest record of what ran and what it found."""

    pass_number: int
    name: str
    matches: int
    exceptions: int
    duration_ms: float


class RunSummary(BaseModel):
    total_orders: int
    total_matches: int
    total_exceptions: int
    match_rate: float
    auto_resolve_rate: float
    money_at_rest_paisa: int
    money_at_rest_codes: list[str] = Field(
        default_factory=list, description="Exception codes summed into money_at_rest_paisa -- see core.exceptions.MONEY_AT_REST_CODES."
    )
    exceptions_by_code: dict[str, int] = Field(default_factory=dict)
    stages: list[StageResult] = Field(default_factory=list)
    duration_ms: float = 0.0
    throughput_rps: float = 0.0


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


class MatchRecordOut(BaseModel):
    id: str
    pass_number: int
    method: str
    confidence: float
    evidence: dict[str, Any] = Field(default_factory=dict)
    matched_at: str
    record_type: str
    left_id: str
    right_id: str


class ProposalOut(BaseModel):
    """Mirrors agent.resolve.ResolutionProposal. Never applied automatically
    -- a human must submit it (or their own resolution) via
    POST /exceptions/{id}/resolve with approved=true (rule 5)."""

    hypothesis: str
    proposed_resolution: str
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    run_id: str
    question: str
    answer: str
    grounded_in: dict[str, int] = Field(
        default_factory=dict, description="Counts of the records the answer was grounded in, e.g. {'exceptions': 12, 'journal_lines': 40}."
    )
