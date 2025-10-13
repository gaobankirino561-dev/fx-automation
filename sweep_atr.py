import os
import subprocess
import itertools


def run(ktp, ksl, trend):
    env = dict(os.environ)
    env.update(
        OB_KTP=str(ktp),
        OB_KSL=str(ksl),
        OB_TREND_SMA=str(trend),
        OB_OUTCSV="nul"
    )
    out = subprocess.check_output(["python", "ohlc_backtest_atr.py"], env=env, text=True).strip()
    pf = float(out.split("PF:")[1].split()[0])
    ret = float(out.split("(")[1].split("%") [0])
    dd = float(out.split("maxDD%:")[1].split()[0])
    trades = int(out.split("trades:")[1].split()[0])
    return trades, pf, ret, dd, out


KTP = [1.0, 1.5, 2.0]
KSL = [0.8, 1.0, 1.5]
TREND = [0, 50]

print("ktp ksl trend | trades PF return% maxDD%")
for ktp, ksl, trend in itertools.product(KTP, KSL, TREND):
    trades, pf, ret, dd, _ = run(ktp, ksl, trend)
    print(f"{ktp:>3} {ksl:>3} {trend:>5} | {trades:>6} {pf:0.2f} {ret:7.1f} {dd:7.1f}")
