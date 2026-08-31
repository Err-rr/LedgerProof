"""Orchestrates one reconciliation run: parses uploaded source files, runs
the four deterministic passes (never an LLM -- CLAUDE.md rule 2), and shapes
the results into rows the Repository can persist plus a RunSummary.

This is the only place in the API that touches core.passes. Nothing in this
module makes a matching decision itself; it only wires the passes together
and joins their outputs into the shapes the DB layer and the response
schemas expect.
"""

from __future__ import annotations

import io
import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from core.exceptions import build_exception_queue, money_at_rest
from core.passes.pass1_bank_settlement import pass1_bank_settlement
from core.passes.pass2_settlement_payments import pass2_settlement_payments
from core.passes.pass3_payment_order import pass3_payment_order
from core.passes.pass4_journal import pass4_journal
from api.schemas import RunSummary


@dataclass(frozen=True)
class UploadedSourceFiles:
    orders_xlsx: bytes
    payments_json: bytes
    settlements_json: bytes
    bank_statement_csv: bytes
    refunds_json: bytes | None = None


@dataclass(frozen=True)
class ReconciliationResult:
    match_record_rows: list[dict]
    exception_rows: list[dict]
    journal_line_rows: list[dict]
    summary: RunSummary


def _parse_json_records(raw: bytes | None) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    data = json.loads(raw.decode("utf-8"))
    if isinstance(data, dict):
        data = data.get("records", data.get("data", [data]))
    return pd.DataFrame(data)


def load_frames(files: UploadedSourceFiles) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    orders_df = pd.read_excel(io.BytesIO(files.orders_xlsx), sheet_name="orders")
    payments_df = _parse_json_records(files.payments_json)
    settlements_df = _parse_json_records(files.settlements_json)
    refunds_df = _parse_json_records(files.refunds_json)
    bank_df = pd.read_csv(io.BytesIO(files.bank_statement_csv))
    return orders_df, payments_df, refunds_df, settlements_df, bank_df


def _match_records_to_rows(matches: list, now: datetime) -> list[dict]:
    rows = []
    for match in matches:
        d = match.asdict()
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "pass_number": d["pass_number"],
                "method": d["method"],
                "confidence": d["confidence"],
                "evidence": d["evidence"],
                "matched_at": d["matched_at"],
                "record_type": d["record_type"],
                "left_id": d["left_id"],
                "right_id": d["right_id"],
                "created_at": now,
            }
        )
    return rows


def _exception_dicts_to_rows(all_exceptions: list[dict], now: datetime) -> list[dict]:
    queue = build_exception_queue(all_exceptions)
    rows = []
    for record in queue:
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "code": record.code.value,
                "severity": record.severity,
                "record_type": record.record_type,
                "record_id": record.record_id,
                "amount_paisa": record.amount_paisa,
                "rupee_at_risk_paisa": record.rupee_at_risk(),
                "details": record.details,
                "created_at": now,
            }
        )
    return rows


def _journal_lines_to_rows(lines: list[dict], now: datetime) -> list[dict]:
    return [
        {
            "id": str(uuid.uuid4()),
            "order_id": line["order_id"],
            "account": line["account"],
            "direction": line["direction"],
            "amount_paisa": line["amount_paisa"],
            "created_at": now,
        }
        for line in lines
    ]


def _build_pass4_input(payment_order_matches: list, payments_df: pd.DataFrame) -> pd.DataFrame:
    """pass4_journal needs order_id + amount/fee/gst per matched payment.

    pass3's MatchRecord evidence carries the gross amount but not fee/gst, so
    join its (payment_id -> order_id) pairs back onto the original payments
    to pull the fee/gst that fund the journal's Dr Gateway Fee / Dr GST lines.
    """
    if not payment_order_matches or payments_df.empty:
        return pd.DataFrame(columns=["order_id", "amount_paisa", "fee_paisa", "gst_paisa"])

    pairs = pd.DataFrame(
        [{"payment_id": m.left_id, "order_id": m.right_id} for m in payment_order_matches]
    )
    payments_indexed = payments_df.set_index(payments_df["payment_id"].astype(str))
    rows = []
    for _, pair in pairs.iterrows():
        payment_id = str(pair["payment_id"])
        if payment_id not in payments_indexed.index:
            continue
        payment = payments_indexed.loc[payment_id]
        rows.append(
            {
                "order_id": pair["order_id"],
                "amount_paisa": int(payment.get("amount_paisa", 0) or 0),
                "fee_paisa": int(payment.get("fee_paisa", 0) or 0),
                "gst_paisa": int(payment.get("gst_paisa", payment.get("tax_paisa", 0)) or 0),
            }
        )
    return pd.DataFrame(rows, columns=["order_id", "amount_paisa", "fee_paisa", "gst_paisa"])


def _refund_totals_by_order(refunds_df: pd.DataFrame) -> dict[str, int]:
    if refunds_df.empty or "order_id" not in refunds_df.columns:
        return {}
    totals = refunds_df.groupby("order_id")["amount_paisa"].sum()
    return {str(order_id): int(amount) for order_id, amount in totals.items()}


def run_reconciliation(files: UploadedSourceFiles) -> ReconciliationResult:
    now = datetime.now(timezone.utc)
    orders_df, payments_df, refunds_df, settlements_df, bank_df = load_frames(files)

    bank_matches, bank_exceptions = pass1_bank_settlement(bank_df, settlements_df)
    settlement_matches, settlement_exceptions = pass2_settlement_payments(settlements_df, payments_df, refunds_df, None)
    order_matches, order_exceptions = pass3_payment_order(payments_df, orders_df)

    pass4_input = _build_pass4_input(order_matches, payments_df)
    refund_totals = _refund_totals_by_order(refunds_df)
    journal_lines = pass4_journal(pass4_input, orders_df, refund_amounts=refund_totals)

    all_matches = bank_matches + settlement_matches + order_matches
    all_exceptions = bank_exceptions + settlement_exceptions + order_exceptions

    match_record_rows = _match_records_to_rows(all_matches, now)
    exception_rows = _exception_dicts_to_rows(all_exceptions, now)
    journal_line_rows = _journal_lines_to_rows(journal_lines, now)

    total_orders = len(orders_df)
    total_matches = len(all_matches)
    total_exceptions = len(exception_rows)
    # match_rate is scoped to pass3 (payment<->order): the most order-centric
    # pass, and the one that answers "how many orders did we identify money
    # for at all." auto_resolve_rate mirrors core.score.compute_score's
    # definition (matches / (matches + exceptions)) across all three passes,
    # since that formula needs no ground truth.
    match_rate = (len(order_matches) / total_orders) if total_orders else 0.0
    auto_resolve_rate = (total_matches / (total_matches + total_exceptions)) if (total_matches + total_exceptions) else 0.0
    exceptions_by_code = dict(Counter(row["code"] for row in exception_rows))

    summary = RunSummary(
        total_orders=total_orders,
        total_matches=total_matches,
        total_exceptions=total_exceptions,
        match_rate=match_rate,
        auto_resolve_rate=auto_resolve_rate,
        money_at_rest_paisa=money_at_rest(all_exceptions),
        exceptions_by_code=exceptions_by_code,
    )

    return ReconciliationResult(
        match_record_rows=match_record_rows,
        exception_rows=exception_rows,
        journal_line_rows=journal_line_rows,
        summary=summary,
    )
