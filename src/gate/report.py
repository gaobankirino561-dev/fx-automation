from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from gate.metrics import Metrics
from gate.papertrade import parse_filename_date, read_log_rows, rows_to_metrics, rows_to_pnls, sort_rows


@dataclass(frozen=True)
class GateThresholds:
    net_pnl_min: float = 0.0
    win_rate_min: float = 0.45
    max_dd_pct_max: float = 0.20
    trades_min: int = 30

    def to_dict(self) -> dict[str, float | int]:
        return {
            "net_pnl_min": self.net_pnl_min,
            "win_rate_min": self.win_rate_min,
            "max_dd_pct_max": self.max_dd_pct_max,
            "trades_min": self.trades_min,
        }


@dataclass(frozen=True)
class CaseReport:
    case: str
    start_date: Optional[dt.date]
    end_date: Optional[dt.date]
    metrics: Metrics
    wins: int
    files: List[Path] = field(default_factory=list)
    fail_reasons: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.fail_reasons

    def to_dict(self) -> dict:
        return {
            "case": self.case,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "metrics": asdict(self.metrics),
            "wins": self.wins,
            "files": [str(path) for path in self.files],
            "fail_reasons": list(self.fail_reasons),
            "passed": self.passed,
        }


@dataclass(frozen=True)
class GateReport:
    generated_at: dt.datetime
    as_of: Optional[dt.date]
    lookback_days: int
    thresholds: GateThresholds
    cases: List[CaseReport]
    totals: Metrics

    @property
    def overall_pass(self) -> bool:
        return all(case.passed for case in self.cases) if self.cases else False

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(timespec="seconds"),
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "lookback_days": self.lookback_days,
            "thresholds": self.thresholds.to_dict(),
            "overall_pass": self.overall_pass,
            "cases": [case.to_dict() for case in self.cases],
            "totals": asdict(self.totals),
        }


def _suffix_from_filename(path: Path) -> Optional[str]:
    stem = path.stem
    parts = stem.split("_", 1)
    if len(parts) != 2:
        return None
    return parts[1]


def discover_cases(logs_dir: Path) -> Dict[str, List[Tuple[dt.date, Path]]]:
    cases: Dict[str, List[Tuple[dt.date, Path]]] = {}
    for path in sorted(logs_dir.glob("*.csv")):
        suffix = _suffix_from_filename(path)
        if not suffix:
            continue
        file_date = parse_filename_date(path.name)
        if not file_date:
            continue
        cases.setdefault(suffix, []).append((file_date, path))
    for suffix in cases:
        cases[suffix].sort(key=lambda item: item[0])
    return cases


def _filter_by_window(
    dated_paths: Sequence[Tuple[dt.date, Path]],
    end_date: dt.date,
    lookback_days: int,
) -> Tuple[List[dt.date], List[Path], Optional[dt.date]]:
    if lookback_days >= 0:
        start_delta = max(0, lookback_days - 1)
        start_date = end_date - dt.timedelta(days=start_delta)
    else:
        start_date = None

    selected_dates: List[dt.date] = []
    selected_paths: List[Path] = []
    for file_date, path in dated_paths:
        if file_date > end_date:
            continue
        if start_date and file_date < start_date:
            continue
        selected_dates.append(file_date)
        selected_paths.append(path)
    return selected_dates, selected_paths, start_date


def evaluate_case(
    case: str,
    dated_paths: Sequence[Tuple[dt.date, Path]],
    thresholds: GateThresholds,
    lookback_days: int,
    as_of: Optional[dt.date],
    initial_equity: float,
) -> CaseReport:
    if not dated_paths:
        return CaseReport(
            case=case,
            start_date=None,
            end_date=None,
            metrics=Metrics(0.0, 0.0, 0.0, 0),
            wins=0,
            files=[],
            fail_reasons=["No log files found"],
        )

    end_date = as_of or dated_paths[-1][0]
    selected_dates, selected_paths, start_date = _filter_by_window(dated_paths, end_date, lookback_days)

    rows = []
    for path in selected_paths:
        rows.extend(read_log_rows(path))
    rows = sort_rows(rows)

    metrics = rows_to_metrics(rows, initial_equity)
    wins = int(round(metrics.win_rate * metrics.trades))
    fail_reasons: List[str] = []
    if metrics.net_pnl < thresholds.net_pnl_min:
        fail_reasons.append(
            f"Net PnL {metrics.net_pnl:.2f} < {thresholds.net_pnl_min:.2f}"
        )
    if metrics.win_rate < thresholds.win_rate_min:
        fail_reasons.append(
            f"Win rate {metrics.win_rate:.2%} < {thresholds.win_rate_min:.2%}"
        )
    if metrics.max_dd_pct > thresholds.max_dd_pct_max:
        fail_reasons.append(
            f"Max DD {metrics.max_dd_pct:.2%} > {thresholds.max_dd_pct_max:.2%}"
        )
    if metrics.trades < thresholds.trades_min:
        fail_reasons.append(
            f"Trades {metrics.trades} < {thresholds.trades_min}"
        )

    return CaseReport(
        case=case,
        start_date=min(selected_dates) if selected_dates else None,
        end_date=max(selected_dates) if selected_dates else None,
        metrics=metrics,
        wins=wins,
        files=list(selected_paths),
        fail_reasons=fail_reasons,
    )


