#!/usr/bin/env python3
import os, json, sys, glob, argparse
S={"net":["net_profit","net","pnl","profit"],"wr":["win_rate","win","winrate","wr","win_percent"],"dd":["max_drawdown","max_dd","dd","drawdown"],"n":["trades","n_trades","count"]}
def pick(d,ks):
  for k in ks:
    if k in d: return d[k]
  return None
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
  print("[FAIL] no metrics.json",file=sys.stderr); sys.exit(2)
tot=len(files); okc=0
for f in files:
  m=json.load(open(f,"r",encoding="utf-8"))
  net=pick(m,S["net"]); wr=norm(pick(m,S["wr"])); dd=norm(pick(m,S["dd"])); n=pick(m,S["n"])
  try: net_val=float(net)
  except (TypeError,ValueError): net_val=None
  try: n_val=int(n)
  except (TypeError,ValueError): n_val=None
  g=(net_val is not None and net_val>a.min_net) and (wr is not None and wr>=a.min_win) and (dd is not None and dd<=a.max_dd) and (n_val is not None and n_val>=a.min_trades)
  print(f"[{ 'PASS' if g else 'FAIL' }] {f} | net={net_val} wr={wr} dd={dd} n={n_val}")
  okc+=int(g)
rate=okc/tot; print(f"[SUMMARY] {okc}/{tot} (rate={rate:.2f}) need>={a.min_pass_rate:.2f}")
sys.exit(0 if rate>=a.min_pass_rate else 1)
