from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

DEFAULT_METRICS_PATH = pathlib.Path("metrics/metrics.csv")
DEFAULT_GATE_PATH = pathlib.Path("metrics/gate_report.json")
DEFAULT_OUTPUT_DIR = pathlib.Path("metrics")
DEFAULT_JSON_NAME = "metrics_report.json"
DEFAULT_MD_NAME = "metrics_report.md"


@dataclass(frozen=True)
class MetricsRow:
    case: str
    net_pnl: float
    win_rate: float
    max_dd_pct: float
    trades: int

    @property
    def suffix(self) -> str:
        parts = self.case.split("_", 1)
        return parts[1] if len(parts) == 2 else self.case


def _resolve_field_map(fieldnames: List[str]) -> Dict[str, str]:
    mapped: Dict[str, str] = {}
    for name in fieldnames:
        key = (name or "").strip().lower()
        if key and key not in mapped:
            mapped[key] = name
    return mapped


def load_metrics_rows(path: pathlib.Path) -> List[MetricsRow]:
    if not path.exists():
        raise FileNotFoundError(f"Metrics CSV not found: {path}")
    rows: List[MetricsRow] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"Metrics CSV {path} is missing headers.")
        field_map = _resolve_field_map(list(reader.fieldnames))
        required = {"case", "net", "win", "dd", "trades"}
        missing = required - set(field_map)
        if missing:
            raise ValueError(
                f"Metrics CSV {path} is missing columns: {', '.join(sorted(missing))}"
            )
        case_key = field_map["case"]
        net_key = field_map["net"]
        win_key = field_map["win"]
        dd_key = field_map["dd"]
        trades_key = field_map["trades"]

        for index, row in enumerate(reader, start=2):
            case = (row.get(case_key) or "").strip()
            if not case:
                continue
            try:
                net = float(row.get(net_key, "0"))
                win = float(row.get(win_key, "0"))
                dd = float(row.get(dd_key, "0"))
                trades = int(float(row.get(trades_key, "0")))
            except ValueError as exc:
                raise ValueError(
                    f"Invalid metric values at row {index} in {path}: {exc}"
                ) from exc
            rows.append(
                MetricsRow(
                    case=case,
                    net_pnl=net,
                    win_rate=win,
                    max_dd_pct=dd,
                    trades=trades,
                )
            )
    if not rows:
        raise ValueError(f"Metrics CSV {path} did not contain any valid rows.")
    return rows


