# LedgerProof

LedgerProof is a reconciliation engine for Razorpay settlement batches. It ingests merchant orders, Razorpay payment data, and bank statements, then matches settlement credits back to order-level transactions while surfacing only honest exceptions.

## Status

This repository is intentionally scaffolded without business logic. The core project structure and Python tooling are in place for the next phase of implementation.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
pytest
```

## Repo layout

- `src/ledgerproof/` — Python package for application logic
- `tests/` — pytest suite
- `data/` — working dataset storage
- `backend/` — API and orchestration layer
- `frontend/` — Next.js application
- `.github/workflows/` — CI and deployment automation
