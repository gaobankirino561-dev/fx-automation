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
    "net_pnl_min": 1.0,       # 円
    "win_rate_min": 0.45,     # 45%
    "max_dd_pct_max": 0.20,   # 20%
    "trades_min": 30,
}


def main() -> int:
    metrics = run_sample(initial=50_000.0)
    payload = {"metrics": metrics, "thresholds": THRESHOLDS}
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    ok = (
        metrics["net_pnl"] >= THRESHOLDS["net_pnl_min"]
        and metrics["win_rate"] >= THRESHOLDS["win_rate_min"]
        and metrics["max_dd_pct"] <= THRESHOLDS["max_dd_pct_max"]
        and metrics["trades"] >= THRESHOLDS["trades_min"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
