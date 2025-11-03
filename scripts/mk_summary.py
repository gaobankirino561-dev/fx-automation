import csv, sys

def load(path):
    d={}
    with open(path,encoding="utf-8") as f:
        for k,v in csv.reader(f):
            if k=="metric": continue
            try: d[k]=float(v)
            except: d[k]=v
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
