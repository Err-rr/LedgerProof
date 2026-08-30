# Defect Model

The synthetic generator can inject defects in a controlled and toggleable way. Each defect is independent and can be enabled or disabled via CLI flags.

## Default rates

These are the default probabilities used when a defect type is enabled.

| defect | CLI flag | default rate | notes |
| --- | --- | ---: | --- |
| missing_payment | `--missing-payment` | 0.02 | Omit a payment for a valid order |
| duplicate_payment | `--duplicate-payment` | 0.01 | Duplicate a payment record for an order |
| payment_amount_mismatch | `--payment-amount-mismatch` | 0.08 | Payment amount differs from the order amount |
| refund_amount_mismatch | `--refund-amount-mismatch` | 0.04 | Refund amount drifts from expected value |
| settlement_amount_mismatch | `--settlement-amount-mismatch` | 0.06 | Settlement net amount differs from payment net |
| bank_credit_amount_mismatch | `--bank-credit-amount-mismatch` | 0.05 | Bank credit not equal to settlement net |
| narration_mismatch | `--narration-mismatch` | 0.03 | Narration no longer matches the expected bank template |

The generator must keep these rates deterministic by seed. The same seed and the same flag set must produce byte-identical outputs.

## Injection semantics

- Each defect type is independent and should only affect the matching records for which it is enabled.
- Every injected defect must be recorded in `ground_truth.json` under the top-level `defects` array.
- Each defect entry must include: `type`, `record_type`, `record_id`, and a `details` object with the exact before/after values that were changed.
- If a defect is not enabled, it must not appear in the output.
- When a defect is enabled, the donation is still constrained to integer paisa values; no floats are used.

Example defect record:

```json
{
  "type": "payment_amount_mismatch",
  "record_type": "payment",
  "record_id": "PAY-000042",
  "details": {
    "expected_amount_paisa": 299900,
    "actual_amount_paisa": 293500
  }
}
```

## Deterministic generation contract

The generator must:

1. Use a seeded PRNG (`random.Random(seed)`) for all sampling.
2. Sort output deterministically before writing JSON or CSV.
3. Produce stable workbook metadata and canonical field ordering so the same seed and inputs generate byte-identical files.
4. Write one output directory per run; do not randomize file names or row ordering.
