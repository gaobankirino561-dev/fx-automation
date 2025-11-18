from __future__ import annotations

from typing import Dict, Type

from .base import StrategyBase, StrategyContext
from .usdjpy_m15_v1 import UsdjpyM15V1

STRATEGY_REGISTRY: Dict[str, Type[StrategyBase]] = {
    UsdjpyM15V1.id: UsdjpyM15V1,
}


def create_strategy(strategy_id: str, context: StrategyContext) -> StrategyBase:
    try:
        cls = STRATEGY_REGISTRY[strategy_id]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Unknown strategy_id: {strategy_id!r}") from exc
    return cls(context)


__all__ = ["StrategyBase", "StrategyContext", "create_strategy", "STRATEGY_REGISTRY"]
