#!/usr/bin/env python3
"""
Deterministic numeric gate for CI.

The script loads a tiny reference walk-forward summary and checks that the
aggregated metrics stay above configured thresholds.  This gives us a simple,
repeatable “green light” before heavier tests run, without relying on external
services.
"""

from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "gates" / "data" / "sample_wf_summary.csv"

# Thresholds chosen so the bundled sample passes with healthy margins.
THRESHOLDS = {
    "pf_avg_min": 1.20,
    "ret_avg_min": 0.50,
    "maxdd_avg_max": 15.0,
}


def load_sample(path: Path) -> list[dict[str, float]]:
    if not path.exists():
        raise FileNotFoundError(f"Sample summary CSV not found: {path}")
    rows: list[dict[str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"split", "pf", "return_pct", "maxdd_pct"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError(f"Sample CSV is missing required headers: {required}")
        for raw in reader:
            try:
                rows.append(
                    {
                        "split": int(raw["split"]),
                        "pf": float(raw["pf"]),
                        "return_pct": float(raw["return_pct"]),
                        "maxdd_pct": float(raw["maxdd_pct"]),
                    }
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid numeric payload in {path}: {raw}") from exc
    if not rows:
        raise ValueError(f"Sample summary CSV {path} is empty")
    return rows


def evaluate(rows: list[dict[str, float]]) -> dict[str, float]:
    pf_values = [row["pf"] for row in rows]
    ret_values = [row["return_pct"] for row in rows]
    dd_values = [row["maxdd_pct"] for row in rows]

    evaluation = {
        "pf_avg": statistics.fmean(pf_values),
        "ret_avg": statistics.fmean(ret_values),
        "maxdd_avg": statistics.fmean(dd_values),
        "pf_min": min(pf_values),
        "ret_min": min(ret_values),
        "maxdd_max": max(dd_values),
    }
    return evaluation


def main() -> int:
    rows = load_sample(DATA_PATH)
    metrics = evaluate(rows)

    pf_ok = metrics["pf_avg"] >= THRESHOLDS["pf_avg_min"]
    ret_ok = metrics["ret_avg"] >= THRESHOLDS["ret_avg_min"]
    dd_ok = metrics["maxdd_avg"] <= THRESHOLDS["maxdd_avg_max"]

    print("[gate] rows=", len(rows))
    print(
        "[gate] pf_avg={pf_avg:.2f} pf_min={pf_min:.2f} "
        "ret_avg={ret_avg:.2f} ret_min={ret_min:.2f} "
        "maxdd_avg={maxdd_avg:.2f} maxdd_max={maxdd_max:.2f}".format(**metrics)
    )
    print(
        "[gate] thresholds pf_avg_min={pf_thr:.2f} ret_avg_min={ret_thr:.2f} "
        "maxdd_avg_max={dd_thr:.2f}".format(
            pf_thr=THRESHOLDS["pf_avg_min"],
            ret_thr=THRESHOLDS["ret_avg_min"],
            dd_thr=THRESHOLDS["maxdd_avg_max"],
        )
    )

    if pf_ok and ret_ok and dd_ok:
        print("[gate] PASS: numeric gate satisfied.")
        return 0

    print("[gate] FAIL: numeric gate violated.", file=sys.stderr)
    if not pf_ok:
        print(
            f"[gate] pf_avg {metrics['pf_avg']:.2f} "
            f"< pf_avg_min {THRESHOLDS['pf_avg_min']:.2f}",
            file=sys.stderr,
        )
    if not ret_ok:
        print(
            f"[gate] ret_avg {metrics['ret_avg']:.2f} "
            f"< ret_avg_min {THRESHOLDS['ret_avg_min']:.2f}",
            file=sys.stderr,
        )
    if not dd_ok:
        print(
            f"[gate] maxdd_avg {metrics['maxdd_avg']:.2f} "
            f"> maxdd_avg_max {THRESHOLDS['maxdd_avg_max']:.2f}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
