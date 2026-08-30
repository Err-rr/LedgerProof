# Exception codes

The reconciliation layer emits deterministic exception codes that are stable across runs and must be treated as machine-readable values.

## Bank-settlement matching

- `UNMATCHED_BANK_CREDIT` — a bank credit has no candidate settlement by UTR or amount/date rules.
- `AMBIGUOUS_MATCH` — a fallback amount/date match resolves to more than one settlement candidate.

## Settlement-to-payment arithmetic

- `SETTLEMENT_IMBALANCE` — the settlement does not close after accounting for payment net, refunds, and adjustments.
- `UNSETTLED_PAYMENT` — a payment exists but is assigned to no settlement.
- `AMOUNT_VARIANCE_PAYMENT_NET` — the variance is driven by the aggregate payment net amount.
- `AMOUNT_VARIANCE_REFUND` — the variance is driven by the refund total.
- `AMOUNT_VARIANCE_ADJUSTMENT` — the variance is driven by adjustments.
- `AMOUNT_VARIANCE_SETTLEMENT` — the variance is driven by the settlement amount itself.

All amounts remain integer paisa values.
