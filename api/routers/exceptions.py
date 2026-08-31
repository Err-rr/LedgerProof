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

from agent.resolve import resolve_exception as generate_resolution_proposal
from api.config import get_settings
from api.deps import get_repository
from api.mappers import exception_row_to_out
from api.repository import Repository
from api.schemas import ProposalOut, ResolveExceptionRequest, ResolveExceptionResponse

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


@router.post("/exceptions/{exception_id}/propose", response_model=ProposalOut)
def propose_resolution(
    exception_id: str,
    repository: Repository = Depends(get_repository),
) -> ProposalOut:
    """Generates a resolution proposal via the LLM surface CLAUDE.md permits
    for exception explanation. Read-only: this never writes anything, and a
    human still has to submit and approve a resolution via
    POST /exceptions/{id}/resolve for it to count for anything."""
    exception_row = repository.get_exception(exception_id)
    if exception_row is None:
        raise HTTPException(status_code=404, detail=f"exception {exception_id} not found")

    related_records = repository.list_match_records_for_record(exception_row["run_id"], exception_row["record_id"])

    anthropic_client = None
    settings = get_settings()
    if settings.anthropic_api_key:
        import anthropic

        anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    try:
        proposal = generate_resolution_proposal(exception_row, related_records, anthropic_client=anthropic_client)
    except Exception:  # noqa: BLE001 - a flaky/malformed LLM response must degrade honestly, never 500
        proposal = None

    if proposal is None:
        return ProposalOut(
            hypothesis="No hypothesis formed.",
            proposed_resolution="No automated resolution proposed; requires human review.",
            confidence=0.0,
            evidence_ids=[],
        )

    return ProposalOut(
        hypothesis=proposal.hypothesis,
        proposed_resolution=proposal.proposed_resolution,
        confidence=proposal.confidence,
        evidence_ids=proposal.evidence_ids,
    )
