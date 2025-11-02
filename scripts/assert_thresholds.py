import csv, sys, operator as op

def read_metrics(path):
    d={}
    with open(path,encoding="utf-8") as f:
        for k,v in csv.reader(f):
            if k=="metric": continue
            try: d[k]=float(v)
            except: pass
    return d

OPS={">":op.gt, ">=":op.ge, "<":op.lt, "<=":op.le, "==":op.eq}

def check_thresholds(metrics, expr):
    fails=[]
    for token in [t.strip() for t in expr.split(",") if t.strip()]:
        for sym in (">=", "<=", ">", "<", "=="):
            if sym in token:
                k,val = token.split(sym,1); k=k.strip(); val=float(val.strip())
                if k not in metrics or not OPS[sym](metrics[k], val):
                    fails.append(f"{k}:{metrics.get(k,'?')} {sym} {val}")
                break
    return fails

if __name__=="__main__":
    if len(sys.argv)<3:
        print("usage: assert_thresholds.py <metrics.csv> <expr>"); sys.exit(2)
    m=read_metrics(sys.argv[1]); expr=sys.argv[2]
    fails=check_thresholds(m, expr)
    if fails:
        print("THRESHOLD FAIL:"); [print(" -",x) for x in fails]; sys.exit(1)
    print("THRESHOLD OK")
