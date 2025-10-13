from __future__ import annotations

import os
import random
import time
from typing import List

from executor import TradeExecutor as Executor
from position_entities import Order, PIP_SIZE
from stats import summarize_pips

N_TRADES = int(os.getenv("RB_TRADES", "300"))
TP_PIPS = float(os.getenv("RB_TP", "10"))
SL_PIPS = float(os.getenv("RB_SL", "8"))
SIDE_MODE = os.getenv("RB_SIDE", "ALT").strip().upper() or "ALT"
RISK = float(os.getenv("RB_RISK", "0.005"))
START_EQUITY = float(os.getenv("RB_EQ", "10000"))
EDGE = float(os.getenv("RB_EDGE", "0.55"))
BASE_PRICE = float(os.getenv("RB_PRICE", "155.00"))
SEED = int(os.getenv("RB_SEED", "42"))

rng = random.Random(SEED)
ex = Executor(pip_size=PIP_SIZE)


def position_size(equity: float) -> float:
    return max((equity * RISK) / SL_PIPS, 0.01)


def one_trade(side: str, price: float, equity: float) -> float:
    size = position_size(equity)
    ex.reset()
    ex.submit(Order(side, price, TP_PIPS, SL_PIPS, size), price, int(time.time()))

    go_tp = rng.random() < EDGE
    if side == "BUY":
        path = [price - 0.03, price, price + 0.03, price + 0.06, price + 0.12] if go_tp else [price + 0.01, price - 0.04, price - 0.08, price - 0.12]
    else:
        path = [price + 0.03, price, price - 0.03, price - 0.06, price - 0.12] if go_tp else [price - 0.01, price + 0.04, price + 0.08, price + 0.12]

    pnl = 0.0
    for step_price in path:
        fills = ex.step(step_price, int(time.time()))
        if fills:
            pnl = sum(f.pnl for f in fills)
            break
    return pnl


def main() -> None:
    equity = START_EQUITY
    price = BASE_PRICE
    peak = equity
    maxdd_pct = 0.0
    pnl_series: List[float] = []

    for i in range(N_TRADES):
        if SIDE_MODE == "BUY":
            side = "BUY"
        elif SIDE_MODE == "SELL":
            side = "SELL"
        else:
            side = "BUY" if i % 2 == 0 else "SELL"

        pnl = one_trade(side, price, equity)
        pnl_series.append(pnl)
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            maxdd_pct = max(maxdd_pct, (peak - equity) / peak * 100.0)

        price += (rng.random() - 0.5) * 0.2

    stats = summarize_pips(pnl_series)
    ret_pct = (equity / START_EQUITY - 1.0) * 100.0
    print(
        f"trades:{stats['trades']} win_rate:{stats['win_rate']:.1f}% PF:{stats['profit_factor']:.2f} "
        f"net_pips:{stats['net_pips']:.1f} equity_final:{equity:.2f} ({ret_pct:.1f}%) maxDD%:{maxdd_pct:.1f}"
    )


if __name__ == "__main__":
    main()
