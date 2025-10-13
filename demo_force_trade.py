"""Forced trade simulator that reuses executor to generate multiple trades and aggregate stats."""

from __future__ import annotations

import os
import random
import time
from typing import Iterable, Literal, Sequence

from executor import TradeExecutor as Executor
from position_entities import Order, PIP_SIZE
from stats import summarize_pips

Side = Literal["BUY", "SELL"]


def _ensure_positive(name: str, value_str: str | None, default: float) -> float:
    if value_str is None:
        return default
    try:
        value = float(value_str)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value!r}")
    return value


def _gen_path(side: Side, price: float, tp: float, sl: float, *, pip_size: float) -> list[float]:
    if side == "BUY":
        bonus = random.uniform(-pip_size * sl, pip_size * tp)
        return [
            price - 0.03,
            price,
            price + 0.03,
            price + 0.06,
            price + tp * pip_size + bonus,
            price - sl * pip_size / 2,
        ]
    bonus = random.uniform(-pip_size * tp, pip_size * sl)
    return [
        price + 0.03,
        price,
        price - 0.03,
        price - 0.06,
        price - tp * pip_size + bonus,
        price + sl * pip_size / 2,
    ]


def _run_trade(ex: Executor, side: Side, price: float, tp: float, sl: float, size: float, *, pip_size: float) -> float:
    now_ts = int(time.time())
    order = Order(side=side, price=price, tp_pips=tp, sl_pips=sl, size=size)
    open_fill = ex.submit(order, price, now_ts)
    print(f"[OPEN] {open_fill}")
    path = _gen_path(side, price, tp, sl, pip_size=pip_size)
    for p in path:
        fills = ex.step(p, int(time.time()))
        if fills:
            for f in fills:
                print("  [FILL]", f.result, "pnl:", round(f.pnl, 2), "close@", round(p, 5))
                return f.pnl
    residual = ex.close_all(price, int(time.time()))
    if residual:
        f = residual[0]
        print("  [FORCE_CLOSE]", f.result, "pnl:", round(f.pnl, 2))
        return f.pnl
    print("  [WARN] no fills?!")
    return 0.0


def main() -> None:
    random.seed(int(os.getenv("SIM_SEED", "1")))

    side_env = os.getenv("FORCE_DECISION", "BUY").strip().upper()
    sides: Sequence[Side]
    if side_env == "BOTH":
        sides = ("BUY", "SELL")
    else:
        sides = (side_env if side_env in {"BUY", "SELL"} else "BUY",)

    tp = _ensure_positive("FORCE_TP", os.getenv("FORCE_TP"), 10.0)
    sl = _ensure_positive("FORCE_SL", os.getenv("FORCE_SL"), 8.0)
    price = _ensure_positive("PRICE", os.getenv("PRICE"), 155.0)
    size = _ensure_positive("SIZE", os.getenv("SIZE"), 1.0)
    pip_size = _ensure_positive("PIP_SIZE", os.getenv("PIP_SIZE"), PIP_SIZE)
    trades = int(os.getenv("NUM_TRADES", "6"))

    print(f"[CONFIG] sides={sides} price={price} tp={tp} sl={sl} size={size} pip={pip_size} trades={trades}")

    ex = Executor(pip_size=pip_size)
    pnl_values: list[float] = []
    for index in range(trades):
        side = sides[index % len(sides)]
        print(f"\n[TRADE {index + 1}/{trades}] side={side}")
        pnl = _run_trade(ex, side, price, tp, sl, size, pip_size=pip_size)
        pnl_values.append(pnl)

    stats = summarize_pips(pnl_values)
    print("\n===== SUMMARY =====")
    for key, value in stats.items():
        print(f"{key:>12}: {value:.4f}" if isinstance(value, float) else f"{key:>12}: {value}")


if __name__ == "__main__":
    main()
