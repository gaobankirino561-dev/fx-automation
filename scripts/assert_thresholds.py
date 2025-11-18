import csv, sys, operator as op, yaml, os, traceback

def read_metrics(path):
    d={}
    with open(path,encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if "metric" in fieldnames and "value" in fieldnames:
            for row in reader:
                key = row.get("metric")
                if not key or key == "metric":
                    continue
                try:
                    d[key] = float(row.get("value","0"))
                except Exception:
                    pass
        else:
            f.seek(0)
            for row in csv.reader(f):
                if not row:
                    continue
                key = row[0]
                if key == "metric":
                    continue
                val = row[1] if len(row) > 1 else "0"
                try:
                    d[key] = float(val)
                except Exception:
                    pass
    return d

OPS={">":op.gt, ">=":op.ge, "<":op.lt, "<=":op.le, "==":op.eq}

def check_expr(metrics, expr):
    fails=[]
    for token in [t.strip() for t in expr.split(",") if t.strip()]:
        for sym in (">=", "<=", ">", "<", "=="):
            if sym in token:
                k,val = token.split(sym,1); k=k.strip(); val=float(val.strip())
                if k not in metrics or not OPS[sym](metrics[k], val):
                    fails.append(f"{k}:{metrics.get(k,'?')} {sym} {val}")
                break
    return fails

def load_expr(key_or_expr):
    if key_or_expr in ("autobot_run","integration","demo"):
        t=yaml.safe_load(open("ci/thresholds.yaml",encoding="utf-8"))
        return t.get(key_or_expr,"")
    if os.path.isfile(key_or_expr) and key_or_expr.endswith(".yaml"):
        t=yaml.safe_load(open(key_or_expr,encoding="utf-8"))
        return t.get("autobot_run","")
    return key_or_expr

def classify_failure(exc:str, metrics_missing:bool, threshold_fail:bool):
    if metrics_missing: return "configs欠落/metrics未生成"
    if "Traceback" in exc: return "実行時例外でmetrics未生成"
    if threshold_fail: return "Gate未達（しきい値NG）"
    return "未知/要調査"

if __name__=="__main__":
    if len(sys.argv)<3:
        print("usage: assert_thresholds.py <metrics.csv> <expr|yaml_key>"); sys.exit(2)
    path, key = sys.argv[1], sys.argv[2]
    exc=""; metrics_missing=not os.path.isfile(path); threshold_fail=False
    try:
        m = read_metrics(path)
        expr = load_expr(key)
        if not expr: 
            print("No thresholds specified -> SKIP"); sys.exit(0)
        fails = check_expr(m, expr)
        if fails:
            threshold_fail=True
            print("THRESHOLD FAIL:"); [print(" -",x) for x in fails]
            sys.exit(1)
        print("THRESHOLD OK"); sys.exit(0)
    except Exception as e:
        exc="Traceback:\n"+traceback.format_exc()
        print(exc); sys.exit(2)
    finally:
        # 失敗時の原因カテゴリを標準出力に必ず出す
        if metrics_missing or threshold_fail or exc:
            print("CLASSIFY:", classify_failure(exc, metrics_missing, threshold_fail))
