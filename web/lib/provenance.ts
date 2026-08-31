import type { ExceptionOut, MatchRecordOut } from "./api-types";

export type HopStatus = "matched" | "ambiguous" | "missing";

export interface ChainHop {
  from: string;
  to: string;
  status: HopStatus;
  match?: MatchRecordOut;
  ambiguousCandidates?: string[];
  ambiguousReason?: string;
  missingReason?: string;
  nextId?: string;
}

export interface Chain {
  orderId: string;
  hops: ChainHop[];
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

/** Every order this run actually has evidence about, derived from real
 * match_records and exceptions -- there is no "list orders" endpoint, so
 * this is the honest source for what's searchable on this screen. */
export function listKnownOrderIds(matchRecords: MatchRecordOut[], exceptions: ExceptionOut[]): string[] {
  const ids = new Set<string>();
  for (const record of matchRecords) {
    if (record.pass_number === 3) ids.add(record.right_id);
  }
  for (const exception of exceptions) {
    if (exception.record_type === "order") ids.add(exception.record_id);
    if (exception.code === "AMBIGUOUS_MATCH" && exception.record_type === "payment") {
      for (const candidate of asStringArray(exception.details.candidates)) ids.add(candidate);
    }
  }
  return [...ids].sort();
}

function findMatch(records: MatchRecordOut[], passNumber: number, by: "left" | "right", id: string): MatchRecordOut | undefined {
  return records.find((r) => r.pass_number === passNumber && (by === "left" ? r.left_id : r.right_id) === id);
}

/**
 * order -> payment (pass 3): a direct match's left_id is the payment.
 * pass3's own ambiguity is reported against the PAYMENT record, with the
 * competing order ids in details.candidates -- so an ambiguous hop here is
 * found by searching for that payment-side exception mentioning this order.
 */
function orderToPaymentHop(orderId: string, records: MatchRecordOut[], exceptions: ExceptionOut[]): ChainHop {
  const direct = findMatch(records, 3, "right", orderId);
  if (direct) {
    return { from: "Order", to: "Payment", status: "matched", match: direct, nextId: direct.left_id };
  }

  const ambiguous = exceptions.find(
    (e) => e.code === "AMBIGUOUS_MATCH" && e.record_type === "payment" && asStringArray(e.details.candidates).includes(orderId),
  );
  if (ambiguous) {
    return {
      from: "Order",
      to: "Payment",
      status: "ambiguous",
      ambiguousCandidates: asStringArray(ambiguous.details.candidates),
      ambiguousReason: `Payment ${ambiguous.record_id} matched this order's amount and time window along with ${asStringArray(ambiguous.details.candidates).length - 1} other order(s); the system refused to guess which one it belongs to.`,
    };
  }

  const orphan = exceptions.find((e) => e.code === "ORPHAN_ORDER" && e.record_id === orderId);
  return {
    from: "Order",
    to: "Payment",
    status: "missing",
    missingReason: orphan ? "This order is marked paid but no payment was ever matched to it." : "No payment reference was found for this order.",
  };
}

/** payment -> settlement (pass 2): pass2 has no ambiguity code -- an
 * unresolved payment is reported as UNSETTLED_PAYMENT. */
function paymentToSettlementHop(paymentId: string, records: MatchRecordOut[], exceptions: ExceptionOut[]): ChainHop {
  const direct = findMatch(records, 2, "left", paymentId);
  if (direct) {
    return { from: "Payment", to: "Settlement", status: "matched", match: direct, nextId: direct.right_id };
  }

  const unsettled = exceptions.find((e) => e.code === "UNSETTLED_PAYMENT" && e.record_id === paymentId);
  return {
    from: "Payment",
    to: "Settlement",
    status: "missing",
    missingReason: unsettled ? "This payment has no settlement_id on file." : "No settlement was matched to this payment.",
  };
}

/** settlement -> bank credit (pass 1): a direct match's left_id is the bank
 * credit. Ambiguity here is reported against the BANK CREDIT record, either
 * as a per-row candidate list or (post Phase 6 fix) a tied-confidence
 * arbitration keyed by settlement_id -- both are checked. */
function settlementToBankCreditHop(settlementId: string, records: MatchRecordOut[], exceptions: ExceptionOut[]): ChainHop {
  const direct = findMatch(records, 1, "right", settlementId);
  if (direct) {
    return { from: "Settlement", to: "Bank credit", status: "matched", match: direct, nextId: direct.left_id };
  }

  const ambiguous = exceptions.find(
    (e) =>
      e.code === "AMBIGUOUS_MATCH" &&
      e.record_type === "bank_credit" &&
      (asStringArray(e.details.candidates).includes(settlementId) || e.details.settlement_id === settlementId),
  );
  if (ambiguous) {
    const competing = asStringArray(ambiguous.details.competing_bank_credit_ids);
    return {
      from: "Settlement",
      to: "Bank credit",
      status: "ambiguous",
      ambiguousCandidates: [ambiguous.record_id, ...competing],
      ambiguousReason:
        typeof ambiguous.details.reason === "string" && ambiguous.details.reason === "tied_confidence_arbitration"
          ? "Two or more bank credits tied at the same confidence for this settlement; the system refused to guess between them."
          : "More than one settlement candidate matched this bank credit; the system refused to guess which one it belongs to.",
    };
  }

  return { from: "Settlement", to: "Bank credit", status: "missing", missingReason: "No bank credit has arrived for this settlement yet." };
}

export function buildChain(orderId: string, matchRecords: MatchRecordOut[], exceptions: ExceptionOut[]): Chain {
  const hops: ChainHop[] = [];

  const hop1 = orderToPaymentHop(orderId, matchRecords, exceptions);
  hops.push(hop1);
  if (hop1.status !== "matched" || !hop1.nextId) return { orderId, hops };

  const hop2 = paymentToSettlementHop(hop1.nextId, matchRecords, exceptions);
  hops.push(hop2);
  if (hop2.status !== "matched" || !hop2.nextId) return { orderId, hops };

  const hop3 = settlementToBankCreditHop(hop2.nextId, matchRecords, exceptions);
  hops.push(hop3);
  return { orderId, hops };
}
