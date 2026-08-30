from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class MatchRecord:
    pass_number: int
    method: str
    confidence: float
    evidence: dict[str, Any]
    matched_at: str
    record_type: str
    left_id: str
    right_id: str

    def asdict(self) -> dict[str, Any]:
        return {
            "pass_number": self.pass_number,
            "method": self.method,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "matched_at": self.matched_at,
            "record_type": self.record_type,
            "left_id": self.left_id,
            "right_id": self.right_id,
        }


def _build_exception(code: str, record_type: str, record_id: str, **details: Any) -> dict[str, Any]:
    return {
        "code": code,
        "record_type": record_type,
        "record_id": record_id,
        "details": details,
    }


def _as_dt(value: Any) -> datetime | None:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        try:
            return pd.to_datetime(value).to_pydatetime()
        except Exception:
            return None
    try:
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return None


def pass3_payment_order(
    payments_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    *,
    pass_number: int = 3,
) -> tuple[list[MatchRecord], list[dict[str, Any]]]:
    """Link payments to orders using a three-tier matching strategy."""
    matches: list[MatchRecord] = []
    exceptions: list[dict[str, Any]] = []

    if payments_df.empty or orders_df.empty:
        return matches, exceptions

    orders_by_id = {str(row["order_id"]): row for _, row in orders_df.iterrows()}
    order_payment_counts: dict[str, int] = {}

    for _, payment in payments_df.iterrows():
        payment_id = str(payment.get("payment_id", "payment-row"))
        payment_notes = str(payment.get("notes", "") or "")
        order_id = None

        if "order_id" in payment.index and pd.notna(payment.get("order_id")):
            order_id = str(payment["order_id"])
        if not order_id:
            if "order_reference" in payment.index and pd.notna(payment.get("order_reference")):
                order_id = str(payment["order_reference"])

        tier = None
        candidate = None

        if "order_id" in payment.index and pd.notna(payment.get("order_id")) and str(payment["order_id"]) in orders_by_id:
            candidate = str(payment["order_id"])
            tier = 1
        elif "receipt" in payment.index and pd.notna(payment.get("receipt")):
            receipt = str(payment["receipt"])
            for order_id_value, order_row in orders_by_id.items():
                if "reference" in order_row and str(order_row["reference"]) == receipt:
                    candidate = order_id_value
                    tier = 2
                    break
        else:
            amount = int(payment.get("amount_paisa", 0) or 0)
            paid_at = _as_dt(payment.get("created_at"))
            candidates = []
            for order_id_value, order_row in orders_by_id.items():
                order_amount = int(order_row.get("amount_paisa", 0) or 0)
                if order_amount != amount:
                    continue
                order_time = _as_dt(order_row.get("created_at"))
                if paid_at is not None and order_time is not None:
                    if abs((paid_at - order_time).total_seconds()) <= 600:
                        email_match = False
                        phone_match = False
                        if "customer_email" in payment.index and "email" in order_row.index:
                            email_match = str(payment.get("customer_email", "")).lower() == str(order_row.get("email", "")).lower()
                        if "customer_phone" in payment.index and "phone" in order_row.index:
                            phone_match = str(payment.get("customer_phone", "")).replace(" ", "") == str(order_row.get("phone", "")).replace(" ", "")
                        if email_match or phone_match:
                            candidates.append(order_id_value)
            if len(candidates) == 1:
                candidate = candidates[0]
                tier = 3
            elif len(candidates) > 1:
                exceptions.append(_build_exception("AMBIGUOUS_MATCH", "payment", payment_id, candidates=candidates, tier=3, amount_paisa=amount))
                continue

        if candidate is None:
            if str(payment.get("status", "")).lower() == "paid":
                exceptions.append(_build_exception("ORPHAN_ORDER", "order", str(payment.get("order_id", payment_id)), payment_id=payment_id))
            continue

        order_payment_counts[candidate] = order_payment_counts.get(candidate, 0) + 1
        if order_payment_counts[candidate] > 1:
            exceptions.append(_build_exception("DUPLICATE_PAYMENT_CANDIDATE", "payment", payment_id, order_id=candidate, candidate_count=order_payment_counts[candidate]))
            continue

        matches.append(
            MatchRecord(
                pass_number=pass_number,
                method=f"tier{tier}",
                confidence=1.0 if tier == 1 else 0.95 if tier == 2 else 0.7,
                evidence={
                    "payment_id": payment_id,
                    "order_id": candidate,
                    "tier": tier,
                    "notes": payment_notes,
                    "amount_paisa": int(payment.get("amount_paisa", 0) or 0),
                },
                matched_at=datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%SZ"),
                record_type="payment",
                left_id=payment_id,
                right_id=candidate,
            )
        )

    for order_id, order_row in orders_by_id.items():
        if str(order_row.get("status", "")).lower() == "paid" and order_id not in order_payment_counts:
            exceptions.append(_build_exception("ORPHAN_ORDER", "order", order_id, status=str(order_row.get("status"))))

    return matches, exceptions
