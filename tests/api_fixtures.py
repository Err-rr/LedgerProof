"""Builds realistic upload bytes (orders.xlsx, payments.json, settlements.json,
refunds.json, bank_statement.csv) from gen.generate's deterministic batches,
for exercising POST /runs end-to-end without needing files on disk.
"""

from __future__ import annotations

import io
import json

import pandas as pd
from openpyxl import Workbook

from gen.generate import generate_orders

ORDER_COLUMNS = ["order_id", "customer_id", "amount_paisa", "currency", "created_at", "status"]


def _orders_xlsx_bytes(orders: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "orders"
    sheet.append(ORDER_COLUMNS)
    for order in orders:
        sheet.append([order[col] for col in ORDER_COLUMNS])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def build_upload_batch(seed: int = 1, order_count: int = 3) -> dict[str, bytes]:
    orders, payments, refunds, settlements, bank_rows, _mapping = generate_orders(seed, order_count)
    return {
        "orders": _orders_xlsx_bytes(orders),
        "payments": json.dumps(payments).encode("utf-8"),
        "settlements": json.dumps(settlements).encode("utf-8"),
        "refunds": json.dumps(refunds).encode("utf-8"),
        "bank_statement": pd.DataFrame(bank_rows).to_csv(index=False).encode("utf-8"),
    }


def as_multipart_files(batch: dict[str, bytes]) -> dict[str, tuple[str, bytes, str]]:
    return {
        "orders": ("orders.xlsx", batch["orders"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "payments": ("payments.json", batch["payments"], "application/json"),
        "settlements": ("settlements.json", batch["settlements"], "application/json"),
        "refunds": ("refunds.json", batch["refunds"], "application/json"),
        "bank_statement": ("bank_statement.csv", batch["bank_statement"], "text/csv"),
    }
