import argparse, csv, sys, os, json
p=argparse.ArgumentParser()
p.add_argument("--root", default="metrics")
p.add_argument("--min_net", type=float, default=0.0)
p.add_argument("--min_win", type=float, default=0.45)
p.add_argument("--max_dd",  type=float, default=0.20)
p.add_argument("--min_trades", type=int, default=30)
p.add_argument("--min_pass_rate", type=float, default=1.0)
a=p.parse_args()

csv_path=os.path.join(a.root,"metrics.csv")
rows=[]
with open(csv_path, newline="", encoding="utf-8") as f:
    for i,r in enumerate(csv.DictReader(f)):
        rows.append({
            "case": r["case"],
            "net": float(r["net"]),
            "win": float(r["win"]),
            "dd":  float(r["dd"]),
            "trades": int(r["trades"]),
        })

def ok(m): 
    return (m["net"]>a.min_net and m["win"]>=a.min_win and 
            m["dd"]<=a.max_dd and m["trades"]>=a.min_trades)

passed=sum(1 for r in rows if ok(r))
rate=passed/len(rows) if rows else 0.0
print(json.dumps({"total":len(rows),"passed":passed,"pass_rate":rate}, ensure_ascii=False))
for r in rows:
    mark="OK" if ok(r) else "NG"
    print(f'{mark}\t{r["case"]}\tnet={r["net"]}\twin={r["win"]}\tdd={r["dd"]}\ttrades={r["trades"]}')

if rate < a.min_pass_rate: 
    sys.exit(1)
