import os, csv, argparse, pathlib, datetime

def parse_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def load_trades(log_files):
    rows = []
    for fp in log_files:
        if not os.path.exists(fp):
            continue
        with open(fp, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                rows.append(row)
    return rows

def sort_rows(rows):
    def key(row):
        for k in ("time_close","time_open"):
            if k in row and row[k]:
                try:
                    return datetime.datetime.fromisoformat(row[k].replace("Z","+00:00"))
                except Exception:
                    pass
        return datetime.datetime.min
    return sorted(rows, key=key)

def compute_metrics(rows, initial_equity):
    pnl_list = []
    for row in rows:
        profit = parse_float(row.get("profit_jpy", 0))
        commission = parse_float(row.get("commission_jpy", 0))
        swap = parse_float(row.get("swap_jpy", 0))
        pnl_net = profit + commission + swap
        pnl_list.append(pnl_net)

    trades = len(pnl_list)
    if trades == 0:
        return 0.0, 0.0, 0.0, 0

    win = sum(1 for x in pnl_list if x > 0) / trades

    equity = initial_equity
    peak = initial_equity
    max_dd_rate = 0.0
    total_net = 0.0
    for pnl in pnl_list:
        total_net += pnl
        equity += pnl
        if equity > peak:
            peak = equity
        if peak > 0:
            dd_rate = (peak - equity) / peak
            if dd_rate > max_dd_rate:
                max_dd_rate = dd_rate

    return total_net, win, max_dd_rate, trades

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="metrics")
    p.add_argument("--case", required=True)       # 例: 20251022_USDJPY_M15
    p.add_argument("--seed", type=int, default=1729)
    p.add_argument("--logs", nargs="+", required=True)
    p.add_argument("--initial_equity", type=float, default=float(os.environ.get("INITIAL_EQUITY", "50000")))
    args = p.parse_args()

    pathlib.Path(args.root).mkdir(parents=True, exist_ok=True)
    csv_path = os.path.join(args.root, "metrics.csv")
    write_header = not os.path.exists(csv_path)

    rows = load_trades(args.logs)
    rows = sort_rows(rows)

    net, win, dd, trades = compute_metrics(rows, args.initial_equity)

    if trades == 0:
        print("ERROR: no trades found in logs:", args.logs)
        exit(2)

    if write_header:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["case","net","win","dd","trades"])
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([args.case, f"{net:.2f}", f"{win:.4f}", f"{dd:.4f}", trades])

    print(f"Wrote {csv_path} -> case={args.case} net={net:.2f} win={win:.4f} dd={dd:.4f} trades={trades}")

if __name__ == "__main__":
    import csv
    main()
