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
    try:
        return pd.to_datetime(value).to_pydatetime()
    except Exception:
        return None


def _payment_timestamp(payment: pd.Series) -> datetime | None:
    """Real Razorpay payment objects report their capture time as
    captured_at, not created_at (created_at, where present, is order-side
    vocabulary) -- check both rather than assuming one name."""
    return _as_dt(payment.get("created_at")) or _as_dt(payment.get("captured_at"))


def _tier1_order_id(payment: pd.Series, orders_by_id: dict[str, pd.Series]) -> str | None:
    if "order_id" in payment.index and pd.notna(payment.get("order_id")) and str(payment["order_id"]) in orders_by_id:
        return str(payment["order_id"])
    return None


def _tier2_receipt(payment: pd.Series, orders_by_id: dict[str, pd.Series]) -> str | None:
    """Matches the payment's receipt against the ORDER's own receipt field.
    (Not "reference" -- no such column exists on a Razorpay order or in this
    project's order schema; "receipt" is the real, populated field on both
    sides, and was already being read correctly off the payment. This was
    the actual bug: the order side of the comparison looked for a field name
    that never existed, so Tier 2 could never succeed for anyone.)
    """
    if "receipt" not in payment.index or pd.isna(payment.get("receipt")):
        return None
    receipt = str(payment["receipt"])
    for order_id_value, order_row in orders_by_id.items():
        if "receipt" in order_row.index and pd.notna(order_row.get("receipt")) and str(order_row["receipt"]) == receipt:
            return order_id_value
    return None


def _tier3_fuzzy_candidates(payment: pd.Series, orders_by_id: dict[str, pd.Series]) -> list[str]:
    """Amount + time window, narrowed by contact match only when the
    payment actually carries contact fields. Real Razorpay payment objects
    do not carry customer_email/customer_phone at all (only orders do) --
    requiring them unconditionally made this tier permanently unreachable
    for real data. When a payment has neither field, amount+time alone (an
    exact amount match within a tight 10-minute window) is the evidence;
    when it does have one, it is still required, preserving the stricter
    behavior for data that supports it.
    """
    amount = int(payment.get("amount_paisa", 0) or 0)
    paid_at = _payment_timestamp(payment)
    has_email = "customer_email" in payment.index and pd.notna(payment.get("customer_email"))
    has_phone = "customer_phone" in payment.index and pd.notna(payment.get("customer_phone"))
    requires_contact = has_email or has_phone

    candidates: list[str] = []
    for order_id_value, order_row in orders_by_id.items():
        if int(order_row.get("amount_paisa", 0) or 0) != amount:
            continue
        order_time = _as_dt(order_row.get("created_at"))
        if paid_at is None or order_time is None:
            continue
        if abs((paid_at - order_time).total_seconds()) > 600:
            continue
        if requires_contact:
            email_match = has_email and "email" in order_row.index and str(payment.get("customer_email", "")).lower() == str(order_row.get("email", "")).lower()
            phone_match = has_phone and "phone" in order_row.index and str(payment.get("customer_phone", "")).replace(" ", "") == str(order_row.get("phone", "")).replace(" ", "")
            if not (email_match or phone_match):
                continue
        candidates.append(order_id_value)
    return candidates


def pass3_payment_order(
    payments_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    *,
    pass_number: int = 3,
) -> tuple[list[MatchRecord], list[dict[str, Any]]]:
    """Link payments to orders using a three-tier matching strategy.

    Tiers cascade -- each is only attempted if the previous one failed to
    produce a candidate, not merely because an earlier tier's identifying
    field happened to be present on the payment (that was a bug: any payment
    carrying a receipt used to skip Tier 3 by construction, even when the
    receipt didn't resolve to any order).
    """
    matches: list[MatchRecord] = []
    exceptions: list[dict[str, Any]] = []

    if payments_df.empty and orders_df.empty:
        return matches, exceptions

    orders_by_id = {str(row["order_id"]): row for _, row in orders_df.iterrows()}
    order_payment_counts: dict[str, int] = {}

    for _, payment in payments_df.iterrows():
        payment_id = str(payment.get("payment_id", "payment-row"))
        payment_notes = str(payment.get("notes", "") or "")

        tier: int | None = None
        candidate: str | None = None

        candidate = _tier1_order_id(payment, orders_by_id)
        if candidate is not None:
            tier = 1

        if candidate is None:
            candidate = _tier2_receipt(payment, orders_by_id)
            if candidate is not None:
                tier = 2

        if candidate is None:
            fuzzy_candidates = _tier3_fuzzy_candidates(payment, orders_by_id)
            if len(fuzzy_candidates) == 1:
                candidate = fuzzy_candidates[0]
                tier = 3
            elif len(fuzzy_candidates) > 1:
                exceptions.append(
                    _build_exception(
                        "AMBIGUOUS_MATCH", "payment", payment_id,
                        candidates=fuzzy_candidates, tier=3, amount_paisa=int(payment.get("amount_paisa", 0) or 0),
                    )
                )
                continue

        if candidate is None:
            # A payment that never resolves to an order must never vanish
            # silently. "paid" is order-status vocabulary and never appears
            # as a payment's own status, so checking for it here (as the
            # original code did) meant this branch could never fire for a
            # real captured/authorized payment -- it silently dropped
            # exactly the records that most needed flagging.
            status = str(payment.get("status", "")).lower()
            if status in {"captured", "authorized", "paid"}:
                exceptions.append(
                    _build_exception(
                        "UNMATCHED_PAYMENT", "payment", payment_id,
                        amount_paisa=int(payment.get("amount_paisa", 0) or 0), status=status,
                    )
                )
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
