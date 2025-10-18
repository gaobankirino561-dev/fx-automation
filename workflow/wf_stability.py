#!/usr/bin/env python3
"""
Automate the 40/60 walk-forward stability re-validation workflow.

Steps:
1. Load candidate metadata produced by analysis/select_candidates.py.
2. For each candidate, run wf_validate.py for the requested WF_SPLITS values.
3. Collect raw metrics (PF/return/maxDD/trades) and emit aggregated summaries.
4. Evaluate strict final criteria and persist audit artefacts (CSV/JSON/log).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
META_GLOB = "select_candidates_*.json"
STRICT_CRITERIA_DEFAULT = {
    "pf_min": 1.05,
    "ret_min": 0.0,
    "dd_max": 20.0,
    "pf_drift_min": -0.10,
}


class StabilityError(Exception):
    """Raised when the stability workflow cannot proceed."""


@dataclass
class Candidate:
    ktp: str
    ksl: str
    trend: str
    rsi: str
    pf_avg_20_30: float
    ret_avg_20_30: float
    maxdd_20_30: float
    trades_20_30: float
    selected_level: Optional[str] = None


@dataclass
class RunResult:
    candidate: Candidate
    split: str
    trades: float
    pf: float
    ret: float
    maxdd: float


def _latest_meta() -> Path:
    matches = sorted(RESULTS_DIR.glob(META_GLOB))
    if not matches:
        raise StabilityError(f"No candidate metadata JSON found (pattern: {META_GLOB}).")
    return matches[-1]


def _load_candidates(meta_path: Path) -> Tuple[List[Candidate], Dict[str, object]]:
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    selected = payload.get("selected") or []
    if not selected:
        raise StabilityError(f"No candidates present in metadata: {meta_path.name}")
    candidates: List[Candidate] = []
    for entry in selected:
        candidates.append(
            Candidate(
                ktp=str(entry["ktp"]),
                ksl=str(entry["ksl"]),
                trend=str(entry["trend"]),
                rsi=str(entry["rsi"]),
                pf_avg_20_30=float(entry.get("pf_avg", 0.0)),
                ret_avg_20_30=float(entry.get("ret_avg", 0.0)),
                maxdd_20_30=float(entry.get("maxDD", 0.0)),
                trades_20_30=float(entry.get("trades", 0.0)),
                selected_level=entry.get("selected_level"),
            )
        )
    return candidates, payload


def _parse_wf_summary(path: Path) -> Tuple[float, float, float, float]:
    if not path.exists():
        raise StabilityError(f"wf_summary.csv not found at {path}")
    rows: List[List[str]] = []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        rows = [row for row in reader if row]
    if not rows:
        raise StabilityError(f"wf_summary.csv at {path} is empty.")
    summary = rows[-1]
    if len(summary) < 8 or summary[0] != "PF(avg)":
        raise StabilityError(f"Unexpected wf_summary format in {path}: {summary}")
    try:
        pf = float(summary[1])
        ret = float(summary[3])
        dd = float(summary[5])
        trades = float(summary[7])
    except ValueError as exc:
        raise StabilityError(f"Invalid numeric data in wf_summary: {summary}") from exc
    return pf, ret, dd, trades


def _run_wf(candidate: Candidate, split: str, wf_script: Path, maxdd_stop: str) -> RunResult:
    rsi_parts = candidate.rsi.split("/")
    if len(rsi_parts) != 2:
        raise StabilityError(f"Unexpected RSI format: {candidate.rsi}")
    env = os.environ.copy()
    env.update(
        {
            "OB_KTP": candidate.ktp,
            "OB_KSL": candidate.ksl,
            "OB_TREND_SMA": candidate.trend,
            "OB_RSI_UP": rsi_parts[0],
            "OB_RSI_DN": rsi_parts[1],
            "OB_MAXDD_STOP": maxdd_stop,
            "WF_SPLITS": split,
        }
    )
    cmd = [sys.executable, str(wf_script)]
    subprocess.run(cmd, check=True, cwd=str(ROOT), env=env)
    pf, ret, dd, trades = _parse_wf_summary(ROOT / "wf_summary.csv")
    return RunResult(candidate=candidate, split=split, trades=trades, pf=pf, ret=ret, maxdd=dd)


def _write_csv(path: Path, header: Sequence[str], rows: Iterable[Iterable[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def _aggregate(results: List[RunResult]) -> List[Dict[str, object]]:
    grouped: Dict[Tuple[str, str, str, str], List[RunResult]] = defaultdict(list)
    for item in results:
        key = (item.candidate.ktp, item.candidate.ksl, item.candidate.trend, item.candidate.rsi)
        grouped[key].append(item)

    aggregates: List[Dict[str, object]] = []
    for idx, (key, runs) in enumerate(grouped.items(), start=1):
        if not runs:
            continue
        cand = runs[0].candidate
        pf_avg = sum(r.pf for r in runs) / len(runs)
        ret_avg = sum(r.ret for r in runs) / len(runs)
        dd_max = max(r.maxdd for r in runs)
        trades_sum = sum(r.trades for r in runs)
        pf_drift = pf_avg - cand.pf_avg_20_30
        ret_drift = ret_avg - cand.ret_avg_20_30
        dd_change = dd_max - cand.maxdd_20_30
        aggregates.append(
            {
                "set_id": idx,
                "ktp": cand.ktp,
                "ksl": cand.ksl,
                "trend": cand.trend,
                "rsi": cand.rsi,
                "params": f"KTP={cand.ktp},KSL={cand.ksl},TREND={cand.trend},RSI={cand.rsi}",
                "splits": "/".join(sorted({r.split for r in runs})),
                "AvgPF_40_60": round(pf_avg, 2),
                "AvgRet_40_60": round(ret_avg, 2),
                "MaxDD_40_60": round(dd_max, 2),
                "Trades_40_60": round(trades_sum, 0),
                "PF_drift": round(pf_drift, 2),
                "Ret_drift": round(ret_drift, 2),
                "DD_change": round(dd_change, 2),
                "AvgPF_20_30": cand.pf_avg_20_30,
                "AvgRet_20_30": cand.ret_avg_20_30,
                "MaxDD_20_30": cand.maxdd_20_30,
                "Trades_20_30": cand.trades_20_30,
                "selected_level": cand.selected_level,
            }
        )
    return aggregates


def _meets_strict(row: Dict[str, object], criteria: Dict[str, float]) -> bool:
    return (
        row["AvgPF_40_60"] >= criteria["pf_min"]
        and row["AvgRet_40_60"] >= criteria["ret_min"]
        and row["MaxDD_40_60"] <= criteria["dd_max"]
        and row["PF_drift"] >= criteria["pf_drift_min"]
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run 40/60 walk-forward stability workflow.")
    parser.add_argument(
        "--meta",
        type=Path,
        help="Path to select_candidates meta JSON (default: latest results/select_candidates_*.json).",
    )
    parser.add_argument(
        "--wf-script",
        type=Path,
        default=ROOT / "wf_validate.py",
        help="Path to wf_validate.py (default: repo root).",
    )
    parser.add_argument(
        "--splits",
        nargs="+",
        default=["40", "60"],
        help="WF_SPLITS values to evaluate (default: 40 60).",
    )
    parser.add_argument(
        "--maxdd-stop",
        type=str,
        default="20",
        help="OB_MAXDD_STOP value during re-validation (default: 20).",
    )
    parser.add_argument(
        "--ts",
        type=str,
        help="Timestamp tag for output artefacts (default: current time).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Emit empty outputs without running wf_validate.py.",
    )
    parser.add_argument(
        "--strict-pf-min",
        type=float,
        help=f"Override strict PF minimum (default: {STRICT_CRITERIA_DEFAULT['pf_min']}).",
    )
    parser.add_argument(
        "--strict-ret-min",
        type=float,
        help=f"Override strict AvgRet minimum (default: {STRICT_CRITERIA_DEFAULT['ret_min']}).",
    )
    parser.add_argument(
        "--strict-dd-max",
        type=float,
        help=f"Override strict MaxDD maximum (default: {STRICT_CRITERIA_DEFAULT['dd_max']}).",
    )
    parser.add_argument(
        "--strict-pf-drift",
        type=float,
        help=f"Override strict PF drift minimum (default: {STRICT_CRITERIA_DEFAULT['pf_drift_min']}).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    meta_path = args.meta or _latest_meta()
    candidates, _meta_payload = _load_candidates(meta_path)
    ts = args.ts or dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = RESULTS_DIR / f"wf_stability_ext_{ts}.csv"
    summary_path = RESULTS_DIR / f"wf_stability_ext_summary_{ts}.csv"
    log_path = RESULTS_DIR / f"wf_stability_ext_{ts}.log"
    meta_out_path = RESULTS_DIR / f"wf_stability_ext_{ts}.json"
    final_csv_path = RESULTS_DIR / f"final_candidates_{ts}.csv"

    strict_criteria = dict(STRICT_CRITERIA_DEFAULT)
    if args.strict_pf_min is not None:
        strict_criteria["pf_min"] = args.strict_pf_min
    if args.strict_ret_min is not None:
        strict_criteria["ret_min"] = args.strict_ret_min
    if args.strict_dd_max is not None:
        strict_criteria["dd_max"] = args.strict_dd_max
    if args.strict_pf_drift is not None:
        strict_criteria["pf_drift_min"] = args.strict_pf_drift

    if args.dry_run:
        _write_csv(
            raw_path,
            ["ktp", "ksl", "trend", "rsi", "splits", "trades", "pf", "return%", "maxDD%"],
            [],
        )
        _write_csv(
            summary_path,
            [
                "set_id",
                "params",
                "AvgPF_20_30",
                "AvgRet_20_30",
                "MaxDD_20_30",
                "trades_20_30",
                "AvgPF_40_60",
                "AvgRet_40_60",
                "MaxDD_40_60",
                "trades_40_60",
                "PF_drift",
                "Ret_drift",
                "DD_change",
            ],
            [],
        )
        log_path.write_text(
            f"[wf] dry-run meta={meta_path.name} candidates={len(candidates)}\n", encoding="utf-8"
        )
        meta_out_path.write_text(
            json.dumps(
                {
                    "timestamp": ts,
                    "meta_in": str(meta_path),
                    "splits": args.splits,
                    "maxdd_stop": args.maxdd_stop,
                    "raw_csv": str(raw_path),
                    "summary_csv": str(summary_path),
                    "candidates": len(candidates),
                    "final_csv": str(final_csv_path),
                    "strict_criteria": strict_criteria,
                    "dry_run": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        _write_csv(
            final_csv_path,
            [
                "set_id",
                "params",
                "AvgPF_20_30",
                "AvgRet_20_30",
                "MaxDD_20_30",
                "trades_20_30",
                "AvgPF_40_60",
                "AvgRet_40_60",
                "MaxDD_40_60",
                "trades_40_60",
                "PF_drift",
                "Ret_drift",
                "DD_change",
            ],
            [],
        )
        print("Dry run complete; empty artefacts emitted.")
        return 0

    raw_rows: List[List[str]] = []
    run_results: List[RunResult] = []

    for candidate in candidates:
        for split in args.splits:
            print(
                f"[wf] validate split={split} KTP={candidate.ktp} KSL={candidate.ksl} "
                f"TREND={candidate.trend} RSI={candidate.rsi}",
                flush=True,
            )
            result = _run_wf(candidate, split, args.wf_script, args.maxdd_stop)
            run_results.append(result)
            raw_rows.append(
                [
                    candidate.ktp,
                    candidate.ksl,
                    candidate.trend,
                    candidate.rsi,
                    split,
                    f"{result.trades:.0f}",
                    f"{result.pf:.2f}",
                    f"{result.ret:.2f}",
                    f"{result.maxdd:.2f}",
                ]
            )

    _write_csv(
        raw_path,
        ["ktp", "ksl", "trend", "rsi", "splits", "trades", "pf", "return%", "maxDD%"],
        raw_rows,
    )

    aggregates = _aggregate(run_results)
    for agg in aggregates:
        agg["meets_strict"] = _meets_strict(agg, strict_criteria)

    _write_csv(
        summary_path,
        [
            "set_id",
            "params",
            "AvgPF_20_30",
            "AvgRet_20_30",
            "MaxDD_20_30",
            "trades_20_30",
            "AvgPF_40_60",
            "AvgRet_40_60",
            "MaxDD_40_60",
            "trades_40_60",
            "PF_drift",
            "Ret_drift",
            "DD_change",
        ],
        [
            [
                agg["set_id"],
                agg["params"],
                f"{agg['AvgPF_20_30']:.2f}",
                f"{agg['AvgRet_20_30']:.2f}",
                f"{agg['MaxDD_20_30']:.2f}",
                f"{agg['Trades_20_30']:.0f}",
                f"{agg['AvgPF_40_60']:.2f}",
                f"{agg['AvgRet_40_60']:.2f}",
                f"{agg['MaxDD_40_60']:.2f}",
                f"{agg['Trades_40_60']:.0f}",
                f"{agg['PF_drift']:.2f}",
                f"{agg['Ret_drift']:.2f}",
                f"{agg['DD_change']:.2f}",
            ]
            for agg in aggregates
        ],
    )

    final_candidates = sorted(
        [agg for agg in aggregates if agg["meets_strict"]],
        key=lambda x: (-x["AvgPF_40_60"], x["MaxDD_40_60"], -x["AvgRet_40_60"]),
    )
    picks = final_candidates[:2]

    log_lines = [
        f"[wf] meta_in={meta_path.name}",
        f"[wf] candidates={len(candidates)}",
        f"[wf] splits={','.join(args.splits)}",
        f"[wf] raw_csv={raw_path.name}",
        f"[wf] summary_csv={summary_path.name}",
    ]
    for agg in aggregates:
        log_lines.append(
            "[wf] result set_id={sid} ktp={ktp} ksl={ksl} trend={trend} rsi={rsi} "
            "PF40/60={pf:.2f} Ret40/60={ret:.2f} MaxDD40/60={dd:.2f} "
            "Trades={tr:.0f} PF_drift={drift:.2f} strict={strict}".format(
                sid=agg["set_id"],
                ktp=agg["ktp"],
                ksl=agg["ksl"],
                trend=agg["trend"],
                rsi=agg["rsi"],
                pf=agg["AvgPF_40_60"],
                ret=agg["AvgRet_40_60"],
                dd=agg["MaxDD_40_60"],
                tr=agg["Trades_40_60"],
                drift=agg["PF_drift"],
                strict="pass" if agg["meets_strict"] else "fail",
            )
        )
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    _write_csv(
        final_csv_path,
        [
            "set_id",
            "params",
            "AvgPF_20_30",
            "AvgRet_20_30",
            "MaxDD_20_30",
            "trades_20_30",
            "AvgPF_40_60",
            "AvgRet_40_60",
            "MaxDD_40_60",
            "trades_40_60",
            "PF_drift",
            "Ret_drift",
            "DD_change",
        ],
        [
            [
                agg["set_id"],
                agg["params"],
                f"{agg['AvgPF_20_30']:.2f}",
                f"{agg['AvgRet_20_30']:.2f}",
                f"{agg['MaxDD_20_30']:.2f}",
                f"{agg['Trades_20_30']:.0f}",
                f"{agg['AvgPF_40_60']:.2f}",
                f"{agg['AvgRet_40_60']:.2f}",
                f"{agg['MaxDD_40_60']:.2f}",
                f"{agg['Trades_40_60']:.0f}",
                f"{agg['PF_drift']:.2f}",
                f"{agg['Ret_drift']:.2f}",
                f"{agg['DD_change']:.2f}",
            ]
            for agg in picks
        ],
    )

    has_summary_rows = len(aggregates) > 0

    meta_out = {
        "timestamp": ts,
        "meta_in": str(meta_path),
        "splits": args.splits,
        "maxdd_stop": args.maxdd_stop,
        "raw_csv": str(raw_path),
        "summary_csv": str(summary_path),
        "candidates": len(candidates),
        "strict_criteria": strict_criteria,
        "results": aggregates,
        "final_picks": picks,
        "final_csv": str(final_csv_path),
        "has_summary_rows": has_summary_rows,
    }
    meta_out_path.write_text(json.dumps(meta_out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"40/60 validation complete. {len(final_candidates)}/{len(aggregates)} candidates meet strict criteria.")
    if final_candidates:
        print(f"Final picks (max 2): {len(picks)}")
        for agg in picks:
            print(
                f"  PASS set_id={agg['set_id']} params={agg['params']} "
                f"PF={agg['AvgPF_40_60']:.2f} Ret={agg['AvgRet_40_60']:.2f} "
                f"MaxDD={agg['MaxDD_40_60']:.2f} PF_drift={agg['PF_drift']:.2f}"
            )
    else:
        print("WARNING: No candidates satisfy strict final criteria.")

    if not args.dry_run and not has_summary_rows:
        print("ERROR: wf_stability_ext_summary is empty; no validation rows recorded.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StabilityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
