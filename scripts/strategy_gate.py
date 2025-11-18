from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-strategy stability gate.")
    parser.add_argument("--stats", required=True, help="Path to strategy_stats.csv")
    parser.add_argument("--strategies", default="configs/strategies.yaml", help="Path to strategies.yaml")
    parser.add_argument("--net-min", type=float, default=0.0, help="Per-strategy minimum net_jpy")
    parser.add_argument("--win-min", type=float, default=45.0, help="Per-strategy minimum win_rate_pct")
    parser.add_argument("--dd-max", type=float, default=20.0, help="Per-strategy maximum drawdown pct")
    parser.add_argument("--trades-min", type=float, default=30.0, help="Per-strategy minimum trade count")
    parser.add_argument("--total-net-min", type=float, default=0.0, help="Portfolio-level minimum net_jpy")
    return parser.parse_args()


def load_enabled_strategies(path: Path) -> Dict[str, str]:
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


def find_value(row: Dict[str, str], columns: List[str]) -> float:
    for col in columns:
        if col in row and row[col] not in (None, ""):
            try:
                return float(row[col])
            except ValueError:
                pass
    raise ValueError(f"Missing columns {columns} in row {row}")


def main() -> int:
    args = parse_args()
    stats_path = Path(args.stats)
    names = load_enabled_strategies(Path(args.strategies))
    enabled_ids = set(names.keys())

    with stats_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    present_ids = set()
    failures: List[str] = []
    portfolio_net = 0.0

    for row in rows:
        sid = row.get("strategy_id")
        if not sid:
            continue
        if sid == "aggregate":
            try:
                portfolio_net = find_value(row, ["net_jpy", "total_net_jpy"])
            except ValueError:
                pass
            continue
        if sid not in enabled_ids:
            continue
        present_ids.add(sid)
        try:
            net = find_value(row, ["net_jpy", "total_net_jpy"])
            win = find_value(row, ["win_rate_pct", "total_win_rate_pct"])
            dd = find_value(row, ["max_drawdown_pct", "total_max_drawdown_pct"])
            trades = find_value(row, ["trades", "total_trades"])
        except ValueError as exc:
            failures.append(f"{sid}: missing metric columns ({exc})")
            continue

        local_fail = []
        if net < args.net_min:
            local_fail.append(f"net_jpy {net:.2f} < {args.net_min}")
        if win < args.win_min:
            local_fail.append(f"win_rate_pct {win:.2f} < {args.win_min}")
        if dd > args.dd_max:
            local_fail.append(f"max_drawdown_pct {dd:.2f} > {args.dd_max}")
        if trades < args.trades_min:
            local_fail.append(f"trades {trades:.0f} < {args.trades_min}")

        if local_fail:
            name = names.get(sid, sid)
            failures.append(f"{name} ({sid}): " + "; ".join(local_fail))

    missing = enabled_ids - present_ids
    if missing:
        failures.append(f"Missing stats for strategies: {', '.join(sorted(missing))}")

    if portfolio_net < args.total_net_min:
        failures.append(
            f"Portfolio net_jpy {portfolio_net:.2f} < total_net_min {args.total_net_min}"
        )

    if failures:
        print("=== Strategy Gate FAIL ===")
        for entry in failures:
            print(f"- {entry}")
        return 1

    print(
        f"Strategy gate PASS (net>={args.net_min}, win>={args.win_min}, "
        f"dd<={args.dd_max}, trades>={args.trades_min}, total_net>={args.total_net_min})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
