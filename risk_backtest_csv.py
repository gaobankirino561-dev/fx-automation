import csv
import os
import random
import time

from executor import TradeExecutor as Executor
from position_entities import Order, PIP_SIZE
from stats import summarize_pips

N = int(os.getenv("RB_TRADES", "300"))
TP = float(os.getenv("RB_TP", "10"))
SL = float(os.getenv("RB_SL", "8"))
SIDE = os.getenv("RB_SIDE", "ALT").upper() or "ALT"
RISK = float(os.getenv("RB_RISK", "0.005"))
E0 = float(os.getenv("RB_EQ", "10000"))
EDGE = float(os.getenv("RB_EDGE", "0.55"))
OUT = os.getenv("RB_OUTCSV", "equity_curve.csv")
BASE_PRICE = float(os.getenv("RB_PRICE", "155.00"))
SEED = int(os.getenv("RB_SEED", "42"))

rng = random.Random(SEED)
ex = Executor(pip_size=PIP_SIZE)


def one_trade(side: str, price: float, eq: float) -> float:
    size = max((eq * RISK) / SL, 0.01)
    ex.reset()
    ex.submit(Order(side, price, TP, SL, size), price, int(time.time()))
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
    if ex.positions():
        residual = ex.close_all(price, int(time.time()))
        if residual:
            pnl = sum(f.pnl for f in residual)
    return pnl


def main() -> None:
    eq = E0
    peak = eq
    maxdd_pct = 0.0
    price = BASE_PRICE
    pips = []

    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["trade", "equity"])
        for i in range(N):
            if SIDE == "BUY":
                side = "BUY"
            elif SIDE == "SELL":
                side = "SELL"
            else:
                side = "BUY" if i % 2 == 0 else "SELL"

            pnl = one_trade(side, price, eq)
            pips.append(pnl)
            eq += pnl
            peak = max(peak, eq)
            if peak > 0:
                maxdd_pct = max(maxdd_pct, (peak - eq) / peak * 100.0)
            writer.writerow([i + 1, round(eq, 2)])
            price += (rng.random() - 0.5) * 0.2

    stats = summarize_pips(pips)
    ret_pct = (eq / E0 - 1) * 100.0
    print(
        f"trades:{int(stats['trades'])} win_rate:{stats['win_rate']:.1f}% PF:{stats['profit_factor']:.2f} "
        f"net_pips:{stats['net_pips']:.1f} equity_final:{eq:.2f} ({ret_pct:.1f}%) maxDD%:{maxdd_pct:.1f} csv:{OUT}"
    )


if __name__ == "__main__":
    main()
