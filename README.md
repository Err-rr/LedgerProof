# LedgerProof

LedgerProof is a reconciliation engine for Razorpay settlement batches. It ingests merchant orders, Razorpay payment data, and bank statements, then matches settlement credits back to order-level transactions while surfacing only honest exceptions.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
pytest
```

Running the tests never requires real credentials: `DATABASE_URL`,
`S3_BUCKET_NAME`, and `ANTHROPIC_API_KEY` are all read lazily and the API
test suite overrides the DB/S3/LLM dependencies with in-memory fakes.

## Running the API locally

```bash
uvicorn api.main:app --reload
```

Then `POST /runs` with multipart file uploads (`orders`, `payments`,
`settlements`, `bank_statement`, optional `refunds`) to run a reconciliation.
See `api/routers/` for all five endpoints.

## Postgres schema

Migrations are hand-written Alembic scripts under `alembic/versions/`
(SQLAlchemy Core table definitions; the app itself queries via raw psycopg,
no ORM). Apply them against your Neon connection string:

```bash
DATABASE_URL=postgresql://... python -m alembic upgrade head
python scripts/db_smoke_test.py  # optional: exercise the real repository end-to-end
```

## Deploying

The API ships as a Lambda container image (pandas/psycopg[binary] exceed the
zip-layer size limit). `deploy/deploy.sh` builds the image, pushes it to
ECR, and creates/updates the Lambda function and an HTTP API Gateway in
front of it:

```bash
DATABASE_URL=... S3_BUCKET_NAME=... ./deploy/deploy.sh
```

See the comment block at the top of that script for the full list of
required and optional environment variables.

## Repo layout

- `core/` — the deterministic matching engine (passes 1-4), exceptions, and scoring
- `agent/` — the LLM resolution-proposal surface (never writes to the ledger)
- `gen/` — the synthetic dataset generator used by tests and the audit suite
- `audit/` — the adversarial mutation-testing harness for the matcher (`audit/mutate.py`, `audit/FINDINGS.md`)
- `api/` — FastAPI + Mangum service: routers, DB repository, S3 storage, LLM Q&A, reconciliation orchestration
- `alembic/` — hand-written Postgres migrations for `runs`, `match_records`, `exceptions`, `journal_lines`
- `scripts/` — `ci_check.py` (mirrors CI locally) and `db_smoke_test.py` (exercises the real Postgres repository)
- `Dockerfile`, `deploy/` — the Lambda container image and its deploy script
- `tests/` — pytest suite, including API tests against in-memory fakes
- `.github/workflows/` — CI
