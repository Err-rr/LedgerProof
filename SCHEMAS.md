# LedgerProof Schemas

This repository uses integer paisa for all financial fields. All amounts are stored as ints and only formatted for display at the presentation layer.

## Core schema

### Orders

The order sheet is exported to `orders.xlsx` as a worksheet named `orders`.

Columns:

| column | type | notes |
| --- | --- | --- |
| order_id | string | Unique order identifier |
| customer_id | string | Merchant customer or buyer identifier |
| amount_paisa | int | Gross order amount in paisa |
| currency | string | Usually `INR` |
| created_at | ISO-8601 UTC timestamp | Order creation time |
| status | string | `paid`, `refunded`, or `pending` |

Example row:

```json
{
  "order_id": "ORD-000001",
  "customer_id": "CUST-00042",
  "amount_paisa": 125500,
  "currency": "INR",
  "created_at": "2026-01-15T10:00:00Z",
  "status": "paid"
}
```

### Payments

File: `payments.json`

Each payment is a JSON object:

```json
{
  "payment_id": "PAY-000001",
  "order_id": "ORD-000001",
  "amount_paisa": 125500,
  "instrument": "CARD",
  "fee_paisa": 2188,
  "gst_paisa": 394,
  "net_amount_paisa": 123918,
  "status": "captured",
  "created_at": "2026-01-15T10:00:10Z"
}
```

Rules:

- `amount_paisa` is the gross payment amount for the order.
- `fee_paisa` is the MDR fee for the instrument.
- `gst_paisa` is 18% of the MDR fee.
- `net_amount_paisa = amount_paisa - fee_paisa - gst_paisa`.
- `instrument` is one of `UPI`, `CARD`, `NETBANKING`, or `WALLET`.

### Refunds

File: `refunds.json`

Each refund is a JSON object:

```json
{
  "refund_id": "REF-000001",
  "payment_id": "PAY-000001",
  "order_id": "ORD-000001",
  "amount_paisa": 25000,
  "status": "processed",
  "created_at": "2026-01-16T11:15:00Z"
}
```

### Settlements

File: `settlements.json`

Each settlement is a JSON object:

```json
{
  "settlement_id": "SET-000001",
  "payment_id": "PAY-000001",
  "order_id": "ORD-000001",
  "gross_amount_paisa": 125500,
  "fee_paisa": 2188,
  "gst_paisa": 394,
  "net_amount_paisa": 123918,
  "status": "settled",
  "settled_at": "2026-01-18T09:00:00Z"
}
```

### Bank statement

File: `bank_statement.csv`

The bank statement is a CSV with one row per settlement credit. Each row contains the settlement-level credit from a single bank account or statement run.

Columns:

| column | type | notes |
| --- | --- | --- |
| bank_credit_id | string | Unique bank credit identifier |
| statement_id | string | Bank statement identifier |
| settlement_id | string | Related settlement identifier |
| order_id | string | Related order identifier |
| amount_paisa | int | Bank credit amount in paisa |
| narration | string | Exact narration generated from a bank template |
| posted_at | ISO-8601 UTC timestamp | Credit posting time |
| source_bank | string | Example: `HDFC`, `ICICI`, `SBI`, `AXIS` |
| bank_template | string | One of the four narration templates |

### Ground truth

File: `ground_truth.json`

Ground truth must include the complete mapping and the defect log.

```json
{
  "seed": 42,
  "order_count": 200,
  "mapping": [
    {
      "order_id": "ORD-000001",
      "payment_id": "PAY-000001",
      "settlement_id": "SET-000001",
      "bank_credit_id": "BC-000001",
      "amount_paisa": 125500,
      "fee_paisa": 2188,
      "gst_paisa": 394,
      "net_amount_paisa": 123918,
      "statement_id": "STMT-0001"
    }
  ],
  "defects": [
    {
      "type": "payment_amount_mismatch",
      "record_type": "payment",
      "record_id": "PAY-000001",
      "details": {
        "expected_amount_paisa": 125500,
        "actual_amount_paisa": 125000
      }
    }
  ]
}
```

## Fee and GST model

The generator must compute fees using instrument-dependent MDR and apply 18% GST to the MDR value.

Instrument rates (annualized test-mode approximation):

| instrument | MDR rate |
| --- | --- |
| UPI | 0.25% |
| CARD | 1.75% |
| NETBANKING | 0.75% |
| WALLET | 1.50% |

The calculation is:

```text
fee_paisa = round(amount_paisa * mdr_rate)

gst_paisa = round(fee_paisa * 0.18)

net_amount_paisa = amount_paisa - fee_paisa - gst_paisa
```

Amounts must remain integer paisa throughout.

## Bank narration templates

Each statement is assigned one of four narration templates at the statement level, not per line.

1. `RAZORPAY {merchant_name} {settlement_id} {date}`
2. `SETTLEMENT {merchant_name} {settlement_id} {date} INR`
3. `MERCHANT Payout {merchant_name} {settlement_id} {date}`
4. `RZP {merchant_name} {settlement_id} {date} SETTLED`

Example final narration for a statement with `merchant_name = ACME MART` and `settlement_id = SET-000001`:

```text
RAZORPAY ACME MART SET-000001 2026-01-18
```

The selected template stays consistent across the bank statement rows.
