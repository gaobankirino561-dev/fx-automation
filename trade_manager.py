from __future__ import annotations

import itertools
import math
import threading
from dataclasses import dataclass
from typing import Dict, Optional

from mt5_adapter import get_quote
from position_manager import Position, PositionManager


@dataclass(frozen=True)
class OrderRecord:
    order_id: int
    symbol: str
    side: str
    volume: float
    price: float
    sl: Optional[float]
    tp: Optional[float]
    status: str = "FILLED"


class TradeManager:
    """Minimal in-memory order submission and position tracking helper."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = itertools.count(1)
        self._orders: list[OrderRecord] = []
        self._positions = PositionManager()

    def submit_market_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        *,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> Dict[str, object]:
        """Submit a simplified market order and update the net position."""

        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        normalized_side = side.upper()
        if normalized_side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if not isinstance(volume, (int, float)) or not math.isfinite(volume) or volume <= 0:
            raise ValueError("volume must be a positive number")

        resolved_price, reason = self._resolve_price(symbol, normalized_side, price)
        if resolved_price is None:
            return {"ok": False, "reason": reason or "PRICE_UNAVAILABLE"}

        with self._lock:
            order_id = next(self._sequence)
            order = OrderRecord(
                order_id=order_id,
                symbol=symbol,
                side=normalized_side,
                volume=float(volume),
                price=resolved_price,
                sl=float(sl) if sl is not None else None,
                tp=float(tp) if tp is not None else None,
            )
            self._orders.append(order)
            position_state = self._apply_fill(order)
            payload = {
                "ok": True,
                "order": self._order_to_dict(order),
                "position": position_state.to_dict() if position_state else None,
            }
        return payload

    def list_orders(self) -> list[Dict[str, object]]:
        with self._lock:
            return [self._order_to_dict(order) for order in self._orders]

    def get_positions(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return self._positions.snapshot()

    def reset(self) -> None:
        with self._lock:
            self._orders.clear()
            self._positions.reset()
            self._sequence = itertools.count(1)

    def _resolve_price(
        self,
        symbol: str,
        side: str,
        supplied: Optional[float],
    ) -> tuple[Optional[float], Optional[str]]:
        if supplied is not None:
            if not isinstance(supplied, (int, float)) or not math.isfinite(supplied) or supplied <= 0:
                return None, "INVALID_PRICE"
            return float(supplied), None

        quote = get_quote(symbol)
        if not isinstance(quote, dict) or not quote.get("ok"):
            return None, "PRICE_UNAVAILABLE"
        if side == "BUY":
            price = float(quote.get("ask", 0.0))
        else:
            price = float(quote.get("bid", 0.0))
        if price <= 0:
            return None, "PRICE_UNAVAILABLE"
        return price, None

    def _apply_fill(self, order: OrderRecord) -> Optional[Position]:
        return self._positions.apply_fill(order.symbol, order.side, order.volume, order.price)

    @staticmethod
    def _order_to_dict(order: OrderRecord) -> Dict[str, object]:
        return {
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side,
            "volume": order.volume,
            "price": order.price,
            "sl": order.sl,
            "tp": order.tp,
            "status": order.status,
        }