def _aggregate_totals(cases: Iterable[CaseReport]) -> Metrics:
    net = 0.0
    trades = 0
    wins = 0
    max_dd = 0.0
    for case in cases:
        net += case.metrics.net_pnl
        trades += case.metrics.trades
        wins += case.wins
        if case.metrics.max_dd_pct > max_dd:
            max_dd = case.metrics.max_dd_pct
    win_rate = wins / trades if trades else 0.0
    return Metrics(net_pnl=net, win_rate=win_rate, max_dd_pct=max_dd, trades=trades)


def build_report(
    logs_dir: Path,
    cases: Optional[Sequence[str]],
    thresholds: GateThresholds,
    lookback_days: int,
    initial_equity: float,
    as_of: Optional[dt.date] = None,
) -> GateReport:
    discovered = discover_cases(logs_dir)
    if cases:
        filtered: Dict[str, List[Tuple[dt.date, Path]]] = {}
        for case in cases:
            if case in discovered:
                filtered[case] = discovered[case]
            else:
                filtered[case] = []
        discovered = filtered

    evaluated: List[CaseReport] = []
    for case, dated_paths in sorted(discovered.items()):
        evaluated.append(
            evaluate_case(
                case=case,
                dated_paths=dated_paths,
                thresholds=thresholds,
                lookback_days=lookback_days,
                as_of=as_of,
                initial_equity=initial_equity,
            )
        )

    totals = _aggregate_totals(evaluated)
    generated_at = dt.datetime.now(dt.timezone.utc)
    return GateReport(
        generated_at=generated_at,
        as_of=as_of,
        lookback_days=lookback_days,
        thresholds=thresholds,
        cases=evaluated,
        totals=totals,
    )


def render_markdown(report: GateReport) -> str:
    header = (
        f"# Gate Report\n\n"
        f"- Generated at: {report.generated_at.isoformat(timespec='seconds')}\n"
        f"- As of date: {report.as_of.isoformat() if report.as_of else 'latest available'}\n"
        f"- Lookback days: {report.lookback_days}\n"
        f"- Overall status: {'PASS' if report.overall_pass else 'FAIL'}\n"
    )
    thresholds = (
        "| Threshold | Value |\n"
        "|-----------|-------|\n"
        f"| Net PnL >= | {report.thresholds.net_pnl_min:.2f} |\n"
        f"| Win Rate >= | {report.thresholds.win_rate_min:.2%} |\n"
        f"| Max DD <= | {report.thresholds.max_dd_pct_max:.2%} |\n"
        f"| Trades >= | {report.thresholds.trades_min} |\n"
    )
    lines = [header, thresholds, "\n## Case Breakdown\n", "| Case | Trades | Wins | Net PnL | Win Rate | Max DD | Status |"]
    lines.append("|------|--------|------|---------|----------|--------|--------|")
    for case in report.cases:
        status = "PASS" if case.passed else "FAIL"
        lines.append(
            "| {case} | {trades} | {wins} | {net:.2f} | {win_rate:.2%} | {dd:.2%} | {status} |".format(
                case=case.case,
                trades=case.metrics.trades,
                wins=case.wins,
                net=case.metrics.net_pnl,
                win_rate=case.metrics.win_rate,
                dd=case.metrics.max_dd_pct,
                status=status,
            )
        )
        if case.fail_reasons:
            reasons = "<br>".join(case.fail_reasons)
            lines.append(f"| -> Reasons |  |  |  |  |  | {reasons} |")

    totals = report.totals
    lines.append(
        "\n**Totals:** trades={trades}, wins~{wins}, net={net:.2f}, win_rate~{win_rate:.2%}, "
        "max_dd~{dd:.2%}".format(
            trades=totals.trades,
            wins=int(round(totals.win_rate * totals.trades)),
            net=totals.net_pnl,
            win_rate=totals.win_rate,
            dd=totals.max_dd_pct,
        )
    )
    return "\n".join(lines)


def render_csv(report: GateReport) -> str:
    import io
    import csv

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "case",
            "start_date",
            "end_date",
            "trades",
            "wins",
            "net_pnl",
            "win_rate",
            "max_dd_pct",
            "status",
            "fail_reasons",
        ]
    )
    for case in report.cases:
        writer.writerow(
            [
                case.case,
                case.start_date.isoformat() if case.start_date else "",
                case.end_date.isoformat() if case.end_date else "",
                case.metrics.trades,
                case.wins,
                f"{case.metrics.net_pnl:.2f}",
                f"{case.metrics.win_rate:.4f}",
                f"{case.metrics.max_dd_pct:.4f}",
                "PASS" if case.passed else "FAIL",
                "; ".join(case.fail_reasons),
            ]
        )
    return buffer.getvalue()


__all__ = [
    "GateThresholds",
    "CaseReport",
    "GateReport",
    "discover_cases",
    "evaluate_case",
    "build_report",
    "render_csv",
    "render_markdown",
]
