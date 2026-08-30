# LedgerProof

Multi-source settlement reconciliation for Razorpay merchants. Takes a merchant's
order data, Razorpay API records, and a bank statement, and reconciles the single
lumped settlement credit back to individual orders, producing double-entry journal
lines and an honest exception list.

Built for the Razorpay AI Buildathon 2026, Track 04 (AI Finance Controller).
The track bar: close one finance-ops loop across a 50+ record batch, reporting
match rate and the exceptions it could not resolve. One cherry-picked match
proves nothing.

## Non-negotiable rules

1. **All money is integer paisa.** Never float, never Decimal-in-passing.
   Amounts enter as int, stay int, and are formatted for display only at the
   presentation layer. Float arithmetic on money causes silent drift that is
   almost impossible to trace later.

2. **The matching engine is deterministic. No LLM anywhere in a money decision.**
   An LLM must never decide which payment belongs to which order, which
   settlement explains which bank credit, or how to classify a variance. LLMs
   are permitted in exactly three places: parsing bank narration text on
   ingest, explaining exceptions after matching, and answering natural language
   questions about an already-reconciled ledger.

3. **Refuse to guess.** If a matching pass produces more than one candidate
   above threshold, do not pick one. Emit AMBIGUOUS_MATCH and route it to the
   exception queue. A lower auto-resolve rate with honest exceptions is the
   goal, not a high match rate.

4. **Every match carries its evidence.** Each MatchRecord records the pass
   number, the method used, the confidence, the specific field values that
   drove the decision, and a UTC timestamp. This is the audit trail and it is
   a deliverable, not a debug aid.

5. **The agent proposes, it never writes.** Resolution suggestions from the LLM
   always require an explicit human approval flag before they affect the
   ledger.

6. **A wrong match is a failure. An exception is a success.** Under adversarial
   input, the system should produce more exceptions, never a confidently wrong
   answer.

7. **Journal lines must balance to zero.** If they do not, the reconciliation
   is wrong regardless of what the match rate says. Assert this.

## Stack

- Python 3.11, pandas, pydantic v2, openpyxl, pytest
- Postgres (Neon or Supabase free tier). NOT DynamoDB: this workload is joins
  and aggregations end to end.
- FastAPI + Mangum, deployed to AWS Lambda as a container image (pandas and
  pyarrow exceed the zip layer limit)
- Next.js 14 App Router, deployed on AWS Amplify
- Anthropic API for the three permitted LLM surfaces
- Razorpay test mode (rzp_test_ keys) and the official Razorpay MCP server

## Repo layout