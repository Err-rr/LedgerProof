"""FastAPI application entrypoint. `handler` is the Lambda entrypoint via
Mangum -- see Dockerfile CMD ["api.main.handler"].
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from api.routers import ask, exceptions, runs

logger = logging.getLogger("ledgerproof.api")

app = FastAPI(
    title="LedgerProof API",
    description="Multi-source settlement reconciliation for Razorpay merchants.",
    version="0.1.0",
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches unhandled exceptions from the router inward -- route bodies
    and dependency resolution (get_repository/get_storage), which runs
    BEFORE a route's own body and so can never be caught by a try/except
    inside that route. This is wired into Starlette's ExceptionMiddleware,
    which sits INSIDE any middleware added via add_middleware() below -- it
    does NOT see exceptions raised by that middleware itself. See
    _catch_all_middleware for the layer that covers that gap.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": f"internal server error: {exc}"})


# CORS is not what causes the frontend's empty-body bug -- the browser never
# calls this API directly; it goes through the Next.js app's own route
# handlers (see web/app/api/**), which is a server-to-server call with no
# CORS involved. This is still added because our own test suite exercises
# routes exclusively via TestClient, which bypasses ASGI middleware and CORS
# entirely, so a real browser calling this API directly (a different
# deployment shape, a debugging session, Amplify preview URLs, etc.) would
# otherwise fail silently with no test ever catching it.
_allowed_origins = [origin.strip() for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _catch_all_middleware(request: Request, call_next):
    """The outer safety net. Starlette.add_middleware() PREPENDS to
    user_middleware, so the middleware stack ends up (outermost to
    innermost) ServerErrorMiddleware -> [most-recently-added user
    middleware] -> ... -> [first-added] -> ExceptionMiddleware -> router.
    @app.exception_handler() is wired into ExceptionMiddleware, so it never
    sees an exception raised by CORSMiddleware itself -- only Starlette's
    own ServerErrorMiddleware would, and its default response is plain text
    with no Content-Type, not JSON. Registering this AFTER add_middleware(
    CORSMiddleware, ...) makes it the most-recently-added -- and therefore
    outermost -- user middleware, wrapping CORSMiddleware, so an exception
    there is caught here instead of falling through to ServerErrorMiddleware.
    (Verified empirically: registering it before CORSMiddleware put it
    INSIDE CORS in the actual stack, not wrapping it -- order here is not
    just documentation, it's load-bearing.)
    """
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001 - this IS the last line of defense
        logger.exception("Unhandled exception (middleware layer) on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": f"internal server error: {exc}"})

app.include_router(runs.router)
app.include_router(exceptions.router)
app.include_router(ask.router)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict[str, str]:
    return {"status": "ok"}


handler = Mangum(app)
