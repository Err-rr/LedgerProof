from __future__ import annotations

import json
import time
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd


def _read_ground_truth(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def compute_score(ground_truth_path: str | Path, *, matches_count: int = 0, exception_count: int = 0) -> dict[str, Any]:
    gt = _read_ground_truth(ground_truth_path)
    mapping = gt.get("mapping", [])
    defects = gt.get("defects", [])
    total_orders = int(gt.get("order_count", 0) or 0)

    actual_matches = max(0, int(matches_count))
    actual_exceptions = max(0, int(exception_count))
    expected_pairs = len(mapping)
    match_rate = (actual_matches / expected_pairs) if expected_pairs else 0.0
    auto_resolve_rate = (actual_matches / (actual_matches + actual_exceptions)) if (actual_matches + actual_exceptions) else 0.0
    precision = (actual_matches / max(1, actual_matches + actual_exceptions)) if (actual_matches + actual_exceptions) else 0.0

    records_processed = max(1, expected_pairs + len(defects))
    throughput = records_processed / max(1.0, (time.perf_counter() / 1.0))

    return {
        "total_orders": total_orders,
        "expected_pairs": expected_pairs,
        "actual_matches": actual_matches,
        "actual_exceptions": actual_exceptions,
        "match_rate": match_rate,
        "auto_resolve_rate": auto_resolve_rate,
        "precision": precision,
        "throughput_rps": throughput,
        "defect_count": len(defects),
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("Summary")
    print("-" * 50)
    print(f"Orders: {summary['total_orders']}")
    print(f"Matches: {summary['actual_matches']}")
    print(f"Exceptions: {summary['actual_exceptions']}")
    print(f"Match rate: {summary['match_rate']:.2%}")
    print(f"Auto-resolve rate: {summary['auto_resolve_rate']:.2%}")
    print(f"Precision: {summary['precision']:.2%}")
    print(f"Throughput: {summary['throughput_rps']:.2f} rec/s")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Score a reconciliation run against ground truth.")
    parser.add_argument("--ground-truth", type=str, required=True)
    parser.add_argument("--matches", type=int, default=0)
    parser.add_argument("--exceptions", type=int, default=0)
    args = parser.parse_args()

    summary = compute_score(args.ground_truth, matches_count=args.matches, exception_count=args.exceptions)
    print_summary(summary)
