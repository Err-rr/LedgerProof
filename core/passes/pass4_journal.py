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
    unsettled_order_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build journal lines per MATCHED payment-order pair and assert batch balance.

    Iterates over `matches_df` (the payment<->order pairs pass3 actually
    resolved), never over the raw order list. An order with no matched
    payment -- and, symmetrically, a payment with no matched order, since
    such a payment never appears in `matches_df` to begin with -- generates
    NO journal lines at all. That silence is deliberate: the order is
    already carried by its own ORPHAN_ORDER exception (or the payment by its
    own UNMATCHED_PAYMENT exception), and recognizing revenue for money that
    never arrived is a distinct, worse failure than an honest exception --
    see audit/FINDINGS.md.

    `unsettled_order_ids` lets the caller mark orders whose matched payment
    has not actually been confirmed settled (see pass2's UNSETTLED_PAYMENT).
    For those, the net amount is debited to "Settlement Receivable" instead
    of "Bank" -- captured money that hasn't reached the bank yet is not the
    same thing as cash in the bank, even though both keep the journal
    balanced (this only changes which account absorbs the debit, never the
    amount).
    """
    refunds = refund_amounts or {}
    unsettled = unsettled_order_ids or set()
    journal_lines: list[dict[str, Any]] = []

    if matches_df.empty or "order_id" not in matches_df.columns:
        return journal_lines

    orders_by_id = {str(row["order_id"]): row for _, row in orders_df.iterrows()}

    for order_id in matches_df["order_id"].astype(str).unique():
        if order_id not in orders_by_id:
            continue  # defensive: a match referencing an order not in this batch
        order = orders_by_id[order_id]
        order_amount = _as_int(order.get("amount_paisa", 0))
        payment_match = matches_df[matches_df["order_id"].astype(str) == order_id]

        payment_total = 0
        fee_total = 0
        gst_total = 0
        for _, row in payment_match.iterrows():
            payment_total += _as_int(row.get("amount_paisa", 0))
            fee_total += _as_int(row.get("fee_paisa", 0))
            gst_total += _as_int(row.get("gst_paisa", 0))
        refund_total = refunds.get(order_id, 0)

        net_amount = max(0, payment_total - fee_total - gst_total - refund_total)
        cash_account = "Settlement Receivable" if order_id in unsettled else "Bank"

        journal_lines.extend([
            {"order_id": order_id, "account": cash_account, "direction": "Dr", "amount_paisa": net_amount},
            {"order_id": order_id, "account": "Gateway Fee", "direction": "Dr", "amount_paisa": fee_total},
            {"order_id": order_id, "account": "GST Input Credit", "direction": "Dr", "amount_paisa": gst_total},
            {"order_id": order_id, "account": "Sales", "direction": "Cr", "amount_paisa": order_amount},
            {"order_id": order_id, "account": "Refunds", "direction": "Dr", "amount_paisa": refund_total},
        ])

    debit_total = sum(line["amount_paisa"] for line in journal_lines if line["direction"] == "Dr")
    credit_total = sum(line["amount_paisa"] for line in journal_lines if line["direction"] == "Cr")
    if debit_total != credit_total:
        raise ValueError(f"Journal imbalance detected: debit={debit_total}, credit={credit_total}")

    return journal_lines
