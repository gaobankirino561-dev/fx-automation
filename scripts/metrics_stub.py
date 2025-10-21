import argparse, csv, os, sys
p=argparse.ArgumentParser()
p.add_argument("--root", default="metrics")
p.add_argument("--cases", nargs="+", required=True)   # 例: 2024M05_USDJPY_M15 など
p.add_argument("--net", type=float, default=200.0)    # 円換算でもOK（ダミー）
p.add_argument("--win", type=float, default=0.55)     # 勝率(0-1)
p.add_argument("--dd",  type=float, default=0.10)     # 最大DD(0-1)
p.add_argument("--trades", type=int, default=35)
p.add_argument("--force", action="store_true")
a=p.parse_args()

os.makedirs(a.root, exist_ok=True)
out_csv=os.path.join(a.root,"metrics.csv")
if (not a.force) and os.path.exists(out_csv):
    print(f"{out_csv} exists; use --force", file=sys.stderr); sys.exit(1)

with open(out_csv,"w",newline="",encoding="utf-8") as f:
    w=csv.writer(f)
    w.writerow(["case","net","win","dd","trades"])
    for c in a.cases:
        w.writerow([c, a.net, a.win, a.dd, a.trades])

print(f"wrote {out_csv} with {len(a.cases)} rows")
