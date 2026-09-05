from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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


@dataclass(frozen=True)
class _Claim:
    """A candidate settlement claim staked by one bank credit.

    Claims are collected for every settlement before any winner is decided,
    so that arbitration (see _arbitrate_claims) can pick the strongest
    evidence regardless of which bank row happened to be processed first.
    """

    bank_id: str
    settlement_id: str
    method: str
    confidence: float
    evidence: dict[str, Any]


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


def _parse_utr_candidates(narration: Any) -> list[str]:
    """Every plausible UTR-shaped token in the narration, in the order they
    appear -- not just the first. A real NEFT narration can read
    "NEFT-RAZORPAYSOFTWAREPRIV-<UTR>-HDFC": the first >=10-char bare token
    is the sender's name, not the UTR, and picking only the first one
    silently matched the wrong (and non-existent) settlement every time.
    The caller checks each candidate against real settlement UTRs and uses
    whichever one actually resolves, rather than guessing narration
    structure -- see pass1_bank_settlement's Phase A.
    """
    if pd.isna(narration):
        return []
    text = str(narration).strip()
    if not text:
        return []
    candidates: list[str] = []
    primary = UTR_RE.search(text)
    if primary:
        candidates.append(primary.group(0).upper())
    for match in re.finditer(r"\b[A-Z0-9]{10,}\b", text):
        token = match.group(0).upper()
        if token not in candidates:
            candidates.append(token)
    return candidates


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
    """Match bank credits to settlements using UTR then amount/date fallback.

    Two-phase, order-independent matching:

    Phase A collects, for every bank row, at most one candidate claim on a
    single settlement (a bank row that is itself ambiguous among several
    settlements is routed straight to AMBIGUOUS_MATCH here and contributes
    no claim). A UTR match is only ever labeled "utr" when the parsed token
    actually equals a real settlement's utr -- a coincidental UTR-shaped
    token that matches nothing is not evidence of anything and falls
    through to the amount+date fallback. A UTR match whose amount does not
    reconcile is never accepted silently: it is routed to
    AMOUNT_VARIANCE_UNEXPLAINED instead of becoming a claim at all.

    Phase B arbitrates per settlement across every bank row's claims: a
    UTR-verified claim always outranks an amount+date claim, regardless of
    which one was delivered first. A tie at the top confidence tier is
    refused rather than guessed (AMBIGUOUS_MATCH, matching neither), and
    every losing claim is reported as its own exception rather than
    silently vanishing.
    """
    matches: list[MatchRecord] = []
    exceptions: list[dict[str, Any]] = []

    if bank_statement_df.empty and settlements_df.empty:
        return matches, exceptions

    bank_df = bank_statement_df.copy()
    settlement_df = settlements_df.copy()
    if "utr" not in settlement_df.columns:
        settlement_df["utr"] = ""
    if "amount_paisa" not in settlement_df.columns and "net_amount_paisa" in settlement_df.columns:
        settlement_df["amount_paisa"] = settlement_df["net_amount_paisa"]
    if "amount_paisa" not in bank_df.columns and "net_amount_paisa" in bank_df.columns:
        bank_df["amount_paisa"] = bank_df["net_amount_paisa"]
    # A real bank statement export (SCHEMAS.md's own credit_paisa/debit_paisa
    # split, e.g.) never carries amount_paisa/posted_at/bank_credit_id under
    # those exact names -- without these fallbacks every bank row silently
    # collapses to amount=0, no timestamp, and the literal id "bank-row" for
    # every row (so a 3-row statement is treated as one row three times).
    if "amount_paisa" not in bank_df.columns and "credit_paisa" in bank_df.columns:
        bank_df["amount_paisa"] = bank_df["credit_paisa"]
    if "posted_at" not in bank_df.columns and "value_date" in bank_df.columns:
        bank_df["posted_at"] = bank_df["value_date"]
    if "bank_credit_id" not in bank_df.columns and "bank_id" not in bank_df.columns and "line_no" in bank_df.columns:
        bank_df["bank_credit_id"] = "bank-line-" + bank_df["line_no"].astype(str)

    all_bank_ids: list[str] = []
    resolved_exceptions: dict[str, dict[str, Any]] = {}
    claims_by_settlement: dict[str, list[_Claim]] = {}
    seen_bank_ids: set[str] = set()

    # --- Phase A: collect claims and self-contained (single-row) exceptions ---
    for _, bank_row in bank_df.iterrows():
        bank_id = str(bank_row.get("bank_credit_id", bank_row.get("bank_id", "bank-row")))
        all_bank_ids.append(bank_id)
        if bank_id in seen_bank_ids:
            continue  # duplicate bank_credit_id in the input; first occurrence's outcome stands
        seen_bank_ids.add(bank_id)

        narration = bank_row.get("narration")
        bank_amount = int(bank_row.get("amount_paisa", 0) or 0)

        # Try each candidate token in narration order, but only ever accept
        # one that is VERIFIED against a real settlement UTR -- this is what
        # keeps a coincidental long token (a merchant name, say) from ever
        # being treated as resolving evidence, without needing to guess at
        # narration structure to find "the right" token in the first place.
        # parsed_token is kept separately (for the amount+date fallback's
        # evidence) precisely so a decoy token that never matched anything
        # is still shown honestly rather than reported as None -- see
        # test_fix1_decoy_token_without_real_utr_match_is_labeled_amount_date.
        narration_candidates = _parse_utr_candidates(narration)
        parsed_token = narration_candidates[0] if narration_candidates else None
        utr_token: str | None = None
        utr_settlement_matches = pd.DataFrame()
        for candidate in narration_candidates:
            candidate_matches = settlement_df[settlement_df["utr"].astype(str).str.upper() == candidate]
            if not candidate_matches.empty:
                utr_token = candidate
                utr_settlement_matches = candidate_matches.drop_duplicates(subset=["settlement_id"])
                break

        if not utr_settlement_matches.empty:
            if len(utr_settlement_matches) > 1:
                resolved_exceptions[bank_id] = _build_exception(
                    "AMBIGUOUS_MATCH", "bank_credit", bank_id,
                    candidates=[str(s) for s in utr_settlement_matches["settlement_id"].tolist()],
                    reason="utr_matches_multiple_settlements",
                    narration=narration,
                )
                continue

            settlement_row = utr_settlement_matches.iloc[0]
            settlement_id = str(settlement_row.get("settlement_id"))
            settlement_amount = int(settlement_row.get("amount_paisa", settlement_row.get("net_amount_paisa", 0)) or 0)

            if bank_amount == settlement_amount:
                claim = _Claim(
                    bank_id=bank_id,
                    settlement_id=settlement_id,
                    method="utr",
                    confidence=1.0,
                    evidence={
                        "bank_credit_id": bank_id,
                        "settlement_id": settlement_id,
                        "utr": utr_token,
                        "bank_amount_paisa": bank_amount,
                        "settlement_amount_paisa": settlement_amount,
                        "bank_posted_at": bank_row.get("posted_at"),
                        "settlement_settled_at": settlement_row.get("settled_at"),
                    },
                )
                claims_by_settlement.setdefault(settlement_id, []).append(claim)
            else:
                # FIX 4: a UTR identifies the settlement with certainty, but
                # the amount does not reconcile. Never accept that silently.
                resolved_exceptions[bank_id] = _build_exception(
                    "AMOUNT_VARIANCE_UNEXPLAINED", "bank_credit", bank_id,
                    settlement_id=settlement_id,
                    utr=utr_token,
                    bank_amount_paisa=bank_amount,
                    settlement_amount_paisa=settlement_amount,
                    drift_paisa=bank_amount - settlement_amount,
                    amount_paisa=bank_amount,
                )
            continue

        # No settlement identified by UTR -> amount+date fallback.
        bank_ts = _as_datetime(bank_row.get("posted_at"))
        if bank_ts is None:
            resolved_exceptions[bank_id] = _build_exception(
                "UNMATCHED_BANK_CREDIT", "bank_credit", bank_id, narration=narration, reason="unparseable_posted_at",
                amount_paisa=bank_amount,
            )
            continue

        amount_matches = settlement_df[settlement_df["amount_paisa"].astype(int) == bank_amount]
        candidates = []
        for _, settlement_row in amount_matches.iterrows():
            settlement_ts = _as_datetime(settlement_row.get("settled_at"))
            if settlement_ts is None:
                continue
            if abs((settlement_ts - bank_ts).days) <= date_window_days:
                candidates.append(settlement_row)

        if not candidates:
            resolved_exceptions[bank_id] = _build_exception(
                "UNMATCHED_BANK_CREDIT", "bank_credit", bank_id, narration=narration, amount_paisa=bank_amount,
            )
            continue

        candidate_df = pd.DataFrame(candidates).drop_duplicates(subset=["settlement_id"])
        if len(candidate_df) > 1:
            resolved_exceptions[bank_id] = _build_exception(
                "AMBIGUOUS_MATCH", "bank_credit", bank_id,
                candidates=[str(s) for s in candidate_df["settlement_id"].tolist()],
                narration=narration,
            )
            continue

        settlement_row = candidate_df.iloc[0]
        settlement_id = str(settlement_row.get("settlement_id"))
        claim = _Claim(
            bank_id=bank_id,
            settlement_id=settlement_id,
            method="amount_date",
            confidence=0.95,
            evidence={
                "bank_credit_id": bank_id,
                "settlement_id": settlement_id,
                "utr": None,
                "parsed_narration_token": parsed_token,
                "bank_amount_paisa": bank_amount,
                "settlement_amount_paisa": int(settlement_row.get("amount_paisa", settlement_row.get("net_amount_paisa", 0)) or 0),
                "bank_posted_at": bank_row.get("posted_at"),
                "settlement_settled_at": settlement_row.get("settled_at"),
            },
        )
        claims_by_settlement.setdefault(settlement_id, []).append(claim)

    # --- Phase B: arbitrate per settlement, independent of delivery order ---
    for settlement_id, claims in claims_by_settlement.items():
        max_confidence = max(c.confidence for c in claims)
        winners = [c for c in claims if c.confidence == max_confidence]
        losers = [c for c in claims if c.confidence != max_confidence]

        if len(winners) == 1:
            winner = winners[0]
            matches.append(
                MatchRecord(
                    pass_number=pass_number,
                    method=winner.method,
                    confidence=winner.confidence,
                    evidence=winner.evidence,
                    matched_at=datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    record_type="bank_credit",
                    left_id=winner.bank_id,
                    right_id=settlement_id,
                )
            )
            for loser in losers:
                resolved_exceptions[loser.bank_id] = _build_exception(
                    "UNMATCHED_BANK_CREDIT", "bank_credit", loser.bank_id,
                    reason="lost_arbitration",
                    settlement_id=settlement_id,
                    losing_method=loser.method,
                    losing_confidence=loser.confidence,
                    winning_bank_credit_id=winner.bank_id,
                    winning_method=winner.method,
                    winning_confidence=winner.confidence,
                    amount_paisa=loser.evidence.get("bank_amount_paisa", 0),
                )
        else:
            competing_ids = [c.bank_id for c in winners]
            for winner in winners:
                resolved_exceptions[winner.bank_id] = _build_exception(
                    "AMBIGUOUS_MATCH", "bank_credit", winner.bank_id,
                    settlement_id=settlement_id,
                    reason="tied_confidence_arbitration",
                    tied_confidence=max_confidence,
                    competing_bank_credit_ids=[b for b in competing_ids if b != winner.bank_id],
                )
            for loser in losers:
                resolved_exceptions[loser.bank_id] = _build_exception(
                    "UNMATCHED_BANK_CREDIT", "bank_credit", loser.bank_id,
                    reason="lost_arbitration",
                    settlement_id=settlement_id,
                    losing_confidence=loser.confidence,
                    winning_confidence=max_confidence,
                    amount_paisa=loser.evidence.get("bank_amount_paisa", 0),
                )

    matched_bank_ids = {m.left_id for m in matches}
    for bank_id in dict.fromkeys(all_bank_ids):  # de-duplicated, original order preserved
        if bank_id in matched_bank_ids:
            continue
        exceptions.append(resolved_exceptions.get(bank_id) or _build_exception("UNMATCHED_BANK_CREDIT", "bank_credit", bank_id, reason="unresolved"))

    return matches, exceptions
