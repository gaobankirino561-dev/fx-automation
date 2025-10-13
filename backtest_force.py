from __future__ import annotations

import os
import random
import time

from executor import TradeExecutor as Executor
from position_entities import Order, PIP_SIZE
from stats import summarize_pips

SIDE = os.getenv("BT_SIDE", "ALT").upper() or "ALT"
N = int(os.getenv("BT_TRADES", "20"))
BASE = float(os.getenv("BT_PRICE", "155.00"))
TP = float(os.getenv("BT_TP", "10"))
SL = float(os.getenv("BT_SL", "8"))
SIZE = float(os.getenv("BT_SIZE", "1.0"))
PIP = float(os.getenv("BT_PIP", str(PIP_SIZE)))
SEED = int(os.getenv("BT_SEED", "42"))

rng = random.Random(SEED)
ex = Executor(pip_size=PIP)
pips_outcomes: list[float] = []


def do_trade(side: str, price: float) -> float:
    ex.reset()
    ex.submit(Order(side, price, TP, SL, SIZE), price, int(time.time()))
    go_tp = rng.random() < 0.55
    if side == "BUY":
        path = [price - 0.03, price, price + 0.03, price + 0.06, price + 0.12] if go_tp else [price + 0.01, price - 0.04, price - 0.08, price - 0.12]
    else:
        path = [price + 0.03, price, price - 0.03, price - 0.06, price - 0.12] if go_tp else [price - 0.01, price + 0.04, price + 0.08, price + 0.12]

    out = 0.0
    for step_price in path:
        fills = ex.step(step_price, int(time.time()))
        if fills:
            out = sum(f.pnl for f in fills)
            break

    if ex.positions():
        residual = ex.close_all(price, int(time.time()))
        if residual:
            out = sum(f.pnl for f in residual)

    return out


def main() -> None:
    price = BASE
    for i in range(N):
        if SIDE == "BUY":
            active_side = "BUY"
        elif SIDE == "SELL":
            active_side = "SELL"
        else:
            active_side = "BUY" if i % 2 == 0 else "SELL"

        pnl = do_trade(active_side, price)
        pips_outcomes.append(pnl)

        price += (rng.random() - 0.5) * 0.2

    s = summarize_pips(pips_outcomes)
    print(
        "trades:",
        s["trades"],
        "win_rate(%):",
        round(s["win_rate"], 1),
        "PF:",
        round(s["profit_factor"], 2),
        "net_pips:",
        round(s["net_pips"], 1),
        "maxDD:",
        round(s["max_dd"], 1),
    )


if __name__ == "__main__":
    main()
