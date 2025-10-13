from __future__ import annotations

import math
from typing import Dict, List

from position_entities import (
    Fill,
    Order,
    Position,
    PIP_SIZE,
    close_position,
    open_position,
    update_position,
)


class TradeExecutor:
    """Track open positions and resolve TP/SL or manual exits."""

    def __init__(self, *, pip_size: float = PIP_SIZE) -> None:
        if pip_size <= 0 or not math.isfinite(pip_size):
            raise ValueError("pip_size must be a positive finite number")
        self._pip_size = float(pip_size)
        self._positions: Dict[str, Position] = {}

    def submit(self, order: Order, now_price: float, now_ts: int) -> Fill:
        fill = open_position(order, now_price, now_ts, pip_size=self._pip_size)
        self._positions[fill.position.id] = fill.position
        return fill

    def step(self, now_price: float, now_ts: int) -> List[Fill]:
        fills: List[Fill] = []
        for pos_id, position in list(self._positions.items()):
            fill = update_position(position, now_price, now_ts, pip_size=self._pip_size)
            if fill is not None:
                fills.append(fill)
                self._positions.pop(pos_id, None)
        return fills

    def close_all(self, now_price: float, now_ts: int) -> List[Fill]:
        fills: List[Fill] = []
        for pos_id, position in list(self._positions.items()):
            fill = close_position(
                position,
                now_price,
                now_ts,
                result="MANUAL_CLOSE",
                pip_size=self._pip_size,
            )
            fills.append(fill)
            self._positions.pop(pos_id, None)
        return fills

    def positions(self) -> List[Position]:
        return list(self._positions.values())

    def reset(self) -> None:
        self._positions.clear()
