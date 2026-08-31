# Phase 6 Adversarial Audit — Findings & Fixes

`audit/mutate.py` ran 315 mutations across four families (narration, amount,
timing, structural) against the real `pass1_bank_settlement` and
`pass2_settlement_payments` matchers. 45 came back `WRONG_MATCH` across three
systemic bugs. A fourth bug — real, but not exercised by the original suite
because of how one mutation family was scoped — was found while fixing the
other three. All four are launch-blocking under CLAUDE.md rule 6 ("a wrong
match is a failure... never a confidently wrong answer").

This document records what the audit found, the root cause, the fix, and the
before/after containment rate for each. All four are now fixed. The suite was
extended to close the scoping gap that hid bug 4, and re-run: **0 WRONG_MATCH,
0 CRASH, across 330 mutations, 100% containment.**

## Summary

| # | Bug | Mutation(s) | Before | After |
|---|-----|-------------|--------|-------|
| 1 | False confidence labeling | `narration/false_confidence` | 0/15 contained | 15/15 |
| 2 | Priority theft via delivery order | `structural/priority_theft_via_collision` | 0/15 contained | 15/15 |
| 3 | Silent skip on zero-payment settlement | `structural/delete_payment_mid_batch` | 0/15 contained | 15/15 |
| 4 | UTR path doesn't validate amount | `amount/utr_verified_amount_mismatch` (new) | not covered | 15/15 |

| Family | Before (315 total) | After (330 total) |
|---|---|---|
| narration | 60/75 (80.0%) | 75/75 (100%) |
| amount | 120/120 (100%, but scoped around bug 4 — see below) | 135/135 (100%) |
| timing | 45/45 (100%) | 45/45 (100%) |
| structural | 45/75 (60.0%) | 75/75 (100%) |
| **overall** | **270/315 (85.7%)** | **330/330 (100%)** |

---

## Bug 1 — False confidence labeling (`pass1_bank_settlement`)

**What the audit found.** `narration/false_confidence` fed a narration
containing an innocuous word ("REFERENCE", "UNVERIFIED", "PROCESSING", ...)
that happens to satisfy the UTR-detection regex, on a row whose real UTR had
been removed. In all 15/15 trials, the resulting match landed on the correct
settlement but was labeled `method="utr", confidence=1.0` — a confident,
dishonest claim about how the match was actually made.

**Root cause.** In the old code, `method` and `confidence` were derived from
whether `_parse_utr_from_narration` returned *any* token, not from whether
that token matched a real settlement:

```python
method = "utr" if utr else "amount_date"
confidence = 1.0 if utr else 0.95
```

The word "REFERENCE" matches `UTR_RE` (`REF` + 6+ chars), gets extracted as a
candidate token, and — even after the UTR-based settlement lookup came back
empty and the match was actually resolved via amount+date fallback — the
label was still stamped `"utr"` / `1.0` purely because `utr` was truthy.

**Fix.** `core/passes/pass1_bank_settlement.py` now sets method/confidence at
the point a claim is actually created, from the path that produced it. A
`"utr"` claim is only ever created after `settlement_df["utr"]` is checked for
exact equality against the parsed token; everything else — including a
narration containing a UTR-shaped decoy — falls through to the amount+date
path and is honestly labeled `"amount_date"` / `0.95`. The evidence dict on an
amount+date claim now also carries `parsed_narration_token`, so a reviewer can
see that a token was present without it being mistaken for a resolving UTR.

**Test.** `tests/test_pass1_pass2_fixes.py::test_fix1_decoy_token_without_real_utr_match_is_labeled_amount_date`
and `::test_fix1_real_utr_match_still_gets_utr_label_and_full_confidence`.

**Containment: 0/15 → 15/15.**

---

## Bug 2 — Priority theft via delivery order (`pass1_bank_settlement`)

**What the audit found.** `structural/priority_theft_via_collision` delivered
a fabricated bank credit with no UTR — sharing a real settlement's exact
amount and posting date — *before* the legitimate UTR-verified credit for
that same settlement. In all 15/15 trials, the fabricated credit won the
settlement (`method=amount_date, confidence=0.95`), and the legitimate,
cryptographically-stronger credit was bumped into
`UNMATCHED_BANK_CREDIT (reason=settlement_already_matched)`.

**Root cause.** The old pass1 processed bank rows one at a time and claimed
settlements first-come-first-served:

```python
if settlement_id in used_settlement_ids:
    exceptions.append(_build_exception("UNMATCHED_BANK_CREDIT", ...))
    continue
...
used_settlement_ids.add(settlement_id)
```

Whichever row happened to be iterated first won the settlement, regardless of
the strength of its evidence. A weak amount+date coincidence processed early
could permanently lock out a strong UTR match processed later.

**Fix.** `pass1_bank_settlement` is now two-phase:

- **Phase A** collects, for every bank row, at most one candidate *claim* on
  a settlement (method, confidence, evidence), without deciding a winner. A
  bank row that is itself ambiguous among several settlements still routes
  straight to `AMBIGUOUS_MATCH` here, unchanged from before.
- **Phase B** arbitrates *per settlement*, across every bank row's claims,
  independent of input order: the highest-confidence claim(s) win. A
  UTR-verified claim (1.0) always beats an amount+date claim (0.95). If two
  or more claims tie at the top tier, **none** of them win —
  `AMBIGUOUS_MATCH` is emitted for each, per rule 3. Every losing claim is
  reported as `UNMATCHED_BANK_CREDIT (reason=lost_arbitration)`, naming the
  settlement and the winning claim, instead of vanishing.

**Test.** `tests/test_pass1_pass2_fixes.py::test_fix2_utr_verified_claim_always_wins_regardless_of_delivery_order`
runs the same batch as `[thief, legit]`, `[legit, thief]`, reversed, and
shuffled (fixed seed) and asserts an identical result — the UTR-verified
credit wins and the loser is reported — in every ordering.
`::test_fix2_tied_confidence_claims_are_ambiguous_not_guessed` covers the tie
case (two same-tier claims on one settlement → both excepted, neither
matched).

**Containment: 0/15 → 15/15.**

---

## Bug 3 — Silent skip on a zero-payment settlement (`pass2_settlement_payments`)

**What the audit found.** `structural/delete_payment_mid_batch` deleted a
settlement's only payment from the batch before running pass2. In all 15/15
trials, the settlement produced no `SETTLEMENT_IMBALANCE` and no exception of
any kind — the deletion was completely invisible to the reconciliation
output.

**Root cause.**

```python
settlement_payments = payments_df[payments_df["settlement_id"] == settlement_id]
if settlement_payments.empty:
    continue
```

A settlement with zero attached payments skipped the entire arithmetic check
instead of falling through to it. While auditing the rest of both passes for
the same pattern (per the fix instructions), a second instance turned up in
the same function:

```python
if settlements_df.empty:
    return matches, exceptions
```

If `settlements_df` was empty but `payments_df` had real rows (e.g. the
entire settlement feed failed to load for a batch), this returned
immediately with no exceptions for *any* of those payments — the same class
of silent swallow, at the whole-batch level.

**Fix.** The `continue` was deleted. A settlement with zero payments now
falls through to the same arithmetic the normal path uses:
`payment_net_total = 0`, so `expected_total = -refund_total -
adjustment_total` (typically `0`), and `delta = expected_total -
settlement_amount` — a drift equal to the *full* settlement amount, correctly
classified `variance_code="AMOUNT_VARIANCE_PAYMENT_NET"` by the existing
logic. No special-cased branch was needed; removing the shortcut was the fix.
The exception's details now also carry `amount_paisa=settlement_amount`, and
`SETTLEMENT_IMBALANCE` (and the new `AMOUNT_VARIANCE_UNEXPLAINED`, bug 4) were
added to `rupee_at_risk()` and `money_at_rest()` in `core/exceptions.py` — a
`SETTLEMENT_IMBALANCE` previously contributed **zero** to rupee-at-risk
regardless of its size, which is its own quiet bug fixed here as required by
"the settlement amount as rupee-at-risk."

The top-level early return was narrowed to
`if settlements_df.empty and payments_df.empty:` so a payments batch is never
discarded just because the settlements side happened to be empty.

**Test.** `tests/test_pass1_pass2_fixes.py::test_fix3_settlement_with_no_payments_raises_maximal_imbalance`
(asserts `delta_paisa == -settlement_amount` and
`rupee_at_risk() == settlement_amount`) and
`::test_fix3_payments_are_not_silently_dropped_when_settlements_df_is_empty`.

**Containment: 0/15 → 15/15.**

---

## Bug 4 — UTR path doesn't validate amount (`pass1_bank_settlement`)

**What the audit found.** This bug was **not** among the 45 `WRONG_MATCH`
cases in the original 315-mutation run — the `amount` family's bank-credit
mutations stripped the row's UTR before mutating the amount, specifically to
force the amount+date fallback path (workaround for the fact that path is
where amount is actually compared). That workaround meant the suite never
exercised "UTR matches, amount doesn't" at all. Manually verified directly
against the matcher:

```python
bank = {"amount_paisa": 999999, "narration": "... UTR000000001"}
settlement = {"amount_paisa": 125500, "utr": "UTR000000001"}
pass1_bank_settlement(...)
# -> matched, method="utr", confidence=1.0, no exception
```

A credit off by ₹8,745 was accepted as a perfect, maximum-confidence match
because the UTR path never looked at the amount at all.

**Root cause.** The UTR branch built its candidate set purely from
`settlement_df["utr"] == utr`, with no amount comparison anywhere in that
branch — unlike the amount+date fallback, which by construction only ever
matches on amount.

**Fix.** As part of the bug 2 rewrite, a UTR claim is only created when the
amount also matches. When a UTR identifies a settlement but the amount
doesn't reconcile, pass1 now emits a new exception code,
`AMOUNT_VARIANCE_UNEXPLAINED` (added to `ExceptionCode` in
`core/exceptions.py` and documented in `EXCEPTIONS.md`), carrying
`settlement_id`, `utr`, both amounts, and `drift_paisa`. No match is created
for that bank credit — the settlement's identity is certain, but the money is
not, so nothing is accepted at face value. `AMOUNT_VARIANCE_UNEXPLAINED` was
rated `critical` severity and wired into `rupee_at_risk()` /
`money_at_rest()` against the bank credit's amount.

**Audit suite change.** The UTR-stripping workaround was removed from
`make_amount_pass1_mutation` — those mutations now run against the real
primary (UTR) path, which is what "amount" mutations should have been
attacking all along. A new dedicated mutation,
`amount/utr_verified_amount_mismatch`, was added specifically for this case:
an intact, correct UTR paired with a drifted amount.

**Test.** `tests/test_pass1_pass2_fixes.py::test_fix4_utr_match_with_wrong_amount_is_never_silently_accepted`.

**Containment: not covered → 15/15 (new).**

---

## Re-run after all four fixes

330 mutations (315 original + 15 new `utr_verified_amount_mismatch` trials),
same seeds, same harness, `python audit/mutate.py`:

```
Family        Total  Contained  WrongMatch  Crash   Containment
narration        75         75           0      0        100.0%
amount          135        135           0      0        100.0%
timing           45         45           0      0        100.0%
structural       75         75           0      0        100.0%
------------------------------------------------------------------------------
OVERALL         330        330           0      0        100.0%
```

0 `WRONG_MATCH`, 0 `CRASH`. Full machine-readable detail in
`audit/scorecard.json`. Deterministic — re-running produces byte-identical
output (verified across independent runs before and after the fixes).

No mutation was removed, weakened, or reclassified to reach this number: the
same 20 original mutation types still run at the same 15 trials each, plus
one new mutation type added specifically to close the bug-4 coverage gap.
