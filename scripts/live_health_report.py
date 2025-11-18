from __future__ import annotations

import argparse
import csv
import datetime as dt
import pathlib
import sys
from typing import Any, Dict, List, Tuple

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from notifiers.notify import notify


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize latest papertrade-live metrics and emit a Discord health report."
    )
    parser.add_argument("--metrics", required=True, help="Path to metrics.csv downloaded from papertrade-live artifacts")
    parser.add_argument("--trades", help="Optional trades.csv path for additional context")
    parser.add_argument(
        "--config",
        default="papertrade/config_live.yaml",
        help="Live config that defines risk thresholds (default: papertrade/config_live.yaml)",
    )
    parser.add_argument("--pair", help="Override currency pair shown in notifications")
    parser.add_argument(
        "--fail-on-alert",
        action="store_true",
        help="Exit with code 1 when computed status is ALERT (default: disabled)",
    )
    parser.add_argument(
        "--rolling-days",
        type=int,
        default=7,
        help="Rolling window (in days) for extended health summary (default: 7)",
    )
    return parser.parse_args()


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_metrics(path: pathlib.Path) -> Dict[str, float]:
    metrics, _, _, _ = _load_metrics_dataset(path)
    return metrics


def _load_metrics_dataset(path: pathlib.Path) -> Tuple[Dict[str, float], List[Dict[str, str]], Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"metrics file not found: {path}")
    rows, header_map, headers = _read_csv_rows(path)
    if not rows:
        raise ValueError(f"metrics file has no rows: {path}")
    metrics = _extract_latest_metrics(rows, header_map, headers)
    return metrics, rows, header_map


