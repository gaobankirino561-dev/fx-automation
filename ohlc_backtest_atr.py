from __future__ import annotations

import collections
import csv
import os
import time
from io import StringIO
from pathlib import Path
from typing import List, Optional

from executor import TradeExecutor
from position_entities import Order
from stats import summarize_pips

CSV_PATH = Path(os.getenv("OHLC_CSV", "data/ohlc.csv"))
EQ0 = float(os.getenv("OB_EQ", "10000"))
RISK = float(os.getenv("OB_RISK", "0.005"))
RSI_UP = float(os.getenv("OB_RSI_UP", "55"))
RSI_DN = float(os.getenv("OB_RSI_DN", "45"))
K_TP = float(os.getenv("OB_KTP", "1.5"))
K_SL = float(os.getenv("OB_KSL", "1.0"))
MIN_TP = float(os.getenv("OB_MIN_TP", "6"))
MIN_SL = float(os.getenv("OB_MIN_SL", "6"))
TREND_SMA = int(os.getenv("OB_TREND_SMA", "0"))
SPREAD = float(os.getenv("OB_SPREAD_PIPS", "0.20"))
FEE = float(os.getenv("OB_FEE_PIPS", "0.0"))
MAX_DD_PCT = float(os.getenv("OB_STOP_DD", "100"))
OUTPUT = os.getenv("OB_OUTCSV", "equity_ohlc_atr.csv")
PIP_SIZE = 0.01
ATR_PERIOD = int(os.getenv("OB_ATR_PERIOD", "14"))


def rsi14(values: List[float]) -> List[Optional[float]]:
    gains = collections.deque(maxlen=14)
    losses = collections.deque(maxlen=14)
    output: List[Optional[float]] = []
    prev: Optional[float] = None
    for price in values:
        if prev is None:
            output.append(None)
            prev = price
            continue
        change = price - prev
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
        prev = price
        if len(gains) < 14:
            output.append(None)
            continue
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        rs = avg_gain / (avg_loss + 1e-9)
        output.append(100.0 - 100.0 / (1.0 + rs))
    return output


