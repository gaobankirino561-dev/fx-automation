from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build per-strategy stats from metrics_multi.csv.")
    parser.add_argument("--metrics", required=True, help="Path to metrics_multi.csv")
    parser.add_argument("--strategies", default="configs/strategies.yaml", help="Path to strategies.yaml")
    parser.add_argument("--out-dir", default="artifacts/backtest_matrix", help="Directory for output stats")
    return parser.parse_args()


def load_metrics(path: Path) -> Dict[str, Dict[str, float]]:
    stats: Dict[str, Dict[str, float]] = defaultdict(dict)
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            metric = row.get("metric")
            strategy_id = row.get("strategy_id") or "unknown"
            value_raw = row.get("value", "")
            if not metric:
                continue
            if "." in metric:
                prefix, rest = metric.split(".", 1)
                if prefix == strategy_id:
                    metric = rest
            try:
                value = float(value_raw)
            except (TypeError, ValueError):
                value = value_raw
            stats[strategy_id][metric] = value
    return stats


def load_strategy_names(path: Path) -> Dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    strategies: Iterable[Dict[str, Any]]
    if isinstance(data, dict):
        strategies = data.get("strategies") or []
    elif isinstance(data, list):
        strategies = data
    else:
        strategies = []
    mapping: Dict[str, str] = {}
    for item in strategies:
        if not isinstance(item, dict):
            continue
        if not item.get("enabled_backtest", True):
            continue
        sid = item.get("id")
        if not sid:
            continue
        mapping[sid] = item.get("name") or sid
    return mapping


def core_metrics(metric_dict: Dict[str, float]) -> Dict[str, float]:
    return {
        "net_jpy": metric_dict.get("net_jpy", metric_dict.get("total_net_jpy", 0.0)),
        "win_rate_pct": metric_dict.get("win_rate_pct", metric_dict.get("total_win_rate_pct", 0.0)),
        "max_drawdown_pct": metric_dict.get("max_drawdown_pct", metric_dict.get("total_max_drawdown_pct", 0.0)),
        "trades": metric_dict.get("trades", metric_dict.get("total_trades", 0.0)),
    }


def write_csv(stats: Dict[str, Dict[str, float]], names: Dict[str, str], out_path: Path) -> List[str]:
    keys = list(core_metrics({}).keys())

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["strategy_id", "strategy_name"] + keys
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for sid, metric_dict in stats.items():
            core = core_metrics(metric_dict)
            row = {"strategy_id": sid, "strategy_name": names.get(sid, sid)}
            row.update({k: core.get(k, "") for k in keys})
            writer.writerow(row)
    return keys


def write_json(stats: Dict[str, Dict[str, float]], names: Dict[str, str], keys: List[str], out_path: Path) -> None:
    rows = []
    for sid, metric_dict in stats.items():
        core = core_metrics(metric_dict)
        row = {"strategy_id": sid, "strategy_name": names.get(sid, sid)}
        for key in keys:
            row[key] = core.get(key)
        rows.append(row)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)


def print_leaderboard(stats: Dict[str, Dict[str, float]], names: Dict[str, str]) -> None:
    print("=== Strategy Leaderboard (by net_jpy) ===")
    entries = []
    for sid, metric_dict in stats.items():
        core = core_metrics(metric_dict)
        net = core.get("net_jpy") or 0.0
        try:
            net_val = float(net)
        except (TypeError, ValueError):
            net_val = 0.0
        entries.append((net_val, sid, core))
    entries.sort(key=lambda x: x[0], reverse=True)
    for rank, (_, sid, core) in enumerate(entries, start=1):
        name = names.get(sid, sid)
        print(
            f"{rank:>2}) {name} ({sid})  net={core.get('net_jpy', 0)} "
            f"win={core.get('win_rate_pct', 0)}%  dd={core.get('max_drawdown_pct', 0)}% "
            f"trades={core.get('trades', 0)}"
        )


def main() -> int:
    args = parse_args()
    metrics_path = Path(args.metrics)
    strategies_path = Path(args.strategies)
    out_dir = Path(args.out_dir)

    stats = load_metrics(metrics_path)
    names = load_strategy_names(strategies_path)
    keys = write_csv(stats, names, out_dir / "strategy_stats.csv")
    write_json(stats, names, keys, out_dir / "strategy_stats.json")
    print_leaderboard(stats, names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
