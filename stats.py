from typing import Dict, List


def summarize_pips(pips: List[float]) -> Dict[str, float]:
    trades = len(pips)
    if trades == 0:
        return {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "profit_factor": 0.0,
            "net_pips": 0.0,
            "max_dd": 0.0,
        }

    wins = [x for x in pips if x > 0]
    losses = [-x for x in pips if x < 0]
    gp = float(sum(wins))
    gl = float(sum(losses))
    pf = gp / gl if gl > 0 else (1e9 if gp > 0 else 0.0)
    net = gp - gl

    eq = 0.0
    peak = 0.0
    maxdd = 0.0
    for x in pips:
        eq += x
        peak = max(peak, eq)
        maxdd = max(maxdd, peak - eq)

    return {
        "trades": trades,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": (len(wins) / trades) * 100.0,
        "gross_profit": gp,
        "gross_loss": gl,
        "profit_factor": pf,
        "net_pips": net,
        "max_dd": maxdd,
    }
