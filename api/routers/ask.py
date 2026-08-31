from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.config import get_settings
from api.deps import get_llm_client, get_repository
from api.llm import AnthropicLike, ask_ledger_question
from api.repository import Repository
from api.schemas import AskRequest, AskResponse

router = APIRouter(tags=["ask"])


@router.post("/runs/{run_id}/ask", response_model=AskResponse)
def ask_run(
    run_id: str,
    body: AskRequest,
    repository: Repository = Depends(get_repository),
    llm_client: AnthropicLike = Depends(get_llm_client),
) -> AskResponse:
    run = repository.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    if run["status"] != "completed":
        raise HTTPException(status_code=409, detail=f"run {run_id} has status '{run['status']}', not 'completed' -- nothing to ask about yet")

    bundle = repository.get_ledger_bundle(run_id)
    answer = ask_ledger_question(body.question, bundle, client=llm_client, model=get_settings().anthropic_model)

    return AskResponse(
        run_id=run_id,
        question=body.question,
        answer=answer,
        grounded_in={
            "exceptions": len(bundle.get("exceptions") or []),
            "journal_lines": len(bundle.get("journal_lines") or []),
        },
    )
