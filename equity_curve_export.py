from __future__ import annotations

import csv
import os
import random
import time
from typing import List, Tuple

from executor import TradeExecutor as Executor
from position_entities import Order, PIP_SIZE

TRADES = int(os.getenv("EC_TRADES", "200"))
EDGE = float(os.getenv("EC_EDGE", "0.55"))
RISK = float(os.getenv("EC_RISK", "0.005"))
TP_PIPS = float(os.getenv("EC_TP", "10"))
SL_PIPS = float(os.getenv("EC_SL", "8"))
START_EQUITY = float(os.getenv("EC_EQ", "10000"))
BASE_PRICE = float(os.getenv("EC_PRICE", "155.00"))
SIDE_MODE = os.getenv("EC_SIDE", "ALT").strip().upper() or "ALT"
SEED = int(os.getenv("EC_SEED", "99"))
OUTFILE = os.getenv("EC_OUT", "equity_curve.csv")

rng = random.Random(SEED)
executor = Executor(pip_size=PIP_SIZE)


def _position_size(equity: float) -> float:
    return max((equity * RISK) / SL_PIPS, 0.01)


def _simulate_trade(side: str, entry: float, equity: float) -> Tuple[float, float]:
    size = _position_size(equity)
    order = Order(side=side, price=entry, tp_pips=TP_PIPS, sl_pips=SL_PIPS, size=size)
    executor.reset()
    executor.submit(order, entry, int(time.time()))

    go_tp = rng.random() < EDGE
    path = (
        [entry - 0.03, entry, entry + 0.03, entry + 0.06, entry + 0.12]
        if go_tp and side == "BUY"
        else [entry + 0.03, entry, entry - 0.03, entry - 0.06, entry - 0.12]
        if go_tp
        else [entry + 0.01, entry - 0.04, entry - 0.08, entry - 0.12]
        if side == "BUY"
        else [entry - 0.01, entry + 0.04, entry + 0.08, entry + 0.12]
    )

    pnl = 0.0
    for price in path:
        fills = executor.step(price, int(time.time()))
        if fills:
            pnl = sum(fill.pnl for fill in fills)
            break
    else:
        residual = executor.close_all(entry, int(time.time()))
        if residual:
            pnl = sum(fill.pnl for fill in residual)
    return pnl, size


def main() -> None:
    equity = START_EQUITY
    price = BASE_PRICE
    rows: List[Tuple[int, float, float]] = [(0, equity, 0.0)]

    for index in range(1, TRADES + 1):
        if SIDE_MODE == "BUY":
            side = "BUY"
        elif SIDE_MODE == "SELL":
            side = "SELL"
        else:
            side = "BUY" if index % 2 == 1 else "SELL"

        pnl, size = _simulate_trade(side, price, equity)
        equity += pnl
        price += (rng.random() - 0.5) * 0.2
        rows.append((index, equity, pnl))

    with open(OUTFILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["trade", "equity", "pnl"])
        writer.writerows(rows)

    print(f"Saved equity curve to {OUTFILE}")


if __name__ == "__main__":
    main()
