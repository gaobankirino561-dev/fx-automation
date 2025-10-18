#!/usr/bin/env python3
"""Deterministic CI gate without external inputs.

Evaluates the sample trade series and enforces:
- Net PnL > 0
- Win rate >= 0.45
- Max drawdown <= 0.20
- Trades >= 30
"""

from __future__ import annotations

import sys
from typing import Sequence

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gate.metrics import Metrics, compute_metrics
from gate.metrics import Metrics, compute_metrics
from gate.sample import SAMPLE_TRADES

NET_MIN = 0.0
WIN_RATE_MIN = 0.45
MAX_DD_MAX = 0.20
TRADES_MIN = 30


def evaluate(trades: Sequence[float]) -> Metrics:
    metrics = compute_metrics(list(trades))
    return metrics


def main() -> int:
    metrics = evaluate(SAMPLE_TRADES)
    print(
        f"[gate] net_pnl={metrics.net_pnl:.2f} win_rate={metrics.win_rate:.3f} "
        f"max_dd_pct={metrics.max_dd_pct:.3f} trades={metrics.trades}"
    )
    print(
        f"[gate] thresholds net>{NET_MIN:.2f} win_rate>={WIN_RATE_MIN:.3f} "
        f"max_dd<={MAX_DD_MAX:.3f} trades>={TRADES_MIN}"
    )

    if metrics.net_pnl <= NET_MIN:
        print("[gate] FAIL: net pnl below threshold", file=sys.stderr)
        return 1
    if metrics.win_rate < WIN_RATE_MIN:
        print("[gate] FAIL: win rate below threshold", file=sys.stderr)
        return 1
    if metrics.max_dd_pct > MAX_DD_MAX:
        print("[gate] FAIL: max drawdown above threshold", file=sys.stderr)
        return 1
    if metrics.trades < TRADES_MIN:
        print("[gate] FAIL: insufficient number of trades", file=sys.stderr)
        return 1

    print("[gate] PASS: thresholds satisfied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
