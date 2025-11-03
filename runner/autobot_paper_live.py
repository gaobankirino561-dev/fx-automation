import os, json, csv, pathlib, datetime as dt
OUTDIR = pathlib.Path("artifacts/papertrade_live"); OUTDIR.mkdir(parents=True, exist_ok=True)
halt = (os.getenv("PAPERTRADE_HALT", "false").lower() == "true")
metrics = [
  {"metric":"net_jpy","value":"0"},
  {"metric":"win_rate_pct","value":"0"},
  {"metric":"max_drawdown_pct","value":"0"},
  {"metric":"trades","value":"0"},
]
with open(OUTDIR/"metrics.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=["metric","value"]); w.writeheader(); w.writerows(metrics)
with open(OUTDIR/"trades.csv","w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=["time","side","entry","exit","pnl_jpy","reason"]); w.writeheader()
open(OUTDIR/"decisions.jsonl","w",encoding="utf-8").close()
summary = [
  "## papertrade-live (dry boot)",
  f"- time: {dt.datetime.utcnow().isoformat()}Z",
  f"- halt: {halt}",
  "- gate: n/a (boot)",
  "- artifacts: metrics.csv / trades.csv / decisions.jsonl",
]
text = "\n".join(summary) + "\n"
print(text)
gss = os.getenv("GITHUB_STEP_SUMMARY")
if gss:
    with open(gss,"a",encoding="utf-8") as f: f.write(text)
