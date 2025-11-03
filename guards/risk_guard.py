from dataclasses import dataclass

@dataclass
class EquitySnapshot:
    balance_jpy: float
    equity_jpy: float
    peak_equity_jpy: float
    today_start_equity_jpy: float
    open_positions: int
    minutes_since_last_close: int

@dataclass
class RiskConfig:
    max_daily_loss_pct: float
    max_drawdown_pct: float
    max_concurrent_positions: int
    per_trade_risk_jpy: float
    cooldown_minutes_after_close: int

def check_daily_loss(s: EquitySnapshot, c: RiskConfig):
    base = max(1.0, s.today_start_equity_jpy)
    loss_pct = max(0.0, (s.today_start_equity_jpy - s.equity_jpy) / base * 100.0)
    ok = loss_pct <= c.max_daily_loss_pct
    return ok, f"daily_loss_pct={loss_pct:.2f}<=limit({c.max_daily_loss_pct}%)"

def check_drawdown(s: EquitySnapshot, c: RiskConfig):
    base = max(1.0, s.peak_equity_jpy)
    dd_pct = max(0.0, (s.peak_equity_jpy - s.equity_jpy) / base * 100.0)
    ok = dd_pct <= c.max_drawdown_pct
    return ok, f"dd_pct={dd_pct:.2f}<=limit({c.max_drawdown_pct}%)"

def check_exposure(s: EquitySnapshot, c: RiskConfig):
    ok = s.open_positions < c.max_concurrent_positions
    return ok, f"open_positions={s.open_positions}<limit({c.max_concurrent_positions})"

def check_cooldown(s: EquitySnapshot, c: RiskConfig):
    ok = s.minutes_since_last_close >= c.cooldown_minutes_after_close
    return ok, f"cooldown_ok={ok}({s.minutes_since_last_close}m>= {c.cooldown_minutes_after_close}m)"

def all_checks(s: EquitySnapshot, c: RiskConfig):
    results = [check_daily_loss(s,c), check_drawdown(s,c), check_exposure(s,c), check_cooldown(s,c)]
    oks = [ok for ok,_ in results]
    msgs = [msg for _,msg in results]
    return all(oks), msgs
