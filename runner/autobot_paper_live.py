import os, csv, pathlib, datetime as dt, traceback, sys

OUTDIR = pathlib.Path("artifacts") / "papertrade_live"
OUTDIR.mkdir(parents=True, exist_ok=True)

def ensure_metrics(p):
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["metric","value"])
        w.writeheader()
        w.writerows([
            {"metric":"net_jpy","value":"0"},
            {"metric":"win_rate_pct","value":"0"},
            {"metric":"max_drawdown_pct","value":"0"},
            {"metric":"trades","value":"0"},
        ])

def ensure_trades(p):
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["time","side","entry","exit","pnl_jpy","reason"])
        w.writeheader()

def ensure_decisions(p):
    open(p, "w", encoding="utf-8").close()

def write_summary(lines):
    text = "\n".join(lines) + "\n"
    print(text)
    gss = os.getenv("GITHUB_STEP_SUMMARY")
    if gss:
        with open(gss, "a", encoding="utf-8") as f:
            f.write(text)

def main():
    ensure_metrics(OUTDIR / "metrics.csv")
    ensure_trades(OUTDIR / "trades.csv")
    ensure_decisions(OUTDIR / "decisions.jsonl")
    write_summary([
        "## papertrade-live (dry boot)",
        f"- time: {dt.datetime.utcnow().isoformat()}Z",
        "- gate: n/a (boot)",
        "- artifacts: metrics.csv / trades.csv / decisions.jsonl",
        "- status: OK"
    ])

if __name__ == "__main__":
    try:
        main()
        sys.exit(0)
    except Exception as e:
        err = traceback.format_exc(limit=5)
        ensure_metrics(OUTDIR / "metrics.csv")
        ensure_trades(OUTDIR / "trades.csv")
        ensure_decisions(OUTDIR / "decisions.jsonl")
        write_summary([
            "## papertrade-live (dry boot)",
            f"- time: {dt.datetime.utcnow().isoformat()}Z",
            "- gate: n/a (boot)",
            "- artifacts: metrics.csv / trades.csv / decisions.jsonl",
            f"- WARN: boot exception -> {str(e).strip()}",
            "----- traceback (trimmed) -----",
            err.splitlines()[-1] if err else ""
        ])
        sys.exit(0)
