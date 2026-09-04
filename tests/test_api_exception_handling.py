"""Proves api/main.py's exception-handling guarantee holds at every layer.

The empty-body 500 reported against the real dashboard turned out to be a
stale Next.js dev process running with a mismatched LEDGERPROOF_API_BASE_URL
after a .env.local edit -- not a bug in this API at all (see
audit/FINDINGS.md). But the underlying architectural question the report
raised is real and independent of that incident: Starlette's
@app.exception_handler() is wired into ExceptionMiddleware, which sits
INSIDE any middleware added via add_middleware() -- an exception raised by
CORSMiddleware itself would bypass it entirely and fall through to
Starlette's default ServerErrorMiddleware, which returns plain text with no
Content-Type, not JSON. These tests prove both layers actually work,
including the ordering-sensitive one TestClient's default behavior would
otherwise hide (TestClient re-raises an exception that reaches
ServerErrorMiddleware unhandled instead of returning it as a response,
which is exactly the signal used below to prove the middleware, not
Starlette's default, is what's catching it).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from api.main import app


def test_unhandled_exception_in_a_dependency_returns_json():
    """The ExceptionMiddleware-layer guarantee: a route/dependency-level
    exception (get_repository raising because DATABASE_URL is unset, in
    this app's real code) must come back as JSON, not Starlette's default
    plain-text 500."""
    client = TestClient(app)
    # No dependency override here -- this exercises the REAL get_repository,
    # which raises RuntimeError("DATABASE_URL is not configured") when the
    # env var is unset, which it is not set in this test process.
    import os

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("DATABASE_URL", None)
        response = client.get("/runs/does-not-matter")

    assert response.headers["content-type"].startswith("application/json")
    body = response.json()  # must not raise
    assert response.status_code == 500
    assert "DATABASE_URL" in body["detail"]


def test_unhandled_exception_in_middleware_itself_returns_json():
    """The outer, middleware-layer guarantee: if CORSMiddleware (or any
    other middleware registered before _catch_all_middleware) raises, the
    response must still be JSON, not Starlette's default plain-text 500.

    Uses TestClient's default raise_server_exceptions=True deliberately:
    if _catch_all_middleware were NOT positioned to wrap CORSMiddleware (the
    ordering bug this test is really guarding against), the exception would
    reach Starlette's ServerErrorMiddleware unhandled, and TestClient would
    re-raise it here instead of returning a response -- this test would
    error out, not fail an assertion, making a regression impossible to miss.
    """
    with patch.object(CORSMiddleware, "__call__", side_effect=RuntimeError("boom from CORS middleware")):
        client = TestClient(app)
        response = client.get("/healthz")

    assert response.headers["content-type"].startswith("application/json")
    body = response.json()  # must not raise
    assert response.status_code == 500
    assert "boom from CORS middleware" in body["detail"]


def test_middleware_order_places_catch_all_outside_cors():
    """Documents the load-bearing fact directly: Starlette.add_middleware()
    prepends, so whichever middleware is registered LAST in api/main.py ends
    up OUTERMOST. _catch_all_middleware must be registered after
    add_middleware(CORSMiddleware, ...) for the test above to mean anything."""
    names = [m.cls.__name__ if hasattr(m, "cls") else type(m).__name__ for m in app.user_middleware]
    catch_all_index = next(i for i, m in enumerate(app.user_middleware) if m.cls.__name__ == "BaseHTTPMiddleware")
    cors_index = next(i for i, m in enumerate(app.user_middleware) if m.cls.__name__ == "CORSMiddleware")
    # user_middleware is stored most-recently-added-first; the smaller index
    # is closer to ServerErrorMiddleware, i.e. more "outer".
    assert catch_all_index < cors_index, f"catch-all must be outer (lower index) than CORS: {names}"
