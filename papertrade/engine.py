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
    def __init__(
        self,
        conf: Optional[dict] = None,
        pair: Optional[str] = None,
        lot: Optional[float] = None,
        pip: float = 0.01,
        spread_pips: float = 0.2,
        slip_pips: float = 0.1,
        guard: Optional[Guard] = None,
    ) -> None:
        if isinstance(conf, dict) and pair is None:
            self.pair = conf.get("pair", "USDJPY")
            self.lot = float(conf.get("lot", 0.1))
            self.pip = pip
            self.spread_pips = float(conf.get("spread_pips", 0.2))
            self.slip_pips = float(conf.get("slippage_pips", 0.1))
            rg = conf.get("risk_guard", {}) or {}
            self.guard = guard or Guard(per_trade_risk_jpy=float(rg.get("per_trade_risk_jpy", 1000.0)))
        else:
            self.pair = pair or "USDJPY"
            self.lot = float(lot if lot is not None else 0.1)
            self.pip = pip
            self.spread_pips = spread_pips
            self.slip_pips = slip_pips
            self.guard = guard or Guard(per_trade_risk_jpy=1000.0)
        self.open_pos: Optional[Position] = None
        self.trades = []  # list of dicts
        self._equity = 0.0
        self._peak = 0.0

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

        # 1トレード許容損失チェック
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

    def on_bar(self, i: int, o: float, h: float, l: float, c: float):
        if self.open_pos is None:
            return
        side = self.open_pos.side
        tp = self.open_pos.tp
        sl = self.open_pos.sl
        hit = None
        if side == "BUY":
            if l <= sl:
                hit = ("SL", sl)
            elif h >= tp:
                hit = ("TP", tp)
        else:
            if h >= sl:
                hit = ("SL", sl)
            elif l <= tp:
                hit = ("TP", tp)
        if hit:
            kind, px = hit
            per_pip = self._pip_value_jpy()
            move_pips = (px - self.open_pos.entry_price) / self.pip * (1 if side == "BUY" else -1)
            pnl = move_pips * per_pip
            self._equity += pnl
            self._peak = max(self._peak, self._equity)
            self.trades.append({
                "result": kind,
                "pnl_jpy": pnl,
                "side": side,
                "entry": self.open_pos.entry_price,
                "exit": px,
                "reason": self.open_pos.reason,
            })
            self.open_pos = None

    def finalize(self):
        return

    def metrics(self):
        eq = self._equity
        peak = self._peak
        wins = sum(1 for t in self.trades if t["result"] == "TP")
        total = len(self.trades)
        win_rate = (wins / total * 100.0) if total else 0.0
        dd = ((peak - eq) / (peak if peak > 0 else 1.0) * 100.0) if peak else 0.0
        return {
            "net_jpy": round(eq, 6),
            "win_rate_pct": round(win_rate, 6),
            "max_drawdown_pct": round(dd, 6),
            "trades": float(total),
        }
