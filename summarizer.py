"""Utilities for turning indicator snapshots into human-readable summaries."""

from __future__ import annotations

from indicators import IndicatorSnapshot
from config_loader import CONFIG

__all__ = ["summarize_indicators"]


_SUMMARIZER_CFG = CONFIG.get("summarizer", {})
_DEF_ATR_THRESHOLDS = tuple(float(x) for x in _SUMMARIZER_CFG.get("atr_thresholds", [0.1, 0.25]))
_DEF_RSI_BOUNDS = tuple(float(x) for x in _SUMMARIZER_CFG.get("rsi_bounds", [30.0, 70.0]))


def _classify_atr(value: float) -> str:
    low, high = _DEF_ATR_THRESHOLDS
    if value < low:
        return "low volatility"
    if value < high:
        return "moderate volatility"
    return "elevated volatility"


def _classify_rsi(value: float) -> str:
    lower, upper = _DEF_RSI_BOUNDS
    if value <= lower:
        return "oversold bias"
    if value >= upper:
        return "overbought bias"
    return "neutral momentum"


def summarize_indicators(snapshot: IndicatorSnapshot) -> str:
    """Return a compact textual summary for downstream prompts."""

    if not isinstance(snapshot, IndicatorSnapshot):
        raise TypeError("snapshot must be an IndicatorSnapshot")

    atr_line = f"ATR(14): {snapshot.atr:.3f} ({_classify_atr(snapshot.atr)})"
    rsi_line = f"RSI(14): {snapshot.rsi:.1f} ({_classify_rsi(snapshot.rsi)})"
    sma_line = f"SMA(14): {snapshot.sma:.3f}"
    return " | ".join([atr_line, rsi_line, sma_line])



