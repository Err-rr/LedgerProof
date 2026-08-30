#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import random
import tempfile
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook


INSTRUMENT_MDR = {
    "UPI": 0.0025,
    "CARD": 0.0175,
    "NETBANKING": 0.0075,
    "WALLET": 0.015,
}

BANK_TEMPLATES = [
    "RAZORPAY {merchant_name} {settlement_id} {date}",
    "SETTLEMENT {merchant_name} {settlement_id} {date} INR",
    "MERCHANT Payout {merchant_name} {settlement_id} {date}",
    "RZP {merchant_name} {settlement_id} {date} SETTLED",
]

BANK_SOURCES = ["HDFC", "ICICI", "SBI", "AXIS"]
MERCHANTS = [
    "ACME MART",
    "BLOOM BOUTIQUE",
    "NOVA SUPERMARKET",
    "SOLSTICE TRAVEL",
    "SUNRISE PHARMA",
    "LUMEN ELECTRONICS",
    "ORBIT BOOKS",
    "HARBOUR FASHION",
    "GOLDEN GARDEN",
    "RIVERSTONE FOODS",
]

DEFECT_RATES = {
    "missing_payment": 0.02,
    "duplicate_payment": 0.01,
    "payment_amount_mismatch": 0.08,
    "refund_amount_mismatch": 0.04,
    "settlement_amount_mismatch": 0.06,
    "bank_credit_amount_mismatch": 0.05,
    "narration_mismatch": 0.03,
}


@dataclass(frozen=True)
class DefectSpec:
    type: str
    record_type: str
    rate: float
    enabled: bool = False


def iso_utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_fee_and_gst(amount_paisa: int, instrument: str) -> tuple[int, int, int]:
    mdr = INSTRUMENT_MDR[instrument]
    fee_paisa = round(amount_paisa * mdr)
    gst_paisa = round(fee_paisa * 0.18)
    net_amount_paisa = amount_paisa - fee_paisa - gst_paisa
    return fee_paisa, gst_paisa, net_amount_paisa


def build_statement_meta(order_index: int, settlement_index: int, rng: random.Random) -> tuple[str, str, str, str]:
    statement_index = (settlement_index - 1) // max(1, max(5, min(25, order_index // 8)))
    statement_id = f"STMT-{statement_index + 1:04d}"
    source_bank = BANK_SOURCES[(statement_index + order_index) % len(BANK_SOURCES)]
    merchant_name = MERCHANTS[(statement_index + order_index) % len(MERCHANTS)]
    template = BANK_TEMPLATES[statement_index % len(BANK_TEMPLATES)]
    return statement_id, source_bank, merchant_name, template


def make_order(index: int, rng: random.Random, base_time: datetime) -> dict[str, Any]:
    order_id = f"ORD-{index:06d}"
    customer_id = f"CUST-{index:06d}"
    amount_paisa = rng.randint(50000, 1500000)
    instrument = rng.choice(list(INSTRUMENT_MDR.keys()))
    created_at = base_time + timedelta(minutes=index * 12, seconds=rng.randint(0, 59))
    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "amount_paisa": amount_paisa,
        "currency": "INR",
        "created_at": iso_utc(created_at),
        "status": "paid",
        "instrument": instrument,
    }


