import csv
import os
import subprocess

CSV_IN = os.getenv("OHLC_CSV", "data/ohlc.csv")
W = int(os.getenv("WF_SPLITS", "6"))
SEL = {
    "OB_KTP": os.getenv("OB_KTP", "2.0"),
    "OB_KSL": os.getenv("OB_KSL", "1.2"),
    "OB_TREND_SMA": os.getenv("OB_TREND_SMA", "100"),
    "OB_RSI_UP": os.getenv("OB_RSI_UP", "60"),
    "OB_RSI_DN": os.getenv("OB_RSI_DN", "40"),
}
BASE = {
    "OB_EQ": os.getenv("OB_EQ", "10000"),
    "OB_RISK": os.getenv("OB_RISK", "0.003"),
    "OB_MIN_TP": os.getenv("OB_MIN_TP", "6"),
    "OB_MIN_SL": os.getenv("OB_MIN_SL", "6"),
    "OB_SPREAD_PIPS": os.getenv("OB_SPREAD_PIPS", "0.2"),
    "OB_FEE_PIPS": os.getenv("OB_FEE_PIPS", "0"),
    "OB_MAXDD_STOP": os.getenv("OB_MAXDD_STOP", "20"),
}


def pick(output: str, tag: str, end: str = " ") -> str:
    seg = output.split(tag, 1)[1]
    return seg.split(end, 1)[0]


with open(CSV_IN, encoding="utf-8") as f:
    lines = f.read().splitlines()

header, rows = lines[0], lines[1:]
n = len(rows)
if n == 0:
    raise ValueError("Input CSV has no data rows")
size = max(1, n // W)
splits = [(i * size, (i + 1) * size if i < W - 1 else n) for i in range(W)]

rows_out = []
for idx, (start, end) in enumerate(splits, 1):
    seg = rows[start:end]
    tmp_csv = f"wf_tmp_{idx}.csv"
    with open(tmp_csv, "w", newline="", encoding="utf-8") as f:
        f.write(header + "\n" + "\n".join(seg))
    env = os.environ.copy()
    env.update(BASE)
    env.update(SEL)
    env["OHLC_CSV"] = tmp_csv
    env["OB_OUTCSV"] = f"results/wf_equity_sel_{idx}.csv"
    out = subprocess.check_output(["python", "ohlc_backtest_atr.py"], env=env, text=True)
    trades = int(pick(out, "trades:"))
    pf = float(pick(out, "PF:"))
    ret = float(pick(out, "(", "%"))
    dd = float(pick(out, "maxDD%:"))
    rows_out.append((idx, trades, pf, ret, dd))

avg = lambda xs: sum(xs) / len(xs) if xs else 0.0  # noqa: E731
pf_avg = avg([r[2] for r in rows_out])
ret_avg = avg([r[3] for r in rows_out])
dd_avg = avg([r[4] for r in rows_out])
tr_total = sum(r[1] for r in rows_out)

print("seg trades   PF  return%  maxDD%")
for i, trades, pf, ret, dd in rows_out:
    print(f"{i:>3} {trades:>6} {pf:5.2f} {ret:8.2f} {dd:7.2f}")
print("\n== WF summary ==")
print(f"PF(avg)={pf_avg:.2f}  return%(avg)={ret_avg:.2f}  maxDD%(avg)={dd_avg:.2f}  trades(total)={tr_total}")

with open("wf_summary.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["seg", "trades", "PF", "return%", "maxDD%"])
    for row in rows_out:
        writer.writerow([row[0], row[1], f"{row[2]:.2f}", f"{row[3]:.2f}", f"{row[4]:.2f}"])
    writer.writerow([])
    writer.writerow(["PF(avg)", f"{pf_avg:.2f}", "return%(avg)", f"{ret_avg:.2f}", "maxDD%(avg)", f"{dd_avg:.2f}", "trades(total)", tr_total])