def atr(series: List[dict[str, float]]) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(series)
    if len(series) < ATR_PERIOD + 1:
        return result
    prev_close = series[0]["close"]
    ema: Optional[float] = None
    alpha = 1.0 / ATR_PERIOD
    for idx in range(1, len(series)):
        high = series[idx]["high"]
        low = series[idx]["low"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        ema = tr if ema is None else ema + alpha * (tr - ema)
        result[idx] = ema
        prev_close = series[idx]["close"]
    return result

def sma(values: List[float], period: int) -> List[Optional[float]]:
    if period <= 0:
        return [None] * len(values)
    window = collections.deque(maxlen=period)
    total = 0.0
    output: List[Optional[float]] = []
    for value in values:
        if len(window) == period:
            total -= window[0]
        window.append(value)
        total += value
        output.append(total / period if len(window) == period else None)
    return output


def load_rows(path: Path) -> List[dict[str, float]]:
    rows: List[dict[str, float]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"time", "open", "high", "low", "close"}
        if reader.fieldnames is None or required - set(reader.fieldnames):
            raise ValueError("CSV must contain time,open,high,low,close columns")
        for row in reader:
            rows.append({
                "time": row["time"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })
    return rows


def simulate_path(side: str, entry: float, atr_val: float, open_price: float, high: float, low: float, close: float) -> float:
    tp_pips = max(MIN_TP, atr_val * K_TP / PIP_SIZE)
    sl_pips = max(MIN_SL, atr_val * K_SL / PIP_SIZE)
    tp = entry + tp_pips * PIP_SIZE if side == "BUY" else entry - tp_pips * PIP_SIZE
    sl = entry - sl_pips * PIP_SIZE if side == "BUY" else entry + sl_pips * PIP_SIZE

    if close >= open_price:
        path = [open_price, high, low, close]
    else:
        path = [open_price, low, high, close]

    outcome: Optional[str] = None
    for idx in range(1, len(path)):
        prev = path[idx - 1]
        curr = path[idx]
        if side == "BUY":
            if prev <= curr and prev <= tp <= curr:
                outcome = "TP"
                break
            if prev >= curr and curr <= sl <= prev:
                outcome = "SL"
                break
        else:
            if prev >= curr and curr <= tp <= prev:
                outcome = "TP"
                break
            if prev <= curr and prev <= sl <= curr:
                outcome = "SL"
                break

    if outcome == "TP":
        return tp_pips
    if outcome == "SL":
        return -sl_pips
    if side == "BUY":
        return (close - entry) / PIP_SIZE
    return (entry - close) / PIP_SIZE


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    rows = load_rows(CSV_PATH)
    closes = [row["close"] for row in rows]
    atr_values = atr(rows)
    rsi_values = rsi14(closes)
    trend_values = sma(closes, TREND_SMA) if TREND_SMA > 0 else [None] * len(rows)

    executor = TradeExecutor(pip_size=PIP_SIZE)
    equity = EQ0
    peak = equity
    max_dd_pct = 0.0
    pips_log: List[float] = []

    if OUTPUT:
        out_path = Path(OUTPUT)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = out_path.open("w", newline="", encoding="utf-8")
    else:
        csv_file = StringIO()

    with csv_file as fh:
        writer = csv.writer(fh)
        writer.writerow(["trade", "equity"])
        trade_idx = 0

        for i in range(1, len(rows)):
            if atr_values[i] is None or atr_values[i] <= 0:
                continue
            if max_dd_pct >= MAX_DD_PCT:
                writer.writerow([trade_idx, round(equity, 2)])
                continue
            rsi_prev, rsi_curr = rsi_values[i - 1], rsi_values[i]
            if rsi_prev is None or rsi_curr is None:
                writer.writerow([trade_idx, round(equity, 2)])
                continue
            side: Optional[str] = None
            if rsi_prev < RSI_UP <= rsi_curr:
                side = "BUY"
            elif rsi_prev > RSI_DN >= rsi_curr:
                side = "SELL"
            if side is None or executor.positions():
                writer.writerow([trade_idx, round(equity, 2)])
                continue
            if TREND_SMA > 0 and trend_values[i - 1] is not None:
                trend = trend_values[i - 1]
                if side == "BUY" and closes[i - 1] < trend:
                    writer.writerow([trade_idx, round(equity, 2)])
                    continue
                if side == "SELL" and closes[i - 1] > trend:
                    writer.writerow([trade_idx, round(equity, 2)])
                    continue

            entry = closes[i]
            pips = simulate_path(side, entry, atr_values[i], rows[i]["open"], rows[i]["high"], rows[i]["low"], rows[i]["close"]) - (SPREAD + FEE)
            risk_pips = max(MIN_SL, atr_values[i] * K_SL / PIP_SIZE)
            size = max((equity * RISK) / risk_pips, 0.01)
            pnl = pips * size
            pips_log.append(pips)

            equity += pnl
            peak = max(peak, equity)
            if peak > 0:
                max_dd_pct = max(max_dd_pct, (peak - equity) / peak * 100.0)

            trade_idx += 1
            writer.writerow([trade_idx, round(equity, 2)])

    stats = summarize_pips(pips_log)
    ret_pct = (equity / EQ0 - 1.0) * 100.0
    print(
        f"trades:{int(stats['trades'])} win_rate:{stats['win_rate']:.1f}% PF:{stats['profit_factor']:.2f} "
        f"net_pips:{stats['net_pips']:.1f} equity_final:{equity:.2f} ({ret_pct:.1f}%) maxDD%:{max_dd_pct:.1f} csv:{OUTPUT or 'N/A'}"
    )


if __name__ == "__main__":
    main()

