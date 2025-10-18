from __future__ import annotations

from typing import List

from gate.metrics import compute_metrics

PNL_YEN = [
    +500, -400, +500, -400, +500, +500, -400, +500, -400, +500,
    +500, -400, +500, +500, -400, +500, -400, +500, +500, -400,
    +500, -400, +500, +500, -400, +500, -400, +500, +500, -400,
    +500, -400, +500, +500, -400, +500, -400, +500, +500, -400,
]


def run_sample(initial: float = 50_000.0) -> dict[str, float]:
    metrics = compute_metrics(PNL_YEN, initial=initial)
    return {
        "net_pnl": metrics.net_pnl,
        "win_rate": metrics.win_rate,
        "max_dd_pct": metrics.max_dd_pct,
        "trades": metrics.trades,
    }


if __name__ == "__main__":
    print(run_sample())
