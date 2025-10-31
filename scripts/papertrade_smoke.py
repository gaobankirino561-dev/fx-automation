import csv, os, random, yaml

CONF_PATH = "papertrade/config.yaml"
OUT_DIR = "artifacts/papertrade_smoke"
OUT_CSV = os.path.join(OUT_DIR, "metrics.csv")
os.makedirs(OUT_DIR, exist_ok=True)

with open(CONF_PATH, "r", encoding="utf-8") as f:
    conf = yaml.safe_load(f)

seed = int(conf.get("seed", 1729))
random.seed(seed)

# 決定論固定（将来は実ロジックに置換）
net_jpy = 1200
win_rate = 55.0
max_dd_pct = 12.5
trades = 40

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["metric","value"])
    w.writerow(["net_jpy", net_jpy])
    w.writerow(["win_rate_pct", win_rate])
    w.writerow(["max_drawdown_pct", max_dd_pct])
    w.writerow(["trades", trades])

print(f"Wrote {OUT_CSV}")
