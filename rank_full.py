from pathlib import Path
import csv
import os
import subprocess

BASE = {
    "OHLC_CSV": os.getenv("OHLC_CSV", "data\\ohlc.csv"),
    "OB_EQ": "10000",
    "OB_RISK": "0.003",
    "OB_SPREAD_PIPS": "0.2",
    "OB_FEE_PIPS": "0",
    "OB_MIN_TP": "6",
    "OB_MIN_SL": "6",
}

OB_MAXDD_STOP = os.getenv("OB_MAXDD_STOP", "20")

CANDS = [
    {"KTP": "1.6", "KSL": "1.0", "TREND": "50", "RSI_UP": "55", "RSI_DN": "45"},
    {"KTP": "2.0", "KSL": "1.2", "TREND": "100", "RSI_UP": "60", "RSI_DN": "40"},
    {"KTP": "1.2", "KSL": "1.0", "TREND": "0", "RSI_UP": "55", "RSI_DN": "45"},
]

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = RESULTS_DIR / "atr_rank.csv"
SUMMARY_CSV = Path("runs_summary.csv")


def run_one(idx: int, cand: dict[str, str]):
    env = os.environ.copy()
    env.update(BASE)
    env["OB_KTP"] = cand["KTP"]
    env["OB_KSL"] = cand["KSL"]
    env["OB_TREND_SMA"] = cand["TREND"]
    env["OB_RSI_UP"] = cand["RSI_UP"]
    env["OB_RSI_DN"] = cand["RSI_DN"]
    env["OB_MAXDD_STOP"] = OB_MAXDD_STOP
    equity_csv = RESULTS_DIR / f"equity_full_{idx}.csv"
    env["OB_OUTCSV"] = str(equity_csv)
    out = subprocess.check_output(["python", "ohlc_backtest_atr.py"], env=env, text=True, stderr=subprocess.STDOUT)

    def pick(tag: str, end: str = " ") -> str:
        segment = out.split(tag, 1)[1]
        return segment.split(end, 1)[0]

    trades = int(pick("trades:"))
    pf = float(pick("PF:"))
    ret = float(pick("(", "%"))
    maxdd = float(pick("maxDD%:"))
    win_rate = float(pick("win_rate:", "%"))
    net_pips = float(pick("net_pips:"))
    final_eq = float(pick("equity_final:"))
    return trades, pf, ret, maxdd, win_rate, net_pips, final_eq, cand, str(equity_csv)


rows = []
for i, cand in enumerate(CANDS, start=1):
    rows.append(run_one(i, cand))

rows.sort(key=lambda x: (-x[1], -x[2], x[3], -x[0]))

with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["rank","KTP","KSL","TREND","RSI_UP","RSI_DN","Trades","Win%","PF","Return%","MaxDD%","NetPips","FinalEq","EquityCSV"])
    for rank, (trades, pf, ret, maxdd, win_rate, net_pips, final_eq, cand, equity_csv) in enumerate(rows, start=1):
        writer.writerow([
            rank,
            cand["KTP"],
            cand["KSL"],
            cand["TREND"],
            cand["RSI_UP"],
            cand["RSI_DN"],
            trades,
            f"{win_rate:.2f}",
            f"{pf:.2f}",
            f"{ret:.2f}",
            f"{maxdd:.2f}",
            f"{net_pips:.2f}",
            f"{final_eq:.2f}",
            equity_csv,
        ])

with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["rank","pf","return%","maxDD%","trades","file","params"])
    for rank, (trades, pf, ret, maxdd, _, _, _, cand, equity_csv) in enumerate(rows, start=1):
        writer.writerow([
            rank,
            f"{pf:.2f}",
            f"{ret:.2f}",
            f"{maxdd:.2f}",
            trades,
            equity_csv,
            cand,
        ])

print("rank pf  return% maxDD% trades file params")
for rank, (trades, pf, ret, maxdd, _, _, _, cand, equity_csv) in enumerate(rows, start=1):
    print(f"{rank:>4} {pf:4.2f} {ret:7.2f} {maxdd:6.2f} {trades:6} {equity_csv} {cand}")

print(f"Ranking saved to {OUT_CSV}")
