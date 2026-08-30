import json
from pathlib import Path

import pandas as pd

from core.passes.pass1_bank_settlement import pass1_bank_settlement
from core.passes.pass2_settlement_payments import pass2_settlement_payments


ROOT = Path(__file__).resolve().parents[1]


def _load_fixture(name: str):
    path = ROOT / "data" / "sample" / name
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _make_bank_settlement_fixtures():
    bank_rows = [
        {
            "bank_credit_id": "BC-000001",
            "settlement_id": "SET-000001",
            "amount_paisa": 125500,
            "posted_at": "2026-01-18T09:00:00Z",
            "narration": "RAZORPAY ACME MART SET-000001 2026-01-18 UTR123456789",
        },
        {
            "bank_credit_id": "BC-000002",
            "settlement_id": "SET-000002",
            "amount_paisa": 200000,
            "posted_at": "2026-01-20T09:00:00Z",
            "narration": "SETTLEMENT ACME MART SET-000002 2026-01-20",
        },
        {
            "bank_credit_id": "BC-000003",
            "settlement_id": "SET-000003",
            "amount_paisa": 300000,
            "posted_at": "2026-01-18T09:00:00Z",
            "narration": "BROKEN NARRATION",
        },
    ]
    settlements = [
        {
            "settlement_id": "SET-000001",
            "amount_paisa": 125500,
            "net_amount_paisa": 125500,
            "utr": "UTR123456789",
            "settled_at": "2026-01-18T08:00:00Z",
        },
        {
            "settlement_id": "SET-000002",
            "amount_paisa": 200000,
            "net_amount_paisa": 200000,
            "utr": "UTR998877665",
            "settled_at": "2026-01-20T08:00:00Z",
        },
    ]
    return pd.DataFrame(bank_rows), pd.DataFrame(settlements)


def test_pass1_bank_settlement_exact_utr_and_ambiguous_fallback():
    bank_df, settlement_df = _make_bank_settlement_fixtures()
    matches, exc = pass1_bank_settlement(bank_df, settlement_df)

    assert len(matches) == 2
    assert {m.right_id for m in matches} == {"SET-000001", "SET-000002"}
    assert any(item["code"] == "UNMATCHED_BANK_CREDIT" for item in exc)

    ambiguous_bank = pd.DataFrame([
        {"bank_credit_id": "BC-000090", "amount_paisa": 100000, "posted_at": "2026-01-19T09:00:00Z", "narration": "SETTLEMENT X 2026-01-19"},
        {"bank_credit_id": "BC-000091", "amount_paisa": 100000, "posted_at": "2026-01-19T09:00:00Z", "narration": "SETTLEMENT X 2026-01-19"},
    ])
    match_df = pd.DataFrame([
        {"settlement_id": "SET-1001", "amount_paisa": 100000, "net_amount_paisa": 100000, "utr": "UTR-ALPHA", "settled_at": "2026-01-18T00:00:00Z"},
        {"settlement_id": "SET-1002", "amount_paisa": 100000, "net_amount_paisa": 100000, "utr": "UTR-BETA", "settled_at": "2026-01-19T12:00:00Z"},
    ])
    matches2, exc2 = pass1_bank_settlement(ambiguous_bank, match_df, date_window_days=2)
    assert len(matches2) == 0
    assert any(item["code"] == "AMBIGUOUS_MATCH" for item in exc2)


def test_pass2_settlement_payments_detects_variance_and_unsettled():
    settlements = pd.DataFrame([
        {
            "settlement_id": "SET-000001",
            "amount_paisa": 120000,
            "net_amount_paisa": 120000,
        },
        {
            "settlement_id": "SET-000002",
            "amount_paisa": 90000,
            "net_amount_paisa": 90000,
        },
    ])
    payments = pd.DataFrame([
        {"payment_id": "PAY-000001", "settlement_id": "SET-000001", "amount_paisa": 100000, "fee_paisa": 2500, "gst_paisa": 450},
        {"payment_id": "PAY-000002", "settlement_id": "SET-000001", "amount_paisa": 30000, "fee_paisa": 500, "gst_paisa": 90},
        {"payment_id": "PAY-000003", "settlement_id": "SET-000003", "amount_paisa": 25000, "fee_paisa": 300, "gst_paisa": 60},
    ])
    refunds = pd.DataFrame([
        {"refund_id": "REF-000001", "payment_id": "PAY-000001", "amount_paisa": 2000},
    ])
    adjustments = pd.DataFrame([
        {"adjustment_id": "ADJ-000001", "settlement_id": "SET-000001", "amount_paisa": 500},
    ])

    matches, exc = pass2_settlement_payments(settlements, payments, refunds, adjustments)

    assert any(item["code"] == "UNSETTLED_PAYMENT" for item in exc)
    assert any(item["code"] == "SETTLEMENT_IMBALANCE" for item in exc)
    assert len(matches) >= 2
