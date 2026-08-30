import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_generator(out_dir: Path, *, seed: int, orders: int, **flags: bool) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "gen" / "generate.py"),
        "--seed",
        str(seed),
        "--orders",
        str(orders),
        "--out",
        str(out_dir),
    ]
    for flag_name, enabled in flags.items():
        if enabled:
            cmd.append(f"--{flag_name.replace('_', '-')}")
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def file_hashes(directory: Path):
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def test_deterministic_generation(tmp_path):
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    run_generator(out1, seed=42, orders=120)
    run_generator(out2, seed=42, orders=120)

    assert file_hashes(out1) == file_hashes(out2)


def test_defects_match_configured_rates(tmp_path):
    orders = 200
    out_dir = tmp_path / "run_defects"
    enabled_flags = {
        "missing_payment": True,
        "duplicate_payment": True,
        "payment_amount_mismatch": True,
        "refund_amount_mismatch": True,
        "settlement_amount_mismatch": True,
        "bank_credit_amount_mismatch": True,
        "narration_mismatch": True,
    }

    run_generator(out_dir, seed=123, orders=orders, **enabled_flags)
    truth = json.loads((out_dir / "ground_truth.json").read_text())

    defect_counts = Counter(item["type"] for item in truth["defects"])
    expected_rates = {
        "missing_payment": 0.02,
        "duplicate_payment": 0.01,
        "payment_amount_mismatch": 0.08,
        "refund_amount_mismatch": 0.04,
        "settlement_amount_mismatch": 0.06,
        "bank_credit_amount_mismatch": 0.05,
        "narration_mismatch": 0.03,
    }

    for defect_type, rate in expected_rates.items():
        expected = rate * orders
        observed = defect_counts.get(defect_type, 0)
        tolerance = max(3, int(expected * 0.35) + 2)
        assert abs(observed - expected) <= tolerance, (
            defect_type,
            expected,
            observed,
            tolerance,
        )
