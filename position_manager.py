from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Position:
    symbol: str
    volume: float
    avg_price: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "symbol": self.symbol,
            "volume": self.volume,
            "avg_price": self.avg_price,
        }


class PositionManager:
    """Track net positions per symbol and update them with fills."""

    def __init__(self) -> None:
        self._positions: Dict[str, Position] = {}

    def apply_fill(self, symbol: str, side: str, volume: float, price: float) -> Optional[Position]:
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if volume <= 0 or not math.isfinite(volume):
            raise ValueError("volume must be a positive finite number")
        if price <= 0 or not math.isfinite(price):
            raise ValueError("price must be a positive finite number")

        delta = volume if side == "BUY" else -volume
        state = self._positions.get(symbol)

        if state is None:
            state = Position(symbol=symbol, volume=delta, avg_price=price)
            self._positions[symbol] = state
            return state

        existing_sign = 1 if state.volume > 0 else -1 if state.volume < 0 else 0
        order_sign = 1 if delta > 0 else -1
        new_volume = state.volume + delta

        if existing_sign == 0:
            state.volume = new_volume
            state.avg_price = price
            return state

        if existing_sign == order_sign:
            total = abs(state.volume) + abs(delta)
            state.avg_price = (
                abs(state.volume) * state.avg_price + abs(delta) * price
            ) / total
            state.volume = new_volume
            return state

        remaining_abs = abs(state.volume) - abs(delta)
        if remaining_abs > 0:
            state.volume = new_volume
            return state

        if math.isclose(new_volume, 0.0, abs_tol=1e-9):
            self._positions.pop(symbol, None)
            return None

        new_state = Position(symbol=symbol, volume=new_volume, avg_price=price)
        self._positions[symbol] = new_state
        return new_state

    def get(self, symbol: str) -> Optional[Position]:
        return self._positions.get(symbol)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        return {symbol: pos.to_dict() for symbol, pos in self._positions.items()}

    def reset(self) -> None:
        self._positions.clear()
