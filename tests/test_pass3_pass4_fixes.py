"""Regression tests for the two bugs a real 12-order fixture surfaced:

BUG 1 (pass3): a payment with no order_id and empty notes (pay_LP0003-style)
must cascade through the tiers -- not skip Tier 3 just because a receipt
field happens to be present -- and must actually succeed via Tier 2 once the
receipt comparison reads the ORDER's real field name.

BUG 2 (pass4): an order with no matched payment must generate zero journal
lines (carried entirely by its ORPHAN_ORDER exception), not a phantom
Cr Sales line recognizing revenue that never arrived.

See audit/FINDINGS.md for the full writeup.
"""

from __future__ import annotations

import pandas as pd
from hypothesis import given, settings, strategies as st

from core.passes.pass3_payment_order import pass3_payment_order
from core.passes.pass4_journal import pass4_journal

PAYMENT_COLUMNS = ["payment_id", "order_id", "amount_paisa", "fee_paisa", "gst_paisa", "status", "captured_at", "notes", "receipt"]


def _pass4_input_from_matches(matches: list, payments_df: pd.DataFrame) -> pd.DataFrame:
    """Mirrors api/reconcile.py's _build_pass4_input: pass4_journal needs
    order_id + amount/fee/gst per matched payment, joined back from the
    payment row pass3's MatchRecord doesn't itself carry fee/gst for."""
    if not matches or payments_df.empty:
        return pd.DataFrame(columns=["order_id", "amount_paisa", "fee_paisa", "gst_paisa"])
    indexed = payments_df.set_index(payments_df["payment_id"].astype(str))
    rows = []
    for m in matches:
        if m.left_id not in indexed.index:
            continue
        payment = indexed.loc[m.left_id]
        rows.append({
            "order_id": m.right_id,
            "amount_paisa": int(payment.get("amount_paisa", 0) or 0),
            "fee_paisa": int(payment.get("fee_paisa", 0) or 0),
            "gst_paisa": int(payment.get("gst_paisa", payment.get("tax_paisa", 0)) or 0),
        })
    return pd.DataFrame(rows, columns=["order_id", "amount_paisa", "fee_paisa", "gst_paisa"])


# --------------------------------------------------------------------------
# BUG 2: orphan order -> exception only, never a journal line
# --------------------------------------------------------------------------


def test_orphan_order_produces_exception_and_zero_journal_lines():
    orders = pd.DataFrame([
        {"order_id": "order_LP0012", "amount_paisa": 99900, "created_at": "2026-08-25T21:10:00+05:30", "status": "paid", "receipt": "rcpt_LP0012"},
    ])
    payments = pd.DataFrame([], columns=PAYMENT_COLUMNS)

    matches, exceptions = pass3_payment_order(payments, orders)
    assert matches == []
    assert len(exceptions) == 1
    assert exceptions[0]["code"] == "ORPHAN_ORDER"
    assert exceptions[0]["record_id"] == "order_LP0012"

    pass4_input = _pass4_input_from_matches(matches, payments)
    journal_lines = pass4_journal(pass4_input, orders, refund_amounts={})
    assert journal_lines == [], "an order with no matched payment must generate NO journal lines, not a phantom Cr Sales"


def test_payment_with_no_matched_order_produces_exception_and_zero_journal_lines():
    """The mirror case: a payment pass3 could not link to any order must
    also generate no journal lines -- it never appears in pass4's input at
    all, since that input is built strictly from matched pairs."""
    orders = pd.DataFrame([], columns=["order_id", "amount_paisa", "created_at", "status", "receipt"])
    payments = pd.DataFrame([{
        "payment_id": "pay_orphan", "order_id": None, "amount_paisa": 50000, "fee_paisa": 0, "gst_paisa": 0,
        "status": "captured", "captured_at": "2026-08-25T21:10:00+05:30", "notes": {}, "receipt": None,
    }])

    matches, exceptions = pass3_payment_order(payments, orders)
    assert matches == []
    assert len(exceptions) == 1
    assert exceptions[0]["code"] == "UNMATCHED_PAYMENT"
    assert exceptions[0]["record_id"] == "pay_orphan"

    pass4_input = _pass4_input_from_matches(matches, payments)
    journal_lines = pass4_journal(pass4_input, orders, refund_amounts={})
    assert journal_lines == []


