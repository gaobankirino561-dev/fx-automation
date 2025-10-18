"""
CI gate executor. No external API usage; fully deterministic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gate.backtest_sample import run_sample

THRESHOLDS = {
    "net_pnl_min": 1.0,
    "win_rate_min": 0.45,
    "max_dd_max": 0.20,
    "trades_min": 30,
}


def main() -> int:
    metrics = run_sample(initial=50_000.0)
    print(json.dumps({"metrics": metrics, "thresholds": THRESHOLDS}, indent=2))

    if metrics["net_pnl"] <= THRESHOLDS["net_pnl_min"]:
        print("[gate] FAIL: net pnl below threshold", file=sys.stderr)
        return 1
    if metrics["win_rate"] < THRESHOLDS["win_rate_min"]:
        print("[gate] FAIL: win rate below threshold", file=sys.stderr)
        return 1
    if metrics["max_dd_pct"] > THRESHOLDS["max_dd_max"]:
        print("[gate] FAIL: max drawdown above threshold", file=sys.stderr)
        return 1
    if metrics["trades"] < THRESHOLDS["trades_min"]:
        print("[gate] FAIL: insufficient trades", file=sys.stderr)
        return 1

    print("[gate] PASS: deterministic gate satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
