from __future__ import annotations

import argparse
import csv
import os
import pathlib
import sys
from typing import Sequence

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gate.papertrade import load_trades_with_fallback, sort_rows  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate trade logs into metrics.csv")
    parser.add_argument("--root", default="metrics", help="Output directory (default: metrics)")
    parser.add_argument("--case", required=True, help="Case identifier (e.g. 20250101_USDJPY_M15)")
    parser.add_argument("--seed", type=int, default=1729, help="Unused seed kept for backward compatibility")
    parser.add_argument("--logs", nargs="+", required=True, help="Primary log files for the case")
    parser.add_argument(
        "--initial_equity",
        type=float,
        default=float(os.environ.get("INITIAL_EQUITY", "50000")),
        help="Starting equity used for drawdown calculations",
    )
    parser.add_argument(
        "--lookback_days",
        type=int,
        default=int(os.environ.get("PAPER_METRICS_LOOKBACK_DAYS", "60")),
        help="Additional lookback window (days) if min_trades not met",
    )
    parser.add_argument("--min_trades", type=int, default=30, help="Required minimum trades")
    return parser.parse_args()


def ensure_header(path: pathlib.Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(["case", "net", "win", "dd", "trades"])


def append_row(path: pathlib.Path, case: str, metrics) -> None:
    with path.open("a", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerow(
            [
                case,
                f"{metrics.net_pnl:.2f}",
                f"{metrics.win_rate:.4f}",
                f"{metrics.max_dd_pct:.4f}",
                metrics.trades,
            ]
        )


def main() -> int:
    args = parse_args()
    out_dir = pathlib.Path(args.root)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "metrics.csv"

    rows, used_files = load_trades_with_fallback(
        log_files=args.logs,
        case=args.case,
        lookback_days=max(args.lookback_days, 0),
        min_trades=max(args.min_trades, 0),
    )
    rows = sort_rows(rows)

    if not rows:
        print("ERROR: no trades found in provided logs or fallback window:", file=sys.stderr)
        for log in args.logs:
            print(f"  {log}", file=sys.stderr)
        return 2

    from gate.papertrade import rows_to_metrics  # import lazily to avoid cycles

    metrics = rows_to_metrics(rows, args.initial_equity)
    if metrics.trades == 0:
        print("ERROR: trades loaded but trade count is zero after filtering.", file=sys.stderr)
        return 2

    if not csv_path.exists():
        ensure_header(csv_path)
    append_row(csv_path, args.case, metrics)

    used: Sequence[str] = [str(path) for path in used_files]
    print(
        f"Wrote {csv_path} -> case={args.case} net={metrics.net_pnl:.2f} "
        f"win={metrics.win_rate:.4f} dd={metrics.max_dd_pct:.4f} trades={metrics.trades}"
    )
    if used:
        print("Used log files: " + ", ".join(used))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
