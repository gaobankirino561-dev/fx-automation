from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Literal, Optional

PIP_SIZE = 0.01
Side = Literal["BUY", "SELL"]
FillResult = Literal["OPENED", "TP", "SL", "MANUAL_CLOSE"]


@dataclass(frozen=True)
class Order:
    side: Side
    price: float
    tp_pips: float
    sl_pips: float
    size: float = 1.0

    def __post_init__(self) -> None:
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        for field_name, value in (
            ("price", self.price),
            ("tp_pips", self.tp_pips),
            ("sl_pips", self.sl_pips),
            ("size", self.size),
        ):
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{field_name} must be a finite number")
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.tp_pips < 0 or self.sl_pips < 0:
            raise ValueError("tp_pips and sl_pips must be non-negative")
        if self.size <= 0:
            raise ValueError("size must be positive")


@dataclass(frozen=True)
class Position:
    id: str
    side: Side
    entry: float
    tp: float
    sl: float
    size: float
    open_time: int

    def __post_init__(self) -> None:
        if self.side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if not self.id:
            raise ValueError("id must be a non-empty string")
        if not math.isfinite(self.entry) or self.entry <= 0:
            raise ValueError("entry must be a positive finite number")
        if not math.isfinite(self.tp) or self.tp <= 0:
            raise ValueError("tp must be a positive finite number")
        if not math.isfinite(self.sl) or self.sl <= 0:
            raise ValueError("sl must be a positive finite number")
        if not math.isfinite(self.size) or self.size <= 0:
            raise ValueError("size must be a positive finite number")
        if not isinstance(self.open_time, int) or self.open_time < 0:
            raise ValueError("open_time must be a non-negative integer")


@dataclass(frozen=True)
class Fill:
    result: FillResult
    pnl: float
    close_time: int
    position: Position

    def __post_init__(self) -> None:
        if self.result not in {"OPENED", "TP", "SL", "MANUAL_CLOSE"}:
            raise ValueError("result is invalid")
        if not math.isfinite(self.pnl):
            raise ValueError("pnl must be finite")
        if not isinstance(self.close_time, int) or self.close_time < 0:
            raise ValueError("close_time must be a non-negative integer")


def open_position(order: Order, now_price: float, now_ts: int, *, pip_size: float = PIP_SIZE) -> Fill:
    if not math.isfinite(now_price) or now_price <= 0:
        raise ValueError("now_price must be a positive finite number")
    if not isinstance(now_ts, int) or now_ts < 0:
        raise ValueError("now_ts must be a non-negative integer")
    if pip_size <= 0 or not math.isfinite(pip_size):
        raise ValueError("pip_size must be a positive finite number")

    entry = float(now_price)
    if order.side == "BUY":
        tp = entry + order.tp_pips * pip_size
        sl = entry - order.sl_pips * pip_size
    else:
        tp = entry - order.tp_pips * pip_size
        sl = entry + order.sl_pips * pip_size

    position = Position(
        id=uuid.uuid4().hex,
        side=order.side,
        entry=entry,
        tp=tp,
        sl=sl,
        size=order.size,
        open_time=now_ts,
    )
    return Fill(result="OPENED", pnl=0.0, close_time=now_ts, position=position)


def update_position(position: Position, now_price: float, now_ts: int, *, pip_size: float = PIP_SIZE) -> Optional[Fill]:
    if not math.isfinite(now_price) or now_price <= 0:
        raise ValueError("now_price must be a positive finite number")
    if not isinstance(now_ts, int) or now_ts < 0:
        raise ValueError("now_ts must be a non-negative integer")
    if pip_size <= 0 or not math.isfinite(pip_size):
        raise ValueError("pip_size must be a positive finite number")

    exit_price: Optional[float] = None
    result: Optional[FillResult] = None

    if position.side == "BUY":
        if now_price >= position.tp:
            exit_price = position.tp
            result = "TP"
        elif now_price <= position.sl:
            exit_price = position.sl
            result = "SL"
    else:
        if now_price <= position.tp:
            exit_price = position.tp
            result = "TP"
        elif now_price >= position.sl:
            exit_price = position.sl
            result = "SL"

    if exit_price is None or result is None:
        return None

    return close_position(position, exit_price, now_ts, result, pip_size=pip_size)


def close_position(
    position: Position,
    exit_price: float,
    now_ts: int,
    result: FillResult = "MANUAL_CLOSE",
    *,
    pip_size: float = PIP_SIZE,
) -> Fill:
    if result not in {"TP", "SL", "MANUAL_CLOSE"}:
        raise ValueError("result must be TP, SL, or MANUAL_CLOSE")
    if not math.isfinite(exit_price) or exit_price <= 0:
        raise ValueError("exit_price must be a positive finite number")
    if not isinstance(now_ts, int) or now_ts < 0:
        raise ValueError("now_ts must be a non-negative integer")
    if pip_size <= 0 or not math.isfinite(pip_size):
        raise ValueError("pip_size must be a positive finite number")

    pnl = _calculate_pnl(position, exit_price, pip_size)
    return Fill(result=result, pnl=pnl, close_time=now_ts, position=position)


def _calculate_pnl(position: Position, exit_price: float, pip_size: float) -> float:
    direction = 1 if position.side == "BUY" else -1
    pip_move = (exit_price - position.entry) * direction / pip_size
    return pip_move * position.size
