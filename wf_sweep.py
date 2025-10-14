from __future__ import annotations

import csv
import itertools
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

CSV_IN = Path(os.getenv("OHLC_CSV", "data/ohlc.csv"))
WF_SPLITS = int(os.getenv("WF_SPLITS", "4"))
RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_CSV = RESULTS_DIR / "wf_sweep_summary.csv"

BASE = {
    "OB_EQ": os.getenv("OB_EQ", "10000"),
    "OB_RISK": os.getenv("OB_RISK", "0.003"),
    "OB_MIN_TP": os.getenv("OB_MIN_TP", "6"),
    "OB_MIN_SL": os.getenv("OB_MIN_SL", "6"),
    "OB_SPREAD_PIPS": os.getenv("OB_SPREAD_PIPS", "0.2"),
    "OB_FEE_PIPS": os.getenv("OB_FEE_PIPS", "0"),
    "OB_MAXDD_STOP": os.getenv("OB_MAXDD_STOP", "20"),
}

# broaden search grid for rough sweep
KTP = ["1.0", "1.2", "1.4", "1.6", "1.8", "2.0"]
KSL = ["0.8", "1.0", "1.2", "1.4"]
TREND = ["0", "50", "100", "150", "200"]
RSI = [("52", "48"), ("55", "45"), ("58", "42"), ("60", "40"), ("65", "35")]


def pick(output: str, tag: str, end: str = " ") -> str:
    segment = output.split(tag, 1)[1]
    return segment.split(end, 1)[0]


def chunk_rows(rows: List[str], splits: int) -> Iterable[Tuple[int, List[str]]]:
    n = len(rows)
    size = max(1, n // splits)
    for idx in range(splits):
        start = idx * size
        end = n if idx == splits - 1 else min(n, (idx + 1) * size)
        chunk = rows[start:end]
        if chunk:
            yield idx + 1, chunk


def write_chunk(header: str, chunk: List[str], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        fh.write(header + "\n")
        fh.write("\n".join(chunk))


def run_combo(index: int, params: dict[str, str], header: str, data_rows: List[str]) -> Tuple[float, float, float, int]:
    env_base = os.environ.copy()
    env_base.update(BASE)
    env_base.update(params)

    pf_values: List[float] = []
    ret_values: List[float] = []
    maxdd_values: List[float] = []
    total_trades = 0

    for split_idx, chunk in chunk_rows(data_rows, WF_SPLITS):
        chunk_csv = RESULTS_DIR / f"wf_sweep_chunk_{index}_{split_idx}.csv"
        equity_csv = RESULTS_DIR / f"wf_sweep_equity_{index}_{split_idx}.csv"
        write_chunk(header, chunk, chunk_csv)

        env = env_base.copy()
        env["OHLC_CSV"] = str(chunk_csv)
        env["OB_OUTCSV"] = str(equity_csv)

        output = subprocess.check_output(
            [sys.executable, "ohlc_backtest_atr.py"],
            env=env,
            text=True,
            stderr=subprocess.STDOUT,
        )
        trades = int(pick(output, "trades:"))
        pf = float(pick(output, "PF:"))
        ret = float(pick(output, "(", "%"))
        maxdd = float(pick(output, "maxDD%:"))

        total_trades += trades
        pf_values.append(pf)
        ret_values.append(ret)
        maxdd_values.append(maxdd)

    if not pf_values:
        return 0.0, 0.0, 0.0, 0

    pf_avg = sum(pf_values) / len(pf_values)
    ret_avg = sum(ret_values) / len(ret_values)
    maxdd_avg = sum(maxdd_values) / len(maxdd_values)
    return pf_avg, ret_avg, maxdd_avg, total_trades


def main() -> None:
    if not CSV_IN.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_IN}")
    with CSV_IN.open("r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    if not lines:
        raise ValueError("CSV has no data")
    header, data_rows = lines[0], lines[1:]

    results = []
    combos = list(itertools.product(KTP, KSL, TREND, RSI))
    for idx, (ktp, ksl, trend, (r_up, r_dn)) in enumerate(combos, start=1):
        params = {
            "OB_KTP": ktp,
            "OB_KSL": ksl,
            "OB_TREND_SMA": trend,
            "OB_RSI_UP": r_up,
            "OB_RSI_DN": r_dn,
        }
        pf_avg, ret_avg, maxdd_avg, trades_total = run_combo(idx, params, header, data_rows)
        results.append((pf_avg, ret_avg, maxdd_avg, trades_total, params))

    results.sort(key=lambda x: (-x[0], -x[1], x[2], -x[3]))

    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["rank", "PF(avg)", "return%(avg)", "maxDD%(avg)", "trades(total)", "KTP", "KSL", "TREND", "RSI_UP", "RSI_DN"])
        for rank, (pf_avg, ret_avg, maxdd_avg, trades_total, params) in enumerate(results, start=1):
            writer.writerow([
                rank,
                f"{pf_avg:.2f}",
                f"{ret_avg:.2f}",
                f"{maxdd_avg:.2f}",
                trades_total,
                params["OB_KTP"],
                params["OB_KSL"],
                params["OB_TREND_SMA"],
                params["OB_RSI_UP"],
                params["OB_RSI_DN"],
            ])

    print("rank PF(avg) return%(avg) maxDD%(avg) trades params")
    for rank, (pf_avg, ret_avg, maxdd_avg, trades_total, params) in enumerate(results, start=1):
        print(f"{rank:4d} {pf_avg:7.2f} {ret_avg:10.2f} {maxdd_avg:10.2f} {trades_total:6d} {params}")
    print(f"Summary saved to {SUMMARY_CSV}")


if __name__ == "__main__":
    main()
