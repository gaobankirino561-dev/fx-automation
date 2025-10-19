#!/usr/bin/env python3
import json, argparse, sys
SYN={"net_profit":["net_profit","net","pnl","profit"],
     "win_rate":["win_rate","win","winrate","wr","win_percent"],
     "max_drawdown":["max_drawdown","max_dd","dd","drawdown"],
     "trades":["trades","n_trades","count"]}
def pick(d,ks):
  for k in ks:
    if k in d: return d[k]
  raise KeyError(ks[0])
def norm(x):
  try:
    v=float(x); return v/100.0 if v>1.0 else v
  except: return None
ap=argparse.ArgumentParser()
ap.add_argument("--file",required=True)
ap.add_argument("--min_net",type=float,default=0.0)
ap.add_argument("--min_win",type=float,default=0.45)
ap.add_argument("--max_dd", type=float,default=0.20)
ap.add_argument("--min_trades",type=int,default=30)
a=ap.parse_args()
m=json.load(open(a.file,"r",encoding="utf-8"))
try:
  net=float(pick(m,SYN["net_profit"]))
  win=norm(pick(m,SYN["win_rate"]))
  dd=norm(pick(m,SYN["max_drawdown"]))
  n=int(pick(m,SYN["trades"]))
except Exception as e:
  print(f"[FAIL] metrics.json 不足不正: {e}",file=sys.stderr); sys.exit(2)
ok=True
def j(label,val,cond,passed):
  global ok; print(f"{label}: {val} | gate: {cond} -> {'PASS' if passed else 'FAIL'}"); ok = ok and passed
j("net_profit",net,f"> {a.min_net}",net>a.min_net)
j("win_rate",win,f">= {a.min_win}",(win is not None) and (win>=a.min_win))
j("max_drawdown",dd,f"<= {a.max_dd}",(dd is not None) and (dd<=a.max_dd))
j("trades",n,f">= {a.min_trades}",n>=a.min_trades)
if not ok:
  print("[RESULT] Gate FAILED — PRを停止します。",file=sys.stderr); sys.exit(1)
print("[RESULT] Gate PASSED")