def generate_orders(seed: int, order_count: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    base_time = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)
    orders: list[dict[str, Any]] = []
    payments: list[dict[str, Any]] = []
    refunds: list[dict[str, Any]] = []
    settlements: list[dict[str, Any]] = []
    bank_rows: list[dict[str, Any]] = []
    mapping: list[dict[str, Any]] = []

    for index in range(1, order_count + 1):
        order = make_order(index, rng, base_time)
        orders.append(order)

        payment_id = f"PAY-{index:06d}"
        fee_paisa, gst_paisa, net_amount_paisa = compute_fee_and_gst(order["amount_paisa"], order["instrument"])
        payment = {
            "payment_id": payment_id,
            "order_id": order["order_id"],
            "amount_paisa": order["amount_paisa"],
            "instrument": order["instrument"],
            "fee_paisa": fee_paisa,
            "gst_paisa": gst_paisa,
            "net_amount_paisa": net_amount_paisa,
            "status": "captured",
            "created_at": iso_utc(base_time + timedelta(minutes=index * 12 + 2, seconds=10)),
        }
        payments.append(payment)

        refund_amount = 0
        if rng.random() < 0.22:
            refund_amount = max(1000, int(order["amount_paisa"] * rng.uniform(0.08, 0.25)))
            refund_id = f"REF-{index:06d}"
            refunds.append({
                "refund_id": refund_id,
                "payment_id": payment_id,
                "order_id": order["order_id"],
                "amount_paisa": refund_amount,
                "status": "processed",
                "created_at": iso_utc(base_time + timedelta(minutes=index * 12 + 8, seconds=15)),
            })

        settlement_id = f"SET-{index:06d}"
        settlement = {
            "settlement_id": settlement_id,
            "payment_id": payment_id,
            "order_id": order["order_id"],
            "gross_amount_paisa": order["amount_paisa"],
            "fee_paisa": fee_paisa,
            "gst_paisa": gst_paisa,
            "net_amount_paisa": net_amount_paisa,
            "status": "settled",
            "settled_at": iso_utc(base_time + timedelta(days=index // 2 + 2, hours=9, minutes=5)),
        }
        settlements.append(settlement)

        statement_id, source_bank, merchant_name, template = build_statement_meta(index, index, rng)
        settled_dt = datetime.fromisoformat(settlement["settled_at"].replace("Z", "+00:00"))
        date_str = settled_dt.strftime("%Y-%m-%d")
        narration = template.format(
            merchant_name=merchant_name.upper(),
            settlement_id=settlement_id,
            date=date_str,
        )
        bank_credit_id = f"BC-{index:06d}"
        bank_row = {
            "bank_credit_id": bank_credit_id,
            "statement_id": statement_id,
            "settlement_id": settlement_id,
            "order_id": order["order_id"],
            "amount_paisa": settlement["net_amount_paisa"],
            "narration": narration,
            "posted_at": iso_utc(settled_dt + timedelta(hours=2)),
            "source_bank": source_bank,
            "bank_template": template,
        }
        bank_rows.append(bank_row)

        mapping.append({
            "order_id": order["order_id"],
            "payment_id": payment_id,
            "settlement_id": settlement_id,
            "bank_credit_id": bank_credit_id,
            "amount_paisa": order["amount_paisa"],
            "fee_paisa": fee_paisa,
            "gst_paisa": gst_paisa,
            "net_amount_paisa": net_amount_paisa,
            "statement_id": statement_id,
            "refund_amount_paisa": refund_amount,
        })

    return orders, payments, refunds, settlements, bank_rows, mapping


def write_excel_orders(orders: list[dict[str, Any]], out_path: Path) -> None:
    workbook = Workbook()
    ws = workbook.active
    ws.title = "orders"
    headers = [
        "order_id",
        "customer_id",
        "amount_paisa",
        "currency",
        "created_at",
        "status",
    ]
    ws.append(headers)
    for row in orders:
        ws.append([
            row["order_id"],
            row["customer_id"],
            row["amount_paisa"],
            row["currency"],
            row["created_at"],
            row["status"],
        ])
    ws.freeze_panes = "A2"
    workbook.properties.creator = "LedgerProof"
    workbook.properties.lastModifiedBy = "LedgerProof"
    workbook.properties.created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    workbook.properties.modified = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_file:
        temp_path = Path(tmp_file.name)

    workbook.save(temp_path)

    with zipfile.ZipFile(temp_path, "r") as source_zip:
        file_map = {info.filename: source_zip.read(info.filename) for info in source_zip.infolist()}

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as target_zip:
        for filename in sorted(file_map):
            data = file_map[filename]
            if filename == "docProps/core.xml":
                text = data.decode("utf-8")
                text = text.replace(
                    "2026-01-01T00:00:00Z",
                    "1980-01-01T00:00:00Z",
                )
                text = text.replace(
                    "2026-01-01T00:00:00Z",
                    "1980-01-01T00:00:00Z",
                )
                data = text.encode("utf-8")
            entry = zipfile.ZipInfo(filename=filename, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            target_zip.writestr(entry, data)

    temp_path.unlink(missing_ok=True)


def apply_defects(
    orders: list[dict[str, Any]],
    payments: list[dict[str, Any]],
    refunds: list[dict[str, Any]],
    settlements: list[dict[str, Any]],
    bank_rows: list[dict[str, Any]],
    rng: random.Random,
    flags: dict[str, bool],
) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []
    payment_lookup = {payment["payment_id"]: payment for payment in payments}
    settlement_lookup = {settlement["settlement_id"]: settlement for settlement in settlements}
    refund_lookup = {refund["refund_id"]: refund for refund in refunds}
    bank_lookup = {bank_row["bank_credit_id"]: bank_row for bank_row in bank_rows}

    for defect_name, rate in DEFECT_RATES.items():
        if not flags.get(defect_name, False):
            continue
        k = max(0, round(rate * len(orders)))
        selected_indices = set(rng.sample(range(len(orders)), k)) if k else set()

        if defect_name == "missing_payment":
            for idx in sorted(selected_indices):
                order = orders[idx]
                payment = payment_lookup.get(f"PAY-{idx + 1:06d}")
                if payment is not None:
                    payments.remove(payment)
                defects.append({
                    "type": defect_name,
                    "record_type": "payment",
                    "record_id": f"PAY-{idx + 1:06d}",
                    "details": {"expected_record_present": True, "actual_record_present": False},
                })

        elif defect_name == "duplicate_payment":
            for idx in sorted(selected_indices):
                order = orders[idx]
                payment_id = f"PAY-{idx + 1:06d}"
                original = payment_lookup.get(payment_id)
                if original is None:
                    continue
                duplicate = {**original, "payment_id": f"PAY-{idx + 1:06d}-DUP"}
                payments.append(duplicate)
                defects.append({
                    "type": defect_name,
                    "record_type": "payment",
                    "record_id": payment_id,
                    "details": {
                        "original_payment_id": payment_id,
                        "duplicate_payment_id": duplicate["payment_id"],
                    },
                })

        elif defect_name == "payment_amount_mismatch":
            for idx in sorted(selected_indices):
                order = orders[idx]
                payment_id = f"PAY-{idx + 1:06d}"
                payment = payment_lookup.get(payment_id)
                if payment is None:
                    continue
                expected = payment["amount_paisa"]
                actual = max(1000, expected - rng.randint(1000, 50000))
                payment["amount_paisa"] = actual
                payment["net_amount_paisa"] = actual - payment["fee_paisa"] - payment["gst_paisa"]
                defects.append({
                    "type": defect_name,
                    "record_type": "payment",
                    "record_id": payment_id,
                    "details": {"expected_amount_paisa": expected, "actual_amount_paisa": actual},
                })

        elif defect_name == "refund_amount_mismatch":
            k2 = max(0, round(rate * len(orders)))
            selected_order_indices = set(rng.sample(range(len(orders)), k2)) if k2 else set()
            for idx in sorted(selected_order_indices):
                order = orders[idx]
                matched_refund = next((refund for refund in refunds if refund["order_id"] == order["order_id"]), None)
                if matched_refund is None:
                    refund_id = f"REF-{idx + 1:06d}"
                    refund = {
                        "refund_id": refund_id,
                        "payment_id": f"PAY-{idx + 1:06d}",
                        "order_id": order["order_id"],
                        "amount_paisa": max(1000, int(order["amount_paisa"] * 0.10)),
                        "status": "processed",
                        "created_at": iso_utc(datetime(2026, 1, 15, tzinfo=timezone.utc) + timedelta(minutes=idx * 12 + 16)),
                    }
                    refunds.append(refund)
                    matched_refund = refund
                expected = matched_refund["amount_paisa"]
                actual = max(1000, expected - rng.randint(250, 2500))
                matched_refund["amount_paisa"] = actual
                defects.append({
                    "type": defect_name,
                    "record_type": "refund",
                    "record_id": matched_refund["refund_id"],
                    "details": {"expected_amount_paisa": expected, "actual_amount_paisa": actual},
                })

        elif defect_name == "settlement_amount_mismatch":
            for idx in sorted(selected_indices):
                settlement_id = f"SET-{idx + 1:06d}"
                settlement = settlement_lookup.get(settlement_id)
                if settlement is None:
                    continue
                expected = settlement["net_amount_paisa"]
                actual = max(1000, expected - rng.randint(250, 15000))
                settlement["net_amount_paisa"] = actual
                defects.append({
                    "type": defect_name,
                    "record_type": "settlement",
                    "record_id": settlement_id,
                    "details": {"expected_net_amount_paisa": expected, "actual_net_amount_paisa": actual},
                })

        elif defect_name == "bank_credit_amount_mismatch":
            for idx in sorted(selected_indices):
                bank_id = f"BC-{idx + 1:06d}"
                bank_row = bank_lookup.get(bank_id)
                if bank_row is None:
                    continue
                expected = bank_row["amount_paisa"]
                actual = max(1000, expected - rng.randint(500, 10000))
                bank_row["amount_paisa"] = actual
                defects.append({
                    "type": defect_name,
                    "record_type": "bank_credit",
                    "record_id": bank_id,
                    "details": {"expected_amount_paisa": expected, "actual_amount_paisa": actual},
                })

        elif defect_name == "narration_mismatch":
            for idx in sorted(selected_indices):
                bank_id = f"BC-{idx + 1:06d}"
                bank_row = bank_lookup.get(bank_id)
                if bank_row is None:
                    continue
                original = bank_row["narration"]
                bank_row["narration"] = f"BROKEN NARRATION {original}"
                defects.append({
                    "type": defect_name,
                    "record_type": "bank_credit",
                    "record_id": bank_id,
                    "details": {"expected_narration": original, "actual_narration": bank_row["narration"]},
                })

    return defects


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic LedgerProof data.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--orders", type=int, default=200)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--missing-payment", action="store_true", dest="missing_payment")
    parser.add_argument("--duplicate-payment", action="store_true", dest="duplicate_payment")
    parser.add_argument("--payment-amount-mismatch", action="store_true", dest="payment_amount_mismatch")
    parser.add_argument("--refund-amount-mismatch", action="store_true", dest="refund_amount_mismatch")
    parser.add_argument("--settlement-amount-mismatch", action="store_true", dest="settlement_amount_mismatch")
    parser.add_argument("--bank-credit-amount-mismatch", action="store_true", dest="bank_credit_amount_mismatch")
    parser.add_argument("--narration-mismatch", action="store_true", dest="narration_mismatch")
    args = parser.parse_args()

    flags = {
        "missing_payment": bool(args.missing_payment),
        "duplicate_payment": bool(args.duplicate_payment),
        "payment_amount_mismatch": bool(args.payment_amount_mismatch),
        "refund_amount_mismatch": bool(args.refund_amount_mismatch),
        "settlement_amount_mismatch": bool(args.settlement_amount_mismatch),
        "bank_credit_amount_mismatch": bool(args.bank_credit_amount_mismatch),
        "narration_mismatch": bool(args.narration_mismatch),
    }

    root = args.out
    root.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    orders, payments, refunds, settlements, bank_rows, mapping = generate_orders(args.seed, args.orders)
    defects = apply_defects(orders, payments, refunds, settlements, bank_rows, rng, flags)

    write_excel_orders(orders, root / "orders.xlsx")
    (root / "payments.json").write_text(json.dumps(payments, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "refunds.json").write_text(json.dumps(refunds, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "settlements.json").write_text(json.dumps(settlements, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with (root / "bank_statement.csv").open("w", newline="", encoding="utf-8") as csv_file:
        fieldnames = [
            "bank_credit_id",
            "statement_id",
            "settlement_id",
            "order_id",
            "amount_paisa",
            "narration",
            "posted_at",
            "source_bank",
            "bank_template",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in bank_rows:
            writer.writerow({key: row[key] for key in fieldnames})

    ground_truth = {
        "seed": args.seed,
        "order_count": args.orders,
        "mapping": mapping,
        "defects": defects,
    }
    (root / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
