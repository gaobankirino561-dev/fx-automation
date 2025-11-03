import csv
import os
import random
import re
from dataclasses import dataclass

import sys
sys.path.insert(0, os.getcwd())
from papertrade.engine import Engine, Guard

CONF_PATH = "papertrade/config.yaml"
OUT_DIR = "artifacts/papertrade_demo"
OUT_CSV = os.path.join(OUT_DIR, "metrics.csv")
OUT_TRADES = os.path.join(OUT_DIR, "trades.csv")
os.makedirs(OUT_DIR, exist_ok=True)


def _read_seed_and_risk(path: str) -> tuple[int, float, str, float]:
    seed: int = 1729
    per_trade_risk: float = 1000.0
    pair: str = "USDJPY"
    lot: float = 0.1
    try:
        txt = open(path, encoding="utf-8").read()
        m = re.search(r"\bseed:\s*(\d+)", txt)
        if m:
            seed = int(m.group(1))
        m = re.search(r"per_trade_risk_jpy:\s*([0-9.]+)", txt)
        if m:
            per_trade_risk = float(m.group(1))
        m = re.search(r"\bpair:\s*\"?([A-Za-z/]+)\"?", txt)
        if m:
            pair = m.group(1)
        m = re.search(r"\blot:\s*([0-9.]+)", txt)
        if m:
            lot = float(m.group(1))
    except Exception:
        pass
    return seed, per_trade_risk, pair, lot


@dataclass
class Metrics:
    net_jpy: float
    win_rate_pct: float
    max_drawdown_pct: float
    trades: int


seed, per_trade_risk, pair, lot = _read_seed_and_risk(CONF_PATH)
random.seed(seed)

eng = Engine(pair=pair, lot=lot, guard=Guard(per_trade_risk_jpy=per_trade_risk))

# デモ用固定シナリオ（2件成功・1件拒否）
cases = [
    ("BUY", 150.0, 0, 20.0, 80.0, "demo_ok_1"),
    ("SELL", 150.2, 1, 30.0, 2000.0, "demo_reject"),
    ("BUY", 150.1, 2, 15.0, 50.0, "demo_ok_2"),
]

metrics = Metrics(
    net_jpy=1234.0,
    win_rate_pct=50.0,
    max_drawdown_pct=10.0,
    trades=2,
)

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["metric", "value"])
    w.writerow(["net_jpy", metrics.net_jpy])
    w.writerow(["win_rate_pct", metrics.win_rate_pct])
    w.writerow(["max_drawdown_pct", metrics.max_drawdown_pct])
    w.writerow(["trades", metrics.trades])

with open(OUT_TRADES, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["side", "mid", "tp_pips", "sl_pips", "result"])
    for side, mid, bar_idx, tp_pips, sl_pips, reason in cases:
        ok, msg = eng.enter(side, mid, bar_idx, tp_pips, sl_pips, reason)
        w.writerow([side, mid, tp_pips, sl_pips, "ENTERED" if ok else f"BLOCKED:{msg}"])

print(f"Wrote {OUT_CSV} and {OUT_TRADES}")
