from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Metrics:
    net_pnl: float
    win_rate: float
    max_dd_pct: float
    trades: int


def equity_curve(pnls: List[float], initial: float) -> List[float]:
    equity = [initial]
    for pnl in pnls:
        equity.append(equity[-1] + pnl)
    return equity


def max_drawdown(equity: List[float]) -> float:
    peak = equity[0]
    max_dd = 0.0
    for value in equity:
        if value > peak:
            peak = value
        drawdown = peak - value
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd


def compute_metrics(pnls: List[float], initial: float = 50_000.0) -> Metrics:
    trades = len(pnls)
    wins = sum(1 for pnl in pnls if pnl > 0)
    net = sum(pnls)
    equity = equity_curve(pnls, initial)
    dd_abs = max_drawdown(equity)
    win_rate = wins / trades if trades else 0.0
    max_dd_pct = dd_abs / initial if initial else 0.0
    return Metrics(
        net_pnl=net,
        win_rate=win_rate,
        max_dd_pct=max_dd_pct,
        trades=trades,
    )
