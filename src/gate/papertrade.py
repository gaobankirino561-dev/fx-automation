from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from gate.metrics import Metrics, compute_metrics as _compute_metrics

DATE_FMT = "%Y%m%d"


def parse_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def parse_case_date(case: str) -> dt.date | None:
    token = (case or "").split("_", 1)[0]
    if len(token) != 8 or not token.isdigit():
        return None
    try:
        return dt.datetime.strptime(token, DATE_FMT).date()
    except ValueError:
        return None


def parse_filename_date(filename: str) -> dt.date | None:
    stem = Path(filename).stem
    token = stem.split("_", 1)[0]
    if len(token) != 8 or not token.isdigit():
        return None
    try:
        return dt.datetime.strptime(token, DATE_FMT).date()
    except ValueError:
        return None


def derive_suffix(case: str, fallback_path: str | Path) -> str:
    parts = (case or "").split("_", 1)
    if len(parts) == 2 and parts[1]:
        return f"{parts[1]}.csv"
    name = Path(fallback_path).name
    idx = name.find("_")
    return name[idx + 1 :] if idx != -1 else name


def read_log_rows(path: str | Path) -> List[dict[str, str]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def find_recent_logs(base_path: str | Path, case: str, lookback_days: int) -> List[Path]:
    base_path = Path(base_path)
    directory = base_path.parent
    suffix = derive_suffix(case, base_path)
    pattern = f"*_{suffix}"
    candidates = sorted(directory.glob(pattern))
    case_date = parse_case_date(case)

    eligible: List[Path] = []
    for candidate in reversed(candidates):
        file_date = parse_filename_date(candidate.name)
        if case_date and file_date:
            delta = (case_date - file_date).days
            if delta < 0:
                continue
            if lookback_days >= 0 and delta > lookback_days:
                continue
        eligible.append(candidate)
    return eligible


def load_trades(log_files: Iterable[str | Path]) -> List[dict[str, str]]:
    rows: List[dict[str, str]] = []
    for path in log_files:
        rows.extend(read_log_rows(path))
    return rows


def load_trades_with_fallback(
    log_files: Sequence[str | Path],
    case: str,
    lookback_days: int,
    min_trades: int,
) -> Tuple[List[dict[str, str]], List[Path]]:
    rows: List[dict[str, str]] = []
    used_files: List[Path] = []
    for path in log_files:
        current_rows = read_log_rows(path)
        if current_rows:
            rows.extend(current_rows)
            used_files.append(Path(path))

    target = max(1, min_trades)
    if len(rows) >= target:
        return rows, used_files

    for path in log_files:
        for candidate in find_recent_logs(path, case, lookback_days):
            candidate = Path(candidate)
            if candidate in used_files:
                continue
            candidate_rows = read_log_rows(candidate)
            if not candidate_rows:
                continue
            rows.extend(candidate_rows)
            used_files.append(candidate)
            if len(rows) >= target:
                return rows, used_files

    return rows, used_files


def sort_rows(rows: Sequence[dict[str, str]]) -> List[dict[str, str]]:
    def key(row: dict[str, str]) -> dt.datetime:
        for k in ("time_close", "time_open"):
            value = row.get(k)
            if not value:
                continue
            try:
                return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                continue
        return dt.datetime.min

    return sorted(rows, key=key)


def rows_to_pnls(rows: Sequence[dict[str, str]]) -> List[float]:
    pnls: List[float] = []
    for row in rows:
        profit = parse_float(row.get("profit_jpy", 0.0))
        commission = parse_float(row.get("commission_jpy", 0.0))
        swap = parse_float(row.get("swap_jpy", 0.0))
        pnls.append(profit + commission + swap)
    return pnls


def rows_to_metrics(rows: Sequence[dict[str, str]], initial_equity: float) -> Metrics:
    pnls = rows_to_pnls(rows)
    return _compute_metrics(pnls, initial=initial_equity)


__all__ = [
    "parse_float",
    "parse_case_date",
    "parse_filename_date",
    "derive_suffix",
    "read_log_rows",
    "find_recent_logs",
    "load_trades",
    "load_trades_with_fallback",
    "sort_rows",
    "rows_to_pnls",
    "rows_to_metrics",
]
