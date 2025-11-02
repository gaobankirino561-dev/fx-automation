from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional

from notifiers.notify import notify

Side = Literal["BUY", "SELL"]


def worsen_for_trader(side: Side, mid: float, spread_pips: float, slip_pips: float, pip: float, *, is_entry: bool) -> float:
    spread = spread_pips * pip
    slip = slip_pips * pip
    if side == "BUY":
        return mid + (spread / 2.0) + (slip if is_entry else 0.0)
    else:
        return mid - (spread / 2.0) - (slip if is_entry else 0.0)


@dataclass
class Position:
    side: Side
    entry_price: float
    lot: float
    tp: float
    sl: float
    open_bar_idx: int
    reason: str


@dataclass
class Guard:
    per_trade_risk_jpy: float


class Engine:
    def __init__(self, pair: str, lot: float, pip: float = 0.01, spread_pips: float = 0.2, slip_pips: float = 0.1, guard: Optional[Guard] = None) -> None:
        self.pair = pair
        self.lot = lot
        self.pip = pip
        self.spread_pips = spread_pips
        self.slip_pips = slip_pips
        self.guard = guard or Guard(per_trade_risk_jpy=1000.0)
        self.open_pos: Optional[Position] = None

    def _pip_value_jpy(self) -> float:
        if self.pair.upper().endswith("JPY"):
            return 1000.0 * self.lot
        return 10.0 * self.lot

    def can_enter(self, reason: str):
        if self.open_pos is not None:
            return False, "already in market"
        return True, "ok"

    def enter(self, side: Side, mid: float, bar_idx: int, tp_pips: float, sl_pips: float, reason: str):
        if self.open_pos is not None:
            return False, "already in market"
        ok, gmsg = self.can_enter(reason)
        if not ok:
            notify("entry_blocked", {"pair": self.pair, "side": side, "price": "-", "pnl_jpy": "-", "reason": gmsg})
            return False, gmsg

        per_pip_jpy = self._pip_value_jpy()
        est_loss = max(0.0, sl_pips) * per_pip_jpy
        if est_loss > self.guard.per_trade_risk_jpy + 1e-9:
            msg = f"risk_per_trade={est_loss:.1f}JPY>limit({self.guard.per_trade_risk_jpy}JPY); reason={reason}"
            notify("entry_blocked", {"pair": self.pair, "side": side, "price": "-", "pnl_jpy": "-", "reason": msg})
            return False, msg

        price = worsen_for_trader(side, mid, self.spread_pips, self.slip_pips, self.pip, is_entry=True)
        tp = price + tp_pips * self.pip if side == "BUY" else price - tp_pips * self.pip
        sl = price - sl_pips * self.pip if side == "BUY" else price + sl_pips * self.pip
        self.open_pos = Position(side=side, entry_price=price, lot=self.lot, tp=tp, sl=sl, open_bar_idx=bar_idx, reason=reason)
        notify("entry", {"pair": self.pair, "side": side, "price": round(price, 3), "pnl_jpy": 0, "reason": reason})
        return True, "entered"
