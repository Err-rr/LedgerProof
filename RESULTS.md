# Results

Every number on this page is measured from one real run of the actual
pipeline — `python gen/generate.py --seed 7 --orders 200 --out data/demo/`,
uploaded through the live dashboard, run through `pass1` → `pass4` exactly as
a merchant's batch would be. Nothing here is an estimate, a placeholder, or
carried over from an earlier phase. Where a metric could not be measured
honestly (the narration LLM path), that is stated plainly instead of filled
in.

Run: `data/demo/`, seed 7, 200 orders, `ground_truth.json` reports 0 injected
defects. Reproduce with the same command above, then upload the five files
in `data/demo/` through the dashboard, or `POST /runs` directly.

## Headline numbers

| Metric | Value |
|---|---|
| Match rate | **100.0%** (200/200 orders linked to a payment) |
| Auto-resolve rate | **93.46%** (600/642) |
| Precision | **100.0%** (600/600 matches produced were correct against `ground_truth.json`) |
| Throughput | **464.9 records/sec** (1,811ms of actual reconciliation time; 4.07s including the HTTP round trip and file parsing) |
| Money at rest | **₹3,29,113.68** |
| Adversarial containment | **100%** (330/330 mutations, up from 85.7% — see `audit/FINDINGS.md`) |

## Match rate vs. auto-resolve rate — the gap is deliberate

**Match rate (100.0%)** answers "did every order get linked to a payment?" —
scoped to `pass3` (payment↔order), the most order-centric pass.

**Auto-resolve rate (93.46%)** answers a different, stricter question: "of
everything the pipeline touched across all three matching passes —
600 matches plus 42 exceptions, 642 total — how much closed with no human
needed?" The 6.54-point gap is **42 records the system refused to guess
at**, not 42 records it failed to link. Every one of them is a
`SETTLEMENT_IMBALANCE`: a settlement whose declared net amount didn't
arithmetically reconcile against payment-net-minus-refunds. The engine could
have silently netted the refund and called it balanced. It didn't — it
flagged all 42, by design, per CLAUDE.md rule 6 ("an exception is a
success"). See "Why every SETTLEMENT_IMBALANCE this run" below for the exact
mechanism.

## Precision (scored against ground_truth.json)

600 match records were produced this run (200 bank↔settlement, 200
settlement↔payment, 200 payment↔order). Cross-checked every single one
against `ground_truth.json`'s mapping directly: **600/600 correct, 0
incorrect — 100% precision.**

This number was computed directly for this document, not read from
`core/score.py::compute_score` — that function's `precision` field is
currently defined as `matches / (matches + exceptions)`, identical to
`auto_resolve_rate`, not an actual check against ground truth (it never
receives the match records at all, only aggregate counts, so it structurally
cannot verify correctness). Real bug, low blast radius (standalone CLI
utility, not called by the API or the audit suite), not touched today for
that reason — noted honestly in `README.md`'s limitations rather than
patched under time pressure or quietly relied on for this figure.

## Full exception table

| Code | Count | Rupees at risk |
|---|---|---|
| `SETTLEMENT_IMBALANCE` | 42 | ₹3,29,113.68 |

(This run produced exactly one exception code. A smaller 12-order batch with
intentional edge cases — run during Priority 1 verification, not part of
this document's headline numbers — produced four: `SETTLEMENT_IMBALANCE`,
`UNSETTLED_PAYMENT`, `UNMATCHED_BANK_CREDIT`, `ORPHAN_ORDER`, all handled
correctly. See `audit/FINDINGS.md` for that scenario.)

## Why every `SETTLEMENT_IMBALANCE` this run

All 42 exceptions carry `variance_code: AMOUNT_VARIANCE_REFUND`, and this
batch has exactly 42 refunds — a 1:1 correspondence, confirmed directly, not
assumed. `gen/generate.py` computes a settlement's `net_amount_paisa` from
the payment alone (`amount - fee - gst`), independent of any refund on that
order, even though the refund's timestamp is generated earlier than the
settlement's. `pass2` correctly expects `settlement_amount == payment_net -
refund - adjustment` and correctly flags the 42 orders where the generator's
settlement doesn't reflect the refund it should already know about.

This is a modeling gap in the **synthetic data generator**, not in the
matching engine — `pass2` is doing exactly its job (rule 7: the arithmetic
either reconciles or it's flagged, no in-between). Fixing `gen/generate.py`
was considered and deliberately deferred: it is a foundational dependency of
the entire 330-mutation adversarial suite and most of the test suite, and
today is triage, not feature work, days/hours from submission. Flagged here
plainly rather than quietly smoothed over or hidden by softening the
exception table.

## Money at rest

**₹3,29,113.68**, summing exactly the codes `pass1`/`pass2`/`pass3` produced
that represent real, unreconciled money: `AMOUNT_VARIANCE_UNEXPLAINED`,
`DUPLICATE_REFUND`, `ORPHAN_ORDER`, `SETTLEMENT_IMBALANCE`,
`UNMATCHED_BANK_CREDIT`, `UNMATCHED_PAYMENT`, `UNSETTLED_PAYMENT` — the exact
set in `core.exceptions.MONEY_AT_REST_CODES`, single-sourced so the API,
the dashboard, and this document can never drift from what the number
actually claims to sum (only `SETTLEMENT_IMBALANCE` occurred this run, so it
accounts for the full figure here).

## Adversarial containment by mutation family

| Family | Containment |
|---|---|
| narration | 100% (75/75) |
| amount | 100% (135/135) |
| timing | 100% (45/45) |
| structural | 100% (75/75) |
| **overall** | **100% (330/330)** |

Up from 85.7% overall (60% structural, the worst family) before the four
Phase 6 fixes. Full root cause, before/after evidence, and reproduction
commands for each: `audit/FINDINGS.md`. Reproduce this table directly:
`python audit/mutate.py`.

## Narration parsing coverage

**The LLM-augmented narration parser did not ship into the live pipeline.**
`pass1_bank_settlement.py` uses its own pure-regex UTR extractor
(`_parse_utr_from_narration`) with no LLM path at all — confirmed by
inspection (`core/narration.py::parse_narration_v2`, which does support an
optional LLM fallback, is never imported by `api/` or `core/passes/`
anywhere). This is compliant with rule 2 either way (LLM narration parsing
is *permitted*, not required), but the two numbers the brief asks for
("regex baseline vs. regex + LLM") don't both exist in production, and
presenting one as if the other existed would misrepresent what's live.

What was actually measured: of the 200 bank-statement narrations in this
run, regex extracts a UTR-shaped token from **73 (36.5%)**. This batch's
settlements carry no `utr` field to compare that token against at all
(`gen/generate.py` doesn't emit one by default), so in this specific run
100% of bank-credit↔settlement matches resolved via the amount+date fallback
regardless of what the regex found — the 36.5% figure measures "regex found
something," not "regex decided a match."

`core/narration.py::parse_narration_v2` (regex first; LLM only invoked if
regex fails; the LLM still never decides a money match, only proposes a
token a human-equivalent regex check would also accept) is implemented and
covered by its own test
(`tests/test_agent_and_narration.py::test_narration_v2_uses_llm_only_when_regex_fails_and_reports_coverage_lift`),
just not wired into `pass1`. Wiring it in is real, scoped, low-risk future
work — not attempted today.
