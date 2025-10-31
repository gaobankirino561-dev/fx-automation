import csv, sys
def load(path):
    d={}
    with open(path, encoding="utf-8") as f:
        for k,v in csv.reader(f):
            if k=="metric": continue
            d[k]=float(v)
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
