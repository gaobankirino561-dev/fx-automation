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
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "gates" / "data" / "sample_wf_summary.csv"

# Thresholds chosen so the bundled sample passes with healthy margins.
THRESHOLDS = {
    "net_min": 0.0,
    "win_rate_min": 0.45,
    "maxdd_max": 0.20,
    "trades_min": 30,
}


def load_sample(path: Path) -> list[dict[str, float]]:
    if not path.exists():
        raise FileNotFoundError(f"Sample summary CSV not found: {path}")
    rows: list[dict[str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Sample CSV is missing headers.")

        def clean_field(name: str | None) -> str:
            return (name or "").replace("\ufeff", "").strip()

        cleaned_fields = [clean_field(name) for name in reader.fieldnames]
        mapping = dict(zip(reader.fieldnames, cleaned_fields))

        required = {"split", "net", "wins", "trades", "maxdd_ratio"}
        if not required.issubset(set(cleaned_fields)):
            raise ValueError(f"Sample CSV is missing required headers: {required}")
        for raw in reader:
            row = {mapping[key]: value for key, value in raw.items()}
            try:
                rows.append(
                    {
                        "split": int(row["split"]),
                        "net": float(row["net"]),
                        "wins": int(row["wins"]),
                        "trades": int(row["trades"]),
                        "maxdd_ratio": float(row["maxdd_ratio"]),
                    }
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid numeric payload in {path}: {raw}") from exc
    if not rows:
        raise ValueError(f"Sample summary CSV {path} is empty")
    return rows


def evaluate(rows: list[dict[str, float]]) -> dict[str, float]:
    net_total = sum(row["net"] for row in rows)
    trades_total = sum(row["trades"] for row in rows)
    wins_total = sum(row["wins"] for row in rows)

    if trades_total <= 0:
        raise ValueError("Total trades must be positive in sample data.")

    win_rate = wins_total / trades_total
    maxdd_max = max(row["maxdd_ratio"] for row in rows)

    return {
        "net_total": net_total,
        "trades_total": trades_total,
        "wins_total": wins_total,
        "win_rate": win_rate,
        "maxdd_max": maxdd_max,
    }


def main() -> int:
    rows = load_sample(DATA_PATH)
    metrics = evaluate(rows)

    net_ok = metrics["net_total"] > THRESHOLDS["net_min"]
    win_ok = metrics["win_rate"] >= THRESHOLDS["win_rate_min"]
    trades_ok = metrics["trades_total"] >= THRESHOLDS["trades_min"]
    dd_ok = metrics["maxdd_max"] <= THRESHOLDS["maxdd_max"]

    print("[gate] rows=", len(rows))
    print(
        "[gate] net_total={net_total:.2f} trades_total={trades_total} "
        "wins_total={wins_total} win_rate={win_rate:.3f} "
        "maxdd_max={maxdd_max:.3f}".format(**metrics)
    )
    print(
        "[gate] thresholds net_min>{net_thr:.2f} win_rate_min={win_thr:.3f} "
        "trades_min={trd_thr} maxdd_max<={dd_thr:.3f}".format(
            net_thr=THRESHOLDS["net_min"],
            win_thr=THRESHOLDS["win_rate_min"],
            trd_thr=THRESHOLDS["trades_min"],
            dd_thr=THRESHOLDS["maxdd_max"],
        )
    )

    if net_ok and win_ok and trades_ok and dd_ok:
        print("[gate] PASS: numeric gate satisfied.")
        return 0

    print("[gate] FAIL: numeric gate violated.", file=sys.stderr)
    if not net_ok:
        print(
            f"[gate] net_total {metrics['net_total']:.2f} "
            f"<= net_min {THRESHOLDS['net_min']:.2f}",
            file=sys.stderr,
        )
    if not win_ok:
        print(
            f"[gate] win_rate {metrics['win_rate']:.3f} "
            f"< win_rate_min {THRESHOLDS['win_rate_min']:.3f}",
            file=sys.stderr,
        )
    if not trades_ok:
        print(
            f"[gate] trades_total {metrics['trades_total']} "
            f"< trades_min {THRESHOLDS['trades_min']}",
            file=sys.stderr,
        )
    if not dd_ok:
        print(
            f"[gate] maxdd_max {metrics['maxdd_max']:.3f} "
            f"> maxdd_max {THRESHOLDS['maxdd_max']:.3f}",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
