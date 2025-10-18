#!/usr/bin/env python3
"""
Candidate selection utility for walk-forward stability summaries.

Steps:
1. Load the latest 20/30 stability summary (or a user-provided path).
2. Pair each summary row with raw split metrics to recover trade counts.
3. Apply tiered thresholds (L0 ↁEL1 ↁEL2) until the minimum quota is met.
4. Emit structured logs and metadata for auditability.
"""

from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import json
import sys
from collections import defaultdict, OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = ROOT / "results"

# Threshold definitions
DEFAULT_LEVELS = [
    ("L0", {"pf_min": 1.05, "ret_min": 0.0, "dd_max": 20.0}),
    ("L1", {"pf_min": 1.02, "ret_min": -0.05, "dd_max": 22.0}),
    ("L2", {"pf_min": 1.00, "ret_min": -0.10, "dd_max": 25.0}),
]
TRADES_MIN_DEFAULT = 30


class SelectionError(Exception):
    """Raised when candidate selection cannot proceed."""


def latest_summary() -> Path:
    """Return the newest 20/30 summary CSV."""
    candidates = sorted(DEFAULT_RESULTS_DIR.glob("wf_stability_summary_*.csv"))
    if not candidates:
        raise SelectionError("No wf_stability_summary_*.csv files found in results/.")
    return candidates[-1]


def matching_raw(summary_path: Path) -> Optional[Path]:
    """Return the raw CSV that matches the summary timestamp, if present."""
    name = summary_path.name.replace("summary_", "")
    raw_path = summary_path.with_name(name)
    return raw_path if raw_path.exists() else None


def clean_field(name: str) -> str:
    """Strip BOM markers and surrounding quotes from a CSV header."""
    name = (name or "").replace("\ufeff", "").strip()
    if name.startswith('"') and name.endswith('"') and len(name) >= 2:
        name = name[1:-1]
    return name.strip()


def load_summary(path: Path) -> List[Dict[str, str]]:
    """Read a stability summary CSV."""
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise SelectionError(f"Summary CSV {path} is missing headers.")
        fieldnames = [clean_field(name) for name in reader.fieldnames]
        rows = []
        for raw_row in reader:
            if not any(raw_row.values()):
                continue
            row = {fieldnames[idx]: value for idx, (key, value) in enumerate(raw_row.items())}
            rows.append(row)
    if not rows:
        return []
    return rows