def load_gate_report(path: pathlib.Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Gate report at {path} is not a JSON object.")
    return data


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def combine_cases(
    metrics_rows: List[MetricsRow],
    gate: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    gate_cases: Dict[str, Dict[str, Any]] = {}
    matched_gate: Set[str] = set()
    if gate:
        for entry in gate.get("cases", []):
            case_name = entry.get("case")
            if case_name:
                gate_cases[case_name] = entry

    combined: List[Dict[str, Any]] = []
    for row in metrics_rows:
        gate_entry = gate_cases.get(row.case) or gate_cases.get(row.suffix)
        if gate_entry:
            matched_gate.add(gate_entry.get("case", ""))
            source = "metrics+gate"
        else:
            source = "metrics_only"
        combined.append(
            {
                "case": row.case,
                "suffix": row.suffix,
                "net_pnl": row.net_pnl,
                "win_rate": row.win_rate,
                "max_dd_pct": row.max_dd_pct,
                "trades": row.trades,
                "gate_case": gate_entry.get("case") if gate_entry else None,
                "gate_passed": gate_entry.get("passed") if gate_entry else None,
                "gate_fail_reasons": list(gate_entry.get("fail_reasons", []))
                if gate_entry
                else [],
                "source": source,
            }
        )

    if gate_cases:
        for name, entry in gate_cases.items():
            if name in matched_gate:
                continue
            metrics = entry.get("metrics", {})
            combined.append(
                {
                    "case": entry.get("case", name),
                    "suffix": entry.get("case", name),
                    "net_pnl": safe_float(metrics.get("net_pnl")),
                    "win_rate": safe_float(metrics.get("win_rate")),
                    "max_dd_pct": safe_float(metrics.get("max_dd_pct")),
                    "trades": safe_int(metrics.get("trades")),
                    "gate_case": entry.get("case"),
                    "gate_passed": entry.get("passed"),
                    "gate_fail_reasons": list(entry.get("fail_reasons", [])),
                    "source": "gate_only",
                }
            )

    combined.sort(key=lambda item: item["suffix"])
    return combined


def compute_totals(metrics_rows: List[MetricsRow]) -> Dict[str, float]:
    net_total = sum(row.net_pnl for row in metrics_rows)
    trades_total = sum(row.trades for row in metrics_rows)
    wins_total = sum(row.win_rate * row.trades for row in metrics_rows)
    max_dd = max((row.max_dd_pct for row in metrics_rows), default=0.0)
    win_rate = wins_total / trades_total if trades_total else 0.0
    return {
        "net_pnl": net_total,
        "win_rate": win_rate,
        "max_dd_pct": max_dd,
        "trades": trades_total,
    }


def render_markdown(summary: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Metrics Report")
    lines.append("")
    lines.append(f"- Generated at: {summary['generated_at']}")
    lines.append(f"- Metrics CSV: {summary['metrics_source']}")
    gate_source = summary.get("gate_source")
    if gate_source:
        lines.append(f"- Gate report: {gate_source}")
    lookback = summary.get("lookback_days")
    if lookback is not None:
        lines.append(f"- Lookback days: {lookback}")
    as_of = summary.get("as_of")
    if as_of:
        lines.append(f"- As of date: {as_of}")
    overall = summary.get("overall_gate_pass")
    if overall is not None:
        lines.append(f"- Gate status: {'PASS' if overall else 'FAIL'}")
    lines.append("")
    lines.append("| Case | Net PnL | Win Rate | Max DD | Trades | Gate |")
    lines.append("|------|---------|----------|--------|--------|------|")

    for case in summary.get("cases", []):
        gate_passed = case.get("gate_passed")
        if gate_passed is True:
            gate_status = "PASS"
        elif gate_passed is False:
            gate_status = "FAIL"
        else:
            gate_status = "N/A"
        lines.append(
            "| {case} | {net:.2f} | {win:.2%} | {dd:.2%} | {trades} | {gate} |".format(
                case=case.get("case", ""),
                net=case.get("net_pnl", 0.0),
                win=case.get("win_rate", 0.0),
                dd=case.get("max_dd_pct", 0.0),
                trades=case.get("trades", 0),
                gate=gate_status,
            )
        )
        reasons = case.get("gate_fail_reasons") or []
        if reasons:
            joined = "; ".join(reasons)
            lines.append(f"| -> reasons |  |  |  |  | {joined} |")

    totals = summary.get("totals") or {}
    lines.append("")
    lines.append(
        "Totals: net={net:.2f}, win_rate={win:.2%}, max_dd={dd:.2%}, trades={trades}".format(
            net=totals.get("net_pnl", 0.0),
            win=totals.get("win_rate", 0.0),
            dd=totals.get("max_dd_pct", 0.0),
            trades=int(totals.get("trades", 0)),
        )
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate human-readable metrics report artifacts."
    )
    parser.add_argument(
        "--metrics-csv",
        default=str(DEFAULT_METRICS_PATH),
        help="Path to metrics.csv produced by paper_metrics.py.",
    )
    parser.add_argument(
        "--gate-report",
        default=str(DEFAULT_GATE_PATH),
        help="Path to gate_report.json produced by aggregate_gate.py.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where report artifacts will be written.",
    )
    parser.add_argument(
        "--json-name",
        default=DEFAULT_JSON_NAME,
        help="Filename for the structured JSON summary.",
    )
    parser.add_argument(
        "--markdown-name",
        default=DEFAULT_MD_NAME,
        help="Filename for the Markdown summary.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    metrics_path = pathlib.Path(args.metrics_csv)
    gate_path = pathlib.Path(args.gate_report) if args.gate_report else None
    metrics_rows = load_metrics_rows(metrics_path)

    gate_data: Optional[Dict[str, Any]] = None
    if gate_path:
        if gate_path.exists():
            gate_data = load_gate_report(gate_path)
        else:
            print(
                f"WARNING: Gate report not found at {gate_path}; continuing without gate data.",
                file=sys.stderr,
            )

    combined = combine_cases(metrics_rows, gate_data)
    totals = (
        gate_data.get("totals")
        if gate_data and isinstance(gate_data.get("totals"), dict)
        else compute_totals(metrics_rows)
    )

    summary: Dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "metrics_source": str(metrics_path),
        "gate_source": str(gate_path) if gate_data else None,
        "lookback_days": gate_data.get("lookback_days") if gate_data else None,
        "as_of": gate_data.get("as_of") if gate_data else None,
        "overall_gate_pass": gate_data.get("overall_pass") if gate_data else None,
        "thresholds": gate_data.get("thresholds") if gate_data else None,
        "cases": combined,
        "totals": totals,
    }

    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / args.json_name
    md_path = output_dir / args.markdown_name

    with json_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    md_path.write_text(render_markdown(summary), encoding="utf-8")

    pass_rate = 0.0
    if summary["cases"]:
        passes = sum(1 for case in summary["cases"] if case.get("gate_passed", True))
        pass_rate = passes / len(summary["cases"])
    pass_rate_path = output_dir / "pass_rate.txt"
    pass_rate_path.write_text(f"{pass_rate:.4f}", encoding="utf-8")
    print(f"PASS_RATE={pass_rate:.4f}")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    if summary.get("overall_gate_pass") is False:
        print("Gate status is FAIL; see Markdown for details.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
