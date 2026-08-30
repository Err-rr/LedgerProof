from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.passes.pass3_payment_order import pass3_payment_order
from core.passes.pass4_journal import pass4_journal
from core.score import compute_score


ROOT = Path(__file__).resolve().parents[1]


def test_pass3_payment_order_matches_and_exceptions():
    payments = pd.DataFrame([
        {
            "payment_id": "PAY-000001",
            "order_id": "ORD-000001",
            "amount_paisa": 125500,
            "fee_paisa": 2188,
            "gst_paisa": 394,
            "created_at": "2026-01-15T10:00:00Z",
            "status": "paid",
            "notes": "order=ORD-000001",
        },
        {
            "payment_id": "PAY-000002",
            "amount_paisa": 100000,
            "fee_paisa": 1750,
            "gst_paisa": 315,
            "created_at": "2026-01-15T10:05:00Z",
            "status": "paid",
            "notes": "",
            "customer_email": "alice@example.com",
            "customer_phone": "+91 99999 99999",
        },
        {
            "payment_id": "PAY-000003",
            "amount_paisa": 200000,
            "fee_paisa": 3500,
            "gst_paisa": 630,
            "created_at": "2026-01-15T10:04:00Z",
            "status": "paid",
            "notes": "",
        },
    ])
    orders = pd.DataFrame([
        {"order_id": "ORD-000001", "amount_paisa": 125500, "status": "paid", "created_at": "2026-01-15T09:59:00Z"},
        {"order_id": "ORD-000002", "amount_paisa": 100000, "status": "paid", "created_at": "2026-01-15T10:00:00Z", "email": "alice@example.com"},
        {"order_id": "ORD-000003", "amount_paisa": 50000, "status": "paid", "created_at": "2026-01-15T10:10:00Z"},
    ])

    matches, exc = pass3_payment_order(payments, orders)
    codes = {item["code"] for item in exc}
    assert len(matches) >= 2
    assert "ORPHAN_ORDER" in codes or "DUPLICATE_PAYMENT_CANDIDATE" in codes or "AMBIGUOUS_MATCH" in codes


def test_pass4_journal_balances_and_raises_on_imbalance():
    matches = pd.DataFrame([
        {"order_id": "ORD-000001", "amount_paisa": 100000, "fee_paisa": 1750, "gst_paisa": 315},
        {"order_id": "ORD-000001", "amount_paisa": 50000, "fee_paisa": 875, "gst_paisa": 158},
    ])
    orders = pd.DataFrame([{"order_id": "ORD-000001", "amount_paisa": 150000, "status": "paid"}])
    lines = pass4_journal(matches, orders, refund_amounts={"ORD-000001": 1000})
    debit_total = sum(line["amount_paisa"] for line in lines if line["direction"] == "Dr")
    credit_total = sum(line["amount_paisa"] for line in lines if line["direction"] == "Cr")
    assert debit_total == credit_total

    bad_orders = pd.DataFrame([{"order_id": "ORD-000002", "amount_paisa": 200000, "status": "paid"}])
    try:
        pass4_journal(pd.DataFrame([{"order_id": "ORD-000002", "amount_paisa": 90000, "fee_paisa": 1000, "gst_paisa": 100}]), bad_orders)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected journal imbalance to raise ValueError")


def test_score_summary_values(tmp_path):
    ground_truth = {
        "seed": 42,
        "order_count": 10,
        "mapping": [{"order_id": "ORD-1", "payment_id": "PAY-1"}, {"order_id": "ORD-2", "payment_id": "PAY-2"}],
        "defects": [{"type": "missing_payment"}],
    }
    path = tmp_path / "ground_truth.json"
    path.write_text(json.dumps(ground_truth), encoding="utf-8")

    summary = compute_score(path, matches_count=2, exception_count=1)
    assert summary["match_rate"] == 1.0
    assert summary["auto_resolve_rate"] == 0.6666666666666666
    assert summary["precision"] == 0.6666666666666666