def _read_csv_rows(path: pathlib.Path) -> Tuple[List[Dict[str, str]], Dict[str, str], List[str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        headers = reader.fieldnames or []
    header_map = {h.strip().lower(): h for h in headers if h}
    return rows, header_map, headers


def _extract_latest_metrics(
    rows: List[Dict[str, str]], header_map: Dict[str, str], headers: List[str]
) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    if "metric" in header_map and "value" in header_map:
        m_key = header_map["metric"]
        v_key = header_map["value"]
        for row in rows:
            key = row.get(m_key)
            if not key:
                continue
            metrics[key] = _to_float(row.get(v_key))
        return metrics
    latest = rows[-1]
    skip_cols = {"date", "day", "ts", "timestamp", "case"}
    for header in headers:
        if not header:
            continue
        if header.strip().lower() in skip_cols:
            continue
        metrics[header] = _to_float(latest.get(header))
    return metrics


def read_trades(path: pathlib.Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def load_thresholds(path: pathlib.Path) -> Tuple[str, Dict[str, float]]:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    pair = data.get("pair", "UNKNOWN")
    risk = data.get("risk", {}) or {}
    health_cfg = data.get("health", {}) or {}

    thresholds = {
        "daily_max_loss_jpy": float(risk.get("daily_max_loss_jpy", 0) or 0),
        "max_drawdown_pct": float(risk.get("max_drawdown_pct", 0) or 0),
        "min_trades": float(
            health_cfg.get("min_trades", health_cfg.get("min_daily_trades", 1))
        ),
    }
    rolling_cfg = health_cfg.get("rolling", {}) or {}
    thresholds.update(
        {
            "rolling_days_config": int(rolling_cfg.get("days", 0) or 0),
            "rolling_loss_jpy": float(
                rolling_cfg.get("loss_limit_jpy")
                or rolling_cfg.get("max_loss_jpy")
                or risk.get("daily_max_loss_jpy", 0)
                or 0
            ),
            "rolling_max_dd_pct": float(
                rolling_cfg.get("max_drawdown_pct")
                or risk.get("max_drawdown_pct", 0)
                or 0
            ),
            "rolling_min_win_rate_pct": float(
                rolling_cfg.get("min_win_rate_pct") or health_cfg.get("min_win_rate_pct") or 45.0
            ),
            "rolling_min_trades": float(rolling_cfg.get("min_trades") or max(health_cfg.get("min_trades", 1), 5)),
        }
    )
    return pair, thresholds


def classify_status(
    metrics: Dict[str, float],
    thresholds: Dict[str, float],
) -> Tuple[str, List[str]]:
    breaches: List[str] = []
    net = metrics.get("net_jpy", 0.0)
    dd = metrics.get("max_drawdown_pct", 0.0)
    trades = metrics.get("trades", 0.0)

    loss_limit = thresholds.get("daily_max_loss_jpy", 0.0)
    dd_limit = thresholds.get("max_drawdown_pct", 0.0)
    trades_min = thresholds.get("min_trades", 0.0)

    if loss_limit > 0 and net <= -abs(loss_limit):
        breaches.append(f"loss_limit({loss_limit:.0f})")
    if dd_limit > 0 and dd >= dd_limit:
        breaches.append(f"max_dd({dd_limit:.1f}%)")
    if trades_min > 0 and trades < trades_min:
        breaches.append(f"low_trades(min={trades_min:.0f})")

    if breaches:
        return "ALERT", breaches

    warnings: List[str] = []
    if net < 0:
        warnings.append("net_neg")
    if dd_limit > 0 and dd >= 0.7 * dd_limit:
        warnings.append("dd_high")

    if warnings:
        return "WARN", warnings

    return "OK", []


def summarize(metrics: Dict[str, float], status: str, notes: List[str]) -> str:
    net = metrics.get("net_jpy", 0.0)
    win = metrics.get("win_rate_pct", 0.0)
    dd = metrics.get("max_drawdown_pct", 0.0)
    trades = metrics.get("trades", 0.0)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    notes_text = ", ".join(notes) if notes else "none"
    return (
        f"[LIVE HEALTH] date={today} net={net:+.1f}JPY win={win:.1f}% "
        f"dd={dd:.1f}% trades={trades:.0f} status={status} notes={notes_text}"
    )


def summarize_with_rolling(
    metrics: Dict[str, float],
    status: str,
    notes: List[str],
    rolling_stats: Dict[str, float],
    rolling_status: str,
    rolling_notes: List[str],
) -> str:
    base = summarize(metrics, status, notes)
    rolling_notes_text = ", ".join(rolling_notes) if rolling_notes else "none"
    rolling_line = (
        f"[ROLLING] window={int(rolling_stats.get('days', 0))}d "
        f"observed={int(rolling_stats.get('observed_days', 0))}d "
        f"net={rolling_stats.get('net_jpy', 0.0):+.1f}JPY "
        f"win={rolling_stats.get('win_rate', 0.0):.1f}% "
        f"dd={rolling_stats.get('max_dd_pct', 0.0):.1f}% "
        f"trades={rolling_stats.get('trades', 0.0):.0f} "
        f"status={rolling_status} notes={rolling_notes_text}"
    )
    return f"{base}\n{rolling_line}"


def _build_history_records(
    rows: List[Dict[str, str]],
    header_map: Dict[str, str],
    fallback_metrics: Dict[str, float],
) -> List[Dict[str, Any]]:
    if not rows:
        return []
    if "metric" in header_map and "value" in header_map:
        record_date = _find_metric_row_date(rows, header_map)
        return [_record_from_metrics(fallback_metrics, record_date)]
    records: List[Dict[str, Any]] = []
    for row in rows:
        record_date = _extract_date_from_row(row, header_map) or _today()
        records.append(
            {
                "date": record_date,
                "net_jpy": _to_float(_get_row_value(row, header_map, ["net_jpy", "net", "net_pnl"])),
                "win_rate_pct": _to_float(_get_row_value(row, header_map, ["win_rate_pct", "win_rate", "win"])),
                "max_drawdown_pct": _to_float(_get_row_value(row, header_map, ["max_drawdown_pct", "max_dd", "dd"])),
                "trades": _to_float(_get_row_value(row, header_map, ["trades", "trade_count"])),
            }
        )
    records.sort(key=lambda r: r["date"])
    return records


def _find_metric_row_date(rows: List[Dict[str, str]], header_map: Dict[str, str]) -> dt.date:
    metric_col = header_map["metric"]
    value_col = header_map["value"]
    for row in rows:
        key = (row.get(metric_col) or "").strip().lower()
        if key in {"date", "day", "asof", "as_of"}:
            parsed = _parse_date_value(row.get(value_col))
            if parsed:
                return parsed
    return _today()


def _get_row_value(row: Dict[str, str], header_map: Dict[str, str], candidates: List[str]) -> str | None:
    for key in candidates:
        column = header_map.get(key)
        if column:
            value = row.get(column)
            if value:
                return value
    return None


def _extract_date_from_row(row: Dict[str, str], header_map: Dict[str, str]) -> dt.date | None:
    for key in ("date", "day", "ts", "timestamp"):
        column = header_map.get(key)
        if column:
            parsed = _parse_date_value(row.get(column))
            if parsed:
                return parsed
    case_column = header_map.get("case")
    if case_column:
        parsed = _parse_case_date(row.get(case_column))
        if parsed:
            return parsed
    return None


def _parse_date_value(value: str | None) -> dt.date | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    text_clean = text.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            snippet = text_clean[: len(fmt)]
            return dt.datetime.strptime(snippet, fmt).date()
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(text_clean).date()
    except ValueError:
        pass
    if "T" in text_clean:
        try:
            return dt.datetime.strptime(text_clean[:19], "%Y-%m-%dT%H:%M:%S").date()
        except ValueError:
            pass
    return None


def _parse_case_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    token = str(value).split("_", 1)[0]
    if len(token) == 8 and token.isdigit():
        try:
            return dt.datetime.strptime(token, "%Y%m%d").date()
        except ValueError:
            return None
    return _parse_date_value(value)


def _record_from_metrics(metrics: Dict[str, float], when: dt.date) -> Dict[str, Any]:
    return {
        "date": when,
        "net_jpy": metrics.get("net_jpy", 0.0),
        "win_rate_pct": metrics.get("win_rate_pct", 0.0),
        "max_drawdown_pct": metrics.get("max_drawdown_pct", 0.0),
        "trades": metrics.get("trades", 0.0),
    }


def _today() -> dt.date:
    return dt.datetime.now(dt.timezone.utc).date()


def compute_rolling_stats(records: List[Dict[str, Any]], rolling_days: int) -> Dict[str, float]:
    stats: Dict[str, float] = {
        "days": int(max(rolling_days, 0)),
        "observed_days": 0,
        "net_jpy": 0.0,
        "win_rate": 0.0,
        "max_dd_pct": 0.0,
        "trades": 0.0,
    }
    if not records:
        return stats
    ordered = sorted(records, key=lambda r: r["date"])
    end_date = ordered[-1]["date"]
    if stats["days"] > 0:
        start_date = end_date - dt.timedelta(days=int(stats["days"]) - 1)
        window = [r for r in ordered if r["date"] >= start_date]
        if not window:
            window = ordered[-int(stats["days"]) :]
    else:
        window = ordered
    if not window:
        return stats
    observed_days = len({r["date"] for r in window})
    total_trades = sum(r["trades"] for r in window)
    total_net = sum(r["net_jpy"] for r in window)
    max_dd = max((r["max_drawdown_pct"] for r in window), default=0.0)
    if total_trades > 0:
        win_weighted = sum(
            (r["win_rate_pct"] / 100.0) * r["trades"] for r in window if r.get("trades")
        )
        win_rate = (win_weighted / total_trades) * 100.0
    else:
        win_rate = sum(r["win_rate_pct"] for r in window) / len(window)
    stats.update(
        {
            "observed_days": observed_days,
            "net_jpy": total_net,
            "win_rate": win_rate,
            "max_dd_pct": max_dd,
            "trades": total_trades,
        }
    )
    return stats


def classify_rolling_status(
    rolling_stats: Dict[str, float], thresholds: Dict[str, float]
) -> Tuple[str, List[str]]:
    if rolling_stats.get("observed_days", 0) == 0:
        return "UNKNOWN", ["no_data"]
    alerts: List[str] = []
    warnings: List[str] = []
    net = rolling_stats.get("net_jpy", 0.0)
    dd = rolling_stats.get("max_dd_pct", 0.0)
    trades = rolling_stats.get("trades", 0.0)
    win = rolling_stats.get("win_rate", 0.0)
    loss_limit = thresholds.get("rolling_loss_jpy") or thresholds.get("daily_max_loss_jpy") or 0.0
    dd_limit = thresholds.get("rolling_max_dd_pct") or thresholds.get("max_drawdown_pct") or 0.0
    min_win = thresholds.get("rolling_min_win_rate_pct", 0.0)
    min_trades = thresholds.get("rolling_min_trades", 0.0)

    if loss_limit and net <= -abs(loss_limit):
        alerts.append(f"net<=-{abs(loss_limit):.0f}")
    if dd_limit and dd >= dd_limit:
        alerts.append(f"dd>={dd_limit:.1f}%")

    if min_trades and trades < min_trades:
        warnings.append(f"trades<{min_trades:.0f}")
    if min_win and win < min_win:
        warnings.append(f"win<{min_win:.1f}%")
    if net < 0:
        warnings.append("net_neg")

    details = alerts + warnings
    if alerts:
        return "ALERT", details
    if warnings:
        return "WATCH", details
    return "OK", []


def main() -> int:
    args = parse_args()
    metrics_path = pathlib.Path(args.metrics)
    trades_path = pathlib.Path(args.trades) if args.trades else None
    config_path = pathlib.Path(args.config)

    metrics, metric_rows, header_map = _load_metrics_dataset(metrics_path)
    trades = read_trades(trades_path) if trades_path else []
    pair, thresholds = load_thresholds(config_path)
    if args.pair:
        pair = args.pair

    rolling_days = args.rolling_days
    if not rolling_days and thresholds.get("rolling_days_config"):
        rolling_days = int(thresholds["rolling_days_config"])
    records = _build_history_records(metric_rows, header_map, metrics)
    rolling_stats = compute_rolling_stats(records, rolling_days or 7)
    rolling_status, rolling_notes = classify_rolling_status(rolling_stats, thresholds)

    status, notes = classify_status(metrics, thresholds)
    summary = summarize_with_rolling(metrics, status, notes, rolling_stats, rolling_status, rolling_notes)

    print(summary)
    if trades:
        sample = trades[-1]
        print(
            f"Latest trade: side={sample.get('side')} pnl_jpy={sample.get('pnl_jpy')} reason={sample.get('reason')}"
        )
    print(
        f"Thresholds: loss={thresholds.get('daily_max_loss_jpy', 0):.0f}JPY "
        f"dd={thresholds.get('max_drawdown_pct', 0):.1f}% "
        f"min_trades={thresholds.get('min_trades', 0):.0f}"
    )

    try:
        notify(
            "live_health",
            {
                "pair": pair,
                "side": "LIVE",
                "price": "-",
                "pnl_jpy": round(metrics.get("net_jpy", 0.0), 1),
                "reason": summary,
            },
        )
    except Exception as exc:  # noqa: BLE001 - log and continue
        print(f"[live_health] notify failed: {exc}")

    print(f"HEALTH_STATUS={status}")
    print(f"ROLLING_STATUS={rolling_status}")
    print(f"ROLLING_WINDOW_DAYS={int(rolling_stats.get('days', 0))}")

    # observability only; never fail due to healthy/alert state
    if args.fail_on_alert and status == "ALERT":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
