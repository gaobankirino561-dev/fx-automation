import os, csv, argparse, yaml, sys, pathlib

# add repo root to import path for sibling packages
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.make_synth_series import gen_synth_bars
from papertrade.engine import Engine
from trading.signal_gpt import decide_with_gpt
from notifiers.notify import notify

def run_sim(conf_path, mode, outdir):
    with open(conf_path,"r",encoding="utf-8") as f: conf=yaml.safe_load(f)
    os.makedirs(outdir, exist_ok=True)
    eng = Engine(conf)
    bars = gen_synth_bars(n=96, seed=int(conf.get("seed",1729)))
    schedule = {5:"trend up", 25:"pullback", 45:"breakout", 65:"mean reversion"}

    for i,(o,h,l,c) in enumerate(bars):
        if eng.open_pos is None:
            if mode=="dry" and i in schedule:
                side = "BUY" if (len(getattr(eng,'trades',[]))%2==0) else "SELL"
                eng.enter(side, mid=c, bar_idx=i, tp_pips=15, sl_pips=10, reason=f"dry:{schedule[i]}")
            elif mode=="gpt":
                dec = decide_with_gpt({"pair":eng.pair, "m15":[c], "atr":0.1, "spread":0.2})
                if dec.side in ("BUY","SELL"):
                    eng.enter(dec.side, mid=c, bar_idx=i, tp_pips=max(5,dec.tp_pips), sl_pips=max(5,dec.sl_pips), reason=dec.reason or "gpt")
        eng.on_bar(i,o,h,l,c)
    eng.finalize()

    # trades.csv
    with open(os.path.join(outdir,"trades.csv"),"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["side","entry","exit","pnl_jpy","reason"])
        for t in getattr(eng,'trades',[]):
            w.writerow([t.get("side"),t.get("entry"),t.get("exit"),round(t.get("pnl_jpy",0.0),1),t.get("reason")])

    # metrics.csv + notify summary
    m = eng.metrics()
    try:
        notify("run_summary", {"pair":eng.pair,"side":"-","price":"-","pnl_jpy":m.get("net_jpy",0),
               "reason":f"net={m.get('net_jpy',0)}, win={m.get('win_rate_pct',0)}%, dd={m.get('max_drawdown_pct',0)}%, trades={m.get('trades',0)}"})
    except Exception:
        pass
    with open(os.path.join(outdir,"metrics.csv"),"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["metric","value"]); [w.writerow([k,v]) for k,v in m.items()]
    print("DONE metrics:", m)

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--config", default="papertrade/config.yaml"); ap.add_argument("--mode", choices=["dry","gpt"], default="dry"); ap.add_argument("--outdir", default="artifacts/papertrade_run"); a=ap.parse_args(); run_sim(a.config, a.mode, a.outdir)

