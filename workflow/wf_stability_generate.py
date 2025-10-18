#!/usr/bin/env python3
"""
Generate 20/30 stability metrics for parameter combinations using walk-forward validation.

The generator loads a base parameter grid and, optionally, staged augmentation
definitions to widen the search space when the base combinations do not yield
enough viable candidates. It writes two artefacts:

* results/wf_stability_{ts}.csv          - raw per-split metrics
* results/wf_stability_summary_{ts}.csv  - aggregated metrics (pf_avg, etc.)

Each invocation prints a single JSON object describing the run so that the
PowerShell orchestrator can capture stats (combos evaluated, stage applied, etc.).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import subprocess
import time
import sys
from decimal import Decimal, getcontext
from itertools import product
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


def _safe_stream(stream: io.TextIOBase) -> io.TextIOBase:
    """Wrap a text stream so flush/write ignore OSError (Codex stdout quirk)."""

    class _SafeWrapper(io.TextIOBase):
        def __init__(self, wrapped: io.TextIOBase) -> None:
            self._wrapped = wrapped

        def write(self, data: str) -> int:  # type: ignore[override]
            try:
                return self._wrapped.write(data)
            except OSError:
                return len(data)

        def flush(self) -> None:  # type: ignore[override]
            try:
                self._wrapped.flush()
            except OSError:
                pass

        @property
        def encoding(self) -> str | None:  # type: ignore[override]
            return getattr(self._wrapped, "encoding", None)

        @property
        def errors(self) -> str | None:
            return getattr(self._wrapped, "errors", None)

        @property
        def buffer(self):  # pragma: no cover - passthrough
            return getattr(self._wrapped, "buffer", None)

        def fileno(self) -> int:  # type: ignore[override]
            return self._wrapped.fileno()

        def isatty(self) -> bool:  # type: ignore[override]
            return self._wrapped.isatty()

        def __getattr__(self, name: str):
            return getattr(self._wrapped, name)

    return _SafeWrapper(stream)


sys.stdout = _safe_stream(sys.stdout)  # type: ignore[assignment]
sys.stderr = _safe_stream(sys.stderr)  # type: ignore[assignment]

getcontext().prec = 12

RESULTS_DIR = Path("results")

PARAM_ORDER = ["OB_KTP", "OB_KSL", "OB_TREND_SMA", "OB_RSI_UP", "OB_RSI_DN"]
RAW_HEADER = ["ktp", "ksl", "trend", "rsi", "splits", "trades", "pf", "return%", "maxDD%"]
SUMMARY_HEADER = ["ktp", "ksl", "trend", "rsi", "pf_avg", "ret_avg", "maxDD_max", "splits"]


class GenerationError(RuntimeError):
    pass


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # Retry with UTF-8-SIG in case BOM is present.
        return json.loads(path.read_text(encoding="utf-8-sig"))


def format_number(value: float) -> str:
    if math.isclose(value, round(value)):
        return str(int(round(value)))
    return f"{value:.10f}".rstrip("0").rstrip(".")


def decimal_range(start: Decimal, stop: Decimal, step: Decimal) -> List[str]:
    values: List[str] = []
    current = start
    # Add a small epsilon to avoid floating point miss on inclusive stop.
    epsilon = step / Decimal("1000000")
    while current <= stop + epsilon:
        values.append(format_number(float(current)))
        current += step
    return values


def parse_float_list(values: Iterable[str]) -> List[float]:
    return sorted({float(v) for v in values})


def load_base_grid(path: Path) -> Tuple[Dict[str, List[str]], Dict[str, dict], Dict[str, str]]:
    config = load_json(path)
    params_cfg = config.get("parameters")
    if not params_cfg:
        raise GenerationError(f"config file {path} missing 'parameters' section")

    options: Dict[str, List[str]] = {}
    meta: Dict[str, dict] = {}

    for name, cfg in params_cfg.items():
        kind = cfg.get("kind")
        meta[name] = dict(cfg)
        meta[name]["kind"] = kind
        if kind == "range":
            start = Decimal(str(cfg["start"]))
            stop = Decimal(str(cfg["stop"]))
            step = Decimal(str(cfg["step"]))
            values = decimal_range(start, stop, step)
            meta[name]["step"] = float(cfg["step"])
        elif kind == "values":
            values = [format_number(float(v)) for v in cfg.get("values", [])]
        elif kind == "pairs":
            pairs = cfg.get("values", [])
            values = [
                (format_number(float(up)), format_number(float(dn)))
                for up, dn in pairs
            ]
            options[name] = values
            continue
        else:
            raise GenerationError(f"Unsupported kind '{kind}' for parameter {name}")
        values = sorted(set(values), key=lambda x: float(x))
        options[name] = values

    base_env = config.get("base_env", {})
    base_env = {k: str(v) for k, v in base_env.items()}

    return options, meta, base_env


def clone_options(options: Dict[str, List[str]]) -> Dict[str, List[str]]:
    cloned: Dict[str, List[str]] = {}
    for key, value in options.items():
        if key == "OB_RSI":
            cloned[key] = [tuple(pair) for pair in value]  # type: ignore[list-item]
        else:
            cloned[key] = value[:]
    return cloned


def ensure_pair_list(value: List[List[float]]) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for pair in value:
        if len(pair) != 2:
            raise GenerationError(f"RSI pair must have two entries: {pair}")
        up, dn = pair
        pairs.append((format_number(float(up)), format_number(float(dn))))
    return pairs


def apply_stage(
    options: Dict[str, List[str]],
    meta: Dict[str, dict],
    stage_cfg: dict,
) -> Dict[str, List[str]]:
    adjustments = stage_cfg.get("adjustments", {})
    updated = {key: value[:] if key != "OB_RSI" else value[:] for key, value in options.items()}

    for name, adj in adjustments.items():
        action = adj.get("action")
        if name == "OB_RSI":
            current_pairs = updated.get("OB_RSI", [])
            if action == "add_pairs":
                new_pairs = ensure_pair_list(adj.get("values", []))
                new_set = {pair for pair in current_pairs}
                new_set.update(new_pairs)
                updated["OB_RSI"] = sorted(new_set, key=lambda x: (float(x[0]), float(x[1])))
            else:
                raise GenerationError(f"Unsupported action '{action}' for OB_RSI")
            continue

        if name not in updated:
            raise GenerationError(f"Unknown parameter '{name}' referenced in augmentation")

        current_values = updated[name]
        if action == "range_expand":
            base_kind = meta.get(name, {}).get("kind", "values")
            if base_kind not in {"range", "values"}:
                raise GenerationError(f"range_expand requires numeric parameter, got kind {base_kind}")
            current_numeric = [Decimal(str(v)) for v in current_values]
            min_val = min(current_numeric)
            max_val = max(current_numeric)
            scale = Decimal(str(adj.get("scale", 0)))
            if scale <= 0:
                raise GenerationError("range_expand requires positive 'scale'")
            step = Decimal(str(adj.get("step", meta.get(name, {}).get("step", 0.1))))
            new_min = min_val * (Decimal("1") - scale)
            new_max = max_val * (Decimal("1") + scale)
            new_values = decimal_range(new_min, new_max, step)
            union = {format_number(float(v)) for v in new_values}
            union.update(current_values)
            updated[name] = sorted(union, key=lambda x: float(x))
        elif action == "add_values":
            new_values = [format_number(float(v)) for v in adj.get("values", [])]
            union = set(current_values)
            union.update(new_values)
            updated[name] = sorted(union, key=lambda x: float(x))
        else:
            raise GenerationError(f"Unsupported action '{action}' for parameter {name}")

    return updated


def iter_combos(options: Dict[str, List[str]]) -> Iterable[Dict[str, str]]:
    ktp_values = options["OB_KTP"]
    ksl_values = options["OB_KSL"]
    trend_values = options["OB_TREND_SMA"]
    rsi_pairs = options["OB_RSI"]
    for ktp, ksl, trend, (r_up, r_dn) in product(ktp_values, ksl_values, trend_values, rsi_pairs):
        yield {
            "OB_KTP": ktp,
            "OB_KSL": ksl,
            "OB_TREND_SMA": trend,
            "OB_RSI_UP": r_up,
            "OB_RSI_DN": r_dn,
        }


def combo_key(combo: Dict[str, str]) -> Tuple[str, str, str, str]:
    rsi = f"{combo['OB_RSI_UP']}/{combo['OB_RSI_DN']}"
    return (combo["OB_KTP"], combo["OB_KSL"], combo["OB_TREND_SMA"], rsi)


def load_existing_combos(summary_path: Path) -> set[Tuple[str, str, str, str]]:
    if not summary_path.exists():
        return set()
    existing: set[Tuple[str, str, str, str]] = set()
    with summary_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = (row["ktp"], row["ksl"], row["trend"], row["rsi"])
            existing.add(key)
    return existing


def parse_split_output(output: str) -> Tuple[int, float, float, float]:
    trades_total = 0
    pf_values: List[float] = []
    ret_values: List[float] = []
    dd_values: List[float] = []

    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("split"):
            continue
        tokens = line.split()
        trades = None
        pf = None
        ret = None
        dd = None
        for token in tokens:
            if token.startswith("trades="):
                trades = int(token.split("=", 1)[1])
            elif token.startswith("PF="):
                pf = float(token.split("=", 1)[1])
            elif token.startswith("return="):
                value = token.split("=", 1)[1].rstrip("%")
                ret = float(value)
            elif token.startswith("maxDD="):
                value = token.split("=", 1)[1].rstrip("%")
                dd = float(value)
        if trades is None or pf is None or ret is None or dd is None:
            continue
        trades_total += trades
        pf_values.append(pf)
        ret_values.append(ret)
        dd_values.append(dd)

    if not pf_values:
        return 0, 0.0, 0.0, 0.0

    pf_avg = sum(pf_values) / len(pf_values)
    ret_avg = sum(ret_values) / len(ret_values)
    dd_max = max(dd_values)
    return trades_total, pf_avg, ret_avg, dd_max


def run_wf(combo: Dict[str, str], splits: Sequence[int], base_env: Dict[str, str]) -> Tuple[List[dict], dict]:
    split_records: List[dict] = []
    pf_collect: List[float] = []
    ret_collect: List[float] = []
    dd_collect: List[float] = []
    trades_collect: List[int] = []

    for split in splits:
        env = os.environ.copy()
        env.update(base_env)
        env.update(combo)
        env["WF_SPLITS"] = str(split)
        proc_output = subprocess.check_output(
            [sys.executable, "wf_validate.py"],
            env=env,
            text=True,
            stderr=subprocess.STDOUT,
        )
        trades, pf_avg, ret_avg, dd_max = parse_split_output(proc_output)
        split_records.append(
            {
                "split": split,
                "trades": trades,
                "pf": pf_avg,
                "ret": ret_avg,
                "maxdd": dd_max,
            }
        )
        pf_collect.append(pf_avg)
        ret_collect.append(ret_avg)
        dd_collect.append(dd_max)
        trades_collect.append(trades)

    if not split_records:
        return split_records, {
            "pf_avg": 0.0,
            "ret_avg": 0.0,
            "maxdd_max": 0.0,
            "trades_total": 0,
        }

    agg = {
        "pf_avg": sum(pf_collect) / len(pf_collect),
        "ret_avg": sum(ret_collect) / len(ret_collect),
        "maxdd_max": max(dd_collect),
        "trades_total": sum(trades_collect),
    }
    return split_records, agg


def append_results(
    raw_path: Path,
    summary_path: Path,
    combo: Dict[str, str],
    split_records: List[dict],
    aggregate: dict,
    splits: Sequence[int],
) -> None:
    raw_exists = raw_path.exists()
    with raw_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if not raw_exists:
            writer.writerow(RAW_HEADER)
        for record in split_records:
            rsi = f"{combo['OB_RSI_UP']}/{combo['OB_RSI_DN']}"
            writer.writerow(
                [
                    combo["OB_KTP"],
                    combo["OB_KSL"],
                    combo["OB_TREND_SMA"],
                    rsi,
                    str(record["split"]),
                    record["trades"],
                    f"{record['pf']:.4f}",
                    f"{record['ret']:.4f}",
                    f"{record['maxdd']:.4f}",
                ]
            )

    summary_exists = summary_path.exists()
    with summary_path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if not summary_exists:
            writer.writerow(SUMMARY_HEADER)
        rsi = f"{combo['OB_RSI_UP']}/{combo['OB_RSI_DN']}"
        splits_str = "/".join(str(s) for s in splits)
        writer.writerow(
            [
                combo["OB_KTP"],
                combo["OB_KSL"],
                combo["OB_TREND_SMA"],
                rsi,
                f"{aggregate['pf_avg']:.4f}",
                f"{aggregate['ret_avg']:.4f}",
                f"{aggregate['maxdd_max']:.4f}",
                splits_str,
            ]
        )


def positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return ivalue


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate 20/30 stability metrics.")
    parser.add_argument("--mode", choices=["base", "augment"], required=True)
    parser.add_argument("--grid", type=Path, required=True, help="Path to param_grid_base.yaml")
    parser.add_argument("--aug", type=Path, help="Path to param_grid_aug.yaml (required for augment mode)")
    parser.add_argument("--stage", help="Stage name to apply (augment mode)")
    parser.add_argument("--splits", nargs="+", type=positive_int, required=True, help="Split counts for stability stage (e.g. 20 30)")
    parser.add_argument("--ts", required=True, help="Timestamp tag for output files")
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR, help="Directory for output artefacts")
    parser.add_argument("--max-combinations", type=positive_int, default=2000, help="Maximum combinations per augmentation")
    parser.add_argument("--dry-run", action="store_true", help="Skip evaluation and only touch summary headers.")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    results_dir: Path = args.results_dir
    results_dir.mkdir(parents=True, exist_ok=True)

    raw_path = results_dir / f"wf_stability_{args.ts}.csv"
    summary_path = results_dir / f"wf_stability_summary_{args.ts}.csv"

    options, meta, base_env = load_base_grid(args.grid)
    if "OB_RSI" not in options:
        raise GenerationError("Base grid must include OB_RSI pairs")

    existing = load_existing_combos(summary_path)

    if args.mode == "base":
        # Overwrite existing files for base run.
        if raw_path.exists():
            raw_path.unlink()
        if summary_path.exists():
            summary_path.unlink()
        iterator_options = clone_options(options)
        max_combos = None  # No limit for base run.
    else:
        if not args.aug:
            raise GenerationError("--aug is required for augment mode")
        if not args.stage:
            raise GenerationError("--stage is required for augment mode")
        aug_config = load_json(args.aug)
        stage_list = aug_config.get("stages", [])
        stage_names = [stage["name"] for stage in stage_list]
        if args.stage not in stage_names:
            raise GenerationError(f"Stage '{args.stage}' not found in {args.aug}")
        iterator_options = clone_options(options)
        for stage in stage_list:
            iterator_options = apply_stage(iterator_options, meta, stage)
            if stage["name"] == args.stage:
                break
        max_combos = args.max_combinations

    total_candidates = 0
    duplicates_skipped = 0
    combos_to_evaluate: List[Dict[str, str]] = []
    for combo in iter_combos(iterator_options):
        total_candidates += 1
        key = combo_key(combo)
        if key in existing:
            duplicates_skipped += 1
            continue
        combos_to_evaluate.append(combo)
    combos_to_evaluate.sort(
        key=lambda c: (
            float(c["OB_KTP"]),
            float(c["OB_KSL"]),
            float(c["OB_TREND_SMA"]),
            float(c["OB_RSI_UP"]),
            float(c["OB_RSI_DN"]),
        )
    )

    combos_after_filter = len(combos_to_evaluate)

    if max_combos is not None and len(combos_to_evaluate) > max_combos:
        combos_to_evaluate = combos_to_evaluate[:max_combos]
    combos_scheduled = len(combos_to_evaluate)

    start_time = time.time()
    evaluated = 0
    if not args.dry_run:
        for combo in combos_to_evaluate:
            split_records, aggregate = run_wf(combo, args.splits, base_env)
            append_results(raw_path, summary_path, combo, split_records, aggregate, args.splits)
            existing.add(combo_key(combo))
            evaluated += 1
    else:
        # Ensure headers exist even during dry-run so downstream steps can proceed.
        if not raw_path.exists():
            with raw_path.open("w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(RAW_HEADER)
        if not summary_path.exists():
            with summary_path.open("w", newline="", encoding="utf-8") as fh:
                csv.writer(fh).writerow(SUMMARY_HEADER)
    duration_sec = time.time() - start_time if not args.dry_run else 0.0

    result = {
        "mode": args.mode,
        "stage": args.stage if args.mode == "augment" else "base",
        "combos_total": total_candidates,
        "duplicates_skipped": duplicates_skipped,
        "combos_after_filter": combos_after_filter,
        "combos_scheduled": combos_scheduled,
        "combos_evaluated": evaluated,
        "raw_csv": str(raw_path),
        "summary_csv": str(summary_path),
        "duration_sec": duration_sec,
        "dry_run": bool(args.dry_run),
    }
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GenerationError as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(1)