def load_raw(path: Path) -> Dict[Tuple[str, str, str, str], List[Dict[str, float]]]:
    """Group raw split rows by parameter tuple."""
    result: Dict[Tuple[str, str, str, str], List[Dict[str, float]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return result
        fieldnames = [clean_field(name) for name in reader.fieldnames]
        for raw_row in reader:
            if not any(raw_row.values()):
                continue
            row = {fieldnames[idx]: value for idx, (key, value) in enumerate(raw_row.items())}
            if not row or not row.get("ktp"):
                continue
            key = (row["ktp"], row["ksl"], row["trend"], row["rsi"])
            result[key].append(
                {
                    "split": row.get("splits", "").strip(),
                    "trades": float(row.get("trades") or 0.0),
                    "pf": float(row.get("pf") or 0.0),
                    "ret": float(row.get("return%") or 0.0),
                    "dd": float(row.get("maxDD%") or 0.0),
                }
            )
    return result


def numeric(value: str, default: float = 0.0) -> float:
    """Parse numeric fields safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def unique_rows(rows: Iterable[Dict[str, str]]) -> Tuple[List[Dict[str, str]], int]:
    """Deduplicate by (ktp, ksl, trend, rsi) preserving order."""
    seen = OrderedDict()
    for row in rows:
        key = (row["ktp"], row["ksl"], row["trend"], row["rsi"])
        if key not in seen:
            seen[key] = row
    return list(seen.values()), len(rows) - len(seen)


def attach_metrics(
    summary_rows: Iterable[Dict[str, str]],
    raw_map: Optional[Dict[Tuple[str, str, str, str], List[Dict[str, float]]]],
) -> List[Dict[str, object]]:
    """Decorate summary rows with numeric metrics and aggregated splits."""
    decorated = []
    for row in summary_rows:
        key = (row["ktp"], row["ksl"], row["trend"], row["rsi"])
        splits = [s.strip() for s in (row.get("splits", "") or "").split("/") if s.strip()]
        pf_avg = numeric(row.get("pf_avg"))
        ret_avg = numeric(row.get("ret_avg"))
        dd_max = numeric(row.get("maxDD_max"))
        trade_total = 0.0
        if raw_map:
            for entry in raw_map.get(key, []):
                if not splits or entry["split"] in splits:
                    trade_total += entry["trades"]
        decorated.append(
            {
                "key": key,
                "pf_avg": pf_avg,
                "ret_avg": ret_avg,
                "dd_max": dd_max,
                "splits": splits,
                "trades": trade_total,
            }
        )
    return decorated


def select_candidates(
    rows: List[Dict[str, object]],
    n_min: int,
    trades_min: int,
    levels: Sequence[Tuple[str, Dict[str, float]]],
) -> Tuple[List[Dict[str, object]], Dict[str, Dict[str, int]]]:
    """Apply tiered selection and return chosen rows plus exclusion stats."""
    remaining = rows.copy()
    chosen: List[Dict[str, object]] = []
    stats: Dict[str, Dict[str, int]] = {}

    for level_name, threshold in levels:
        if not remaining:
            stats[level_name] = {"pf": 0, "ret": 0, "dd": 0, "trades": 0, "accepted": 0}
            continue
        level_selected = []
        reasons = {"pf": 0, "ret": 0, "dd": 0, "trades": 0, "accepted": 0}
        still_remaining = []
        for item in remaining:
            fail_reason = None
            if item["trades"] < trades_min:
                fail_reason = "trades"
            elif item["pf_avg"] < threshold["pf_min"]:
                fail_reason = "pf"
            elif item["ret_avg"] < threshold["ret_min"]:
                fail_reason = "ret"
            elif item["dd_max"] > threshold["dd_max"]:
                fail_reason = "dd"

            if fail_reason:
                reasons[fail_reason] += 1
                still_remaining.append(item)
                continue

            item_copy = dict(item)
            item_copy["selected_level"] = level_name
            level_selected.append(item_copy)
            reasons["accepted"] += 1

        stats[level_name] = reasons
        chosen.extend(level_selected)
        remaining = still_remaining

        if len(chosen) >= n_min:
            break

    return chosen, stats


def emit_log(log_path: Path, lines: Iterable[str]) -> None:
    with log_path.open("w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line.rstrip() + "\n")


def emit_meta(meta_path: Path, payload: Dict[str, object]) -> None:
    with meta_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Select walk-forward stability candidates.")
    parser.add_argument(
        "--summary",
        type=Path,
        help="Path to a wf_stability_summary CSV (defaults to the latest in results/).",
    )
    parser.add_argument(
        "--n-min",
        type=int,
        default=5,
        help="Minimum number of candidates to secure before stopping (default: 5).",
    )
    parser.add_argument(
        "--trades-min",
        type=int,
        default=TRADES_MIN_DEFAULT,
        help=f"Minimum combined trades required per parameter set (default: {TRADES_MIN_DEFAULT}).",
    )
    parser.add_argument(
        "--widening-levels",
        type=str,
        help="Override widening thresholds as Python literal, e.g. \"[(1.05,0,20),(1.02,-0.05,22)]\".",
    )
    parser.add_argument(
        "--stages",
        type=str,
        default="20,30",
        help="Comma separated list of WF stages covered (default: 20,30).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Directory to place log/meta outputs (default: results/).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run selection without writing log/meta files.",
    )
    parser.add_argument(
        "--ts",
        type=str,
        help="Optional timestamp tag for outputs (default: current time).",
    )
    args = parser.parse_args(argv)

    summary_path = args.summary or latest_summary()
    rows_raw = load_summary(summary_path)
    unique, duplicates = unique_rows(rows_raw)
    raw_map = None
    raw_path = matching_raw(summary_path)
    if raw_path:
        raw_map = load_raw(raw_path)

    decorated = attach_metrics(unique, raw_map)

    if args.widening_levels:
        try:
            parsed_levels = ast.literal_eval(args.widening_levels)
        except (ValueError, SyntaxError) as exc:
            raise SelectionError(f"Failed to parse widening-levels: {exc}") from exc
        try:
            levels = [
                (
                    f"L{idx}",
                    {
                        "pf_min": float(entry[0]),
                        "ret_min": float(entry[1]),
                        "dd_max": float(entry[2]),
                    },
                )
                for idx, entry in enumerate(parsed_levels)
            ]
        except (TypeError, IndexError, ValueError) as exc:
            raise SelectionError(f"Invalid widening-levels payload: {exc}") from exc
    else:
        levels = DEFAULT_LEVELS

    stages = [stage.strip() for stage in args.stages.split(",") if stage.strip()]
    if not stages:
        stages = ["20", "30"]

    chosen, stats = select_candidates(
        decorated, max(args.n_min, 0), max(args.trades_min, 0), levels
    )
    ts = args.ts or dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) if args.out is not None else DEFAULT_RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"select_candidates_{ts}.log"
    meta_path = out_dir / f"select_candidates_{ts}.json"

    log_lines = [
        f"[select] summary={summary_path.name}",
        f"[select] raw={raw_path.name if raw_path else 'N/A'}",
        f"[select] total_rows={len(rows_raw)} unique_rows={len(unique)} duplicates_removed={duplicates}",
        f"[select] n_min={args.n_min} trades_min={args.trades_min} selected_total={len(chosen)}",
    ]
    for level_name, threshold in levels:
        reasons = stats.get(level_name, {})
        log_lines.append(
            "[select] level={lvl} pf_min={pf:.2f} ret_min={ret:.2f} dd_max={dd:.2f} "
            "excluded_pf={ep} excluded_ret={er} excluded_dd={ed} "
            "excluded_trades={et} accepted={acc}".format(
                lvl=level_name,
                pf=threshold["pf_min"],
                ret=threshold["ret_min"],
                dd=threshold["dd_max"],
                ep=reasons.get("pf", 0),
                er=reasons.get("ret", 0),
                ed=reasons.get("dd", 0),
                et=reasons.get("trades", 0),
                acc=reasons.get("accepted", 0),
            )
        )

    if args.dry_run:
        for line in log_lines:
            print(line)
    emit_log(log_path, log_lines)

    meta_payload = {
        "timestamp": ts,
        "summary_csv": str(summary_path),
        "raw_csv": str(raw_path) if raw_path else None,
        "n_min": args.n_min,
        "trades_min": args.trades_min,
        "levels": [
            {
                "name": level_name,
                "thresholds": threshold,
                "excluded": stats.get(level_name, {}),
                "accepted": stats.get(level_name, {}).get("accepted", 0),
            }
            for level_name, threshold in levels
        ],
        "duplicates_removed": duplicates,
        "stages": stages,
        "selected": [
            {
                "ktp": item["key"][0],
                "ksl": item["key"][1],
                "trend": item["key"][2],
                "rsi": item["key"][3],
                "pf_avg": item["pf_avg"],
                "ret_avg": item["ret_avg"],
                "maxDD": item["dd_max"],
                "trades": item["trades"],
                "selected_level": item.get("selected_level"),
            }
            for item in chosen
        ],
    }
    if args.dry_run:
        print(json.dumps(meta_payload, ensure_ascii=False, indent=2))
    emit_meta(meta_path, meta_payload)

    # Print concise summary for CLI consumption.
    if args.dry_run:
        print(f"Dry run complete. Outputs available at: {log_path.parent}")
    print(f"Log written to: {log_path}")
    print(f"Meta written to: {meta_path}")
    print(f"Selected {len(chosen)} candidate(s).")
    if not chosen:
        print("WARNING: No candidates met the thresholds. Consider relaxing criteria.")
    else:
        for item in chosen:
            ktp, ksl, trend, rsi = item["key"]
            print(
                f"  {ktp}/{ksl}/{trend}/{rsi}  "
                f"PF={item['pf_avg']:.2f}  Ret={item['ret_avg']:.2f}  "
                f"MaxDD={item['dd_max']:.2f}  Trades={item['trades']:.0f}"
            )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SelectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