# --------------------------------------------------------------------------
# BUG 1: pay_LP0003-style linking (no order_id, empty notes, receipt present)
# --------------------------------------------------------------------------


def test_payment_with_no_order_id_links_via_receipt_tier_at_tier2_confidence():
    payments = pd.DataFrame([{
        "payment_id": "pay_LP0003", "order_id": None, "amount_paisa": 89900, "fee_paisa": 0, "gst_paisa": 0,
        "status": "captured", "captured_at": "2026-08-24T13:41:09+05:30", "notes": {}, "receipt": "rcpt_LP0003",
    }])
    orders = pd.DataFrame([{
        "order_id": "order_LP0003", "amount_paisa": 89900, "created_at": "2026-08-24T13:41:09+05:30",
        "customer_email": "kabir.rao@example.com", "customer_phone": "+919812340003",
        "status": "paid", "receipt": "rcpt_LP0003",
    }])

    matches, exceptions = pass3_payment_order(payments, orders)

    assert exceptions == []
    assert len(matches) == 1
    match = matches[0]
    assert match.left_id == "pay_LP0003"
    assert match.right_id == "order_LP0003"
    assert match.method == "tier2"
    assert match.confidence == 0.95  # not 1.0 -- stamping certainty a receipt match doesn't have is the false_confidence bug from Phase 6


def test_payment_with_no_identifying_fields_falls_back_to_tier3_amount_time_match():
    """No order_id, no receipt, no notes, and -- as with real Razorpay
    payments -- no customer_email/customer_phone on the payment at all.
    Amount + a tight capture-time window against the order is the only
    evidence available, and must still be enough to link at Tier 3."""
    payments = pd.DataFrame([{
        "payment_id": "pay_fuzzy", "order_id": None, "amount_paisa": 89900, "fee_paisa": 0, "gst_paisa": 0,
        "status": "captured", "captured_at": "2026-08-24T13:41:09+05:30", "notes": {}, "receipt": None,
    }])
    orders = pd.DataFrame([{
        "order_id": "order_fuzzy", "amount_paisa": 89900, "created_at": "2026-08-24T13:45:00+05:30",
        "status": "paid", "receipt": "rcpt_unrelated",
    }])

    matches, exceptions = pass3_payment_order(payments, orders)

    assert exceptions == []
    assert len(matches) == 1
    assert matches[0].method == "tier3"
    assert matches[0].confidence == 0.7


def test_tier3_still_requires_contact_match_when_payment_has_contact_fields():
    """Where a payment DOES carry contact info, Tier 3 must still require
    it to agree with the order -- the optional-contact relaxation only
    applies when the payment has no contact fields to check at all."""
    payments = pd.DataFrame([{
        "payment_id": "pay_wrong_contact", "order_id": None, "amount_paisa": 89900, "fee_paisa": 0, "gst_paisa": 0,
        "status": "captured", "captured_at": "2026-08-24T13:41:09+05:30", "notes": {}, "receipt": None,
        "customer_email": "someone-else@example.com",
    }])
    orders = pd.DataFrame([{
        "order_id": "order_fuzzy", "amount_paisa": 89900, "created_at": "2026-08-24T13:45:00+05:30",
        "status": "paid", "receipt": "rcpt_unrelated", "email": "kabir.rao@example.com",
    }])

    matches, exceptions = pass3_payment_order(payments, orders)

    assert matches == []  # contact mismatch must not be waved through just because amount+time lined up
    assert any(e["code"] == "UNMATCHED_PAYMENT" for e in exceptions)


# --------------------------------------------------------------------------
# Journal balance across a full batch
# --------------------------------------------------------------------------


