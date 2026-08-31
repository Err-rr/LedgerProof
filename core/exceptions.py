from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExceptionCode(str, Enum):
    UNMATCHED_BANK_CREDIT = "UNMATCHED_BANK_CREDIT"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    SETTLEMENT_IMBALANCE = "SETTLEMENT_IMBALANCE"
    UNSETTLED_PAYMENT = "UNSETTLED_PAYMENT"
    ORPHAN_ORDER = "ORPHAN_ORDER"
    DUPLICATE_REFUND = "DUPLICATE_REFUND"
    DUPLICATE_PAYMENT_CANDIDATE = "DUPLICATE_PAYMENT_CANDIDATE"
    AMOUNT_VARIANCE_PAYMENT_NET = "AMOUNT_VARIANCE_PAYMENT_NET"
    AMOUNT_VARIANCE_REFUND = "AMOUNT_VARIANCE_REFUND"
    AMOUNT_VARIANCE_ADJUSTMENT = "AMOUNT_VARIANCE_ADJUSTMENT"
    AMOUNT_VARIANCE_SETTLEMENT = "AMOUNT_VARIANCE_SETTLEMENT"
    AMOUNT_VARIANCE_UNEXPLAINED = "AMOUNT_VARIANCE_UNEXPLAINED"


SEVERITY_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


@dataclass(frozen=True)
class ExceptionRecord:
    code: ExceptionCode
    severity: str
    record_type: str
    record_id: str
    amount_paisa: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def rupee_at_risk(self) -> int:
        if self.code in {
            ExceptionCode.UNSETTLED_PAYMENT,
            ExceptionCode.ORPHAN_ORDER,
            ExceptionCode.DUPLICATE_REFUND,
            ExceptionCode.UNMATCHED_BANK_CREDIT,
            ExceptionCode.SETTLEMENT_IMBALANCE,
            ExceptionCode.AMOUNT_VARIANCE_UNEXPLAINED,
        }:
            return max(0, self.amount_paisa)
        return 0


def build_exception_queue(exceptions: list[dict[str, Any]]) -> list[ExceptionRecord]:
    records: list[ExceptionRecord] = []
    for item in exceptions:
        code = ExceptionCode(item["code"])
        amount = int(item.get("details", {}).get("amount_paisa", item.get("details", {}).get("expected_amount_paisa", 0)) or 0)
        severity = {
            ExceptionCode.UNMATCHED_BANK_CREDIT: "high",
            ExceptionCode.AMBIGUOUS_MATCH: "medium",
            ExceptionCode.SETTLEMENT_IMBALANCE: "critical",
            ExceptionCode.UNSETTLED_PAYMENT: "high",
            ExceptionCode.ORPHAN_ORDER: "high",
            ExceptionCode.DUPLICATE_REFUND: "medium",
            ExceptionCode.DUPLICATE_PAYMENT_CANDIDATE: "medium",
            ExceptionCode.AMOUNT_VARIANCE_PAYMENT_NET: "medium",
            ExceptionCode.AMOUNT_VARIANCE_REFUND: "medium",
            ExceptionCode.AMOUNT_VARIANCE_ADJUSTMENT: "medium",
            ExceptionCode.AMOUNT_VARIANCE_SETTLEMENT: "medium",
            ExceptionCode.AMOUNT_VARIANCE_UNEXPLAINED: "critical",
        }[code]
        record_type = item.get("record_type", "unknown")
        record_id = str(item.get("record_id", "unknown"))
        records.append(
            ExceptionRecord(
                code=code,
                severity=severity,
                record_type=record_type,
                record_id=record_id,
                amount_paisa=amount,
                details=item.get("details", {}),
            )
        )
    return sorted(records, key=lambda item: (-item.rupee_at_risk(), -SEVERITY_RANK[item.severity], item.record_id))


def money_at_rest(exceptions: list[dict[str, Any]]) -> int:
    queue = build_exception_queue(exceptions)
    return sum(item.rupee_at_risk() for item in queue if item.code in {
        ExceptionCode.UNSETTLED_PAYMENT,
        ExceptionCode.ORPHAN_ORDER,
        ExceptionCode.DUPLICATE_REFUND,
        ExceptionCode.UNMATCHED_BANK_CREDIT,
        ExceptionCode.SETTLEMENT_IMBALANCE,
        ExceptionCode.AMOUNT_VARIANCE_UNEXPLAINED,
    })
