"""Adversarial mutation suite that attacks LedgerProof's own matcher.

This is not a unit test suite -- it deliberately constructs corrupted,
ambiguous, and adversarial inputs and feeds them through the real pass1
(bank<->settlement) and pass2 (settlement<->payment) matchers, then checks
whether the system upheld CLAUDE.md's core promise: "A wrong match is a
failure. An exception is a success. Under adversarial input, the system
should produce more exceptions, never a confidently wrong answer."

Verdict taxonomy
-----------------
CONTAINED   The attack did not fool the matcher: either it was correctly
            routed to an exception, or the matcher still produced the
            objectively correct match despite the corruption.
WRONG_MATCH The matcher produced a confident result that does not reflect
            reality -- an incorrect settlement/order pairing, a settlement
            that should have been flagged imbalanced but silently wasn't,
            or a match whose recorded evidence misrepresents how it was
            actually resolved (dishonest confidence/method labeling).
CRASH       The pass raised an unhandled exception while processing the
            mutated input.

Every case is fully reproducible from its `seed` plus the mutation function
named in `mutation` -- see reproduction steps printed for WRONG_MATCH cases,
or pass --replay <mutation_name> <seed>.

Usage:
    python audit/mutate.py [--trials 15] [--base-seed 100000]
                            [--out audit/scorecard.json]
    python audit/mutate.py --replay priority_theft_via_collision 100042
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import sys
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.passes.pass1_bank_settlement import UTR_RE, pass1_bank_settlement  # noqa: E402
from core.passes.pass2_settlement_payments import pass2_settlement_payments  # noqa: E402
from gen.generate import BANK_TEMPLATES, MERCHANTS, generate_orders  # noqa: E402


CONTAINED = "CONTAINED"
WRONG_MATCH = "WRONG_MATCH"
CRASH = "CRASH"

FAMILIES = ["narration", "amount", "timing", "structural"]

DATE_WINDOW_DAYS = 2


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass
class Scenario:
    seed: int
    orders: list[dict[str, Any]]
    payments: list[dict[str, Any]]
    refunds: list[dict[str, Any]]
    settlements: list[dict[str, Any]]
    bank_rows: list[dict[str, Any]]
    mapping: list[dict[str, Any]]
    target_index: int


@dataclass
class Case:
    family: str
    mutation: str
    seed: int
    target_pass: str
    verdict: str
    detail: str
    reproduction: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def build_scenario(seed: int, n_records: int = 8) -> Scenario:
    """Build a small deterministic batch and enrich it with realistic UTRs.

    gen.generate's baseline output never gives settlements a UTR (matching
    SCHEMAS.md, which has no `utr` column), so pass1's exact-match path never
    fires on unmutated data. Real Razorpay settlement narrations do carry a
    UTR-like reference, so we embed one here -- this lets the suite exercise
    both of pass1's matching paths (UTR-exact and amount+date fallback)
    rather than only ever hitting the fallback.
    """
    orders, payments, refunds, settlements, bank_rows, mapping = generate_orders(seed, n_records)
    orders = copy.deepcopy(orders)
    payments = copy.deepcopy(payments)
    refunds = copy.deepcopy(refunds)
    settlements = copy.deepcopy(settlements)
    bank_rows = copy.deepcopy(bank_rows)

    for i, (settlement, bank_row) in enumerate(zip(settlements, bank_rows)):
        utr = f"UTR{seed % 10_000:04d}{i:06d}"
        settlement["utr"] = utr
        bank_row["narration"] = f"{bank_row['narration']} {utr}"

    target_index = seed % n_records
    return Scenario(seed, orders, payments, refunds, settlements, bank_rows, mapping, target_index)


def _safe_run(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, str | None]:
    try:
        return fn(*args, **kwargs), None
    except Exception:  # noqa: BLE001 - deliberately broad: this IS the crash detector
        return None, traceback.format_exc()


def _crash(family: str, mutation: str, seed: int, target_pass: str, error: str, repro: dict[str, Any]) -> Case:
    last_line = error.strip().splitlines()[-1] if error.strip() else "unknown error"
    return Case(family=family, mutation=mutation, seed=seed, target_pass=target_pass, verdict=CRASH, detail=last_line, reproduction=repro, error=error)


def classify_pass1(
    matches: list[Any],
    exceptions: list[dict[str, Any]],
    bank_id: str,
    expected_settlement_id: str | None,
    *,
    must_except: bool = False,
) -> tuple[str, str]:
    """Score a pass1 outcome for one target bank credit against ground truth.

    must_except=True marks scenarios that are genuinely ambiguous by
    construction (e.g. two indistinguishable candidate settlements) --
    there, ANY confident pick is unsafe per CLAUDE.md rule 3 ("Refuse to
    guess"), regardless of which candidate it happens to name.
    """
    match = next((m for m in matches if m.left_id == bank_id), None)
    exc = next((e for e in exceptions if e.get("record_id") == bank_id), None)

    if must_except:
        if match is not None:
            return WRONG_MATCH, f"confidently matched {match.right_id} in a scenario that is genuinely ambiguous by construction"
        if exc is not None:
            return CONTAINED, f"correctly routed to {exc['code']}"
        return WRONG_MATCH, "silent drop: no match and no exception recorded for a genuinely ambiguous scenario"

    if match is not None:
        if expected_settlement_id is None:
            return WRONG_MATCH, f"confidently matched fabricated/orphan bank credit to real settlement {match.right_id}, but no real settlement should exist for it"
        if match.right_id == expected_settlement_id:
            return CONTAINED, f"matched correct settlement {expected_settlement_id} despite the attack"
        return WRONG_MATCH, f"matched wrong settlement {match.right_id}, expected {expected_settlement_id}"
    if exc is not None:
        return CONTAINED, f"correctly routed to {exc['code']}"
    return WRONG_MATCH, "silent drop: neither matched nor routed to an exception"


# --------------------------------------------------------------------------
# Mutation primitives
# --------------------------------------------------------------------------


def _truncate(rng: random.Random, text: str) -> str:
    if not text:
        return text
    cut = rng.randint(0, max(0, len(text) - 1))
    return text[:cut]


def _inject_noise(rng: random.Random, text: str, n_chars: int = 6) -> str:
    noise_pool = "!@#$%^&*_?~<>|\\/#"
    chars = list(text)
    for _ in range(n_chars):
        pos = rng.randint(0, len(chars))
        chars.insert(pos, rng.choice(noise_pool))
    return "".join(chars)


def _drift_paisa(rng: random.Random, amount: int, max_drift: int = 500) -> int:
    delta = 0
    while delta == 0:
        delta = rng.randint(-max_drift, max_drift)
    return amount + delta


def _transpose_digits(rng: random.Random, amount: int) -> int:
    digits = list(str(abs(amount)))
    if len(digits) >= 2:
        for _ in range(10):
            i = rng.randint(0, len(digits) - 2)
            if digits[i] != digits[i + 1]:
                digits[i], digits[i + 1] = digits[i + 1], digits[i]
                sign = -1 if amount < 0 else 1
                return sign * int("".join(digits))
    return amount + 1  # fallback: no transposable pair found (e.g. all-repeated digits)


def _sign_flip(_rng: random.Random, amount: int) -> int:
    return -amount


def _off_by_one_rupee(rng: random.Random, amount: int) -> int:
    return amount + rng.choice([-100, 100])


AMOUNT_MUTATORS: dict[str, Callable[[random.Random, int], int]] = {
    "paisa_drift": _drift_paisa,
    "transposed_digits": _transpose_digits,
    "sign_flip": _sign_flip,
    "off_by_one_rupee": _off_by_one_rupee,
}


# --------------------------------------------------------------------------
# Narration family (pass1)
# --------------------------------------------------------------------------


def _run_pass1_and_classify(
    scenario: Scenario,
    bank_id: str,
    expected_settlement_id: str | None,
    *,
    family: str,
    mutation: str,
    seed: int,
    must_except: bool = False,
    extra_repro: dict[str, Any] | None = None,
) -> Case:
    bank_df = pd.DataFrame(scenario.bank_rows)
    settlement_df = pd.DataFrame(scenario.settlements)
    result, error = _safe_run(pass1_bank_settlement, bank_df, settlement_df)
    repro = {"bank_credit_id": bank_id, "expected_settlement_id": expected_settlement_id, **(extra_repro or {})}
    if error:
        return _crash(family, mutation, seed, "pass1", error, repro)
    matches, exceptions = result
    verdict, detail = classify_pass1(matches, exceptions, bank_id, expected_settlement_id, must_except=must_except)
    match = next((m for m in matches if m.left_id == bank_id), None)
    if match is not None:
        repro["result_method"] = match.method
        repro["result_confidence"] = match.confidence
        repro["result_evidence"] = match.evidence
    return Case(family=family, mutation=mutation, seed=seed, target_pass="pass1", verdict=verdict, detail=detail, reproduction=repro)


def mut_narration_truncate(seed: int) -> Case:
    scenario = build_scenario(seed)
    rng = random.Random(seed + 7919)
    idx = scenario.target_index
    bank_row = scenario.bank_rows[idx]
    settlement = scenario.settlements[idx]

    original = bank_row["narration"]
    bank_row["narration"] = _truncate(rng, original)

    return _run_pass1_and_classify(
        scenario, bank_row["bank_credit_id"], settlement["settlement_id"],
        family="narration", mutation="truncate", seed=seed,
        extra_repro={"original_narration": original, "mutated_narration": bank_row["narration"]},
    )


def mut_narration_noise(seed: int) -> Case:
    scenario = build_scenario(seed)
    rng = random.Random(seed + 7919)
    idx = scenario.target_index
    bank_row = scenario.bank_rows[idx]
    settlement = scenario.settlements[idx]

    original = bank_row["narration"]
    bank_row["narration"] = _inject_noise(rng, original)

    return _run_pass1_and_classify(
        scenario, bank_row["bank_credit_id"], settlement["settlement_id"],
        family="narration", mutation="noise", seed=seed,
        extra_repro={"original_narration": original, "mutated_narration": bank_row["narration"]},
    )


def mut_narration_template_swap(seed: int) -> Case:
    scenario = build_scenario(seed)
    rng = random.Random(seed + 7919)
    idx = scenario.target_index
    bank_row = scenario.bank_rows[idx]
    settlement = scenario.settlements[idx]

    original = bank_row["narration"]
    other_templates = [t for t in BANK_TEMPLATES if t != bank_row.get("bank_template")]
    template = rng.choice(other_templates) if other_templates else BANK_TEMPLATES[0]
    merchant = rng.choice(MERCHANTS)
    date_str = bank_row["posted_at"][:10]
    rebuilt = template.format(merchant_name=merchant.upper(), settlement_id=bank_row["settlement_id"], date=date_str)
    utr_match = UTR_RE.search(original)
    bank_row["narration"] = f"{rebuilt} {utr_match.group(0)}" if utr_match else rebuilt

    return _run_pass1_and_classify(
        scenario, bank_row["bank_credit_id"], settlement["settlement_id"],
        family="narration", mutation="template_swap", seed=seed,
        extra_repro={"original_narration": original, "mutated_narration": bank_row["narration"]},
    )


def mut_narration_strip_utr(seed: int) -> Case:
    scenario = build_scenario(seed)
    idx = scenario.target_index
    bank_row = scenario.bank_rows[idx]
    settlement = scenario.settlements[idx]

    original = bank_row["narration"]
    bank_row["narration"] = UTR_RE.sub("", original).strip()

    return _run_pass1_and_classify(
        scenario, bank_row["bank_credit_id"], settlement["settlement_id"],
        family="narration", mutation="strip_utr", seed=seed,
        extra_repro={"original_narration": original, "mutated_narration": bank_row["narration"]},
    )


_DECOY_WORDS = ["REFERENCE", "UNVERIFIED", "PROCESSING", "CONFIRMATION", "TRANSACTION"]


def mut_narration_false_confidence(seed: int) -> Case:
    """A narration containing an innocuous word that happens to satisfy
    pass1's own "looks like a UTR" heuristics, on a row whose real UTR has
    been removed. Tests evidence honesty (rule 4), not just ID correctness:
    if the match still lands on the right settlement via amount+date
    fallback, does pass1 honestly label it as such, or does it dishonestly
    claim method="utr" / confidence=1.0 because *some* UTR-shaped token was
    found in the text -- regardless of whether that token matched anything?
    """
    scenario = build_scenario(seed)
    rng = random.Random(seed + 7919)
    idx = scenario.target_index
    bank_row = scenario.bank_rows[idx]
    settlement = scenario.settlements[idx]

    decoy = rng.choice(_DECOY_WORDS)
    original = bank_row["narration"]
    bank_row["narration"] = f"BANK CREDIT {decoy} NOTE"

    bank_df = pd.DataFrame(scenario.bank_rows)
    settlement_df = pd.DataFrame(scenario.settlements)
    result, error = _safe_run(pass1_bank_settlement, bank_df, settlement_df)
    repro = {
        "bank_credit_id": bank_row["bank_credit_id"],
        "expected_settlement_id": settlement["settlement_id"],
        "original_narration": original,
        "mutated_narration": bank_row["narration"],
        "true_utr": settlement["utr"],
    }
    if error:
        return _crash("narration", "false_confidence", seed, "pass1", error, repro)
    matches, exceptions = result
    match = next((m for m in matches if m.left_id == bank_row["bank_credit_id"]), None)

    if match is None:
        exc = next((e for e in exceptions if e.get("record_id") == bank_row["bank_credit_id"]), None)
        verdict, detail = (CONTAINED, f"routed to {exc['code']}") if exc else (WRONG_MATCH, "silent drop: neither matched nor excepted")
    elif match.right_id != settlement["settlement_id"]:
        verdict, detail = WRONG_MATCH, f"matched wrong settlement {match.right_id}, expected {settlement['settlement_id']}"
    elif match.method == "utr" and str(match.evidence.get("utr", "")).upper() != str(settlement["utr"]).upper():
        verdict = WRONG_MATCH
        detail = (
            f"matched the correct settlement, but evidence dishonestly claims method='utr' confidence=1.0 "
            f"based on the coincidental non-UTR word '{decoy}' in the narration (evidence.utr={match.evidence.get('utr')!r}), "
            f"which does not equal the settlement's real UTR ({settlement['utr']!r}); the real signal was amount+date fallback"
        )
    else:
        verdict, detail = CONTAINED, "matched correctly via honestly-labeled amount+date fallback"

    if match is not None:
        repro["result_method"] = match.method
        repro["result_confidence"] = match.confidence
        repro["result_evidence"] = match.evidence
    return Case(family="narration", mutation="false_confidence", seed=seed, target_pass="pass1", verdict=verdict, detail=detail, reproduction=repro)


# --------------------------------------------------------------------------
# Amount family (pass1 bank-credit leg, and pass2 payment-net leg)
# --------------------------------------------------------------------------


def make_amount_pass1_mutation(name: str) -> Callable[[int], Case]:
    mutate_fn = AMOUNT_MUTATORS[name]

    def _fn(seed: int) -> Case:
        scenario = build_scenario(seed)
        rng = random.Random(seed + 7919)
        idx = scenario.target_index
        bank_row = scenario.bank_rows[idx]
        settlement = scenario.settlements[idx]

        # Isolate the amount/date fallback path: this mutation targets amount
        # handling specifically, not the (already-covered) UTR path, which
        # doesn't cross-check amount at all -- see narration_false_confidence
        # and the module docstring for that separate finding.
        bank_row["narration"] = UTR_RE.sub("", bank_row["narration"]).strip()
        original = int(bank_row["amount_paisa"])
        mutated = mutate_fn(rng, original)
        bank_row["amount_paisa"] = mutated

        return _run_pass1_and_classify(
            scenario, bank_row["bank_credit_id"], settlement["settlement_id"],
            family="amount", mutation=f"{name}_bank_credit", seed=seed,
            extra_repro={"original_amount_paisa": original, "mutated_amount_paisa": mutated},
        )

    return _fn


def make_amount_pass2_mutation(name: str) -> Callable[[int], Case]:
    mutate_fn = AMOUNT_MUTATORS[name]

    def _fn(seed: int) -> Case:
        scenario = build_scenario(seed)
        rng = random.Random(seed + 7919)
        idx = scenario.target_index
        settlement = scenario.settlements[idx]
        payment = copy.deepcopy(scenario.payments[idx])

        original = int(payment["amount_paisa"])
        mutated = mutate_fn(rng, original)
        payment["amount_paisa"] = mutated

        payments_list = [p for i, p in enumerate(scenario.payments) if i != idx] + [payment]
        settlement_df = pd.DataFrame(scenario.settlements)
        payments_df = pd.DataFrame(payments_list)

        result, error = _safe_run(pass2_settlement_payments, settlement_df, payments_df, None, None)
        repro = {
            "payment_id": payment["payment_id"],
            "settlement_id": settlement["settlement_id"],
            "original_amount_paisa": original,
            "mutated_amount_paisa": mutated,
        }
        if error:
            return _crash("amount", f"{name}_payment_net", seed, "pass2", error, repro)
        matches, exceptions = result
        match = next((m for m in matches if m.left_id == payment["payment_id"]), None)
        imbalance = next(
            (e for e in exceptions if e.get("record_type") == "settlement" and e.get("record_id") == settlement["settlement_id"] and e["code"] == "SETTLEMENT_IMBALANCE"),
            None,
        )
        if match is None:
            verdict, detail = WRONG_MATCH, "payment vanished from matching entirely after the amount mutation (no match, no imbalance flag)"
        elif imbalance is not None:
            verdict, detail = CONTAINED, f"payment matched as expected and the amount discrepancy was flagged as {imbalance['details'].get('variance_code')}"
        else:
            verdict, detail = WRONG_MATCH, f"payment amount mutated by {mutated - original} paisa but settlement was never flagged as imbalanced"
        if imbalance is not None:
            repro["imbalance_details"] = imbalance["details"]
        return Case(family="amount", mutation=f"{name}_payment_net", seed=seed, target_pass="pass2", verdict=verdict, detail=detail, reproduction=repro)

    return _fn


# --------------------------------------------------------------------------
# Timing family (pass1)
# --------------------------------------------------------------------------


def mut_timing_period_boundary_shift(seed: int) -> Case:
    scenario = build_scenario(seed)
    rng = random.Random(seed + 7919)
    idx = scenario.target_index
    bank_row = scenario.bank_rows[idx]
    settlement = scenario.settlements[idx]

    bank_row["narration"] = UTR_RE.sub("", bank_row["narration"]).strip()
    original = bank_row["posted_at"]
    posted_dt = datetime.fromisoformat(original.replace("Z", "+00:00"))
    shift_days = rng.randint(DATE_WINDOW_DAYS + 1, DATE_WINDOW_DAYS + 8)
    direction = rng.choice([1, -1])
    new_dt = posted_dt + timedelta(days=shift_days * direction)
    bank_row["posted_at"] = new_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return _run_pass1_and_classify(
        scenario, bank_row["bank_credit_id"], settlement["settlement_id"],
        family="timing", mutation="period_boundary_shift", seed=seed,
        extra_repro={"original_posted_at": original, "mutated_posted_at": bank_row["posted_at"], "shift_days": shift_days * direction},
    )


def mut_timing_backdate_bank_line(seed: int) -> Case:
    scenario = build_scenario(seed)
    rng = random.Random(seed + 7919)
    idx = scenario.target_index
    bank_row = scenario.bank_rows[idx]
    settlement = scenario.settlements[idx]

    bank_row["narration"] = UTR_RE.sub("", bank_row["narration"]).strip()
    original = bank_row["posted_at"]
    posted_dt = datetime.fromisoformat(original.replace("Z", "+00:00"))
    shift_days = rng.randint(DATE_WINDOW_DAYS + 1, DATE_WINDOW_DAYS + 8)
    new_dt = posted_dt - timedelta(days=shift_days)
    bank_row["posted_at"] = new_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    return _run_pass1_and_classify(
        scenario, bank_row["bank_credit_id"], settlement["settlement_id"],
        family="timing", mutation="backdate_bank_line", seed=seed,
        extra_repro={"original_posted_at": original, "mutated_posted_at": bank_row["posted_at"], "shift_days": -shift_days},
    )


def mut_timing_out_of_order_delivery(seed: int) -> Case:
    scenario = build_scenario(seed)
    rng = random.Random(seed + 7919)
    idx = scenario.target_index
    bank_row = scenario.bank_rows[idx]
    settlement = scenario.settlements[idx]

    shuffled_bank_rows = scenario.bank_rows[:]
    shuffled_settlements = scenario.settlements[:]
    rng.shuffle(shuffled_bank_rows)
    rng.shuffle(shuffled_settlements)
    scenario.bank_rows = shuffled_bank_rows
    scenario.settlements = shuffled_settlements

    return _run_pass1_and_classify(
        scenario, bank_row["bank_credit_id"], settlement["settlement_id"],
        family="timing", mutation="out_of_order_delivery", seed=seed,
        extra_repro={"note": "bank_rows and settlements shuffled; target record values unchanged"},
    )


# --------------------------------------------------------------------------
# Structural family (pass1 and pass2)
# --------------------------------------------------------------------------


def mut_structural_duplicate_settlement(seed: int) -> Case:
    scenario = build_scenario(seed)
    idx = scenario.target_index
    bank_row = scenario.bank_rows[idx]
    settlement = scenario.settlements[idx]

    dup = copy.deepcopy(settlement)
    dup["settlement_id"] = f"{settlement['settlement_id']}-DUP"
    scenario.settlements.append(dup)

    return _run_pass1_and_classify(
        scenario, bank_row["bank_credit_id"], settlement["settlement_id"],
        family="structural", mutation="duplicate_settlement", seed=seed,
        must_except=True,
        extra_repro={"original_settlement_id": settlement["settlement_id"], "duplicate_settlement_id": dup["settlement_id"]},
    )


def mut_structural_two_same_day_same_amount(seed: int) -> Case:
    scenario = build_scenario(seed)
    idx = scenario.target_index
    n = len(scenario.settlements)
    twin_idx = (idx + 1) % n

    target_settlement = scenario.settlements[idx]
    twin_settlement = scenario.settlements[twin_idx]
    twin_settlement["net_amount_paisa"] = target_settlement["net_amount_paisa"]
    twin_settlement["gross_amount_paisa"] = target_settlement["net_amount_paisa"]
    twin_settlement["settled_at"] = target_settlement["settled_at"]

    bank_row = scenario.bank_rows[idx]
    bank_row["narration"] = UTR_RE.sub("", bank_row["narration"]).strip()

    return _run_pass1_and_classify(
        scenario, bank_row["bank_credit_id"], target_settlement["settlement_id"],
        family="structural", mutation="two_same_day_same_amount_settlements", seed=seed,
        must_except=True,
        extra_repro={"twin_settlement_id": twin_settlement["settlement_id"], "shared_amount_paisa": target_settlement["net_amount_paisa"], "shared_settled_at": target_settlement["settled_at"]},
    )


def mut_structural_bank_credit_no_settlement(seed: int) -> Case:
    scenario = build_scenario(seed)
    rng = random.Random(seed + 7919)
    orphan_id = "BC-ORPHAN-0001"
    collide = rng.random() < 0.5
    if collide and scenario.settlements:
        donor = rng.choice(scenario.settlements)
        amount = int(donor["net_amount_paisa"])
        posted_at = donor["settled_at"]
        collide_with = donor["settlement_id"]
    else:
        amount = rng.randint(2_000_000, 5_000_000)  # outside the generator's normal order-amount range
        posted_at = (datetime(2026, 1, 15, tzinfo=timezone.utc) + timedelta(days=rng.randint(0, 60))).strftime("%Y-%m-%dT%H:%M:%SZ")
        collide_with = None

    orphan_row = {
        "bank_credit_id": orphan_id,
        "statement_id": "STMT-ORPHAN",
        "settlement_id": "SET-NONE",
        "order_id": "ORD-NONE",
        "amount_paisa": amount,
        "narration": f"UNKNOWN CREDIT {orphan_id}",
        "posted_at": posted_at,
        "source_bank": "UNKNOWN",
        "bank_template": "UNKNOWN",
    }
    scenario.bank_rows.append(orphan_row)

    return _run_pass1_and_classify(
        scenario, orphan_id, None,
        family="structural", mutation="bank_credit_no_settlement", seed=seed,
        extra_repro={"amount_paisa": amount, "posted_at": posted_at, "collided_with_settlement": collide_with},
    )


def mut_structural_delete_payment_mid_batch(seed: int) -> Case:
    scenario = build_scenario(seed)
    idx = scenario.target_index
    settlement = scenario.settlements[idx]
    deleted_payment = scenario.payments[idx]
    remaining_payments = [p for i, p in enumerate(scenario.payments) if i != idx]

    settlement_df = pd.DataFrame(scenario.settlements)
    payments_df = pd.DataFrame(remaining_payments)
    result, error = _safe_run(pass2_settlement_payments, settlement_df, payments_df, None, None)
    repro = {"settlement_id": settlement["settlement_id"], "deleted_payment_id": deleted_payment["payment_id"]}
    if error:
        return _crash("structural", "delete_payment_mid_batch", seed, "pass2", error, repro)
    matches, exceptions = result
    exc = next((e for e in exceptions if e.get("record_type") == "settlement" and e.get("record_id") == settlement["settlement_id"]), None)
    if exc is not None and exc["code"] == "SETTLEMENT_IMBALANCE":
        verdict, detail = CONTAINED, "settlement correctly flagged as imbalanced after its only payment was deleted mid-batch"
    else:
        verdict, detail = WRONG_MATCH, "settlement silently skipped: deleting its only payment produced no SETTLEMENT_IMBALANCE exception (pass2 `continue`s on an empty settlement_payments slice)"
    return Case(family="structural", mutation="delete_payment_mid_batch", seed=seed, target_pass="pass2", verdict=verdict, detail=detail, reproduction=repro)


def mut_structural_priority_theft_via_collision(seed: int) -> Case:
    """A fabricated, unverified bank credit with no UTR is delivered BEFORE
    the legitimate UTR-verified credit for the same settlement, sharing its
    exact amount and posting date. pass1 claims settlements first-come,
    first-served with no confidence-based arbitration -- so this checks
    whether a low-evidence row can preempt a cryptographically-strong one.
    """
    scenario = build_scenario(seed)
    idx = scenario.target_index
    donor_settlement = scenario.settlements[idx]
    donor_bank_row = scenario.bank_rows[idx]

    thief_row = {
        "bank_credit_id": "BC-THIEF-0001",
        "statement_id": "STMT-THIEF",
        "settlement_id": donor_settlement["settlement_id"],
        "order_id": donor_settlement.get("order_id", ""),
        "amount_paisa": int(donor_settlement["net_amount_paisa"]),
        "narration": "UNKNOWN CREDIT",  # deliberately free of UTR-shaped tokens
        "posted_at": donor_bank_row["posted_at"],
        "source_bank": "UNKNOWN",
        "bank_template": "UNKNOWN",
    }
    scenario.bank_rows.insert(idx, thief_row)  # processed before the legitimate row

    bank_df = pd.DataFrame(scenario.bank_rows)
    settlement_df = pd.DataFrame(scenario.settlements)
    result, error = _safe_run(pass1_bank_settlement, bank_df, settlement_df)
    repro = {
        "thief_bank_credit_id": thief_row["bank_credit_id"],
        "legitimate_bank_credit_id": donor_bank_row["bank_credit_id"],
        "contested_settlement_id": donor_settlement["settlement_id"],
        "shared_amount_paisa": thief_row["amount_paisa"],
        "shared_posted_at": thief_row["posted_at"],
    }
    if error:
        return _crash("structural", "priority_theft_via_collision", seed, "pass1", error, repro)
    matches, exceptions = result
    thief_match = next((m for m in matches if m.left_id == thief_row["bank_credit_id"]), None)
    legit_match = next((m for m in matches if m.left_id == donor_bank_row["bank_credit_id"]), None)
    legit_exc = next((e for e in exceptions if e.get("record_id") == donor_bank_row["bank_credit_id"]), None)

    if thief_match is not None:
        verdict = WRONG_MATCH
        legit_fate = f"matched to {legit_match.right_id}" if legit_match else f"bumped to {legit_exc['code'] if legit_exc else 'nothing'}"
        detail = (
            f"fabricated, unverified bank credit was confidently matched to real settlement "
            f"{thief_match.right_id} (method={thief_match.method}, confidence={thief_match.confidence}) "
            f"because it was processed first; the legitimate UTR-verified credit was {legit_fate}"
        )
    else:
        thief_exc = next((e for e in exceptions if e.get("record_id") == thief_row["bank_credit_id"]), None)
        if thief_exc is not None:
            verdict, detail = CONTAINED, f"fabricated bank credit correctly routed to {thief_exc['code']}; legitimate credit unaffected"
        else:
            verdict, detail = WRONG_MATCH, "silent drop: fabricated bank credit neither matched nor excepted"

    if thief_match is not None:
        repro["thief_result_method"] = thief_match.method
        repro["thief_result_confidence"] = thief_match.confidence
    return Case(family="structural", mutation="priority_theft_via_collision", seed=seed, target_pass="pass1", verdict=verdict, detail=detail, reproduction=repro)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

MUTATIONS: list[tuple[str, str, Callable[[int], Case]]] = [
    ("narration", "truncate", mut_narration_truncate),
    ("narration", "noise", mut_narration_noise),
    ("narration", "template_swap", mut_narration_template_swap),
    ("narration", "strip_utr", mut_narration_strip_utr),
    ("narration", "false_confidence", mut_narration_false_confidence),
    ("amount", "paisa_drift_bank_credit", make_amount_pass1_mutation("paisa_drift")),
    ("amount", "paisa_drift_payment_net", make_amount_pass2_mutation("paisa_drift")),
    ("amount", "transposed_digits_bank_credit", make_amount_pass1_mutation("transposed_digits")),
    ("amount", "transposed_digits_payment_net", make_amount_pass2_mutation("transposed_digits")),
    ("amount", "sign_flip_bank_credit", make_amount_pass1_mutation("sign_flip")),
    ("amount", "sign_flip_payment_net", make_amount_pass2_mutation("sign_flip")),
    ("amount", "off_by_one_rupee_bank_credit", make_amount_pass1_mutation("off_by_one_rupee")),
    ("amount", "off_by_one_rupee_payment_net", make_amount_pass2_mutation("off_by_one_rupee")),
    ("timing", "period_boundary_shift", mut_timing_period_boundary_shift),
    ("timing", "out_of_order_delivery", mut_timing_out_of_order_delivery),
    ("timing", "backdate_bank_line", mut_timing_backdate_bank_line),
    ("structural", "duplicate_settlement", mut_structural_duplicate_settlement),
    ("structural", "two_same_day_same_amount_settlements", mut_structural_two_same_day_same_amount),
    ("structural", "bank_credit_no_settlement", mut_structural_bank_credit_no_settlement),
    ("structural", "delete_payment_mid_batch", mut_structural_delete_payment_mid_batch),
    ("structural", "priority_theft_via_collision", mut_structural_priority_theft_via_collision),
]

MUTATIONS_BY_NAME = {name: fn for _, name, fn in MUTATIONS}


# --------------------------------------------------------------------------
# Runner / reporting
# --------------------------------------------------------------------------


def run_all(trials_per_mutation: int, base_seed: int) -> list[Case]:
    cases: list[Case] = []
    global_index = 0
    for family, name, fn in MUTATIONS:
        for _ in range(trials_per_mutation):
            seed = base_seed + global_index
            global_index += 1
            cases.append(fn(seed))
    return cases


def aggregate(cases: list[Case]) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, Any]]]:
    family_stats: dict[str, dict[str, int]] = {f: {"total": 0, "contained": 0, "wrong_match": 0, "crash": 0} for f in FAMILIES}
    mutation_stats: dict[str, dict[str, Any]] = {}
    for case in cases:
        fs = family_stats[case.family]
        fs["total"] += 1
        fs[case.verdict.lower()] += 1

        ms = mutation_stats.setdefault(case.mutation, {"family": case.family, "target_pass": case.target_pass, "total": 0, "contained": 0, "wrong_match": 0, "crash": 0})
        ms["total"] += 1
        ms[case.verdict.lower()] += 1
    return family_stats, mutation_stats


def print_report(cases: list[Case], family_stats: dict[str, dict[str, int]], mutation_stats: dict[str, dict[str, Any]]) -> None:
    total = len(cases)
    total_contained = sum(1 for c in cases if c.verdict == CONTAINED)
    total_wrong = sum(1 for c in cases if c.verdict == WRONG_MATCH)
    total_crash = sum(1 for c in cases if c.verdict == CRASH)

    print("=" * 78)
    print(f"LedgerProof adversarial mutation audit -- {total} mutations run")
    print("=" * 78)
    print(f"{'Family':<12}{'Total':>7}{'Contained':>11}{'WrongMatch':>12}{'Crash':>7}{'Containment':>14}")
    for family in FAMILIES:
        fs = family_stats[family]
        rate = (fs["contained"] / fs["total"]) if fs["total"] else 0.0
        print(f"{family:<12}{fs['total']:>7}{fs['contained']:>11}{fs['wrong_match']:>12}{fs['crash']:>7}{rate:>13.1%}")
    overall_rate = (total_contained / total) if total else 0.0
    print("-" * 78)
    print(f"{'OVERALL':<12}{total:>7}{total_contained:>11}{total_wrong:>12}{total_crash:>7}{overall_rate:>13.1%}")

    print()
    print(f"{'Mutation':<38}{'Pass':>7}{'Total':>7}{'Contained':>11}{'Wrong':>7}{'Crash':>7}")
    for name, ms in sorted(mutation_stats.items(), key=lambda kv: (kv[1]["family"], kv[0])):
        print(f"{name:<38}{ms['target_pass']:>7}{ms['total']:>7}{ms['contained']:>11}{ms['wrong_match']:>7}{ms['crash']:>7}")

    wrong_cases = [c for c in cases if c.verdict == WRONG_MATCH]
    crash_cases = [c for c in cases if c.verdict == CRASH]

    print()
    print("=" * 78)
    print(f"WRONG_MATCH cases ({len(wrong_cases)}) -- critical failures with reproduction steps")
    print("=" * 78)
    if not wrong_cases:
        print("(none)")
    for case in wrong_cases:
        print(f"\n[{case.family}/{case.mutation}] seed={case.seed} pass={case.target_pass}")
        print(f"  {case.detail}")
        print(f"  reproduce: python -c \"from audit.mutate import MUTATIONS_BY_NAME; print(MUTATIONS_BY_NAME['{case.mutation}']({case.seed}))\"")
        print(f"  params: {json.dumps(case.reproduction, default=str)}")

    if crash_cases:
        print()
        print("=" * 78)
        print(f"CRASH cases ({len(crash_cases)})")
        print("=" * 78)
        for case in crash_cases:
            print(f"\n[{case.family}/{case.mutation}] seed={case.seed} pass={case.target_pass}: {case.detail}")


def write_scorecard(path: Path, cases: list[Case], family_stats: dict[str, dict[str, int]], mutation_stats: dict[str, dict[str, Any]]) -> None:
    total = len(cases)
    total_contained = sum(1 for c in cases if c.verdict == CONTAINED)
    scorecard = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_mutations": total,
        "overall_containment_rate": (total_contained / total) if total else 0.0,
        "families": {
            family: {**stats, "containment_rate": (stats["contained"] / stats["total"]) if stats["total"] else 0.0}
            for family, stats in family_stats.items()
        },
        "mutations": {
            name: {**stats, "containment_rate": (stats["contained"] / stats["total"]) if stats["total"] else 0.0}
            for name, stats in mutation_stats.items()
        },
        "wrong_match_cases": [asdict(c) for c in cases if c.verdict == WRONG_MATCH],
        "crash_cases": [asdict(c) for c in cases if c.verdict == CRASH],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trials", type=int, default=15, help="trials per mutation type (default: 15)")
    parser.add_argument("--base-seed", type=int, default=100_000, help="base seed for the first trial")
    parser.add_argument("--out", type=str, default=str(ROOT / "audit" / "scorecard.json"))
    parser.add_argument("--replay", nargs=2, metavar=("MUTATION", "SEED"), help="re-run one mutation by name and seed, printing full detail")
    args = parser.parse_args()

    if args.replay:
        name, seed_str = args.replay
        fn = MUTATIONS_BY_NAME.get(name)
        if fn is None:
            print(f"Unknown mutation {name!r}. Known mutations:\n  " + "\n  ".join(sorted(MUTATIONS_BY_NAME)))
            return 1
        case = fn(int(seed_str))
        print(json.dumps(asdict(case), indent=2, default=str))
        return 0

    cases = run_all(args.trials, args.base_seed)
    family_stats, mutation_stats = aggregate(cases)
    print_report(cases, family_stats, mutation_stats)
    write_scorecard(Path(args.out), cases, family_stats, mutation_stats)
    print(f"\nScorecard written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