def _full_fixture() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """A 12-order/11-payment/1-refund batch shaped like the real fixture
    that surfaced these bugs: order_LP0003's payment carries no order_id
    (receipt-only linkage), order_LP0012 is a genuine orphan, and one
    refund applies against order_LP0005."""
    orders = []
    payments = []
    for i in range(1, 13):
        order_id = f"order_LP{i:04d}"
        amount = 100000 + i * 1000
        orders.append({
            "order_id": order_id, "amount_paisa": amount, "created_at": f"2026-08-24T{10 + i}:00:00+05:30",
            "customer_email": f"user{i}@example.com", "customer_phone": f"+9198123400{i:02d}",
            "status": "paid", "receipt": f"rcpt_LP{i:04d}",
        })
        if i == 12:
            continue  # order_LP0012: genuine orphan, no payment at all
        payment = {
            "payment_id": f"pay_LP{i:04d}", "order_id": order_id, "amount_paisa": amount,
            "fee_paisa": amount // 50, "gst_paisa": (amount // 50) // 6,
            "status": "captured", "captured_at": f"2026-08-24T{10 + i}:00:10+05:30",
            "notes": {"order_id": order_id}, "receipt": f"rcpt_LP{i:04d}",
        }
        if i == 3:
            payment["order_id"] = None  # pay_LP0003: must fall back to the receipt tier
            payment["notes"] = {}
        payments.append(payment)

    orders_df = pd.DataFrame(orders)
    payments_df = pd.DataFrame(payments)
    refund_amounts = {"order_LP0005": 10000}
    return orders_df, payments_df, refund_amounts


def test_journal_balances_across_the_full_fixture_batch():
    orders, payments, refund_amounts = _full_fixture()

    matches, exceptions = pass3_payment_order(payments, orders)

    assert len(matches) == 11  # every payment except the deliberately-absent order_LP0012 links
    assert {e["code"] for e in exceptions} == {"ORPHAN_ORDER"}
    assert exceptions[0]["record_id"] == "order_LP0012"

    pass4_input = _pass4_input_from_matches(matches, payments)
    journal_lines = pass4_journal(pass4_input, orders, refund_amounts=refund_amounts)  # must not raise

    debit_total = sum(line["amount_paisa"] for line in journal_lines if line["direction"] == "Dr")
    credit_total = sum(line["amount_paisa"] for line in journal_lines if line["direction"] == "Cr")
    assert debit_total == credit_total

    journal_order_ids = {line["order_id"] for line in journal_lines}
    assert "order_LP0012" not in journal_order_ids
    assert journal_order_ids == {m.right_id for m in matches}


# --------------------------------------------------------------------------
# Property: for any batch, debits == credits, and every journal line traces
# to an actual matched payment-order pair.
# --------------------------------------------------------------------------


@st.composite
def _order_payment_batch(draw):
    n = draw(st.integers(min_value=0, max_value=8))
    orders = []
    payments = []
    for i in range(n):
        amount = draw(st.integers(min_value=1000, max_value=999_999))
        order_id = f"order_{i}"
        orders.append({
            "order_id": order_id, "amount_paisa": amount, "created_at": "2026-01-01T00:00:00+05:30", "status": "paid",
        })
        if draw(st.booleans()):  # some orders get no payment at all
            fee = draw(st.integers(min_value=0, max_value=max(0, amount // 10)))
            gst = draw(st.integers(min_value=0, max_value=max(0, fee // 6)))
            payments.append({
                "payment_id": f"pay_{i}", "order_id": order_id, "amount_paisa": amount,
                "fee_paisa": fee, "gst_paisa": gst, "status": "captured",
                "captured_at": "2026-01-01T00:00:05+05:30", "notes": {}, "receipt": f"rcpt_{i}",
            })
    orders_df = pd.DataFrame(orders, columns=["order_id", "amount_paisa", "created_at", "status"])
    payments_df = pd.DataFrame(payments, columns=["payment_id", "order_id", "amount_paisa", "fee_paisa", "gst_paisa", "status", "captured_at", "notes", "receipt"])
    return orders_df, payments_df


@settings(max_examples=100, deadline=None)
@given(_order_payment_batch())
def test_property_journal_always_balances_and_every_line_traces_to_a_match(batch):
    orders, payments = batch

    matches, _ = pass3_payment_order(payments, orders)
    pass4_input = _pass4_input_from_matches(matches, payments)
    journal_lines = pass4_journal(pass4_input, orders, refund_amounts={})  # must never raise

    debit_total = sum(line["amount_paisa"] for line in journal_lines if line["direction"] == "Dr")
    credit_total = sum(line["amount_paisa"] for line in journal_lines if line["direction"] == "Cr")
    assert debit_total == credit_total

    matched_order_ids = {m.right_id for m in matches}
    journal_order_ids = {line["order_id"] for line in journal_lines}
    assert journal_order_ids <= matched_order_ids
