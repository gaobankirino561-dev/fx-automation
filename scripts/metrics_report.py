import csv, argparse, pathlib

p=argparse.ArgumentParser()
p.add_argument("--csv", default="metrics/metrics.csv")
p.add_argument("--out", default="metrics/report.md")
p.add_argument("--min_net", type=float, default=0.0)
p.add_argument("--min_win", type=float, default=0.45)
p.add_argument("--max_dd",  type=float, default=0.20)
p.add_argument("--min_trades", type=int, default=30)
a=p.parse_args()

pathlib.Path("metrics").mkdir(parents=True, exist_ok=True)
rows=[]
with open(a.csv, newline="", encoding="utf-8") as f:
    r=csv.DictReader(f)
    for x in r:
        rec = dict(case=x["case"],
                   net=float(x["net"]),
                   win=float(x["win"]),
                   dd=float(x["dd"]),
                   trades=int(x["trades"]))
        rec["pass"] = "PASS" if (rec["net"]>a.min_net and rec["win"]>=a.min_win and
                                 rec["dd"]<=a.max_dd and rec["trades"]>=a.min_trades) else "FAIL"
        rows.append(rec)

pass_rate = (sum(1 for z in rows if z["pass"]=="PASS")/len(rows)) if rows else 0.0
with open(a.out,"w",encoding="utf-8") as f:
    f.write("# Gate Report\n\n")
    f.write(f"Thresholds: net>{a.min_net}, win>={a.min_win}, dd<={a.max_dd}, trades>={a.min_trades}\n\n")
    f.write("| case | net | win | dd | trades | verdict |\n|---|---:|---:|---:|---:|---|\n")
    for r in rows:
        f.write(f"| {r['case']} | {r['net']:.2f} | {r['win']:.3f} | {r['dd']:.3f} | {r['trades']} | {r['pass']} |\n")
    f.write(f"\n**pass_rate = {pass_rate:.2%}**\n")
print(f"Wrote {a.out}")
