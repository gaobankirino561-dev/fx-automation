#!/usr/bin/env python3
"""
Extended backtest and equity analysis for final walk-forward candidates.

Processes the latest final_candidates CSV (or a user-specified set), replays
the full OHLC history between --equity-start and --equity-end, and emits:
  * results/equity_{setid}_{start}_{end}.csv  (time, equity, drawdown)
  * results/equity_{setid}_{start}_{end}.png  (equity curve + DD subplot)
  * results/metrics_{setid}_{start}_{end}.json (rich metrics + drift audit)

The script prints a JSON summary containing each set_id, acceptance flag, and
paths to the artefacts so that callers can persist into run_meta.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Dict, List, Optional, Sequence, Tuple
import zipfile

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates  # noqa: E402
    import matplotlib.pyplot as plt  # noqa: E402
except Exception:  # pragma: no cover - optional dependency
    matplotlib = None
    plt = None
    mdates = None

from workflow.wf_stability_generate import load_json as load_grid_json  # type: ignore

# Default environment values (match param_grid_base.yaml base_env).
EQ0_DEFAULT = 10_000.0
RISK_DEFAULT = 0.003
MIN_TP_DEFAULT = 6.0
MIN_SL_DEFAULT = 6.0
SPREAD_DEFAULT = 0.2
FEE_DEFAULT = 0.0
PIP_SIZE = 0.01
ATR_PERIOD = 14

# Acceptance thresholds
PF_MIN = 1.05
AVGRET_MIN = 0.0
MAXDD_MAX = 20.0
PF_DRIFT_MIN = -0.15


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extended backtest for final candidates.")
    parser.add_argument(
        "--candidates",
        default="results/final_candidates_*.csv",
        help="Path or glob pattern to final_candidates CSV (default: results/final_candidates_*.csv).",
    )
    parser.add_argument("--equity-start", required=True, help="Start datetime (ISO, e.g. 2023-01-01).")
    parser.add_argument("--equity-end", required=True, help="End datetime (ISO, e.g. 2024-12-31).")
    parser.add_argument("--out", default="results", help="Output directory (default: results).")
    parser.add_argument("--ohlc", default="data/ohlc.csv", help="OHLC CSV path (default: data/ohlc.csv).")
    parser.add_argument(
        "--base-grid",
        default="config/param_grid_base.yaml",
        help="Base grid config (for default base_env values).",
    )
    parser.add_argument(
        "--pack-ts",
        help="If provided, generate results/README_<ts>.md and pack_<ts>.zip containing artefacts.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and report but skip heavy processing.")
    return parser.parse_args()


def read_candidates(glob_pattern: str) -> Dict[str, dict]:
    paths = sorted(Path(".").glob(glob_pattern))
    if not paths:
        raise FileNotFoundError(f"No final_candidates CSV matched pattern: {glob_pattern}")
    candidates: Dict[str, dict] = {}
    for path in paths:
        with path.open("r", newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                set_id = row.get("set_id")
                if not set_id:
                    continue
                # later files override earlier ones
                row["_source"] = str(path)
                candidates[set_id] = row
    return candidates


def parse_params(params_str: str) -> Dict[str, float]:
    params: Dict[str, float] = {}
    for part in params_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().upper()
        value = value.strip()
        if key == "RSI":
            up, dn = value.split("/")
            params["OB_RSI_UP"] = float(up)
            params["OB_RSI_DN"] = float(dn)
        elif key in {"KTP", "KSL"}:
            params[f"OB_{key}"] = float(value)
        elif key == "TREND":
            params["OB_TREND_SMA"] = float(value)
        else:
            params[key] = float(value)
    return params


def load_base_env(base_grid_path: Path) -> Dict[str, float]:
    config = load_grid_json(base_grid_path)
    env = config.get("base_env", {}) if isinstance(config, dict) else {}
    merged = {
        "OB_EQ": float(env.get("OB_EQ", EQ0_DEFAULT)),
        "OB_RISK": float(env.get("OB_RISK", RISK_DEFAULT)),
        "OB_MIN_TP": float(env.get("OB_MIN_TP", MIN_TP_DEFAULT)),
        "OB_MIN_SL": float(env.get("OB_MIN_SL", MIN_SL_DEFAULT)),
        "OB_SPREAD_PIPS": float(env.get("OB_SPREAD_PIPS", SPREAD_DEFAULT)),
        "OB_FEE_PIPS": float(env.get("OB_FEE_PIPS", FEE_DEFAULT)),
    }
    return merged


def load_ohlc(path: Path) -> List[dict]:
    rows: List[dict] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(
                {
                    "time": datetime.fromisoformat(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                }
            )
    return rows


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    gains: List[float] = []
    losses: List[float] = []
    rsis: List[Optional[float]] = []
    for idx, price in enumerate(values):
        if idx == 0:
            rsis.append(None)
            continue
        delta = price - values[idx - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
        if len(gains) < period:
            rsis.append(None)
            continue
        if len(gains) > period:
            gains.pop(0)
            losses.pop(0)
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            rsis.append(100.0)
            continue
        rs = avg_gain / avg_loss
        rsis.append(100.0 - 100.0 / (1.0 + rs))
    return rsis


def atr(series: List[dict], period: int = ATR_PERIOD) -> List[Optional[float]]:
    if not series:
        return []
    atr_values: List[Optional[float]] = [None] * len(series)
    prev_close = series[0]["close"]
    ema: Optional[float] = None
    alpha = 1.0 / period
    for idx in range(1, len(series)):
        high = series[idx]["high"]
        low = series[idx]["low"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ema = tr if ema is None else ema + alpha * (tr - ema)
        atr_values[idx] = ema
        prev_close = series[idx]["close"]
    return atr_values


def sma(values: List[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        return [None] * len(values)
    sums: List[Optional[float]] = []
    window: List[float] = []
    total = 0.0
    for v in values:
        window.append(v)
        total += v
        if len(window) > period:
            total -= window.pop(0)
        if len(window) == period:
            sums.append(total / period)
        else:
            sums.append(None)
    return sums


def simulate_bar(
    side: str,
    entry: float,
    atr_val: float,
    bar: dict,
    params: Dict[str, float],
) -> Tuple[float, str]:
    tp_pips = max(params["OB_MIN_TP"], atr_val * params["OB_KTP"] / PIP_SIZE)
    sl_pips = max(params["OB_MIN_SL"], atr_val * params["OB_KSL"] / PIP_SIZE)
    if side == "BUY":
        tp = entry + tp_pips * PIP_SIZE
        sl = entry - sl_pips * PIP_SIZE
        path = [bar["open"], bar["high"], bar["low"], bar["close"]]
    else:
        tp = entry - tp_pips * PIP_SIZE
        sl = entry + sl_pips * PIP_SIZE
        path = [bar["open"], bar["low"], bar["high"], bar["close"]]

    outcome = "CLOSE"
    exit_price = bar["close"]
    if side == "BUY":
        if min(path) <= sl <= max(path):
            outcome = "SL"
            exit_price = sl
        elif min(path) <= tp <= max(path):
            outcome = "TP"
            exit_price = tp
    else:
        if min(path) <= tp <= max(path):
            outcome = "TP"
            exit_price = tp
        elif min(path) <= sl <= max(path):
            outcome = "SL"
            exit_price = sl

    direction = 1 if side == "BUY" else -1
    pip_move = (exit_price - entry) * direction / PIP_SIZE
    return pip_move, outcome


@dataclass
class BacktestResult:
    set_id: str
    pf_ext: float
    avg_ret_ext: float
    max_dd_pct_ext: float
    max_dd_amt_ext: float
    pf_drift_ext: float
    dd_change_ext: float
    metrics_path: str
    equity_csv: str
    equity_png: Optional[str]
    trades_total: int
    win_rate: float
    accepted: bool
    reasons: Dict[str, bool]


def _to_float(value: Optional[object]) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _to_int(value: Optional[object]) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _git_snapshot(root: Path) -> Dict[str, object]:
    info: Dict[str, object] = {
        "available": False,
        "short_sha": None,
        "branch": None,
        "dirty": None,
        "changed": 0,
        "status_sample": [],
    }
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if sha:
            info["short_sha"] = sha
    except Exception:
        pass
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if branch:
            info["branch"] = branch
    except Exception:
        pass
    try:
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        lines = [line for line in status_out.splitlines() if line.strip()]
        info["available"] = True
        info["dirty"] = bool(lines)
        info["changed"] = len(lines)
        info["status_sample"] = lines[:10]
    except Exception:
        pass
    return info


def create_results_pack(
    pack_ts: str,
    out_dir: Path,
    results_summary: List[dict],
    equity_start: datetime,
    equity_end: datetime,
) -> dict:
    now = datetime.now()
    readme_path = out_dir / f"README_{pack_ts}.md"
    zip_path = out_dir / f"pack_{pack_ts}.zip"

    files_to_include: List[Path] = []
    missing: List[str] = []

    def normalise_path(path_like: Optional[object]) -> Optional[Path]:
        if path_like is None:
            return None
        if isinstance(path_like, Path):
            return path_like
        text = str(path_like).strip()
        if not text:
            return None
        return Path(text)

    def present_path(path: Path) -> str:
        for base in (out_dir, ROOT_DIR):
            try:
                return str(path.relative_to(base))
            except ValueError:
                continue
        return str(path)

    def add_file(path_like: Optional[object], required: bool = True) -> Optional[Path]:
        path = normalise_path(path_like)
        if path is None:
            if required:
                missing.append("(not provided)")
            return None
        if path.exists():
            files_to_include.append(path)
            return path
        if required:
            missing.append(present_path(path))
        return None

    def dedup_list(values: Sequence[str]) -> List[str]:
        seen = set()
        result: List[str] = []
        for item in values:
            if not item:
                continue
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

    candidate_paths = sorted(out_dir.glob(f"final_candidates_{pack_ts}*.csv"))
    primary_candidates_path = candidate_paths[-1] if candidate_paths else None
    if candidate_paths:
        for cand in candidate_paths:
            add_file(cand)
    else:
        for result in results_summary:
            add_file(result.get("source"), required=False)

    final_rows: Dict[str, dict] = {}
    for cand in candidate_paths:
        try:
            with cand.open("r", newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    set_id = (row.get("set_id") or "").strip()
                    if not set_id:
                        continue
                    row["_source"] = str(cand)
                    final_rows[set_id] = row
        except Exception:
            continue

    summary_path = add_file(out_dir / f"wf_stability_ext_summary_{pack_ts}.csv")
    add_file(out_dir / f"wf_stability_ext_{pack_ts}.csv", required=False)

    metrics_by_set: Dict[str, dict] = {}
    for result in results_summary:
        if result.get("dry_run"):
            continue
        metrics_path = add_file(result.get("metrics_json"))
        payload: Dict[str, object] = {}
        if metrics_path and metrics_path.exists():
            try:
                payload = json.loads(metrics_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
        metrics_by_set[result["set_id"]] = payload
        add_file(result.get("equity_csv"))
        add_file(result.get("equity_png"), required=False)

    run_meta_source = add_file(out_dir / f"run_meta_{pack_ts}.json", required=False)
    if run_meta_source is None:
        for cand in candidate_paths:
            suffix = cand.stem.replace("final_candidates_", "")
            if suffix:
                candidate_meta = add_file(out_dir / f"run_meta_{suffix}.json", required=False)
                if candidate_meta:
                    run_meta_source = candidate_meta
                    break
    if run_meta_source is None:
        try:
            latest_meta = max(out_dir.glob("run_meta_*.json"), key=lambda p: p.stat().st_mtime)
        except ValueError:
            latest_meta = None
        if latest_meta:
            run_meta_source = add_file(latest_meta, required=False)

    run_meta_data: Optional[dict] = None
    if run_meta_source and run_meta_source.exists():
        try:
            run_meta_data = json.loads(run_meta_source.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            run_meta_data = None

    params = dict(run_meta_data.get("params", {})) if run_meta_data else {}
    strict = dict(run_meta_data.get("validation", {}).get("strict", {})) if run_meta_data else {}
    stage_names: List[str] = []
    if run_meta_data:
        for entry in run_meta_data.get("generation", []):
            stage = entry.get("stage")
            if stage and stage not in stage_names:
                stage_names.append(stage)
    git_short_from_meta = run_meta_data.get("git_sha") if run_meta_data else None

    def normalise_cli_path(value: Optional[object]) -> Optional[str]:
        path = normalise_path(value)
        if path is None:
            return None
        return present_path(path)

    for key in ("out_dir", "base_grid", "aug_grid"):
        if key in params:
            normalised = normalise_cli_path(params.get(key))
            if normalised:
                params[key] = normalised

    git_info = _git_snapshot(ROOT_DIR)
    if not git_info.get("short_sha") and git_short_from_meta:
        git_info["short_sha"] = git_short_from_meta
    if git_info.get("available"):
        if git_info.get("dirty"):
            commit_label = f"コミット推奨 (未コミット{git_info.get('changed', 0)}件)"
        else:
            commit_label = "コミット不要"
    else:
        commit_label = "コミット判定不可 (git取得エラー)"

    git_snapshot = dict(git_info)
    git_snapshot["recommendation"] = commit_label

    summary_entries: List[Dict[str, object]] = []
    for result in results_summary:
        if result.get("dry_run"):
            continue
        set_id = result["set_id"]
        metrics_payload = metrics_by_set.get(set_id, {})
        final_row = final_rows.get(set_id, {})

        pf_40 = _to_float(final_row.get("AvgPF_40_60")) or _to_float(metrics_payload.get("pf_40_60"))
        trades_40 = _to_int(final_row.get("trades_40_60"))
        win_40 = _to_float(metrics_payload.get("win_rate_40_60"))
        maxdd_40 = _to_float(final_row.get("MaxDD_40_60")) or _to_float(metrics_payload.get("max_dd_40_60"))

        pf_ext = _to_float(result.get("pf_ext"))
        win_ext = _to_float(result.get("win_rate_ext")) or _to_float(metrics_payload.get("win_rate"))
        trades_ext = _to_int(result.get("trades_ext")) or _to_int(metrics_payload.get("trades_total"))
        maxdd_ext = _to_float(result.get("max_dd_pct_ext"))
        pf_drift = _to_float(result.get("pf_drift_ext"))
        dd_drift = _to_float(result.get("dd_change_ext"))

        summary_entries.append(
            {
                "set_id": set_id,
                "pf_40_60": pf_40,
                "win_40_60": win_40,
                "maxdd_40_60": maxdd_40,
                "trades_40_60": trades_40,
                "pf_ext": pf_ext,
                "win_ext": win_ext,
                "maxdd_ext": maxdd_ext,
                "trades_ext": trades_ext,
                "pf_drift": pf_drift,
                "dd_drift": dd_drift,
                "accepted": bool(result.get("accepted")),
            }
        )

    summary_entries.sort(key=lambda item: item["set_id"])

    def fmt_float(value: Optional[float], digits: int = 2, suffix: str = "") -> str:
        if value is None:
            return "--"
        return f"{value:.{digits}f}{suffix}"

    def fmt_trades(value: Optional[int]) -> str:
        if value is None:
            return "--"
        return f"{value:d}"

    pf_min = _to_float(strict.get("pf_min"))
    ret_min = _to_float(strict.get("ret_min"))
    dd_max = _to_float(strict.get("dd_max"))
    drift_min = _to_float(strict.get("pf_drift_min"))

    threshold_parts: List[str] = []
    if pf_min is not None:
        threshold_parts.append(f"PF ≥ {pf_min:.2f}")
    if ret_min is not None:
        threshold_parts.append(f"Ret ≥ {ret_min:.2f}")
    if dd_max is not None:
        threshold_parts.append(f"MaxDD ≤ {dd_max:.2f}")
    if drift_min is not None:
        threshold_parts.append(f"PF drift ≥ {drift_min:.2f}")

    n_min_val = params.get("n_min")
    trades_min_val = params.get("trades_min")
    stability_splits = params.get("stability_splits")
    validation_splits = params.get("validation_splits")

    stage_line = ", ".join(stage_names) if stage_names else "--"

    readme_lines: List[str] = []
    readme_lines.append(f"# 成果パック {pack_ts}")
    readme_lines.append("")
    readme_lines.append("## 実行条件")
    readme_lines.append(f"- 生成日時: {now.isoformat(timespec='seconds')}")
    readme_lines.append(f"- Equity期間: {equity_start.isoformat()} → {equity_end.isoformat()}")
    short_sha = git_info.get("short_sha") or git_short_from_meta or "--"
    branch = git_info.get("branch") or "--"
    readme_lines.append(f"- Git: {short_sha} (branch: {branch})")
    readme_lines.append(f"- コミット判定: {commit_label}")
    if git_info.get("dirty"):
        readme_lines.append(f"- 未コミット件数: {git_info.get('changed', 0)}")
    if threshold_parts:
        readme_lines.append("- Strict閾値: " + " / ".join(threshold_parts))
    else:
        readme_lines.append("- Strict閾値: 情報なし")
    readme_lines.append(
        "- N_min: {n} / Trades最小: {t}".format(
            n=n_min_val if n_min_val is not None else "--",
            t=trades_min_val if trades_min_val is not None else "--",
        )
    )
    readme_lines.append(f"- 使用グリッド段: {stage_line}")
    if isinstance(stability_splits, list) and stability_splits:
        readme_lines.append(f"- Stability Splits: {', '.join(str(s) for s in stability_splits)}")
    if isinstance(validation_splits, list) and validation_splits:
        readme_lines.append(f"- Validation Splits: {', '.join(str(s) for s in validation_splits)}")
    if params.get("out_dir"):
        readme_lines.append(f"- 出力ディレクトリ: {params['out_dir']}")
    if params.get("base_grid"):
        readme_lines.append(f"- Base Grid: {params['base_grid']}")
    if params.get("aug_grid"):
        readme_lines.append(f"- Aug Grid: {params['aug_grid']}")

    readme_lines.append("")
    readme_lines.append("## 要約表")
    if summary_entries:
        readme_lines.append(
            "| set_id | 40/60 PF | 40/60 Win% | 40/60 MaxDD% | 40/60 Trades | Extended PF | Extended Win% | Extended MaxDD% | Extended Trades | PF Drift | MaxDD Drift | 判定 |"
        )
        readme_lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for entry in summary_entries:
            readme_lines.append(
                "| {set_id} | {pf40} | {win40} | {dd40} | {tr40} | {pfext} | {winext} | {ddext} | {trext} | {pfd} | {ddd} | {status} |".format(
                    set_id=entry["set_id"],
                    pf40=fmt_float(entry["pf_40_60"]),
                    win40=fmt_float(entry["win_40_60"], 1, "%") if entry["win_40_60"] is not None else "--",
                    dd40=fmt_float(entry["maxdd_40_60"], 2, "%"),
                    tr40=fmt_trades(entry["trades_40_60"]),
                    pfext=fmt_float(entry["pf_ext"]),
                    winext=fmt_float(entry["win_ext"], 1, "%"),
                    ddext=fmt_float(entry["maxdd_ext"], 2, "%"),
                    trext=fmt_trades(entry["trades_ext"]),
                    pfd=fmt_float(entry["pf_drift"]),
                    ddd=fmt_float(entry["dd_drift"], 2, "%"),
                    status="PASS" if entry["accepted"] else "FAIL",
                )
            )
        readme_lines.append("")
        readme_lines.append("※ 40/60 Win% は集計未対応のため `--` 表示。")
    else:
        readme_lines.append("- 対象候補なし")

    repro_cmds: List[str] = []
    if params:
        runner_parts = ["pwsh workflow/stability_runner.ps1"]

        def add_runner_arg(flag: str, key: str, quote: bool = False) -> None:
            value = params.get(key)
            if value is None or value == "":
                return
            if isinstance(value, list):
                text = ",".join(str(v) for v in value)
            else:
                text = str(value)
            if not text:
                return
            needs_quote = quote or any(ch in text for ch in (" ", ",", "[", "]", "(", ")"))
            if needs_quote:
                text = f'"{text}"'
            runner_parts.append(f"{flag} {text}")

        add_runner_arg("-NMin", "n_min")
        add_runner_arg("-TradesMin", "trades_min")
        if "widening_levels" in params:
            add_runner_arg("-WideningLevels", "widening_levels", quote=True)
        if "stages" in params:
            add_runner_arg("-Stages", "stages", quote=True)
        add_runner_arg("-Out", "out_dir", quote=True)
        add_runner_arg("-BaseGrid", "base_grid", quote=True)
        add_runner_arg("-AugGrid", "aug_grid", quote=True)
        add_runner_arg("-MaxCombinations", "max_combinations")
        if params.get("dry_run"):
            runner_parts.append("-DryRun")
        if len(runner_parts) > 1:
            repro_cmds.append(" ".join(runner_parts))

    candidates_arg = present_path(primary_candidates_path) if primary_candidates_path else f"results/final_candidates_{pack_ts}.csv"
    ext_parts = [
        "python tools/extended_backtest.py",
        f"--candidates {candidates_arg}",
        f"--equity-start {equity_start.date().isoformat()}",
        f"--equity-end {equity_end.date().isoformat()}",
        f"--out {present_path(out_dir)}",
        f"--pack-ts {pack_ts}",
    ]
    if params.get("base_grid"):
        ext_parts.append(f"--base-grid {params['base_grid']}")
    ext_parts.append("--ohlc data/ohlc.csv")
    repro_cmds.append(" ".join(ext_parts))

    readme_lines.append("")
    readme_lines.append("## 再現手順（CLI例）")
    if repro_cmds:
        readme_lines.append("```pwsh")
        for cmd in repro_cmds:
            readme_lines.append(cmd)
        readme_lines.append("```")
    else:
        readme_lines.append("- 情報不足のため CLI 例を生成できませんでした。")

    missing = dedup_list(missing)

    base_readme_content = "\n".join(readme_lines) + "\n"
    readme_path.write_text(base_readme_content, encoding="utf-8")
    files_to_include.append(readme_path)

    pack_meta = {
        "timestamp": pack_ts,
        "generated_at": now.isoformat(timespec="seconds"),
        "equity_window": {
            "start": equity_start.isoformat(),
            "end": equity_end.isoformat(),
        },
        "git": git_snapshot,
        "params": params,
        "strict": strict,
        "stages": stage_names,
        "summary": summary_entries,
        "source_run_meta": str(run_meta_source) if run_meta_source else None,
        "missing": missing,
    }
    pack_meta_path = out_dir / f"run_meta_{pack_ts}.json"
    pack_meta_path.write_text(json.dumps(pack_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    files_to_include.append(pack_meta_path)

    unique_files: List[Path] = []
    seen_paths: set[Path] = set()
    for file_path in files_to_include:
        try:
            resolved = file_path.resolve()
        except OSError:
            resolved = file_path
        if resolved in seen_paths:
            continue
        if file_path.exists():
            seen_paths.add(resolved)
            unique_files.append(file_path)

    included_names = [path.name for path in unique_files]

    files_section: List[str] = []
    files_section.append("")
    files_section.append("## 同梱ファイル")
    if included_names:
        for name in included_names:
            files_section.append(f"- {name}")
    else:
        files_section.append("- (なし)")
    if missing:
        files_section.append("")
        files_section.append("## 欠損ファイル")
        for item in missing:
            files_section.append(f"- {item}")

    final_readme_lines = readme_lines + files_section
    readme_path.write_text("\n".join(final_readme_lines) + "\n", encoding="utf-8")

    pack_meta["files_included"] = included_names
    pack_meta["files_included_count"] = len(included_names)
    pack_meta["missing"] = missing
    pack_meta_path.write_text(json.dumps(pack_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w") as zf:
        for file_path in unique_files:
            zf.write(file_path, arcname=file_path.name)

    pack_info: Dict[str, object] = {
        "timestamp": pack_ts,
        "zip": str(zip_path),
        "readme": str(readme_path),
        "run_meta": str(pack_meta_path),
        "files_included": included_names,
        "missing": missing,
        "git": git_snapshot,
        "summary": summary_entries,
        "commit_recommendation": commit_label,
    }
    if run_meta_source:
        pack_info["source_run_meta"] = str(run_meta_source)
    if summary_path:
        pack_info["summary_csv"] = str(summary_path)

    return pack_info


def quantiles(values: Sequence[float]) -> Tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    sorted_vals = sorted(values)
    def percentile(p: float) -> float:
        if len(sorted_vals) == 1:
            return sorted_vals[0]
        k = (len(sorted_vals) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        d0 = sorted_vals[f] * (c - k)
        d1 = sorted_vals[c] * (k - f)
        return d0 + d1
    return (
        percentile(0.10),
        percentile(0.50),
        percentile(0.90),
    )


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def run_backtest(
    set_id: str,
    params: Dict[str, float],
    rows: List[dict],
    start: datetime,
    end: datetime,
    base_env: Dict[str, float],
    out_dir: Path,
    pf_40_60: float,
    maxdd_40_60: float,
) -> BacktestResult:
    eq0 = base_env["OB_EQ"]
    risk = base_env["OB_RISK"]
    min_tp = base_env["OB_MIN_TP"]
    min_sl = base_env["OB_MIN_SL"]
    spread = base_env["OB_SPREAD_PIPS"]
    fee = base_env["OB_FEE_PIPS"]

    params = params.copy()
    params["OB_MIN_TP"] = min_tp
    params["OB_MIN_SL"] = min_sl

    closes = [row["close"] for row in rows]
    atr_values = atr(rows, ATR_PERIOD)
    rsi_values = rsi(closes, 14)
    trend_values = sma(closes, int(params.get("OB_TREND_SMA", 0))) if params.get("OB_TREND_SMA", 0) > 0 else [None] * len(rows)

    equity = eq0
    peak = eq0
    max_dd_pct = 0.0
    max_dd_amt = 0.0

    trade_records: List[dict] = []
    equity_series: List[Tuple[datetime, float, float]] = []

    for idx in range(1, len(rows)):
        bar = rows[idx]
        now = bar["time"]
        if now < start:
            continue
        if now > end:
            break
        atr_val = atr_values[idx]
        if atr_val is None or atr_val <= 0.0:
            equity_series.append((now, equity, peak - equity))
            continue
        rsi_curr = rsi_values[idx]
        rsi_prev = rsi_values[idx - 1]
        if rsi_prev is None or rsi_curr is None:
            equity_series.append((now, equity, peak - equity))
            continue
        side: Optional[str] = None
        if rsi_prev < params["OB_RSI_UP"] <= rsi_curr:
            side = "BUY"
        elif rsi_prev > params["OB_RSI_DN"] >= rsi_curr:
            side = "SELL"
        if side is None:
            equity_series.append((now, equity, peak - equity))
            continue
        if params.get("OB_TREND_SMA", 0) > 0 and trend_values[idx - 1] is not None:
            trend = trend_values[idx - 1]
            prev_close = rows[idx - 1]["close"]
            if side == "BUY" and prev_close < trend:
                equity_series.append((now, equity, peak - equity))
                continue
            if side == "SELL" and prev_close > trend:
                equity_series.append((now, equity, peak - equity))
                continue

        entry = bar["close"]
        pip_result, outcome = simulate_bar(side, entry, atr_val, bar, params)
        pip_result -= (spread + fee)
        risk_pips = max(min_sl, atr_val * params["OB_KSL"] / PIP_SIZE)
        size = max((equity * risk) / risk_pips, 0.01)
        pnl = pip_result * size
        equity_before = equity
        equity += pnl
        peak = max(peak, equity)
        dd_amt = peak - equity
        if peak > 0:
            dd_pct = dd_amt / peak * 100.0
            max_dd_pct = max(max_dd_pct, dd_pct)
        else:
            dd_pct = 0.0
        max_dd_amt = max(max_dd_amt, dd_amt)

        r_multiple = (pip_result / risk_pips) if risk_pips > 0 else 0.0
        trade_records.append(
            {
                "time": now.isoformat(),
                "side": side,
                "pips": pip_result,
                "size": size,
                "pnl": pnl,
                "r_multiple": r_multiple,
                "outcome": outcome,
                "equity_before": equity_before,
                "equity_after": equity,
                "drawdown": dd_amt,
                "drawdown_pct": dd_pct,
            }
        )
        equity_series.append((now, equity, dd_amt))

    # If no equity records, add final snapshot
    if not equity_series:
        equity_series.append((end, equity, peak - equity))

    pnl_values = [t["pnl"] for t in trade_records]
    wins = [p for p in pnl_values if p > 0]
    losses = [-p for p in pnl_values if p < 0]
    gross_profit = sum(wins)
    gross_loss = sum(losses)
    trades_total = len(trade_records)
    pf_ext = gross_profit / gross_loss if gross_loss > 0 else (1e9 if gross_profit > 0 else 0.0)
    win_rate = (len(wins) / trades_total * 100.0) if trades_total > 0 else 0.0
    net_profit = sum(pnl_values)
    avg_return_pct = ((equity / eq0) - 1.0) * 100.0
    max_dd_pct_ext = max_dd_pct
    max_dd_amt_ext = max_dd_amt

    r_values = [t["r_multiple"] for t in trade_records]
    dist_p10, dist_p50, dist_p90 = quantiles(pnl_values)

    monthly = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    for trade, pnl in zip(trade_records, pnl_values):
        dt = datetime.fromisoformat(trade["time"])
        key = month_key(dt)
        monthly[key]["pnl"] += pnl
        monthly[key]["trades"] += 1
        if pnl > 0:
            monthly[key]["wins"] += 1
    monthly_table = []
    for key in sorted(monthly.keys()):
        info = monthly[key]
        trades = info["trades"]
        wins_month = info["wins"]
        monthly_table.append(
            {
                "month": key,
                "pnl": info["pnl"],
                "trades": trades,
                "win_rate": (wins_month / trades * 100.0) if trades else 0.0,
            }
        )

    pf_drift_ext = pf_ext - pf_40_60
    dd_change_ext = max_dd_pct_ext - maxdd_40_60

    equity_csv_path = out_dir / f"equity_{set_id}_{start.date()}_{end.date()}.csv"
    with equity_csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time", "equity", "drawdown"])
        for time_point, eq_val, dd_amt_val in equity_series:
            writer.writerow([time_point.isoformat(), f"{eq_val:.2f}", f"{dd_amt_val:.2f}"])

    equity_png_path: Optional[Path] = out_dir / f"equity_{set_id}_{start.date()}_{end.date()}.png"
    try:
        plot_equity_chart(equity_series, set_id, equity_png_path)
    except Exception:
        equity_png_path = None

    metrics_path = out_dir / f"metrics_{set_id}_{start.date()}_{end.date()}.json"
    metrics = {
        "set_id": set_id,
        "pf_ext": pf_ext,
        "avg_return_pct_ext": avg_return_pct,
        "max_dd_pct_ext": max_dd_pct_ext,
        "max_dd_amount_ext": max_dd_amt_ext,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "trades_total": trades_total,
        "win_rate": win_rate,
        "average_r": statistics.mean(r_values) if r_values else 0.0,
        "return_distribution": {"p10": dist_p10, "p50": dist_p50, "p90": dist_p90},
        "monthly": monthly_table,
        "pf_drift_ext": pf_drift_ext,
        "dd_change_ext": dd_change_ext,
        "pf_40_60": pf_40_60,
        "max_dd_40_60": maxdd_40_60,
        "final_equity": equity,
        "net_profit": net_profit,
    }
    with metrics_path.open("w", encoding="utf-8") as fh:
        json.dump(metrics, fh, ensure_ascii=False, indent=2)

    reasons = {
        "pf": pf_ext >= PF_MIN,
        "avg_return": avg_return_pct >= AVGRET_MIN,
        "max_dd": max_dd_pct_ext <= MAXDD_MAX,
        "pf_drift": pf_drift_ext >= PF_DRIFT_MIN,
    }
    accepted = all(reasons.values())

    return BacktestResult(
        set_id=set_id,
        pf_ext=pf_ext,
        avg_ret_ext=avg_return_pct,
        max_dd_pct_ext=max_dd_pct_ext,
        max_dd_amt_ext=max_dd_amt_ext,
        pf_drift_ext=pf_drift_ext,
        dd_change_ext=dd_change_ext,
        metrics_path=str(metrics_path),
        equity_csv=str(equity_csv_path),
        equity_png=str(equity_png_path) if equity_png_path else None,
        trades_total=trades_total,
        win_rate=win_rate,
        accepted=accepted,
        reasons=reasons,
    )


def plot_equity_chart(series: List[Tuple[datetime, float, float]], set_id: str, path: Path) -> None:
    if plt is None or mdates is None:  # matplotlib not available
        return
    times = [point[0] for point in series]
    equities = [point[1] for point in series]
    drawdowns = [point[2] for point in series]
    fig, (ax_eq, ax_dd) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax_eq.plot(times, equities, color="steelblue", label="Equity")
    ax_eq.set_ylabel("Equity")
    ax_eq.set_title(f"Extended Equity Curve (set {set_id})")
    ax_eq.grid(True, alpha=0.3)
    ax_eq.legend(loc="upper left")

    ax_dd.fill_between(times, drawdowns, color="firebrick", alpha=0.4)
    ax_dd.set_ylabel("Drawdown")
    ax_dd.set_xlabel("Time")
    ax_dd.grid(True, alpha=0.3)

    locator = mdates.AutoDateLocator()
    formatter = mdates.ConciseDateFormatter(locator)
    ax_dd.xaxis.set_major_locator(locator)
    ax_dd.xaxis.set_major_formatter(formatter)

    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_dt = datetime.fromisoformat(args.equity_start)
    end_dt = datetime.fromisoformat(args.equity_end)
    if start_dt >= end_dt:
        raise ValueError("equity-start must be earlier than equity-end")

    candidates = read_candidates(args.candidates)
    rows = load_ohlc(Path(args.ohlc))
    base_env = load_base_env(Path(args.base_grid))

    results_summary: List[dict] = []
    for set_id, row in candidates.items():
        params = parse_params(row["params"])
        pf_40_60 = float(row.get("AvgPF_40_60", 0.0))
        maxdd_40_60 = float(row.get("MaxDD_40_60", 0.0))
        if args.dry_run:
            results_summary.append(
                {
                    "set_id": set_id,
                    "dry_run": True,
                    "source": row.get("_source"),
                }
            )
            continue

        result = run_backtest(
            set_id=set_id,
            params=params,
            rows=rows,
            start=start_dt,
            end=end_dt,
            base_env=base_env,
            out_dir=out_dir,
            pf_40_60=pf_40_60,
            maxdd_40_60=maxdd_40_60,
        )
        results_summary.append(
            {
                "set_id": set_id,
                "pf_ext": result.pf_ext,
                "avg_ret_ext": result.avg_ret_ext,
                "max_dd_pct_ext": result.max_dd_pct_ext,
                "pf_drift_ext": result.pf_drift_ext,
                "dd_change_ext": result.dd_change_ext,
                "trades_ext": result.trades_total,
                "win_rate_ext": result.win_rate,
                "accepted": result.accepted,
                "reasons": result.reasons,
                "metrics_json": result.metrics_path,
                "equity_csv": result.equity_csv,
                "equity_png": result.equity_png,
                "source": row.get("_source"),
            }
        )

    pack_info = None
    if args.pack_ts and not args.dry_run:
        pack_info = create_results_pack(
            args.pack_ts,
            out_dir,
            results_summary,
            start_dt,
            end_dt,
        )

    output = {"extended_results": results_summary}
    if pack_info:
        output["pack"] = pack_info
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
