# Architecture

## The four passes

Reconciliation runs as four independent, deterministic passes over pandas
DataFrames (`core/passes/`), orchestrated by `api/reconcile.py`. Each pass
takes the previous data as input but does not depend on another pass's
*output* — pass1 and pass2 both run off the raw uploaded files, not off each
other's matches — so a failure or gap in one pass never silently corrupts
another's results.

1. **`pass1_bank_settlement`** — bank credit ↔ settlement. Two-phase:
   collects every bank row's candidate claim (UTR-exact or amount+date
   fallback) without picking a winner, then arbitrates per settlement across
   *all* claims by confidence tier — a UTR-verified claim always beats an
   amount+date claim, regardless of which arrived first. Ties refuse to
   guess (`AMBIGUOUS_MATCH`, matching neither). A UTR match is cross-checked
   against amount before being accepted (`AMOUNT_VARIANCE_UNEXPLAINED` if it
   doesn't reconcile) — see `audit/FINDINGS.md` bugs 2 and 4 for why this
   phrasing is load-bearing, not incidental.
2. **`pass2_settlement_payments`** — settlement ↔ payment arithmetic. Sums
   each settlement's attached payments (net of fee/GST/refunds/adjustments)
   and asserts it reconciles against the settlement's declared amount. A
   settlement with *zero* attached payments is a maximal imbalance, not a
   no-op (`audit/FINDINGS.md` bug 3) — that class of "empty means nothing to
   report" mistake was found and fixed twice more, once in `pass1`'s
   top-level empty-batch guard and once in `pass3`'s.
3. **`pass3_payment_order`** — payment ↔ order. A three-tier cascade, each
   tier only attempted if the previous found nothing: exact `order_id` on
   the payment (confidence 1.0) → receipt match, payment's `receipt` against
   the order's `receipt` (0.95) → amount + a 10-minute time window, narrowed
   by a contact match only when the payment actually carries a contact field
   at all (0.7 — real Razorpay payments don't carry customer contact info
   directly, so requiring it unconditionally would make this tier permanently
   unreachable). A payment that resolves nothing raises `UNMATCHED_PAYMENT`;
   an order left unclaimed raises `ORPHAN_ORDER`.
4. **`pass4_journal`** — journal generation. Iterates *matched
   payment-order pairs*, never the raw order list — an order with no
   matched payment generates zero journal lines, carried entirely by its
   `ORPHAN_ORDER` exception, never a phantom `Cr Sales` (`audit/FINDINGS.md`
   bug 6, the most serious finding: the old code recognized revenue for
   money that never arrived). Asserts `sum(debits) == sum(credits)` before
   returning anything — CLAUDE.md rule 7, unconditional.

`core/score.py` is a separate, standalone scoring CLI, not called by the API
or the four passes above — see `README.md`'s limitations for a known gap in
its `precision` field.

## Why the matching core is deterministic

No pass above calls an LLM, and none ever will by design. A matching
decision — which payment belongs to which order, which settlement explains
which bank credit, how to classify a variance — is either resolvable from
the data with evidence a human could check by hand, or it isn't, in which
case the honest answer is an exception, not a guess. An LLM is
non-deterministic and unauditable at the level rule 4 requires ("every match
carries its evidence... a UTC timestamp, this is the audit trail and it is a
deliverable"), so it is structurally excluded from ever producing a
`MatchRecord`. This is not a caution; it's the product's core bet, stated in
`CLAUDE.md` rule 3: a lower auto-resolve rate with honest exceptions is the
goal, not a high match rate.

LLMs are confined to exactly three surfaces, none of which can move money or
decide a match:

- **Narration parsing on ingest** (`core/narration.py::parse_narration_v2`) —
  regex first, LLM only as a fallback when regex fails, and even then the
  LLM only proposes a token; it does not decide whether that token matches a
  settlement (the deterministic passes still do that comparison). Not
  currently wired into the live pipeline — see `RESULTS.md`.
- **Exception explanation** (`agent/resolve.py::resolve_exception`) —
  proposes a hypothesis, a confidence, and cited evidence IDs for a human to
  read. Returns "no hypothesis formed" rather than a low-confidence guess
  when it lacks real evidence to reason from.
- **Q&A over an already-reconciled ledger** (`api/llm.py::ask_ledger_question`,
  behind `POST /runs/{id}/ask`) — answers questions about data the
  deterministic passes already produced. Cannot see or touch match_records
  or exceptions it didn't ground its answer in.

Every one of the three requires a human in the loop before anything it
produces can change the ledger — `POST /exceptions/{id}/resolve` rejects any
request that doesn't set `approved: true` explicitly, whether or not an LLM
proposal is attached.

## Exception taxonomy

Every exception is a `{code, record_type, record_id, details}` tuple built
by `_build_exception()` in each pass, then run through
`core.exceptions.build_exception_queue()`, which assigns a severity
(`critical` > `high` > `medium` > `low`) and a `rupee_at_risk()` — the money
figure, only for codes in `MONEY_AT_REST_CODES` (a single set both the
scoring functions and the API's `RunSummary.money_at_rest_codes` read from,
so the dashboard can never claim to sum a different set of codes than it
actually does). Full code list and what each means: `EXCEPTIONS.md`.

The queue is sorted `(-rupee_at_risk, -severity_rank, record_id)` — highest
money at risk first, ties broken by severity, then a stable ID order. This
is the same order `GET /runs/{id}/exceptions` returns and the dashboard
renders without re-sorting client-side.

## Data flow

```
orders.xlsx ─┐
payments.json ─┼─▶ pass1/pass2/pass3 (independent) ─▶ pass4 (needs pass3's matches)
settlements.json ─┤        │                                  │
bank_statement.csv ─┘      ▼                                  ▼
refunds.json ─┘      match_records, exceptions            journal_lines
                             │
                             ▼
                    api/reconcile.py assembles RunSummary
                             │
                             ▼
                    Repository (Postgres in prod, in-memory fake in dev/tests)
                             │
                             ▼
                    web/ dashboard (screens 01-04)
```
