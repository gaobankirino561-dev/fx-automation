import csv
import os
import yaml
import argparse
import sys
import pathlib

# add repo root to import path
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from make_synth_series import gen_synth_bars
from papertrade.engine import Engine
from trading.decision import Decision
from trading.signal_gpt import decide_with_gpt

OUTDIR = "artifacts/papertrade_integration"; CONF = "papertrade/config.yaml"

def main(dry: bool):
    os.makedirs(OUTDIR, exist_ok=True)
    with open(CONF, "r", encoding="utf-8") as f: conf = yaml.safe_load(f)
    eng = Engine(conf)
    bars = gen_synth_bars(n=96, seed=int(conf.get("seed", 1729)))
    schedule = {5: "trend up", 25: "pullback", 45: "breakout", 65: "mean reversion"}
    for i, (o, h, l, c) in enumerate(bars):
        if eng.open_pos is None:
            if dry and i in schedule:
                side = "BUY" if (len(getattr(eng, 'trades', [])) % 2 == 0) else "SELL"
                eng.enter(side, mid=c, bar_idx=i, tp_pips=15, sl_pips=10, reason=f"dry:{schedule[i]}")
            elif not dry:
                dec = decide_with_gpt({"pair": eng.pair, "m15": [c], "atr": 0.1, "spread": 0.2})
                if dec.side in ("BUY", "SELL"):
                    eng.enter(dec.side, mid=c, bar_idx=i, tp_pips=max(5, dec.tp_pips), sl_pips=max(5, dec.sl_pips), reason=dec.reason or "gpt")
        eng.on_bar(i, o, h, l, c)
    if hasattr(eng, 'finalize'):
        eng.finalize()
    m = eng.metrics()
    with open(os.path.join(OUTDIR, "metrics.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["metric", "value"]); [w.writerow([k, v]) for k, v in m.items()]

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--dry", action="store_true"); a = ap.parse_args(); main(dry=a.dry)
