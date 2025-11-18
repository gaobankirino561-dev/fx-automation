from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class StrategyContext:
    strategy_id: str
    symbol: str
    timeframes: Dict[str, str]
    config: Dict[str, Any]


class StrategyBase(ABC):
    """
    Base interface shared by live and backtest flows.
    """

    id: str
    name: str

    def __init__(self, context: StrategyContext) -> None:
        self.context = context

    @abstractmethod
    def decide_entry(self, market_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decide whether to enter a new position.
        """

    @abstractmethod
    def decide_exit(self, position_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decide how to close/manage the current position.
        """
