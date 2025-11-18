import csv, sys
def load(path):
    d={}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "metric" in reader.fieldnames and "value" in reader.fieldnames:
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
                try:
                    d[key] = float(row[1])
                except Exception:
                    pass
    return d

cur = load(sys.argv[1])
base = load(sys.argv[2])
keys = sorted(set(cur) | set(base))
fails=[]
for k in keys:
    if k not in cur or k not in base:
        fails.append(f"missing metric: {k}")
        continue
    if abs(cur[k]-base[k])>1e-9:
        fails.append(f"{k}: {cur[k]} != {base[k]}")
if fails:
    print("ASSERT FAIL:"); [print(' -',m) for m in fails]; sys.exit(1)
print("ASSERT OK")
