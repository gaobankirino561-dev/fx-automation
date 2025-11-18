from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backtests for all enabled strategies.")
    parser.add_argument("--strategies", default="configs/strategies.yaml", help="Path to strategies.yaml")
    parser.add_argument("--out-dir", default="artifacts/backtest_matrix", help="Directory for aggregated artifacts")
    parser.add_argument("--runner", default="run_backtest.py", help="Single-strategy backtest runner")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to invoke runner")
    return parser.parse_args()


def load_strategies(path: Path) -> List[Dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, dict):
        items = data.get("strategies")
        if items is None:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        items = []
    result: List[Dict[str, Any]] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        entry.setdefault("enabled_backtest", True)
        result.append(entry)
    return result


def ensure_metrics_csv(path: Path, metrics: Dict[str, float], strategy_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["metric", "value", "strategy_id"])
        writer.writeheader()
        for key, value in metrics.items():
            writer.writerow({"metric": key, "value": f"{value:.6f}", "strategy_id": strategy_id})


def convert_json_to_metrics(raw: Dict[str, Any]) -> Dict[str, float]:
    net = float(raw.get("net_profit") or raw.get("net_jpy") or 0.0)
    win = float(raw.get("win_rate") or raw.get("win_rate_pct") or 0.0)
    if win <= 1:
        win *= 100.0
    dd = float(raw.get("max_drawdown") or raw.get("max_drawdown_pct") or 0.0)
    if dd <= 1:
        dd *= 100.0
    trades = float(raw.get("trades") or raw.get("trade_count") or 0.0)
    return {
        "net_jpy": net,
        "win_rate_pct": win,
        "max_drawdown_pct": dd,
        "trades": trades,
    }


def write_merged(metrics_rows: Iterable[Dict[str, str]], out_file: Path) -> None:
    rows = list(metrics_rows)
    if not rows:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=["metric", "value", "strategy_id"]).writeheader()
        return
    fieldnames = ["metric", "value", "strategy_id"]
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def run_backtest(python_exe: str, runner: str, cfg_path: Path, out_path: Path) -> None:
    cmd = [python_exe, runner, "--config", str(cfg_path), "--out", str(out_path)]
    subprocess.run(cmd, check=True)


def main() -> int:
    args = parse_args()
    strategies_path = Path(args.strategies)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    strategies = load_strategies(strategies_path)
    merged_rows: List[Dict[str, str]] = []
    total_net = 0.0
    total_trades = 0.0
    total_wins = 0.0
    max_dd = 0.0

    for entry in strategies:
        if not entry.get("enabled_backtest", True):
            continue
        sid = entry.get("id")
        cfg = entry.get("backtest_config")
        if not sid or not cfg:
            continue
        cfg_path = Path(cfg)
        strategy_out = out_dir / sid
        strategy_out.mkdir(parents=True, exist_ok=True)
        metrics_json = strategy_out / "metrics.json"

        run_backtest(args.python, args.runner, cfg_path, metrics_json)

        raw = json.loads(metrics_json.read_text(encoding="utf-8"))
        metrics = convert_json_to_metrics(raw)
        ensure_metrics_csv(strategy_out / "metrics.csv", metrics, sid)

        wins = (metrics["win_rate_pct"] / 100.0) * metrics["trades"]
        total_net += metrics["net_jpy"]
        total_trades += metrics["trades"]
        total_wins += wins
        max_dd = max(max_dd, metrics["max_drawdown_pct"])

        for key, value in metrics.items():
            merged_rows.append(
                {
                    "metric": f"{sid}.{key}",
                    "value": f"{value:.6f}",
                    "strategy_id": sid,
                }
            )

    if total_trades > 0:
        total_win_rate = (total_wins / total_trades) * 100.0
    else:
        total_win_rate = 0.0
    merged_rows.extend(
        [
            {"metric": "total_net_jpy", "value": f"{total_net:.6f}", "strategy_id": "aggregate"},
            {"metric": "total_win_rate_pct", "value": f"{total_win_rate:.6f}", "strategy_id": "aggregate"},
            {"metric": "total_max_drawdown_pct", "value": f"{max_dd:.6f}", "strategy_id": "aggregate"},
            {"metric": "total_trades", "value": f"{total_trades:.6f}", "strategy_id": "aggregate"},
            {"metric": "net_jpy", "value": f"{total_net:.6f}", "strategy_id": "aggregate"},
            {"metric": "win_rate_pct", "value": f"{total_win_rate:.6f}", "strategy_id": "aggregate"},
            {"metric": "max_drawdown_pct", "value": f"{max_dd:.6f}", "strategy_id": "aggregate"},
            {"metric": "trades", "value": f"{total_trades:.6f}", "strategy_id": "aggregate"},
        ]
    )

    write_merged(merged_rows, out_dir / "metrics_multi.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
