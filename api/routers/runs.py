from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_repository, get_storage
from api.mappers import exception_row_to_out, run_row_to_out
from api.reconcile import ReconciliationResult, UploadedSourceFiles, run_reconciliation
from api.repository import Repository
from api.schemas import ExceptionOut, RunCreateResponse, RunOut, RunStatus
from api.storage import Storage

router = APIRouter(tags=["runs"])


@router.post("/runs", response_model=RunCreateResponse, status_code=201)
async def create_run(
    orders: UploadFile = File(..., description="orders.xlsx"),
    payments: UploadFile = File(..., description="payments.json"),
    settlements: UploadFile = File(..., description="settlements.json"),
    bank_statement: UploadFile = File(..., description="bank_statement.csv"),
    refunds: UploadFile | None = File(None, description="refunds.json (optional)"),
    repository: Repository = Depends(get_repository),
    storage: Storage = Depends(get_storage),
) -> RunCreateResponse:
    run_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)

    orders_bytes = await orders.read()
    payments_bytes = await payments.read()
    settlements_bytes = await settlements.read()
    bank_statement_bytes = await bank_statement.read()
    refunds_bytes = await refunds.read() if refunds is not None else None

    uploaded_files = {
        "orders": storage.put(f"runs/{run_id}/orders.xlsx", orders_bytes),
        "payments": storage.put(f"runs/{run_id}/payments.json", payments_bytes),
        "settlements": storage.put(f"runs/{run_id}/settlements.json", settlements_bytes),
        "bank_statement": storage.put(f"runs/{run_id}/bank_statement.csv", bank_statement_bytes),
    }
    if refunds_bytes is not None:
        uploaded_files["refunds"] = storage.put(f"runs/{run_id}/refunds.json", refunds_bytes)

    repository.create_run(run_id, uploaded_files=uploaded_files, status=RunStatus.PENDING.value, created_at=created_at)

    files = UploadedSourceFiles(
        orders_xlsx=orders_bytes,
        payments_json=payments_bytes,
        settlements_json=settlements_bytes,
        bank_statement_csv=bank_statement_bytes,
        refunds_json=refunds_bytes,
    )

    repository.update_run_status(run_id, status=RunStatus.PROCESSING.value)
    try:
        result: ReconciliationResult = run_reconciliation(files)
    except Exception as exc:  # noqa: BLE001 - a bad upload must fail the run, not the request
        repository.update_run_status(
            run_id, status=RunStatus.FAILED.value, error=str(exc), completed_at=datetime.now(timezone.utc)
        )
        return RunCreateResponse(run_id=run_id, status=RunStatus.FAILED)

    repository.insert_match_records(run_id, result.match_record_rows)
    repository.insert_exceptions(run_id, result.exception_rows)
    repository.insert_journal_lines(run_id, result.journal_line_rows)
    repository.update_run_status(
        run_id,
        status=RunStatus.COMPLETED.value,
        summary=result.summary.model_dump(),
        completed_at=datetime.now(timezone.utc),
    )

    return RunCreateResponse(run_id=run_id, status=RunStatus.COMPLETED)


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, repository: Repository = Depends(get_repository)) -> RunOut:
    row = repository.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return run_row_to_out(row)


@router.get("/runs/{run_id}/exceptions", response_model=list[ExceptionOut])
def list_run_exceptions(run_id: str, repository: Repository = Depends(get_repository)) -> list[ExceptionOut]:
    if repository.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    rows = repository.list_exceptions(run_id)  # repository sorts by rupee_at_risk_paisa desc
    return [exception_row_to_out(row) for row in rows]
