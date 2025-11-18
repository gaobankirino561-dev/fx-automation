from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict

from trading import signal_gpt

from .base import StrategyBase, StrategyContext


class UsdjpyM15V1(StrategyBase):
    id = "usdjpy_m15_v1"
    name = "USDJPY M15 Daytrade v1"

    def __init__(self, context: StrategyContext) -> None:
        super().__init__(context)
        gpt_cfg = context.config.get("gpt", {}) or {}
        self.default_model = str(gpt_cfg.get("model") or "gpt-4o")
        try:
            self.default_max_tokens = int(gpt_cfg.get("max_tokens") or 300)
        except (TypeError, ValueError):
            self.default_max_tokens = 300
        self.loss_env = "TEST_LOSS_JPY"

    def decide_entry(self, market_state: Dict[str, Any]) -> Dict[str, Any]:
        price = float(market_state.get("price") or 0.0)
        timestamp = market_state.get("timestamp") or dt.datetime.utcnow()
        model = str(market_state.get("model") or self.default_model)
        max_tokens = int(market_state.get("max_tokens") or self.default_max_tokens)
        prompt = (
            f"{self.context.symbol} price={price}. "
            "Decide BUY/SELL/NO_ENTRY for next 5-15min with short reason. Reply JSON."
        )
        try:
            dec = signal_gpt.judge(prompt, model=model, max_tokens=max_tokens)
        except Exception as exc:  # pragma: no cover - defensive
            dec = {"decision": "NO_ENTRY", "reason": f"signal_gpt missing: {type(exc).__name__}"}

        side = dec.get("decision", "NO_ENTRY")
        return {
            "action": side,
            "reason": dec.get("reason", ""),
            "raw_decision": dec,
            "prompt": prompt,
            "entry_price": price,
            "timestamp": timestamp,
        }

    def decide_exit(self, position_state: Dict[str, Any]) -> Dict[str, Any]:
        entry_price = float(position_state.get("entry_price") or 0.0)
        side = position_state.get("side", "BUY")
        exit_price = float(position_state.get("exit_price") or entry_price)
        forced_loss = self._read_forced_loss()
        pnl = -abs(forced_loss)
        reason = "forced_loss_env" if forced_loss else "flat_exit"
        return {
            "action": "CLOSE" if side in ("BUY", "SELL") else "HOLD",
            "exit_price": exit_price,
            "pnl_jpy": pnl,
            "reason": reason,
        }

    def _read_forced_loss(self) -> float:
        raw = os.getenv(self.loss_env, "0")
        try:
            return float(raw or 0.0)
        except ValueError:
            return 0.0
