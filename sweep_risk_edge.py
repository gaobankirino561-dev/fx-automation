import os
import subprocess
import sys

RISKS = [0.002, 0.005, 0.01]
EDGES = [0.50, 0.52, 0.55]


def run(risk: float, edge: float) -> tuple[float, float, float]:
    env = dict(
        os.environ,
        RB_TRADES="300",
        RB_SIDE="ALT",
        RB_TP="10",
        RB_SL="8",
        RB_RISK=str(risk),
        RB_EQ="10000",
        RB_EDGE=str(edge),
    )
    output = subprocess.check_output([sys.executable, "risk_backtest.py"], env=env, text=True).strip()
    pf = float(output.split("PF:")[1].split()[0])
    ret = float(output.split("(")[1].split("%") [0])
    dd = float(output.split("maxDD%:")[1].split()[0])
    return pf, ret, dd


print("risk edge |    PF return% maxDD%")
for risk in RISKS:
    for edge in EDGES:
        pf, ret, dd = run(risk, edge)
        print(f"{risk:0.3f} {edge:0.2f} | {pf:5.2f} {ret:7.1f} {dd:7.1f}")
