import os, csv, argparse, pathlib, datetime, glob

def parse_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def parse_case_date(case):
    token = case.split("_", 1)[0]
    try:
        return datetime.datetime.strptime(token, "%Y%m%d").date()
    except Exception:
        return None

def parse_filename_date(filename):
    token = filename.split("_", 1)[0]
    if len(token) != 8 or not token.isdigit():
        return None
    try:
        return datetime.datetime.strptime(token, "%Y%m%d").date()
    except Exception:
        return None

def derive_suffix(case, fallback_path):
    parts = case.split("_", 1)
    if len(parts) == 2 and parts[1]:
        return parts[1] + ".csv"
    name = os.path.basename(fallback_path)
    idx = name.find("_")
    if idx == -1:
        return name
    return name[idx + 1 :]

def read_log_rows(fp):
    if not os.path.exists(fp):
        return []
    with open(fp, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def find_recent_logs(base_path, case, lookback_days):
    directory = os.path.dirname(base_path) or "."
    suffix = derive_suffix(case, base_path)
    pattern = os.path.join(directory, f"*_{suffix}")
    candidates = sorted(glob.glob(pattern))
    case_date = parse_case_date(case)

    eligible = []
    for candidate in reversed(candidates):
        name = os.path.basename(candidate)
        file_date = parse_filename_date(name)
        if case_date and file_date:
            delta = (case_date - file_date).days
            if delta < 0:
                continue
            if lookback_days >= 0 and delta > lookback_days:
                continue
        eligible.append(candidate)
    return eligible

def load_trades(log_files):
    rows = []
    for fp in log_files:
        rows.extend(read_log_rows(fp))
    return rows

def load_trades_with_fallback(log_files, case, lookback_days, min_trades):
    rows = []
    used_files = []
    for fp in log_files:
        current_rows = read_log_rows(fp)
        if current_rows:
            rows.extend(current_rows)
            used_files.append(fp)

    total_trades = len(rows)
    target = max(1, min_trades)
    if total_trades >= target:
        return rows, used_files

    for fp in log_files:
        for candidate in find_recent_logs(fp, case, lookback_days):
            if candidate in used_files:
                continue
            candidate_rows = read_log_rows(candidate)
            if not candidate_rows:
                continue
            rows.extend(candidate_rows)
            used_files.append(candidate)
            total_trades += len(candidate_rows)
            if total_trades >= target:
                return rows, used_files

    return rows, used_files

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
    p.add_argument("--lookback_days", type=int, default=7)
    p.add_argument("--min_trades", type=int, default=30)
    args = p.parse_args()

    pathlib.Path(args.root).mkdir(parents=True, exist_ok=True)
    csv_path = os.path.join(args.root, "metrics.csv")
    write_header = not os.path.exists(csv_path)

    rows, used_files = load_trades_with_fallback(args.logs, args.case, args.lookback_days, args.min_trades)
    rows = sort_rows(rows)

    net, win, dd, trades = compute_metrics(rows, args.initial_equity)

    if trades == 0:
        print("ERROR: no trades found in logs or recent history:", args.logs)
        exit(2)

    if write_header:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["case","net","win","dd","trades"])
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([args.case, f"{net:.2f}", f"{win:.4f}", f"{dd:.4f}", trades])

    print(f"Wrote {csv_path} -> case={args.case} net={net:.2f} win={win:.4f} dd={dd:.4f} trades={trades}")
    if used_files:
        print("Used log files:", ", ".join(used_files))

if __name__ == "__main__":
    import csv
    main()
