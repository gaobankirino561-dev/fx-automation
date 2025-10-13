import os
import subprocess
import itertools

BASE = {
    "OHLC_CSV": os.getenv("OHLC_CSV", "data\\ohlc.csv"),
    "OB_EQ": "10000",
    "OB_RISK": "0.003",
    "OB_MIN_TP": "6",
    "OB_MIN_SL": "6",
    "OB_ATR_MIN_PIPS": "4",
    "OB_ATR_MAX_PIPS": "40",
    "OB_TRADE_START": "07:00",
    "OB_TRADE_END": "22:00",
    "OB_EXCL_DOW": "6",
    "OB_SPREAD_PIPS": "0.2",
    "OB_FEE_PIPS": "0",
}

KTP = [1.2, 1.6, 2.0]
KSL = [0.8, 1.0, 1.2]
TREND = [0, 50, 100]
RSI = [(55, 45), (60, 40)]


def run(env):
    e = os.environ.copy()
    e.update(BASE)
    e.update(env)
    e["OB_OUTCSV"] = "nul"
    out = subprocess.check_output(["python", "ohlc_backtest_atr.py"], env=e, text=True).strip()

    def pick(tag, sep=" "):
        s = out.split(tag, 1)[1]
        return s.split(sep, 1)[0]

    pf = float(pick("PF:"))
    ret = float(pick("(", "%"))
    dd = float(pick("maxDD%:"))
    tr = int(pick("trades:"))
    return tr, pf, ret, dd, out


rows = []
for ktp, ksl, trd, (up, dn) in itertools.product(KTP, KSL, TREND, RSI):
    env = {
        "OB_KTP": str(ktp),
        "OB_KSL": str(ksl),
        "OB_TREND_SMA": str(trd),
        "OB_RSI_UP": str(up),
        "OB_RSI_DN": str(dn),
    }
    tr, pf, ret, dd, out = run(env)
    rows.append((pf, ret, -dd, tr, ktp, ksl, trd, up, dn))

rows.sort(reverse=True)
print("ktp ksl trend rsi  | trades  PF  return%  maxDD%")
for pf, ret, negdd, tr, ktp, ksl, trd, up, dn in rows[:15]:
    print(f"{ktp:>3} {ksl:>3} {trd:>5} {up:>2}/{dn:<2} | {tr:>6} {pf:5.2f} {ret:8.2f} {(-negdd):7.2f}")

