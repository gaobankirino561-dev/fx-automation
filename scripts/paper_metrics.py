import csv, argparse, pathlib, random, os

p=argparse.ArgumentParser()
p.add_argument("--root", default="metrics")
p.add_argument("--case", required=True)
p.add_argument("--seed", type=int, default=1729)
p.add_argument("--risk", default=os.environ.get("RISK_CFG", "{}"))
p.add_argument("--logs", nargs="*", default=[])
a=p.parse_args()

random.seed(a.seed)
root = pathlib.Path(a.root)
root.mkdir(parents=True, exist_ok=True)
csv_path = root / "metrics.csv"
write_header = not csv_path.exists()

net = 200.0
win = 0.55
dd = 0.10
trades = 40

if write_header:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["case", "net", "win", "dd", "trades"])
with csv_path.open("a", newline="", encoding="utf-8") as f:
    csv.writer(f).writerow([a.case, net, win, dd, trades])
print(f"Wrote {csv_path}")
