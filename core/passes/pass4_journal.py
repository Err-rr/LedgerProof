from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or pd.isna(value):
        return default
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return default
        return int(float(cleaned))
    return int(value)


def pass4_journal(
    matches_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    *,
    refund_amounts: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Build journal lines per order and assert batch balance."""
    refunds = refund_amounts or {}
    journal_lines: list[dict[str, Any]] = []

    for _, order in orders_df.iterrows():
        order_id = str(order["order_id"])
        order_amount = _as_int(order.get("amount_paisa", 0))
        payment_match = matches_df[matches_df["order_id"].astype(str) == order_id] if "order_id" in matches_df.columns else pd.DataFrame()
        payment_total = 0
        fee_total = 0
        gst_total = 0
        if not payment_match.empty:
            for _, row in payment_match.iterrows():
                payment_total += _as_int(row.get("amount_paisa", 0))
                fee_total += _as_int(row.get("fee_paisa", 0))
                gst_total += _as_int(row.get("gst_paisa", 0))
        refund_total = refunds.get(order_id, 0)

        net_bank = max(0, payment_total - fee_total - gst_total - refund_total)
        dr_bank = net_bank
        dr_gateway_fee = fee_total
        dr_gst = gst_total
        cr_sales = order_amount
        dr_refunds = refund_total

        journal_lines.extend([
            {"order_id": order_id, "account": "Bank", "direction": "Dr", "amount_paisa": dr_bank},
            {"order_id": order_id, "account": "Gateway Fee", "direction": "Dr", "amount_paisa": dr_gateway_fee},
            {"order_id": order_id, "account": "GST Input Credit", "direction": "Dr", "amount_paisa": dr_gst},
            {"order_id": order_id, "account": "Sales", "direction": "Cr", "amount_paisa": cr_sales},
            {"order_id": order_id, "account": "Refunds", "direction": "Dr", "amount_paisa": dr_refunds},
        ])

    debit_total = sum(line["amount_paisa"] for line in journal_lines if line["direction"] == "Dr")
    credit_total = sum(line["amount_paisa"] for line in journal_lines if line["direction"] == "Cr")
    if debit_total != credit_total:
        raise ValueError(f"Journal imbalance detected: debit={debit_total}, credit={credit_total}")

    return journal_lines
