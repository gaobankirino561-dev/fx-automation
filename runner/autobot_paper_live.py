import os, csv, pathlib, datetime as dt
OUTDIR = pathlib.Path("artifacts") / "papertrade_live"
OUTDIR.mkdir(parents=True, exist_ok=True)
halt = (os.getenv("PAPERTRADE_HALT","false").lower()=="true")
def ensure_metrics(p):
    if (not p.exists()) or p.stat().st_size==0:
        with open(p,"w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=["metric","value"]); w.writeheader()
            w.writerows([{"metric":"net_jpy","value":"0"},
                         {"metric":"win_rate_pct","value":"0"},
                         {"metric":"max_drawdown_pct","value":"0"},
                         {"metric":"trades","value":"0"}])
def ensure_trades(p):
    if (not p.exists()) or p.stat().st_size==0:
        with open(p,"w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=["time","side","entry","exit","pnl_jpy","reason"]); w.writeheader()
def ensure_decisions(p):
    if not p.exists(): open(p,"w",encoding="utf-8").close()
ensure_metrics(OUTDIR/"metrics.csv"); ensure_trades(OUTDIR/"trades.csv"); ensure_decisions(OUTDIR/"decisions.jsonl")
text="\n".join(["## papertrade-live (dry boot)",
                f"- time: {dt.datetime.utcnow().isoformat()}Z",
                f"- halt: {halt}",
                "- gate: n/a (boot)",
                "- artifacts: metrics.csv / trades.csv / decisions.jsonl"])"\n"
print(text)
gss=os.getenv("GITHUB_STEP_SUMMARY")
if gss:
    with open(gss,"a",encoding="utf-8") as f: f.write(text)
