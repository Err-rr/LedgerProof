# LedgerProof

Built for the Razorpay AI Buildathon 2026, Track 04 (AI Finance Controller).

## The problem

A Razorpay settlement lands in the bank account as one lumped credit. It
funds dozens or hundreds of orders at once. Nothing in that single bank line
says which order paid for which slice of it.

## Headline numbers

Measured from one real 200-order run (`gen/generate.py --seed 7`, full
numbers and how they were measured: `RESULTS.md`):

- **Money at rest found: ₹3,29,113.68** — real, unreconciled money the
  system found and refused to silently net out.
- **Match rate: 100.0%** — every order linked to a payment.
- **Auto-resolve rate: 93.46%** — the gap to match rate is 42 records the
  system refused to guess at, not 42 it failed to link. Every one is a real,
  explained arithmetic mismatch (see `RESULTS.md`).
- **Adversarial containment: 100%** (330/330 mutations), up from **85.7%**
  before four launch-blocking bugs our own harness found were fixed (worst
  family, `structural`, was 60%). Full history: `audit/FINDINGS.md`.

## The design decision

The matching core is deterministic. No pass in `core/passes/` ever calls an
LLM, and none decides which payment belongs to which order, which
settlement explains which bank credit, or how to classify a variance —
those decisions are made from evidence a human could check by hand, or they
become an exception. A lower auto-resolve rate with an honest exception list
is the goal here, not a high match rate achieved by guessing.

LLMs are confined to exactly three surfaces, all read-only with respect to
the ledger: parsing bank narration text on ingest (regex first, LLM only as
a fallback, and even then it proposes a token rather than deciding a match),
explaining an already-computed exception with a hypothesis and cited
evidence, and answering natural-language questions over a ledger the
deterministic passes already reconciled. Every one of the three requires an
explicit human `approved: true` before anything it produces can touch the
ledger. Full rationale: `ARCHITECTURE.md`.

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate        # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
pytest                           # 51 tests, no real credentials needed anywhere
```

Generate a batch and run the full local demo (API + dashboard, in-memory
persistence — no Neon/S3/Anthropic credentials needed):

```bash
python gen/generate.py --seed 7 --orders 200 --out data/demo/
powershell -File scripts/dev.ps1 # opens the API dev server and the dashboard,
                                  # each in its own window (Windows PowerShell 5.1+;
                                  # use `pwsh scripts/dev.ps1` if you have PowerShell Core)
```

Then open `http://127.0.0.1:3000`, upload the five files from `data/demo/`,
and click through screens 01-04. Restarting either server forgets every run
— persistence is in-memory only, by design, for local development.

To exercise the matching engine's own adversarial suite:

```bash
python audit/mutate.py           # 330 mutations, ~330/330 contained
```

## Architecture

Four deterministic passes (bank↔settlement, settlement↔payment,
payment↔order, journal generation), an exception taxonomy with a single
source of truth for "what counts as money at rest," and three narrowly-scoped
LLM surfaces that can propose but never write. Full detail: `ARCHITECTURE.md`.

## Limitations

Written plainly, not softened — an honest limitations section is exactly
what this project's own thesis rewards.

- **Not deployed.** This runs locally only. `Dockerfile` and
  `deploy/deploy.sh` (Lambda container image + ECR + API Gateway) and the
  Amplify hosting config for `web/` are written but have never been executed
  against real AWS infrastructure. No AWS account was available during
  development.
- **`PostgresRepository` and `S3Storage` are validated by inspection and a
  standalone smoke-test script (`scripts/db_smoke_test.py`), not against a
  live Neon database or S3 bucket.** Every API test runs against an
  in-memory fake repository/storage instead. The SQL and boto3 calls have
  been read carefully and are believed correct; they have not been executed
  against real infrastructure.
- **Screen 04 (provenance drill-down) works.** Verified directly: real
  order→payment→settlement→bank-credit chains render with real method,
  confidence, and evidence values, including a UTR-verified hop rendering
  distinctly from an amount+date hop, and an `AMBIGUOUS_MATCH` rendering as
  a visible fork rather than a broken chain. It required one backend
  endpoint (`GET /runs/{id}/match-records`) that didn't exist before the
  screen needed it.
- **`pass1`/`pass2` assume the schemas in `SCHEMAS.md`.** A real Razorpay
  export shaped differently — settlements carrying a list of payment IDs
  rather than one per row, or a bank statement using
  `credit_paisa`/`debit_paisa`/`value_date` instead of
  `amount_paisa`/`posted_at`/`bank_credit_id` — is not yet parsed correctly.
  Confirmed directly against a real (non-synthetic) 12-order batch: `pass2`
  flagged all 11 payments `UNSETTLED_PAYMENT` instead of the one that
  actually was, because it can't read that settlement shape. Full detail and
  why it wasn't fixed alongside the bugs that were: `audit/FINDINGS.md`
  (Bug 6's scoping note).
- **`core/score.py::compute_score`'s `precision` field is not a real
  precision score.** It's defined as `matches / (matches + exceptions)`,
  identical to `auto_resolve_rate` — the function only receives aggregate
  counts, never the actual match records, so it cannot check anything
  against `ground_truth.json`. Not called by the API or the audit suite, so
  low blast radius, but real. `RESULTS.md`'s precision figure was computed
  directly against ground truth for this document instead of read from this
  function.
- **`gen/generate.py`'s synthetic settlements don't account for refunds
  that occur before settlement**, which is why a "0 injected defects" batch
  still produces `SETTLEMENT_IMBALANCE` exceptions in `RESULTS.md` — a
  modeling gap in the generator, not the matcher (which is correctly
  flagging a real arithmetic mismatch). Deferred rather than fixed today:
  the generator underpins the entire 330-mutation adversarial suite and most
  of the test suite, too much blast radius for the day of submission.
- **The narration LLM fallback (`core/narration.py::parse_narration_v2`) is
  implemented and tested in isolation but not wired into the live
  pipeline.** `pass1_bank_settlement` uses its own pure-regex UTR extractor
  with no LLM path at all. Compliant either way (LLM narration parsing is
  permitted, not required) but worth being direct about: it did not ship.
- **The 200-order demo batch is deterministic and self-generated**
  (`gen/generate.py --seed 7`), so a fresh clone can reproduce every number
  in `RESULTS.md` exactly. A separate, smaller, hand-authored 12-order batch
  with more varied exception types was used during development and is
  described in `audit/FINDINGS.md`; it is not part of this repository.

## Repo layout

- `core/` — the deterministic matching engine (passes 1-4), exceptions, and scoring
- `agent/` — the LLM resolution-proposal surface (never writes to the ledger)
- `gen/` — the synthetic dataset generator used by tests and the audit suite
- `audit/` — the adversarial mutation-testing harness for the matcher (`audit/mutate.py`, `audit/FINDINGS.md`)
- `api/` — FastAPI + Mangum service: routers, DB repository, S3 storage, LLM Q&A, reconciliation orchestration
- `web/` — Next.js 14 dashboard (screens 01-04), consumes the real API only, no mock data
- `alembic/` — hand-written Postgres migrations for `runs`, `match_records`, `exceptions`, `journal_lines`
- `scripts/` — `dev.ps1` (local demo), `dev_api_server.py` (in-memory API for local dev), `ci_check.py`, `db_smoke_test.py`
- `Dockerfile`, `deploy/` — the Lambda container image and its deploy script (written, not executed — see Limitations)
- `tests/` — pytest suite, including API tests against in-memory fakes
- `.github/workflows/` — CI
