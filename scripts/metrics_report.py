import csv, argparse, pathlib

p = argparse.ArgumentParser()
p.add_argument("--csv", default="metrics/metrics.csv")
p.add_argument("--out", default="metrics/report.md")
p.add_argument("--min_net", type=float, default=0.0)
p.add_argument("--min_win", type=float, default=0.45)
p.add_argument("--max_dd", type=float, default=0.20)
p.add_argument("--min_trades", type=int, default=30)
a = p.parse_args()

pathlib.Path("metrics").mkdir(parents=True, exist_ok=True)
rows = []
with open(a.csv, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(
            dict(
                case=row["case"],
                net=float(row["net"]),
                win=float(row["win"]),
                dd=float(row["dd"]),
                trades=int(row["trades"]),
            )
        )

def passes(z):
    return (
        z["net"] > a.min_net
        and z["win"] >= a.min_win
        and z["dd"] <= a.max_dd
        and z["trades"] >= a.min_trades
    )

pass_rate = (sum(1 for z in rows if passes(z)) / len(rows)) if rows else 0.0
with open(a.out, "w", encoding="utf-8") as f:
    f.write("# Gate Report\n\n")
    f.write(
        f"Thresholds: net>{a.min_net}, win>={a.min_win}, dd<={a.max_dd}, trades>={a.min_trades}\n\n"
    )
    f.write("| case | net | win | dd | trades | verdict |\n|---|---:|---:|---:|---:|---|\n")
    for row in rows:
        verdict = "PASS" if passes(row) else "FAIL"
        f.write(
            f"| {row['case']} | {row['net']:.2f} | {row['win']:.3f} | {row['dd']:.3f} | {row['trades']} | {verdict} |\n"
        )
    f.write(f"\n**pass_rate = {pass_rate:.2%}**\n")
print(f"Wrote {a.out}")
