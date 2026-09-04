# Exception codes

The reconciliation layer emits deterministic exception codes that are stable across runs and must be treated as machine-readable values.

## Bank-settlement matching

- `UNMATCHED_BANK_CREDIT` — a bank credit has no candidate settlement by UTR or amount/date rules, or it lost per-settlement arbitration to a higher-confidence claim on the same settlement.
- `AMBIGUOUS_MATCH` — either a single bank credit resolves to more than one settlement candidate, or two or more bank credits tie at the highest confidence tier for the same settlement (arbitration refuses to guess between them).
- `AMOUNT_VARIANCE_UNEXPLAINED` — a bank credit's UTR matches a settlement exactly, but the credit amount does not equal the settlement amount. The settlement identity is certain; the amount is not, so the match is never accepted at face value.

## Settlement-to-payment arithmetic

- `SETTLEMENT_IMBALANCE` — the settlement does not close after accounting for payment net, refunds, and adjustments. A settlement with zero attached payments is a maximal imbalance (drift equal to the full settlement amount), not a no-op.
- `UNSETTLED_PAYMENT` — a payment exists but is assigned to no settlement.
- `AMOUNT_VARIANCE_PAYMENT_NET` — the variance is driven by the aggregate payment net amount.
- `AMOUNT_VARIANCE_REFUND` — the variance is driven by the refund total.
- `AMOUNT_VARIANCE_ADJUSTMENT` — the variance is driven by adjustments.
- `AMOUNT_VARIANCE_SETTLEMENT` — the variance is driven by the settlement amount itself.

## Payment-to-order matching

- `UNMATCHED_PAYMENT` — a captured/authorized payment could not be linked to any order by any tier (exact order reference, receipt, or amount+time fallback), and the ambiguity/candidate-count checks did not apply. This payment's money is unaccounted for on the order side; it must never be silently dropped.
- `ORPHAN_ORDER` — an order is marked paid but no payment was matched to it.
- `AMBIGUOUS_MATCH` — (also emitted here) a payment's fallback amount+time match resolves to more than one order candidate.
- `DUPLICATE_PAYMENT_CANDIDATE` — more than one payment resolved to the same order.

All amounts remain integer paisa values.
