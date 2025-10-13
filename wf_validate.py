from __future__ import annotations

import csv
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

CSV_IN = Path(os.getenv("OHLC_CSV", "data/ohlc.csv"))
SPLITS = int(os.getenv("WF_SPLITS", "6"))
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_PATH = RESULTS_DIR / "wf_summary.csv"


def _load_rows(path: Path) -> List[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"time", "open", "high", "low", "close"}
        if reader.fieldnames is None or required - set(reader.fieldnames):
            raise ValueError("CSV must contain columns: time, open, high, low, close")
        return list(reader)


def _write_chunk(rows: List[dict[str, str]], path: Path) -> None:
    if not rows:
        raise ValueError("Chunk has no rows")
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["time", "open", "high", "low", "close"])
        writer.writeheader()
        writer.writerows(rows)


def _pick(output: str, tag: str, end: str = " ") -> str:
    segment = output.split(tag, 1)[1]
    return segment.split(end, 1)[0]


def _run_chunk(chunk_csv: Path, equity_csv: Path) -> Tuple[int, float, float, float]:
    env = os.environ.copy()
    env["OHLC_CSV"] = str(chunk_csv)
    env["OB_OUTCSV"] = str(equity_csv)
    out = subprocess.check_output(
        [sys.executable, "ohlc_backtest_atr.py"],
        env=env,
        text=True,
        stderr=subprocess.STDOUT,
    )
    trades = int(_pick(out, "trades:"))
    pf = float(_pick(out, "PF:"))
    ret = float(_pick(out, "(", "%"))
    maxdd = float(_pick(out, "maxDD%:"))
    return trades, pf, ret, maxdd


def main() -> None:
    rows = _load_rows(CSV_IN)
    n = len(rows)
    if SPLITS < 1 or SPLITS > n:
        raise ValueError("WF_SPLITS must be between 1 and the number of rows")

    summary_rows: List[Tuple[int, float, float, float]] = []

    start = 0
    for idx in range(1, SPLITS + 1):
        end = n * idx // SPLITS
        chunk_rows = rows[start:end]
        if not chunk_rows:
            continue
        chunk_csv = RESULTS_DIR / f"wf_chunk_{idx}.csv"
        equity_csv = RESULTS_DIR / f"wf_equity_{idx}.csv"
        _write_chunk(chunk_rows, chunk_csv)
        metrics = _run_chunk(chunk_csv, equity_csv)
        summary_rows.append(metrics)
        trades, pf, ret, maxdd = metrics
        print(f"split {idx}/{SPLITS}: trades={trades} PF={pf:.2f} return={ret:.2f}% maxDD={maxdd:.2f}% -> {chunk_csv.name}")
        start = end

    if not summary_rows:
        print("No splits processed")
        return

    with SUMMARY_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["split", "trades", "PF", "return%", "maxDD%", "chunk_csv", "equity_csv"])
        for idx, (trades, pf, ret, maxdd) in enumerate(summary_rows, start=1):
            writer.writerow([
                idx,
                trades,
                f"{pf:.2f}",
                f"{ret:.2f}",
                f"{maxdd:.2f}",
                f"wf_chunk_{idx}.csv",
                f"wf_equity_{idx}.csv",
            ])
    avg_pf = sum(m[1] for m in summary_rows) / len(summary_rows)
    avg_ret = sum(m[2] for m in summary_rows) / len(summary_rows)
    print(f"Average PF={avg_pf:.2f} return={avg_ret:.2f}% ({len(summary_rows)} splits)")
    print(f"Summary saved to {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
