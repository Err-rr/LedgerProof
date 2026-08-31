"""Regression tests for the four launch-blocking bugs found by the Phase 6
adversarial mutation audit (audit/mutate.py) and fixed per audit/FINDINGS.md.
"""

from __future__ import annotations

import random

import pandas as pd

from core.exceptions import ExceptionCode, build_exception_queue
from core.passes.pass1_bank_settlement import pass1_bank_settlement
from core.passes.pass2_settlement_payments import pass2_settlement_payments


def _settlement(settlement_id: str, amount: int, utr: str, settled_at: str) -> dict:
    return {
        "settlement_id": settlement_id,
        "amount_paisa": amount,
        "net_amount_paisa": amount,
        "utr": utr,
        "settled_at": settled_at,
    }


def _bank_row(bank_id: str, amount: int, posted_at: str, narration: str) -> dict:
    return {
        "bank_credit_id": bank_id,
        "amount_paisa": amount,
        "posted_at": posted_at,
        "narration": narration,
    }


# --------------------------------------------------------------------------
# FIX 1: method/confidence must reflect the path that actually resolved the
# match, not merely whether some UTR-shaped token was present in narration.
# --------------------------------------------------------------------------


def test_fix1_decoy_token_without_real_utr_match_is_labeled_amount_date():
    settlements = pd.DataFrame([_settlement("SET-1", 125500, "UTR000000001", "2026-01-18T08:00:00Z")])
    # "REFERENCE" satisfies the UTR-shaped regex (REF + 6+ chars) but does not
    # equal the settlement's real UTR -- it must not be treated as a UTR match.
    bank = pd.DataFrame([_bank_row("BC-1", 125500, "2026-01-18T09:00:00Z", "BANK CREDIT REFERENCE NOTE")])

    matches, exceptions = pass1_bank_settlement(bank, settlements)

    assert exceptions == []
    assert len(matches) == 1
    match = matches[0]
    assert match.right_id == "SET-1"
    assert match.method == "amount_date"
    assert match.confidence == 0.95
    assert match.evidence["utr"] is None
    assert match.evidence["parsed_narration_token"] == "REFERENCE"


def test_fix1_real_utr_match_still_gets_utr_label_and_full_confidence():
    settlements = pd.DataFrame([_settlement("SET-1", 125500, "UTR000000001", "2026-01-18T08:00:00Z")])
    bank = pd.DataFrame([_bank_row("BC-1", 125500, "2026-01-18T09:00:00Z", "RAZORPAY ACME SET-1 2026-01-18 UTR000000001")])

    matches, exceptions = pass1_bank_settlement(bank, settlements)

    assert exceptions == []
    assert len(matches) == 1
    assert matches[0].method == "utr"
    assert matches[0].confidence == 1.0


# --------------------------------------------------------------------------
# FIX 2: settlements are claimed by arbitrated evidence strength, never by
# delivery order. A UTR-verified claim always beats an amount+date claim.
# --------------------------------------------------------------------------


def _priority_theft_batch() -> tuple[dict, dict, dict]:
    settlement = _settlement("SET-1", 125500, "UTR000000001", "2026-01-18T08:00:00Z")
    legit = _bank_row("BC-REAL", 125500, "2026-01-18T09:00:00Z", "RAZORPAY ACME SET-1 2026-01-18 UTR000000001")
    thief = _bank_row("BC-THIEF", 125500, "2026-01-18T09:00:00Z", "UNKNOWN CREDIT")  # no UTR, same amount+date
    return settlement, legit, thief


def _run_and_summarize(bank_rows: list[dict], settlement: dict) -> set[tuple[str, str, str, float]]:
    matches, _ = pass1_bank_settlement(pd.DataFrame(bank_rows), pd.DataFrame([settlement]))
    return {(m.left_id, m.right_id, m.method, m.confidence) for m in matches}


def test_fix2_utr_verified_claim_always_wins_regardless_of_delivery_order():
    settlement, legit, thief = _priority_theft_batch()

    orderings = [
        [thief, legit],  # thief delivered first (the original vulnerability)
        [legit, thief],  # legit delivered first
        list(reversed([thief, legit])),
    ]
    rng = random.Random(42)
    shuffled = [thief, legit]
    rng.shuffle(shuffled)
    orderings.append(shuffled)

    results = [_run_and_summarize(order, settlement) for order in orderings]

    expected = {("BC-REAL", "SET-1", "utr", 1.0)}
    for result in results:
        assert result == expected, f"delivery order changed the outcome: {result}"

    # And the loser must be reported, not silently dropped, in every ordering.
    for order in orderings:
        _, exceptions = pass1_bank_settlement(pd.DataFrame(order), pd.DataFrame([settlement]))
        thief_exc = next(e for e in exceptions if e["record_id"] == "BC-THIEF")
        assert thief_exc["code"] == "UNMATCHED_BANK_CREDIT"
        assert thief_exc["details"]["reason"] == "lost_arbitration"


