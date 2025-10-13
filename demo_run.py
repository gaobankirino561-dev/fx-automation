"""Minimal end-to-end demo wiring indicators, summarizer, decider, and executor."""

from __future__ import annotations

import os
from typing import List

from config_loader import CONFIG
from decider import decide_entry, get_trading_parameters
from executor import TradeExecutor
from indicators import IndicatorSnapshot, atr, rsi, simple_moving_average
from mt5_adapter import get_bars, init as mt5_init, shutdown as mt5_shutdown
from position_entities import Order, PIP_SIZE
from summarizer import summarize_indicators

_SYMBOL = "USDJPY"
_TIMEFRAME = "M15"
_NEED_BARS = 32

_DUMMY_BARS: List[dict[str, float]] = [
    {"time": 1714400000 + i * 900, "open": 155.8 + i * 0.01, "high": 155.9 + i * 0.01, "low": 155.7 + i * 0.01, "close": 155.85 + i * 0.01}
    for i in range(_NEED_BARS)
]

_DEFAULT_VOLUME = 0.1
_FORCE_DECISION_ENV = "FX_FORCE_DECISION"


def _check_environment() -> None:
    default_model = CONFIG.get("model", {}).get("default", "gpt-4o-mini")
    api_key_present = bool(os.getenv("OPENAI_API_KEY"))
    print(f"Default model: {default_model}")
    print(f"OPENAI_API_KEY set: {'YES' if api_key_present else 'NO'}")


def _load_bars() -> List[dict[str, float]]:
    status = mt5_init()
    if not status.get("ok"):
        print(f"MT5 init failed: {status.get('reason')}, using dummy bars")
        return _DUMMY_BARS
    result = get_bars(_SYMBOL, _TIMEFRAME, _NEED_BARS)
    mt5_shutdown()
    if not result.get("ok"):
        print(f"get_bars failed: {result.get('reason')}, using dummy bars")
        return _DUMMY_BARS
    bars = result.get("bars", [])
    if len(bars) < _NEED_BARS:
        print("Insufficient bars from MT5, using dummy bars")
        return _DUMMY_BARS
    return bars


def _build_snapshot(bars: List[dict[str, float]]) -> IndicatorSnapshot:
    highs = [float(item["high"]) for item in bars]
    lows = [float(item["low"]) for item in bars]
    closes = [float(item["close"]) for item in bars]
    atr_val = atr(highs, lows, closes, 14)
    rsi_val = rsi(closes, 14)
    sma_val = simple_moving_average(closes, 14)
    return IndicatorSnapshot(atr=atr_val, rsi=rsi_val, sma=sma_val)


def _to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _run_forced_simulation(summary: str, params: dict[str, float], executor: TradeExecutor, bars: List[dict[str, float]]) -> None:
    base_bar = bars[-1]
    entry_price = float(base_bar["close"])
    entry_ts = int(base_bar["time"])

    print("Forced decision mode detected. Running offline execution flow.")
    print(f"Summary -> {summary}")

    decision = decide_entry(summary)
    print(f"Forced decision -> {decision}")

    side = decision.get("decision")
    if side not in {"BUY", "SELL"}:
        print("Forced decision did not resolve to BUY/SELL. Nothing to simulate.")
        return

    tp_pips = _to_float(decision.get("tp_pips")) or 1.0
    sl_pips = _to_float(decision.get("sl_pips")) or 1.0

    order = Order(
        side=side,
        price=entry_price,
        tp_pips=tp_pips,
        sl_pips=sl_pips,
        size=_DEFAULT_VOLUME,
    )

    fill = executor.submit(order, entry_price, entry_ts)
    print(f"Forced run: open -> {{'result': {fill.result!r}, 'position': {fill.position}}}")

    tp_price = entry_price + tp_pips * PIP_SIZE if side == "BUY" else entry_price - tp_pips * PIP_SIZE
    tp_fills = executor.step(tp_price, entry_ts + 1)
    if tp_fills:
        print(f"Forced run: TP step @ {tp_price:.5f} -> {tp_fills}")
    else:
        print("Forced run: TP step produced no fills (check tp_pips > 0).")

    order_sl = Order(
        side=side,
        price=entry_price,
        tp_pips=tp_pips,
        sl_pips=sl_pips,
        size=_DEFAULT_VOLUME,
    )
    fill_sl_open = executor.submit(order_sl, entry_price, entry_ts + 2)
    print(f"Forced run: reopen for SL test -> {{'result': {fill_sl_open.result!r}, 'position': {fill_sl_open.position}}}")

    sl_price = entry_price - sl_pips * PIP_SIZE if side == "BUY" else entry_price + sl_pips * PIP_SIZE
    sl_fills = executor.step(sl_price, entry_ts + 3)
    if sl_fills:
        print(f"Forced run: SL step @ {sl_price:.5f} -> {sl_fills}")
    else:
        print("Forced run: SL step produced no fills (check sl_pips > 0).")

    remaining = executor.close_all(entry_price, entry_ts + 4)
    if remaining:
        print(f"Forced run: residual close_all -> {remaining}")
    print(f"Forced run: final positions -> {executor.positions()}")


def run_once(run_id: int, summary: str, params: dict[str, float], executor: TradeExecutor, bar: dict[str, float]) -> None:
    price = float(bar["close"])
    now_ts = int(bar["time"])
    print(f"Run {run_id}: summary -> {summary}")
    print(f"Run {run_id}: trading params -> {params}")
    try:
        decision = decide_entry(summary)
    except RuntimeError as exc:
        decision = {"ok": False, "reason": str(exc)}
    print(f"Run {run_id}: decision -> {decision}")

    side = decision.get("decision") if isinstance(decision, dict) else None
    if side in {"BUY", "SELL"}:
        order = Order(
            side=side,
            price=price,
            tp_pips=_to_float(decision.get("tp_pips")),
            sl_pips=_to_float(decision.get("sl_pips")),
            size=_DEFAULT_VOLUME,
        )
        fill = executor.submit(order, price, now_ts)
        print(f"Run {run_id}: order -> {{'result': {fill.result!r}, 'position': {fill.position}}}")
    else:
        print(f"Run {run_id}: no order placed")

    fills = executor.step(price, now_ts)
    if fills:
        print(f"Run {run_id}: step fills -> {fills}")
    print(f"Run {run_id}: open positions -> {executor.positions()}")


def main() -> None:
    _check_environment()
    params = get_trading_parameters()
    bars = _load_bars()
    snapshot = _build_snapshot(bars)
    summary = summarize_indicators(snapshot)

    executor = TradeExecutor()

    forced_side = os.getenv(_FORCE_DECISION_ENV, "").strip().upper()
    if forced_side in {"BUY", "SELL"}:
        _run_forced_simulation(summary, params, executor, bars)
        return

    for idx, bar in enumerate(bars[-2:], start=1):
        run_once(idx, summary, params, executor, bar)

    last_bar = bars[-1]
    final = executor.close_all(float(last_bar["close"]), int(last_bar["time"]))
    if final:
        print(f"Final close fills -> {final}")
    print(f"Final positions -> {executor.positions()}")


if __name__ == "__main__":
    main()
