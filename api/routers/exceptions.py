"""POST /exceptions/{id}/resolve -- the human-approval gate.

CLAUDE.md rule 5: "The agent proposes, it never writes. Resolution
suggestions from the LLM always require an explicit human approval flag
before they affect the ledger." This endpoint IS that gate: it accepts an
optional LLM-produced proposal purely as an audit-trail attachment, but the
request is rejected outright unless a human has set approved=true. Approving
an exception only annotates the exception row itself (status, resolver,
notes, timestamp) -- it never creates or edits match_records or
journal_lines. Generating compensating ledger entries from a resolution is a
distinct, larger decision this endpoint deliberately does not make.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_repository
from api.mappers import exception_row_to_out
from api.repository import Repository
from api.schemas import ResolveExceptionRequest, ResolveExceptionResponse

router = APIRouter(tags=["exceptions"])


@router.post("/exceptions/{exception_id}/resolve", response_model=ResolveExceptionResponse)
def resolve_exception(
    exception_id: str,
    body: ResolveExceptionRequest,
    repository: Repository = Depends(get_repository),
) -> ResolveExceptionResponse:
    if not body.approved:
        raise HTTPException(
            status_code=422,
            detail="resolution requires explicit human approval: set approved=true to proceed",
        )

    existing = repository.get_exception(exception_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"exception {exception_id} not found")
    if existing["status"] == "resolved":
        raise HTTPException(status_code=409, detail=f"exception {exception_id} is already resolved")

    updated = repository.resolve_exception(
        exception_id,
        resolved_by=body.resolved_by,
        resolution_notes=body.resolution_notes,
        proposal=body.proposal,
        approved=body.approved,
        resolved_at=datetime.now(timezone.utc),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"exception {exception_id} not found")

    return ResolveExceptionResponse(exception=exception_row_to_out(updated))
