"""Core technical indicator utilities.

This module provides a minimal, well-tested set of helpers we can build on
for signal generation.  Each function validates input data, avoids external
numeric dependencies, and keeps behaviour explicit so downstream components
(summarizer/decider) can rely on deterministic snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


Number = float | int


class IndicatorError(ValueError):
    """Raised when input data is insufficient or malformed."""


@dataclass(frozen=True)
class IndicatorSnapshot:
    atr: float
    rsi: float
    sma: float


def _ensure_length(data: Sequence[Number], period: int, name: str) -> None:
    if period <= 0:
        raise IndicatorError(f"period must be positive, got {period}")
    if len(data) <= period:
        raise IndicatorError(
            f"{name} expects more than 'period' samples (len={len(data)}, period={period})"
        )


def _to_float_sequence(values: Iterable[Number]) -> list[float]:
    try:
        return [float(v) for v in values]
    except Exception as exc:  # pragma: no cover - defensive path
        raise IndicatorError("values must be numeric") from exc


def simple_moving_average(values: Sequence[Number], period: int) -> float:
    """Return the arithmetic mean over the last *period* observations."""

    samples = _to_float_sequence(values)
    _ensure_length(samples, period - 1, "simple_moving_average")
    window = samples[-period:]
    return sum(window) / period


def atr(highs: Sequence[Number], lows: Sequence[Number], closes: Sequence[Number], period: int) -> float:
    """Average True Range using the classic Wilder smoothing."""

    h = _to_float_sequence(highs)
    l = _to_float_sequence(lows)
    c = _to_float_sequence(closes)

    if not (len(h) == len(l) == len(c)):
        raise IndicatorError("highs, lows, closes must be the same length")
    _ensure_length(h, period, "atr")

    true_ranges: list[float] = []
    for idx in range(1, len(h)):
        tr = max(
            h[idx] - l[idx],
            abs(h[idx] - c[idx - 1]),
            abs(l[idx] - c[idx - 1]),
        )
        true_ranges.append(tr)

    initial = sum(true_ranges[:period]) / period
    atr_values = [initial]
    alpha = 1.0 / period
    for tr in true_ranges[period:]:
        prev = atr_values[-1]
        atr_values.append(prev + alpha * (tr - prev))
    return atr_values[-1]


def rsi(closes: Sequence[Number], period: int) -> float:
    """Relative Strength Index (Wilder)."""

    prices = _to_float_sequence(closes)
    _ensure_length(prices, period, "rsi")

    gains: list[float] = []
    losses: list[float] = []
    for idx in range(1, len(prices)):
        diff = prices[idx] - prices[idx - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def build_snapshot(
    highs: Sequence[Number],
    lows: Sequence[Number],
    closes: Sequence[Number],
    *,
    atr_period: int = 14,
    rsi_period: int = 14,
    sma_period: int = 14,
) -> IndicatorSnapshot:
    """Convenience helper returning a consistent indicator bundle."""

    atr_value = atr(highs, lows, closes, atr_period)
    rsi_value = rsi(closes, rsi_period)
    sma_value = simple_moving_average(closes, sma_period)
    return IndicatorSnapshot(atr=atr_value, rsi=rsi_value, sma=sma_value)



