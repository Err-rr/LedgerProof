"""FastAPI application entrypoint. `handler` is the Lambda entrypoint via
Mangum -- see Dockerfile CMD ["api.main.handler"].
"""

from __future__ import annotations

from fastapi import FastAPI
from mangum import Mangum

from api.routers import ask, exceptions, runs

app = FastAPI(
    title="LedgerProof API",
    description="Multi-source settlement reconciliation for Razorpay merchants.",
    version="0.1.0",
)

app.include_router(runs.router)
app.include_router(exceptions.router)
app.include_router(ask.router)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


handler = Mangum(app)
