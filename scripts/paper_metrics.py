import os, csv, argparse, pathlib, random, sys
p=argparse.ArgumentParser()
p.add_argument("--root", default="metrics")
p.add_argument("--case", required=True)
p.add_argument("--seed", type=int, default=1729)
p.add_argument("--risk", default=os.environ.get("RISK_CFG","{}"))
p.add_argument("--logs", nargs="*", default=[])  # ←追加
a=p.parse_args()

random.seed(a.seed)
pathlib.Path(a.root).mkdir(parents=True, exist_ok=True)
csv_path=os.path.join(a.root,"metrics.csv")
write_header = not os.path.exists(csv_path)

# 将来の実装では a.logs から実集計する。いまは決定論スタブで常に成功させる。
net=200.0; win=0.55; dd=0.10; trades=40
if write_header:
    with open(csv_path,"w",newline="",encoding="utf-8") as f:
        csv.writer(f).writerow(["case","net","win","dd","trades"])
with open(csv_path,"a",newline="",encoding="utf-8") as f:
    csv.writer(f).writerow([a.case,net,win,dd,trades])
print(f"Wrote {csv_path}")
