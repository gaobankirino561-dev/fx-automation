"""High-level entry decision helper built on top of gpt_client."""

from __future__ import annotations

import math
import os
from typing import Dict, Optional

from config_loader import CONFIG
from gpt_client import ask_decision

__all__ = ["decide_entry", "get_trading_parameters"]

_MODEL_DEFAULT = CONFIG.get("model", {}).get("default", "gpt-4o-mini")
_TRADING_CFG = CONFIG.get("trading", {})

_FORCE_DECISION_ENV = "FX_FORCE_DECISION"
_FORCE_TP_ENV = "FX_FORCE_TP_PIPS"
_FORCE_SL_ENV = "FX_FORCE_SL_PIPS"
_FORCE_REASON_ENV = "FX_FORCE_REASON"


def get_trading_parameters() -> dict[str, float]:
    """Return trading-related scalar thresholds with sensible defaults."""

    return {
        "spread_max": float(_TRADING_CFG.get("spread_max", 2.0)),
        "atr_min_M15": float(_TRADING_CFG.get("atr_min_M15", 0.05)),
        "tp_k_atr": float(_TRADING_CFG.get("tp_k_atr", 1.5)),
        "sl_k_atr": float(_TRADING_CFG.get("sl_k_atr", 0.9)),
        "round_digits": int(_TRADING_CFG.get("round_digits", 4)),
    }


def _coerce_positive(raw: Optional[str], default: float) -> float:
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value <= 0 or not math.isfinite(value):
        return default
    return value


def _maybe_force_decision(summary: str) -> Optional[Dict[str, object]]:
    raw_side = os.getenv(_FORCE_DECISION_ENV)
    if not raw_side:
        return None
    side = raw_side.strip().upper()
    if side not in {"BUY", "SELL"}:
        return None

    tp_pips = _coerce_positive(os.getenv(_FORCE_TP_ENV), default=5.0)
    sl_pips = _coerce_positive(os.getenv(_FORCE_SL_ENV), default=5.0)
    reason = os.getenv(_FORCE_REASON_ENV, "Forced decision via FX_FORCE_DECISION")

    return {
        "decision": side,
        "tp_pips": tp_pips,
        "sl_pips": sl_pips,
        "reason": reason,
        "confidence": 100.0,
    }


def decide_entry(summary: str, *, model: str | None = None) -> Dict[str, object]:
    """Return the structured entry decision for the given summary."""

    if not isinstance(summary, str):
        raise TypeError("summary must be a string")
    cleaned = " ".join(summary.strip().split())
    if not cleaned:
        raise ValueError("summary must not be empty")

    forced = _maybe_force_decision(cleaned)
    if forced is not None:
        return forced

    selected_model = model or _MODEL_DEFAULT
    return ask_decision(cleaned, model=selected_model)
