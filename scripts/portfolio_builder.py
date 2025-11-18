from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build portfolio suggestion from strategy_stats.")
    parser.add_argument("--stats", required=True, help="Path to strategy_stats.csv")
    parser.add_argument("--strategies", default="configs/strategies.yaml", help="Path to strategies.yaml")
    parser.add_argument(
        "--out", default="artifacts/backtest_matrix/portfolio_suggestion.yaml", help="Output YAML file"
    )
    parser.add_argument("--top-k", type=int, default=3, help="Number of strategies to include")
    parser.add_argument("--w-net", type=float, default=0.5, help="Weight for net")
    parser.add_argument("--w-win", type=float, default=0.3, help="Weight for win rate")
    parser.add_argument("--w-dd", type=float, default=0.2, help="Weight for drawdown (lower is better)")
    return parser.parse_args()


def load_enabled_strategies(path: Path) -> Dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
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


def detect_columns(fieldnames: List[str]) -> Tuple[str, str, str, str]:
    lowered = {name.lower(): name for name in fieldnames}

    def find(keywords: Iterable[str]) -> str:
        for raw in fieldnames:
            lower = raw.lower()
            if any(keyword in lower for keyword in keywords):
                return raw
        raise ValueError(f"Unable to detect column for keywords: {keywords}, fields={fieldnames}")

    net_col = find(["net"])
    win_col = find(["win"])
    dd_col = find(["dd", "drawdown"])
    trades_col = find(["trade"])
    return net_col, win_col, dd_col, trades_col


def normalize(values: Dict[str, float], higher_is_better: bool) -> Dict[str, float]:
    if not values:
        return {}
    vals = list(values.values())
    vmin = min(vals)
    vmax = max(vals)
    if abs(vmax - vmin) < 1e-9:
        return {k: 0.5 for k in values}
    result: Dict[str, float] = {}
    for sid, val in values.items():
        ratio = (val - vmin) / (vmax - vmin)
        result[sid] = ratio if higher_is_better else 1 - ratio
    return result


def main() -> int:
    args = parse_args()
    stats_path = Path(args.stats)
    names = load_enabled_strategies(Path(args.strategies))
    enabled_ids = set(names.keys())

    with stats_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        net_col, win_col, dd_col, trades_col = detect_columns(reader.fieldnames or [])
        rows = list(reader)

    metrics_net: Dict[str, float] = {}
    metrics_win: Dict[str, float] = {}
    metrics_dd: Dict[str, float] = {}
    metrics_trades: Dict[str, float] = {}

    for row in rows:
        sid = row.get("strategy_id")
        if not sid or sid == "aggregate" or (enabled_ids and sid not in enabled_ids):
            continue
        try:
            net = float(row.get(net_col, 0) or 0)
            win = float(row.get(win_col, 0) or 0)
            dd = float(row.get(dd_col, 0) or 0)
            trades = float(row.get(trades_col, 0) or 0)
        except ValueError:
            continue
        metrics_net[sid] = net
        metrics_win[sid] = win
        metrics_dd[sid] = dd
        metrics_trades[sid] = trades

    net_norm = normalize(metrics_net, higher_is_better=True)
    win_norm = normalize(metrics_win, higher_is_better=True)
    dd_norm = normalize(metrics_dd, higher_is_better=False)

    scores: List[Tuple[float, str]] = []
    for sid in metrics_net.keys():
        score = (
            args.w_net * net_norm.get(sid, 0.0)
            + args.w_win * win_norm.get(sid, 0.0)
            + args.w_dd * dd_norm.get(sid, 0.0)
        )
        scores.append((score, sid))
    scores.sort(reverse=True)

    if args.top_k > 0:
        selected = scores[: min(args.top_k, len(scores))]
    else:
        selected = scores

    if not selected:
        print("No strategies available for portfolio suggestion.")
        return 0

    weight = 1.0 / len(selected)
    portfolio = []
    for score, sid in selected:
        portfolio.append(
            {
                "id": sid,
                "name": names.get(sid, sid),
                "weight": round(weight, 4),
                "score": round(score, 4),
                "net_jpy": metrics_net.get(sid, 0.0),
                "win_rate_pct": metrics_win.get(sid, 0.0),
                "max_drawdown_pct": metrics_dd.get(sid, 0.0),
                "trades": metrics_trades.get(sid, 0.0),
            }
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "portfolio": {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "scoring": {
                "w_net": args.w_net,
                "w_win": args.w_win,
                "w_dd": args.w_dd,
                "top_k": args.top_k,
            },
            "strategies": portfolio,
        }
    }
    out_path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    print("=== Portfolio Suggestion ===")
    for entry in portfolio:
        print(
            f"- {entry['name']} ({entry['id']}): weight={entry['weight']}, "
            f"score={entry['score']}, net={entry['net_jpy']}, win={entry['win_rate_pct']}%, "
            f"dd={entry['max_drawdown_pct']}%, trades={entry['trades']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
