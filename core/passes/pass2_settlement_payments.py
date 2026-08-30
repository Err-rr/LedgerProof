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


def _val(row: pd.Series, *keys: str, default: int = 0) -> int:
    for key in keys:
        if key in row.index and pd.notna(row[key]):
            value = row[key]
            if isinstance(value, str):
                cleaned = value.replace(",", "")
                try:
                    return int(cleaned)
                except ValueError:
                    pass
            return int(value)
    return int(default)


def _build_exception(code: str, record_type: str, record_id: str, **details: Any) -> dict[str, Any]:
    return {
        "code": code,
        "record_type": record_type,
        "record_id": record_id,
        "details": details,
    }


def pass2_settlement_payments(
    settlements_df: pd.DataFrame,
    payments_df: pd.DataFrame,
    refunds_df: pd.DataFrame | None = None,
    adjustments_df: pd.DataFrame | None = None,
    *,
    pass_number: int = 2,
) -> tuple[list[MatchRecord], list[dict[str, Any]]]:
    """Match payments to settlement totals and report arithmetic drift or orphan payments."""
    matches: list[MatchRecord] = []
    exceptions: list[dict[str, Any]] = []

    if settlements_df.empty:
        return matches, exceptions

    refund_df = refunds_df.copy() if refunds_df is not None else pd.DataFrame(columns=["refund_id", "payment_id", "order_id", "amount_paisa"])
    adjustment_df = adjustments_df.copy() if adjustments_df is not None else pd.DataFrame(columns=["adjustment_id", "settlement_id", "amount_paisa"])

    if "settlement_id" not in payments_df.columns:
        payments_df = payments_df.copy()
        payments_df["settlement_id"] = payments_df.get("order_id").map(
            {row["order_id"]: row["settlement_id"] for _, row in settlements_df.iterrows()}
        ) if "order_id" in settlements_df.columns and "order_id" in payments_df.columns else ""

    # Match each payment to a settlement whenever a settlement_id is available.
    for _, payment_row in payments_df.iterrows():
        payment_id = str(payment_row.get("payment_id", "payment-row"))
        settlement_id = payment_row.get("settlement_id")
        if pd.isna(settlement_id) or str(settlement_id) == "":
            exceptions.append(_build_exception("UNSETTLED_PAYMENT", "payment", payment_id, amount_paisa=_val(payment_row, "amount_paisa", "gross_amount_paisa", default=0)))
            continue
        if settlement_id not in settlements_df["settlement_id"].astype(str).tolist():
            exceptions.append(_build_exception("UNSETTLED_PAYMENT", "payment", payment_id, settlement_id=str(settlement_id), amount_paisa=_val(payment_row, "amount_paisa", "gross_amount_paisa", default=0)))
            continue
        matches.append(
            MatchRecord(
                pass_number=pass_number,
                method="amount_reconciliation",
                confidence=0.98,
                evidence={
                    "payment_id": payment_id,
                    "settlement_id": str(settlement_id),
                    "payment_amount_paisa": _val(payment_row, "amount_paisa", "gross_amount_paisa", default=0),
                    "fee_paisa": _val(payment_row, "fee_paisa", default=0),
                    "gst_paisa": _val(payment_row, "gst_paisa", "tax_paisa", default=0),
                },
                matched_at=datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%SZ"),
                record_type="payment",
                left_id=payment_id,
                right_id=str(settlement_id),
            )
        )

    for _, settlement_row in settlements_df.iterrows():
        settlement_id = str(settlement_row.get("settlement_id", "settlement-row"))
        settlement_amount = _val(settlement_row, "amount_paisa", "net_amount_paisa", "gross_amount_paisa", default=0)

        settlement_payments = payments_df[payments_df["settlement_id"].astype(str) == settlement_id] if "settlement_id" in payments_df.columns else pd.DataFrame()
        if settlement_payments.empty:
            continue

        payment_net_total = 0
        for _, payment_row in settlement_payments.iterrows():
            amount = _val(payment_row, "amount_paisa", "gross_amount_paisa", default=0)
            fee = _val(payment_row, "fee_paisa", default=0)
            tax = _val(payment_row, "gst_paisa", "tax_paisa", default=0)
            payment_net_total += amount - fee - tax

        refund_total = 0
        if "settlement_id" in refund_df.columns:
            refund_total = int(refund_df[refund_df["settlement_id"].astype(str) == settlement_id]["amount_paisa"].sum())
        elif "payment_id" in refund_df.columns:
            payment_ids = settlement_payments["payment_id"].astype(str).tolist()
            refund_total = int(refund_df[refund_df["payment_id"].astype(str).isin(payment_ids)]["amount_paisa"].sum())

        adjustment_total = 0
        if "settlement_id" in adjustment_df.columns:
            adjustment_total = int(adjustment_df[adjustment_df["settlement_id"].astype(str) == settlement_id]["amount_paisa"].sum())

        expected_total = payment_net_total - refund_total - adjustment_total
        delta = expected_total - settlement_amount
        if delta != 0:
            if payment_net_total != settlement_amount:
                variance_code = "AMOUNT_VARIANCE_PAYMENT_NET"
            elif refund_total != 0:
                variance_code = "AMOUNT_VARIANCE_REFUND"
            elif adjustment_total != 0:
                variance_code = "AMOUNT_VARIANCE_ADJUSTMENT"
            else:
                variance_code = "AMOUNT_VARIANCE_SETTLEMENT"
            exceptions.append(
                _build_exception(
                    "SETTLEMENT_IMBALANCE",
                    "settlement",
                    settlement_id,
                    settlement_amount_paisa=settlement_amount,
                    expected_total_paisa=expected_total,
                    delta_paisa=delta,
                    variance_code=variance_code,
                )
            )

    return matches, exceptions
