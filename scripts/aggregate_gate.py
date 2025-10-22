from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gate.report import GateReport, GateThresholds, build_report, render_csv, render_markdown  # noqa: E402


def _parse_as_of(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid --as-of value {value!r}; expected YYYYMMDD"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate gate metrics from logs.")
    parser.add_argument("--logs-dir", default="papertrade/logs", help="Directory containing trade logs")
    parser.add_argument("--output-dir", default="metrics", help="Destination directory for artifacts")
    parser.add_argument("--cases", nargs="+", help="Restrict aggregation to specific case suffixes")
    parser.add_argument("--lookback-days", type=int, default=60, help="Lookback window in days")
    parser.add_argument("--initial-equity", type=float, default=50000.0, help="Initial equity for drawdown calcs")
    parser.add_argument("--as-of", type=str, help="Anchor date (YYYYMMDD). Defaults to latest available")
    parser.add_argument("--min-net", type=float, default=0.0, help="Minimum net PnL threshold")
    parser.add_argument("--min-win", type=float, default=0.45, help="Minimum win rate threshold")
    parser.add_argument("--max-dd", type=float, default=0.20, help="Maximum drawdown threshold")
    parser.add_argument("--min-trades", type=int, default=30, help="Minimum trade count threshold")
    parser.add_argument("--no-markdown", action="store_true", help="Skip Markdown report emission")
    parser.add_argument("--no-csv", action="store_true", help="Skip CSV report emission")
    parser.add_argument(
        "--kill-switch",
        action="store_true",
        help="Exit with code 1 if overall status is FAIL",
    )
    return parser.parse_args()


def write_outputs(
    output_dir: pathlib.Path,
    report: GateReport,
    emit_markdown: bool,
    emit_csv: bool,
) -> List[pathlib.Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: List[pathlib.Path] = []

    json_path = output_dir / "gate_report.json"
    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(report.to_dict(), fh, ensure_ascii=False, indent=2)
    paths.append(json_path)

    if emit_markdown:
        md_path = output_dir / "gate_report.md"
        with md_path.open("w", encoding="utf-8") as fh:
            fh.write(render_markdown(report))
        paths.append(md_path)

    if emit_csv:
        csv_path = output_dir / "gate_report.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            fh.write(render_csv(report))
        paths.append(csv_path)

    return paths


def main() -> int:
    args = parse_args()
    thresholds = GateThresholds(
        net_pnl_min=args.min_net,
        win_rate_min=args.min_win,
        max_dd_pct_max=args.max_dd,
        trades_min=args.min_trades,
    )

    logs_dir = pathlib.Path(args.logs_dir)
    if not logs_dir.exists():
        print(f"ERROR: logs directory not found: {logs_dir}")
        return 2

    report = build_report(
        logs_dir=logs_dir,
        cases=args.cases,
        thresholds=thresholds,
        lookback_days=args.lookback_days,
        initial_equity=args.initial_equity,
        as_of=_parse_as_of(args.as_of),
    )

    emitted = write_outputs(
        output_dir=pathlib.Path(args.output_dir),
        report=report,
        emit_markdown=not args.no_markdown,
        emit_csv=not args.no_csv,
    )

    print(f"Gate report overall status: {'PASS' if report.overall_pass else 'FAIL'}")
    for case in report.cases:
        status = "PASS" if case.passed else "FAIL"
        summary = (
            f"{case.case}: trades={case.metrics.trades}, "
            f"net={case.metrics.net_pnl:.2f}, win_rate={case.metrics.win_rate:.2%}, "
            f"max_dd={case.metrics.max_dd_pct:.2%} -> {status}"
        )
        print(summary)
        for reason in case.fail_reasons:
            print(f"  - {reason}")

    print("Artifacts:")
    for path in emitted:
        print(f"  {path}")

    if args.kill_switch and not report.overall_pass:
        print("Kill-switch engaged: gate failed.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
