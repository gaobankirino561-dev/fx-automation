#!/usr/bin/env python3
import os, json, sys, argparse, glob
S={"net_profit":["net_profit","net","pnl","profit"],"win_rate":["win_rate","win","winrate","wr","win_percent"],"max_drawdown":["max_drawdown","max_dd","dd","drawdown"],"trades":["trades","n_trades","count"]}
def pick(d,ks):
  for k in ks:
    if k in d: return d[k]
  raise KeyError(ks[0])
def norm(x):
  try: v=float(x); return v/100.0 if v>1 else v
  except: return None
ap=argparse.ArgumentParser()
ap.add_argument("--root",default="metrics")
ap.add_argument("--min_net",type=float,default=0.0)
ap.add_argument("--min_win",type=float,default=0.45)
ap.add_argument("--max_dd",type=float,default=0.20)
ap.add_argument("--min_trades",type=int,default=30)
ap.add_argument("--min_pass_rate",type=float,default=1.0)
a=ap.parse_args()
files=sorted(glob.glob(os.path.join(a.root,"**","metrics.json"),recursive=True))
if not files:
  print("[FAIL] no metrics.json found", file=sys.stderr); sys.exit(2)
total=len(files); passed=0
for f in files:
  m=json.load(open(f,"r",encoding="utf-8"))
  net=float(pick(m,S["net_profit"])); win=norm(pick(m,S["win_rate"])); dd=norm(pick(m,S["max_drawdown"])); n=int(pick(m,S["trades"]))
  ok=(net>a.min_net) and (win is not None and win>=a.min_win) and (dd is not None and dd<=a.max_dd) and (n>=a.min_trades)
  print(f"[{ 'PASS' if ok else 'FAIL' }] {f} | net={net} win={win} dd={dd} n={n}")
  passed += 1 if ok else 0
rate=passed/total
print(f"[SUMMARY] passed {passed}/{total} (rate={rate:.2f}) required>={a.min_pass_rate:.2f}")
sys.exit(0 if rate>=a.min_pass_rate else 1)