def test_fix2_tied_confidence_claims_are_ambiguous_not_guessed():
    # Two settlements share amount+date; one bank credit (no UTR) could
    # belong to either. Two *different* bank credits both plausibly claiming
    # the *same* settlement at the same confidence tier must also refuse to
    # guess, matching neither.
    settlement = _settlement("SET-1", 125500, "UTR000000001", "2026-01-18T08:00:00Z")
    claim_a = _bank_row("BC-A", 125500, "2026-01-18T09:00:00Z", "UNKNOWN CREDIT A")
    claim_b = _bank_row("BC-B", 125500, "2026-01-18T09:05:00Z", "UNKNOWN CREDIT B")

    matches, exceptions = pass1_bank_settlement(pd.DataFrame([claim_a, claim_b]), pd.DataFrame([settlement]))

    assert matches == []
    codes = {(e["record_id"], e["code"]) for e in exceptions}
    assert codes == {("BC-A", "AMBIGUOUS_MATCH"), ("BC-B", "AMBIGUOUS_MATCH")}


# --------------------------------------------------------------------------
# FIX 3: a settlement with zero attached payments is a maximal imbalance.
# --------------------------------------------------------------------------


def test_fix3_settlement_with_no_payments_raises_maximal_imbalance():
    settlements = pd.DataFrame([{"settlement_id": "SET-1", "amount_paisa": 125500, "net_amount_paisa": 125500}])
    payments = pd.DataFrame([], columns=["payment_id", "settlement_id", "amount_paisa", "fee_paisa", "gst_paisa"])

    matches, exceptions = pass2_settlement_payments(settlements, payments)

    assert matches == []
    assert len(exceptions) == 1
    exc = exceptions[0]
    assert exc["code"] == "SETTLEMENT_IMBALANCE"
    assert exc["record_id"] == "SET-1"
    assert exc["details"]["delta_paisa"] == -125500
    assert exc["details"]["expected_total_paisa"] == 0
    assert exc["details"]["variance_code"] == "AMOUNT_VARIANCE_PAYMENT_NET"

    queue = build_exception_queue(exceptions)
    assert queue[0].code == ExceptionCode.SETTLEMENT_IMBALANCE
    assert queue[0].rupee_at_risk() == 125500


def test_fix3_payments_are_not_silently_dropped_when_settlements_df_is_empty():
    settlements = pd.DataFrame([], columns=["settlement_id", "amount_paisa"])
    payments = pd.DataFrame([{"payment_id": "PAY-1", "amount_paisa": 100000, "fee_paisa": 100, "gst_paisa": 18}])

    matches, exceptions = pass2_settlement_payments(settlements, payments)

    assert matches == []
    assert len(exceptions) == 1
    assert exceptions[0]["code"] == "UNSETTLED_PAYMENT"
    assert exceptions[0]["record_id"] == "PAY-1"


# --------------------------------------------------------------------------
# FIX 4: a UTR match must cross-check amount before being accepted.
# --------------------------------------------------------------------------


def test_fix4_utr_match_with_wrong_amount_is_never_silently_accepted():
    settlements = pd.DataFrame([_settlement("SET-1", 125500, "UTR000000001", "2026-01-18T08:00:00Z")])
    bank = pd.DataFrame([_bank_row("BC-1", 999999, "2026-01-18T09:00:00Z", "RAZORPAY ACME SET-1 2026-01-18 UTR000000001")])

    matches, exceptions = pass1_bank_settlement(bank, settlements)

    assert matches == [], "a UTR match with a wrong amount must never become a confident match"
    assert len(exceptions) == 1
    exc = exceptions[0]
    assert exc["code"] == "AMOUNT_VARIANCE_UNEXPLAINED"
    assert exc["record_id"] == "BC-1"
    assert exc["details"]["settlement_id"] == "SET-1"
    assert exc["details"]["drift_paisa"] == 999999 - 125500

    queue = build_exception_queue(exceptions)
    assert queue[0].code == ExceptionCode.AMOUNT_VARIANCE_UNEXPLAINED
    assert queue[0].rupee_at_risk() == 999999
