import csv, sys, operator as op, yaml, os

def read_metrics(path):
    d={}
    with open(path,encoding="utf-8") as f:
        for k,v in csv.reader(f):
            if k=="metric": continue
            try: d[k]=float(v)
            except: pass
    return d

OPS={">":op.gt, ">=":op.ge, "<":op.lt, "<=":op.le, "==":op.eq}

def check_expr(metrics, expr):
    fails=[]
    for token in [t.strip() for t in expr.split(",") if t.strip()]:
        for sym in (">=", "<=", ">", "<", "=="):
            if sym in token:
                k,val = token.split(sym,1)
                k=k.strip(); val=float(val.strip())
                if k not in metrics or not OPS[sym](metrics[k], val):
                    fails.append(f"{k}:{metrics.get(k,'?')} {sym} {val}")
                break
    return fails

if __name__=="__main__":
    if len(sys.argv)<2:
        print("usage: assert_thresholds.py <metrics.csv> [expr|yaml_key]"); sys.exit(2)
    mpath = sys.argv[1]; key_or_expr = (sys.argv[2] if len(sys.argv)>=3 else "")
    m = read_metrics(mpath)
    expr = key_or_expr
    if key_or_expr and key_or_expr.endswith(".yaml"):
        t = yaml.safe_load(open(key_or_expr, encoding="utf-8"))
        expr = t.get("autobot_run", "")
    elif key_or_expr and key_or_expr in ("autobot_run","integration","demo"):
        t = yaml.safe_load(open("ci/thresholds.yaml", encoding="utf-8"))
        expr = t.get(key_or_expr, "")
    if not expr:
        print("No thresholds specified -> SKIP"); sys.exit(0)
    fails = check_expr(m, expr)
    if fails:
        print("THRESHOLD FAIL:"); [print(" -",x) for x in fails]; sys.exit(1)
    print("THRESHOLD OK")
