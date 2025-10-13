"""MetaTrader5 adapter with safe fallbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

try:  # optional dependency
    import MetaTrader5 as mt5  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    mt5 = None  # type: ignore


class MT5Error(RuntimeError):
    """Raised when MetaTrader5 operations fail."""


@dataclass
class Rate:
    time: int
    open: float
    high: float
    low: float
    close: float
    spread: int


_SUPPORTED_TIMEFRAMES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
}


# ---------------------------------------------------------------------------
# Initialisation helpers
# ---------------------------------------------------------------------------

def init() -> Dict[str, object]:
    """Attempt to initialise MT5, returning a status dictionary."""

    if mt5 is None:
        return {"ok": False, "reason": "MT5_NOT_AVAILABLE"}
    if mt5.initialize():
        return {"ok": True}
    code, msg = mt5.last_error()
    return {"ok": False, "reason": f"MT5_INIT_FAILED:{code}:{msg}"}


def connect() -> None:
    status = init()
    if not status.get("ok"):
        raise MT5Error(f"MT5 initialize failed: {status.get('reason')}")


def shutdown() -> None:
    if mt5 is not None:
        mt5.shutdown()


# ---------------------------------------------------------------------------
# Symbol utilities
# ---------------------------------------------------------------------------

def ensure_symbol(symbol: str) -> None:
    if mt5 is None:
        raise MT5Error("MT5_NOT_AVAILABLE")
    info = mt5.symbol_info(symbol)
    if info is None:
        raise MT5Error(f"Symbol not found: {symbol}")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise MT5Error(f"Failed to select symbol: {symbol}")


# ---------------------------------------------------------------------------
# Data fetching API
# ---------------------------------------------------------------------------

def _timeframe_to_mt5(timeframe: str) -> Optional[int]:
    key = timeframe.upper()
    constant = getattr(mt5, f"TIMEFRAME_{key}", None) if mt5 else None
    if constant is not None:
        return constant
    return _SUPPORTED_TIMEFRAMES.get(key)


def get_bars(symbol: str, timeframe: str, need: int) -> Dict[str, object]:
    if mt5 is None:
        return {"ok": False, "reason": "MT5_NOT_AVAILABLE"}
    if need <= 0:
        return {"ok": False, "reason": "NO_DATA"}
    tf = _timeframe_to_mt5(timeframe)
    if tf is None:
        return {"ok": False, "reason": "UNSUPPORTED_TF"}
    try:
        ensure_symbol(symbol)
    except MT5Error:
        return {"ok": False, "reason": "NOT_INIT"}
    rates = mt5.copy_rates_from_pos(symbol, tf, 0, need)
    if rates is None:
        return {"ok": False, "reason": "NO_DATA"}
    bars = [
        {
            "time": int(item["time"]),
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
        }
        for item in rates
    ]
    return {"ok": True, "bars": bars}


def get_quote(symbol: str) -> Dict[str, object]:
    if mt5 is None:
        return {"ok": False, "reason": "MT5_NOT_AVAILABLE"}
    try:
        ensure_symbol(symbol)
    except MT5Error:
        return {"ok": False, "reason": "NOT_INIT"}
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"ok": False, "reason": "NO_DATA"}
    bid = float(getattr(tick, "bid", 0.0))
    ask = float(getattr(tick, "ask", 0.0))
    raw_spread = getattr(tick, "spread", None)
    if raw_spread is not None and raw_spread != 0:
        spread_val = float(raw_spread)
    else:
        spread_val = abs(ask - bid)
    return {
        "ok": True,
        "bid": bid,
        "ask": ask,
        "spread": spread_val,
        "time": int(getattr(tick, "time", 0)),
    }



