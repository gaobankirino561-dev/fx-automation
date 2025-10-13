import csv
import os
import time
import collections
from typing import Optional, List

from executor import TradeExecutor
from position_entities import Order
from stats import summarize_pips

CSV   = os.getenv("OHLC_CSV","data/ohlc.csv")
TP    = float(os.getenv("OB_TP","10"))
SL    = float(os.getenv("OB_SL","8"))
RISK  = float(os.getenv("OB_RISK","0.005"))
EQ0   = float(os.getenv("OB_EQ","10000"))
UP    = float(os.getenv("OB_RSI_UP","55"))
DN    = float(os.getenv("OB_RSI_DN","45"))
OUT   = os.getenv("OB_OUTCSV","equity_ohlc.csv")
PIP   = 0.01


def rsi14(series: List[float]) -> List[Optional[float]]:
    gains = collections.deque(maxlen=14)
    losses = collections.deque(maxlen=14)
    prev = None
    output: List[Optional[float]] = []
    for price in series:
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
        output.append(100 - 100 / (1 + rs))
    return output

closes: List[float] = []
prices: List[float] = []
with open(CSV, encoding="utf-8") as fh:
    reader = csv.DictReader(fh)
    for row in reader:
        close = float(row["close"])
        closes.append(close)
        prices.append(close)

rsi = rsi14(closes)

ex = TradeExecutor(pip_size=PIP)
equity = EQ0
peak = equity
maxdd_pct = 0.0
pips: List[float] = []

with open(OUT, "w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(["trade", "equity"])
    for idx, price in enumerate(prices):
        if idx == 0:
            writer.writerow([idx + 1, round(equity, 2)])
            continue

        if rsi[idx - 1] is not None and rsi[idx] is not None and not ex.positions():
            if rsi[idx - 1] < UP <= rsi[idx]:
                size = (equity * RISK) / SL
                ex.submit(Order("BUY", price, TP, SL, size), price, int(time.time()))
            elif rsi[idx - 1] > DN >= rsi[idx]:
                size = (equity * RISK) / SL
                ex.submit(Order("SELL", price, TP, SL, size), price, int(time.time()))

        fills = ex.step(price, int(time.time()))
        if fills:
            pnl = sum(fill.pnl for fill in fills)
            pips.append(pnl)
            equity += pnl
            peak = max(peak, equity)
            if peak > 0:
                maxdd_pct = max(maxdd_pct, (peak - equity) / peak * 100.0)

        writer.writerow([idx + 1, round(equity, 2)])

stats = summarize_pips(pips)
ret_pct = (equity / EQ0 - 1) * 100.0
print(
    f"trades:{int(stats['trades'])} win_rate:{stats['win_rate']:.1f}% PF:{stats['profit_factor']:.2f} "
    f"net_pips:{stats['net_pips']:.1f} equity_final:{equity:.2f} ({ret_pct:.1f}%) maxDD%:{maxdd_pct:.1f} csv:{OUT}"
)
