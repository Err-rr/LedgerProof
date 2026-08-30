from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

import pandas as pd


UTR_RE = re.compile(r"(?:UTR|REF|TXN|NARR|TRACE)[A-Z0-9-]{6,}", re.IGNORECASE)


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


def _as_datetime(value: Any) -> datetime | None:
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            return pd.to_datetime(normalized).to_pydatetime()
        except Exception:
            return None
    return pd.to_datetime(value).to_pydatetime()


def _parse_utr_from_narration(narration: Any) -> str | None:
    if pd.isna(narration):
        return None
    text = str(narration).strip()
    if not text:
        return None
    match = UTR_RE.search(text)
    if match:
        return match.group(0).upper()
    exact = re.search(r"\b[A-Z0-9]{10,}\b", text)
    if exact:
        return exact.group(0).upper()
    return None


def _build_exception(code: str, record_type: str, record_id: str, **details: Any) -> dict[str, Any]:
    return {
        "code": code,
        "record_type": record_type,
        "record_id": record_id,
        "details": details,
    }


def pass1_bank_settlement(
    bank_statement_df: pd.DataFrame,
    settlements_df: pd.DataFrame,
    *,
    date_window_days: int = 2,
    pass_number: int = 1,
) -> tuple[list[MatchRecord], list[dict[str, Any]]]:
    """Match bank credits to settlements using UTR then amount/date fallback."""
    matches: list[MatchRecord] = []
    exceptions: list[dict[str, Any]] = []

    if bank_statement_df.empty or settlements_df.empty:
        return matches, exceptions

    bank_df = bank_statement_df.copy()
    settlement_df = settlements_df.copy()
    if "utr" not in settlement_df.columns:
        settlement_df["utr"] = ""
    if "amount_paisa" not in settlement_df.columns and "net_amount_paisa" in settlement_df.columns:
        settlement_df["amount_paisa"] = settlement_df["net_amount_paisa"]
    if "amount_paisa" not in bank_df.columns and "net_amount_paisa" in bank_df.columns:
        bank_df["amount_paisa"] = bank_df["net_amount_paisa"]

    used_settlement_ids: set[str] = set()
    used_bank_ids: set[str] = set()

    for _, bank_row in bank_df.iterrows():
        bank_id = str(bank_row.get("bank_credit_id", bank_row.get("bank_id", "bank-row")))
        narration = bank_row.get("narration")
        utr = _parse_utr_from_narration(narration)
        candidate_df = pd.DataFrame()

        if utr:
            candidate_df = settlement_df[settlement_df["utr"].astype(str).str.upper() == utr.upper()]
        if candidate_df.empty:
            amount = int(bank_row.get("amount_paisa", 0) or 0)
            bank_ts = _as_datetime(bank_row.get("posted_at"))
            amount_matches = settlement_df[settlement_df["amount_paisa"].astype(int) == int(amount)]
            if bank_ts is not None and not amount_matches.empty:
                candidates = []
                for _, settlement_row in amount_matches.iterrows():
                    settlement_ts = _as_datetime(settlement_row.get("settled_at"))
                    if settlement_ts is None:
                        continue
                    if abs((settlement_ts - bank_ts).days) <= date_window_days:
                        candidates.append(settlement_row)
                if candidates:
                    candidate_df = pd.DataFrame(candidates)

        if candidate_df.empty:
            if bank_id not in used_bank_ids:
                exceptions.append(_build_exception("UNMATCHED_BANK_CREDIT", "bank_credit", str(bank_id), narration=narration))
                used_bank_ids.add(bank_id)
            continue

        candidate_df = candidate_df.drop_duplicates(subset=["settlement_id"]).copy()
        candidate_ids = [str(row.get("settlement_id")) for _, row in candidate_df.iterrows()]

        if len(candidate_ids) > 1:
            exceptions.append(_build_exception("AMBIGUOUS_MATCH", "bank_credit", str(bank_id), candidates=candidate_ids, narration=narration))
            continue

        settlement_id = candidate_ids[0]
        if settlement_id in used_settlement_ids:
            exceptions.append(_build_exception("UNMATCHED_BANK_CREDIT", "bank_credit", str(bank_id), reason="settlement_already_matched"))
            continue

        settlement_row = candidate_df.iloc[0]
        method = "utr" if utr else "amount_date"
        confidence = 1.0 if utr else 0.95
        evidence = {
            "bank_credit_id": str(bank_id),
            "settlement_id": settlement_id,
            "utr": utr,
            "bank_amount_paisa": int(bank_row.get("amount_paisa", 0) or 0),
            "settlement_amount_paisa": int(settlement_row.get("amount_paisa", settlement_row.get("net_amount_paisa", 0)) or 0),
            "bank_posted_at": bank_row.get("posted_at"),
            "settlement_settled_at": settlement_row.get("settled_at"),
        }
        matches.append(
            MatchRecord(
                pass_number=pass_number,
                method=method,
                confidence=confidence,
                evidence=evidence,
                matched_at=datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%SZ"),
                record_type="bank_credit",
                left_id=str(bank_id),
                right_id=str(settlement_id),
            )
        )
        used_settlement_ids.add(settlement_id)
        used_bank_ids.add(bank_id)

    return matches, exceptions
