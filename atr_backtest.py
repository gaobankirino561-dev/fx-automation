from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import List, Optional

from stats import summarize_pips

CSV_PATH = Path(os.getenv("AB_CSV", "data/ohlc.csv"))
ATR_PERIOD = int(os.getenv("AB_ATR_PERIOD", "14"))
TP_K = float(os.getenv("AB_TP_K", "1.5"))
SL_K = float(os.getenv("AB_SL_K", "1.0"))
RISK = float(os.getenv("AB_RISK", "0.005"))
START_EQ = float(os.getenv("AB_EQ", "10000"))
SIDE_MODE = os.getenv("AB_SIDE", "ALT").strip().upper() or "ALT"
OUTPUT = os.getenv("AB_OUTCSV", "equity_atr.csv")
PIP = float(os.getenv("AB_PIP", "0.01"))
SEED_SIDE_ALT = os.getenv("AB_ALT_START", "BUY").upper()


def _load_rows(path: Path) -> List[dict[str, float]]:
    rows: List[dict[str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"time", "open", "high", "low", "close"}
        if reader.fieldnames is None or required - set(reader.fieldnames):
            raise ValueError(f"CSV must contain columns: {sorted(required)}")
        for row in reader:
            rows.append({
                "time": row["time"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    return rows


def _compute_atr(rows: List[dict[str, float]]) -> List[Optional[float]]:
    atr_values: List[Optional[float]] = [None] * len(rows)
    if len(rows) < ATR_PERIOD + 1:
        return atr_values
    tr_history: List[float] = []
    for idx in range(1, len(rows)):
        high = rows[idx]["high"]
        low = rows[idx]["low"]
        prev_close = rows[idx - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_history.append(tr)
        if len(tr_history) < ATR_PERIOD:
            continue
        if len(tr_history) == ATR_PERIOD:
            atr = sum(tr_history) / ATR_PERIOD
        else:
            prev_atr = atr_values[idx - 1]
            if prev_atr is None:
                prev_atr = sum(tr_history[-ATR_PERIOD:]) / ATR_PERIOD
            atr = (prev_atr * (ATR_PERIOD - 1) + tr) / ATR_PERIOD
        atr_values[idx] = atr
    return atr_values


def _next_side(index: int, last_side: str) -> str:
    if SIDE_MODE == "BUY":
        return "BUY"
    if SIDE_MODE == "SELL":
        return "SELL"
    if index == 0:
        return "BUY" if SEED_SIDE_ALT != "SELL" else "SELL"
    return "SELL" if last_side == "BUY" else "BUY"


def _bar_path(open_price: float, high: float, low: float, close: float) -> List[float]:
    if close >= open_price:
        return [open_price, high, low, close]
    return [open_price, low, high, close]


def _simulate_path(side: str, entry: float, tp_price: float, sl_price: float, path: List[float]) -> Optional[str]:
    for i in range(1, len(path)):
        prev = path[i - 1]
        curr = path[i]
        if side == "BUY":
            if prev <= curr:
                if prev <= tp_price <= curr:
                    return "TP"
            else:
                if curr <= sl_price <= prev:
                    return "SL"
        else:
            if prev >= curr:
                if curr <= tp_price <= prev:
                    return "TP"
            else:
                if prev <= sl_price <= curr:
                    return "SL"
    return None


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    rows = _load_rows(CSV_PATH)
    atr_series = _compute_atr(rows)

    equity = START_EQ
    peak = equity
    max_dd_pct = 0.0
    pips_results: List[float] = []

    with Path(OUTPUT).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["trade", "time", "side", "atr", "equity"])
        last_side = "SELL" if SEED_SIDE_ALT == "SELL" else "BUY"
        trade_index = 0

        for idx, row in enumerate(rows):
            atr = atr_series[idx]
            if atr is None or atr <= 0:
                continue

            side = _next_side(trade_index, last_side)
            last_side = side
            trade_index += 1

            entry = row["open"]
            tp_price = entry + TP_K * atr if side == "BUY" else entry - TP_K * atr
            sl_price = entry - SL_K * atr if side == "BUY" else entry + SL_K * atr

            path = _bar_path(entry, row["high"], row["low"], row["close"])
            outcome = _simulate_path(side, entry, tp_price, sl_price, path)

            if outcome == "TP":
                pips = (tp_price - entry) / PIP if side == "BUY" else (entry - tp_price) / PIP
            elif outcome == "SL":
                pips = (sl_price - entry) / PIP if side == "BUY" else (entry - sl_price) / PIP
            else:
                if side == "BUY":
                    pips = (row["close"] - entry) / PIP
                else:
                    pips = (entry - row["close"]) / PIP

            size = max((equity * RISK) / (SL_K * atr / PIP), 0.01)
            pnl = pips * size
            pips_results.append(pips)

            equity += pnl
            peak = max(peak, equity)
            if peak > 0:
                max_dd_pct = max(max_dd_pct, (peak - equity) / peak * 100.0)

            writer.writerow([trade_index, row["time"], side, round(atr, 5), round(equity, 2)])

    stats = summarize_pips(pips_results)
    ret_pct = (equity / START_EQ - 1.0) * 100.0
    print(
        f"trades:{int(stats['trades'])} win_rate:{stats['win_rate']:.1f}% PF:{stats['profit_factor']:.2f} "
        f"net_pips:{stats['net_pips']:.1f} equity_final:{equity:.2f} ({ret_pct:.1f}%) maxDD%:{max_dd_pct:.1f} csv:{OUTPUT}"
    )


if __name__ == "__main__":
    main()
