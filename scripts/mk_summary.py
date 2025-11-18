import csv, sys

def load(path):
    d={}
    with open(path,encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "metric" in reader.fieldnames and "value" in reader.fieldnames:
            for row in reader:
                key = row.get("metric")
                if not key or key == "metric":
                    continue
                val = row.get("value","0")
                try: d[key]=float(val)
                except: d[key]=val
        else:
            f.seek(0)
            for row in csv.reader(f):
                if not row:
                    continue
                key=row[0]
                if key=="metric": continue
                val=row[1] if len(row)>1 else "0"
                try: d[key]=float(val)
                except: d[key]=val
    return d

if __name__=="__main__":
    if len(sys.argv)<2:
        print("usage: mk_summary.py <metrics.csv> [title]"); sys.exit(2)
    m=load(sys.argv[1]); title=sys.argv[2] if len(sys.argv)>=3 else "Papertrade Run Summary"
    print(f"## {title}\n")
    print(f"- net_jpy: **{m.get('net_jpy',0)}**")
    print(f"- win_rate_pct: **{m.get('win_rate_pct',0)}%**")
    print(f"- max_drawdown_pct: **{m.get('max_drawdown_pct',0)}%**")
    print(f"- trades: **{m.get('trades',0)}**")
