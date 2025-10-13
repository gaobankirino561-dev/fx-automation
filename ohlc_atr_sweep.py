import os
import subprocess
import sys

KTP_VALUES = [1.0, 1.5, 2.0]
KSL_VALUES = [0.5, 1.0]
TREND_VALUES = [0, 50]

CSV = os.getenv("OHLC_CSV", "data/ohlc.csv")
EQ = os.getenv("OB_EQ", "10000")
RISK = os.getenv("OB_RISK", "0.005")
RSI_UP = os.getenv("OB_RSI_UP", "55")
RSI_DN = os.getenv("OB_RSI_DN", "45")
SPREAD = os.getenv("OB_SPREAD_PIPS", "0.20")
FEE = os.getenv("OB_FEE_PIPS", "0")

print("KTP KSL Trend | Trades Win% PF NetPips FinalEq Ret% MaxDD%")

for ktp in KTP_VALUES:
    for ksl in KSL_VALUES:
        for trend in TREND_VALUES:
            env = dict(os.environ)
            env.update({
                "OHLC_CSV": CSV,
                "OB_EQ": EQ,
                "OB_RISK": RISK,
                "OB_RSI_UP": RSI_UP,
                "OB_RSI_DN": RSI_DN,
                "OB_KTP": str(ktp),
                "OB_KSL": str(ksl),
                "OB_MIN_TP": os.getenv("OB_MIN_TP", "6"),
                "OB_MIN_SL": os.getenv("OB_MIN_SL", "6"),
                "OB_TREND_SMA": str(trend),
                "OB_SPREAD_PIPS": SPREAD,
                "OB_FEE_PIPS": FEE,
                "OB_OUTCSV": "",  # suppress CSV output
            })
            try:
                output = subprocess.check_output(
                    [sys.executable, "ohlc_backtest_atr.py"],
                    env=env,
                    text=True,
                    stderr=subprocess.STDOUT,
                ).strip()
            except subprocess.CalledProcessError as exc:
                output = exc.output.strip()
            parts = output.split()
            try:
                trades = parts[0].split(":")[1]
                win = parts[1].split(":")[1]
                pf = parts[2].split(":")[1]
                net = parts[3].split(":")[1]
                final = parts[4].split(":")[1]
                ret = parts[5].split("(")[1].split("%") [0]
                maxdd = parts[6].split(":")[1]
                print(f"{ktp:4.1f} {ksl:4.1f} {trend:5d} | {trades:>6} {win:>6} {pf:>4} {net:>8} {final:>8} {ret:>6} {maxdd:>7}")
            except Exception:
                print(f"{ktp:4.1f} {ksl:4.1f} {trend:5d} | failed -> {output}")
