"""Integration tests that hit a real, locally-booted uvicorn over real HTTP.

Every other API test in this suite uses FastAPI's TestClient, which talks to
the ASGI app in-process via an ASGI transport -- it never opens a real
socket and never goes through Starlette/uvicorn's actual exception-to-HTTP-
response machinery. That gap is exactly what let a real bug through:
POST /runs could return a non-JSON ("Internal Server Error" text/plain) or
a truly empty body under real conditions TestClient can't reproduce, and
every fetch() in web/ crashed trying to parse it. These tests boot a real
uvicorn subprocess and hit it with httpx (a real HTTP client) specifically
to catch that failure class.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _cleanup_log_file(log_file) -> None:
    log_file.close()
    try:
        os.unlink(log_file.name)
    except OSError:
        # Windows can briefly hold the file handle open past proc.wait()
        # returning; this is a throwaway temp file, not worth failing a
        # passing test over -- the OS temp dir reaps it eventually.
        pass


def _spawn_uvicorn(args: list[str], *, env: dict[str, str] | None = None) -> tuple[subprocess.Popen, "tempfile._TemporaryFileWrapper"]:
    """subprocess.Popen(stdout=PIPE) deadlocks on Windows once uvicorn's own
    logging fills the OS pipe buffer and nobody drains it -- the child
    blocks mid-write inside its own request-logging call, which stalls the
    very request the test is waiting on, and the test times out looking like
    a server hang that isn't one. Redirecting to a real file sidesteps this
    entirely since a file write is never blocked on a reader.
    """
    log_file = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log")
    proc = subprocess.Popen(args, cwd=str(ROOT), env=env, stdout=log_file, stderr=subprocess.STDOUT, text=True)
    return proc, log_file


def _wait_until_up(base_url: str, *, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            httpx.get(f"{base_url}/healthz", timeout=1.0).raise_for_status()
            return
        except Exception as exc:  # noqa: BLE001 - retry until timeout, then surface the last error
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"server at {base_url} did not come up in time") from last_error


@pytest.fixture(scope="module")
def dev_server_url():
    """Boots scripts/dev_api_server.py (real api/main.py, fake DB/S3/LLM) as
    a real subprocess -- the same server developers run locally."""
    port = _free_port()
    proc, log_file = _spawn_uvicorn([sys.executable, str(ROOT / "scripts" / "dev_api_server.py"), "--port", str(port)])
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_up(base_url)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        _cleanup_log_file(log_file)


def _upload_files() -> dict[str, tuple[str, bytes, str]]:
    sys.path.insert(0, str(ROOT / "tests"))
    from api_fixtures import as_multipart_files, build_upload_batch  # noqa: PLC0415

    batch = build_upload_batch(seed=1, order_count=3)
    return as_multipart_files(batch)


def test_post_runs_over_real_http_returns_json_on_success(dev_server_url: str) -> None:
    with httpx.Client(timeout=30) as client:
        response = client.post(f"{dev_server_url}/runs", files=_upload_files())

    assert response.headers.get("content-type", "").startswith("application/json"), (
        f"expected a JSON content-type, got {response.headers.get('content-type')!r}; body={response.content!r}"
    )
    body = response.json()  # must not raise -- this is exactly the bug class this test guards against
    assert response.status_code == 201
    assert body["status"] == "completed"
    assert "run_id" in body


def test_post_runs_over_real_http_returns_json_on_malformed_upload(dev_server_url: str) -> None:
    files = _upload_files()
    files["payments"] = ("payments.json", b"not valid json {{{", "application/json")

    with httpx.Client(timeout=30) as client:
        response = client.post(f"{dev_server_url}/runs", files=files)

    assert response.headers.get("content-type", "").startswith("application/json"), (
        f"expected a JSON content-type, got {response.headers.get('content-type')!r}; body={response.content!r}"
    )
    body = response.json()  # must not raise
    assert response.status_code == 201
    assert body["status"] == "failed"

    # Confirm the run itself records the real parse error (GET /runs/{id}.error),
    # per the Phase 7 requirement that a malformed upload fails the run, not the request.
    with httpx.Client(timeout=30) as client:
        run = client.get(f"{dev_server_url}/runs/{body['run_id']}").json()
    assert run["status"] == "failed"
    assert run["error"]


def test_post_runs_over_real_http_returns_json_even_when_dependencies_are_unconfigured() -> None:
    """Reproduces the actual root cause: get_repository/get_storage raise
    during FastAPI's dependency resolution -- which runs BEFORE a route's
    own body, so no try/except inside a route can ever catch it -- when
    DATABASE_URL/S3_BUCKET_NAME are unset. Before api/main.py's global
    exception handler existed, Starlette's default behavior returned a bare
    "Internal Server Error" with a text/plain content-type and no parseable
    JSON, which every fetch() in web/ then choked on.

    This boots the REAL api.main:app (not the fake-backed dev server) with
    those env vars explicitly removed, to prove that misconfiguration alone
    -- with no code bug in api/reconcile.py at all -- still always
    produces a JSON body.
    """
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "S3_BUCKET_NAME")}
    proc, log_file = _spawn_uvicorn([sys.executable, "-m", "uvicorn", "api.main:app", "--port", str(port)], env=env)
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_up(base_url)
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{base_url}/runs", files=_upload_files())

        assert response.headers.get("content-type", "").startswith("application/json"), (
            f"expected a JSON content-type even for a misconfigured server, got {response.headers.get('content-type')!r}; "
            f"body={response.content!r}"
        )
        body = response.json()  # must not raise
        assert response.status_code == 500
        assert "DATABASE_URL" in body["detail"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        _cleanup_log_file(log_file)
