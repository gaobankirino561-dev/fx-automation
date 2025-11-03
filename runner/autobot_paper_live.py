import os, csv, pathlib, datetime as dt

OUTDIR = pathlib.Path("artifacts") / "papertrade_live"
OUTDIR.mkdir(parents=True, exist_ok=True)

halt = (os.getenv("PAPERTRADE_HALT", "false").lower() == "true")

metrics_path = OUTDIR / "metrics.csv"
if not metrics_path.exists() or metrics_path.stat().st_size == 0:
    with open(metrics_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["metric","value"])
        w.writeheader()
        w.writerows([
            {"metric":"net_jpy","value":"0"},
            {"metric":"win_rate_pct","value":"0"},
            {"metric":"max_drawdown_pct","value":"0"},
            {"metric":"trades","value":"0"},
        ])

trades_path = OUTDIR / "trades.csv"
if not trades_path.exists() or trades_path.stat().st_size == 0:
    with open(trades_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["time","side","entry","exit","pnl_jpy","reason"])
        w.writeheader()

dec_path = OUTDIR / "decisions.jsonl"
if not dec_path.exists():
    open(dec_path, "w", encoding="utf-8").close()

summary = []
summary.append("## papertrade-live (dry boot)")
summary.append(f"- time: {dt.datetime.utcnow().isoformat()}Z")
summary.append(f"- halt: {halt}")
summary.append("- gate: n/a (boot)")
summary.append("- artifacts: metrics.csv / trades.csv / decisions.jsonl")
text = "\n".join(summary) + "\n"
print(text)

gss = os.getenv("GITHUB_STEP_SUMMARY")
if gss:
    with open(gss, "a", encoding="utf-8") as f:
        f.write(text)
