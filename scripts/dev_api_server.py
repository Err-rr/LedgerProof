#!/usr/bin/env python3
"""Run the real api/main.py FastAPI app for local frontend development,
with the DB/S3 dependencies swapped for the same in-memory fakes the
backend test suite uses (tests/api_fakes.py) -- no Neon, S3, or Anthropic
credentials required.

This is NOT a mock backend: every request goes through the real FastAPI
routers, the real Repository/Storage protocol boundary, and the real
core.passes matching engine on whatever files you actually upload. Only
persistence (the database and object storage) is swapped for memory --
exactly the same substitution the pytest suite makes. Restarting this
process forgets every run, on purpose.

Usage:
    python scripts/dev_api_server.py [--port 8000]

Then point web/'s LEDGERPROOF_API_BASE_URL at http://127.0.0.1:8000.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "tests")):
    if p not in sys.path:
        sys.path.insert(0, p)

from api.deps import get_llm_client, get_repository, get_storage  # noqa: E402
from api.main import app  # noqa: E402
from api_fakes import FakeLLMClient, FakeRepository, FakeStorage  # noqa: E402

_repo = FakeRepository()
_storage = FakeStorage()
_llm = FakeLLMClient(
    answer=(
        "This is the local dev server's canned LLM answer -- ANTHROPIC_API_KEY "
        "is not required for frontend development. Set it and use the real "
        "deployment to get real answers."
    )
)

app.dependency_overrides[get_repository] = lambda: _repo
app.dependency_overrides[get_storage] = lambda: _storage
app.dependency_overrides[get_llm_client] = lambda: _llm


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    print(f"LedgerProof dev API (in-memory persistence) on http://{args.host}:{args.port}")
    print("This is the real FastAPI app with fake DB/S3/LLM -- see this file's docstring.")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
