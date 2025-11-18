# --- sys.path bootstrap for local packages (trading/*) ---
import sys, pathlib, importlib.util
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# ----------------------------------------------------------

def _resolve_signal_gpt():
    """
    1) 通常 import
    2) 直接ファイル読込（衝突/パス問題対策）
    3) 最終モック（BUY固定）— KILLテスト用
    """
    # 1) 標準 import（trading パッケージ）
    try:
        from trading import signal_gpt as _m
        return _m
    except Exception as _e1:
        err1 = _e1

    # 2) 直読み（repo/trading/signal_gpt.py を直接ロード）
    try:
        p = REPO_ROOT / "trading" / "signal_gpt.py"
        if p.exists():
            spec = importlib.util.spec_from_file_location("signal_gpt_local", str(p))
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            return mod
    except Exception as _e2:
        err2 = _e2

    # 3) 最終モック：必ず BUY を返す（KILL動作検証のため）
    class _Mock:
        @staticmethod
        def judge(prompt:str, model:str="gpt-4o", max_tokens:int=300):
            return {"decision":"BUY",
                    "reason":f"embedded mock (import error: {type(err1).__name__ if 'err1' in locals() else ''}/{type(err2).__name__ if 'err2' in locals() else ''})"}
    return _Mock

# 以降のコードからは `signal_gpt.judge(...)` をそのまま使えるように束ねる
signal_gpt = _resolve_signal_gpt()
# --- sys.path bootstrap for local packages (trading/*) ---
import sys, pathlib
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
# ----------------------------------------------------------
import os, csv, json, pathlib, datetime as dt, traceback, re
from typing import Any, Dict, List, Tuple
import yaml

from strategies import StrategyBase, StrategyContext, create_strategy

OUTDIR = pathlib.Path("artifacts") / "papertrade_live"
OUTDIR.mkdir(parents=True, exist_ok=True)
STATE = OUTDIR / "state.json"
TRADES = OUTDIR / "trades.csv"
METRICS = OUTDIR / "metrics.csv"
DECISIONS = OUTDIR / "decisions.jsonl"
DEFAULT_STRATEGY_ID = "usdjpy_m15_v1"

def read_cfg(path="papertrade/config_live.yaml")->dict:
    with open(path,"r",encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        return {"strategy_id": DEFAULT_STRATEGY_ID}
    cfg.setdefault("strategy_id", DEFAULT_STRATEGY_ID)
    cfg.setdefault("symbol", cfg.get("pair", "USDJPY"))
    cfg.setdefault("pair", cfg.get("symbol", "USDJPY"))
    return cfg


def load_portfolio_config(path="configs/portfolio_live.yaml") -> List[Dict[str, float]]:
    cfg_path = pathlib.Path(path)
    if not cfg_path.exists():
        return []
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        print(f"[portfolio] failed to read {path}: {exc}; fallback to single strategy")
        return []
    portfolio = data.get("portfolio", {})
    entries = portfolio.get("strategies", []) or []
    result: List[Dict[str, float]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        sid = entry.get("id")
        if not sid:
            continue
        try:
            weight = float(entry.get("weight", 1.0))
        except (TypeError, ValueError):
            weight = 0.0
        result.append({"id": str(sid), "weight": weight})
    return result

# --- 追加: ${VAR:default} / 数値文字列の両対応パーサ ---
_env_pat = re.compile(r"^\$\{([A-Z0-9_]+)(?::([^}]*))?\}$")
def as_int(val, default:int)->int:
    if isinstance(val,int): return val
    if isinstance(val,float): return int(val)
    if isinstance(val,str):
        m=_env_pat.match(val.strip())
        if m:
            var=m.group(1); d=m.group(2)
            raw=os.getenv(var, d if d not in (None,"") else str(default))
            try: return int(str(raw))
            except: return int(default)
        try: return int(val.strip())
        except: return int(default)
    return int(default)

def as_str(val, default:str)->str:
    if val is None: return default
    if isinstance(val,str):
        m=_env_pat.match(val.strip())
        if m:
            var=m.group(1); d=m.group(2)
            return os.getenv(var, d if d is not None else default)
        return val
    return str(val)

def read_state()->dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"equity_jpy":0.0,"wins":0,"losses":0,"trades":0,
            "max_dd_jpy":0.0,"peak_equity_jpy":0.0,"consec_losses":0,
            "last_reset_date": None}

def write_state(s:dict)->None:
    STATE.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")

def ensure_csv_headers(strategy_id: str):
    expected = ["time","side","entry","exit","pnl_jpy","reason","strategy_id"]
    if not TRADES.exists():
        with open(TRADES,"w",newline="",encoding="utf-8") as f:
            csv.DictWriter(f,fieldnames=expected).writeheader()
        return
    with open(TRADES,"r",encoding="utf-8") as f:
        header = f.readline()
    if "strategy_id" in header:
        return
    with open(TRADES,"r",encoding="utf-8",newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    with open(TRADES,"w",newline="",encoding="utf-8") as f:
        writer = csv.DictWriter(f,fieldnames=expected)
        writer.writeheader()
        for row in rows:
            row = {k: row.get(k,"") for k in expected}
            row["strategy_id"] = row["strategy_id"] or strategy_id
            writer.writerow(row)

def append_decision(obj:dict)->None:
    with open(DECISIONS,"a",encoding="utf-8") as f:
        f.write(json.dumps(obj,ensure_ascii=False)+"\n")

def write_metrics(s:dict, strategy_id: str):
    rows=[("net_jpy",s["equity_jpy"]),
          ("win_rate_pct",(100*s["wins"]/max(1,s["trades"])) if s["trades"] else 0),
          ("max_drawdown_pct",(100*abs(s["max_dd_jpy"])/max(1,s["peak_equity_jpy"])) if s["peak_equity_jpy"]>0 else 0),
          ("trades", s["trades"])]
    with open(METRICS,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["metric","value","strategy_id"]); w.writeheader()
        for k,v in rows:
            w.writerow({"metric":k,"value":str(round(v,4)),"strategy_id":strategy_id})

def paper_entry(side:str, price:float, cfg:dict)->dict:
    atr_p = 0.002
    tp = price*(1+atr_p) if side=="BUY" else price*(1-atr_p)
    sl = price*(1-atr_p) if side=="BUY" else price*(1+atr_p)
    return {"tp":tp,"sl":sl}

def kill_switch(s:dict, cfg:dict)->tuple[bool,str]:
    r = cfg["risk"]
    today = dt.datetime.utcnow().date().isoformat()
    if s["last_reset_date"] != today:
        s["last_reset_date"] = today
        s["consec_losses"] = 0
        write_state(s)
    if as_int(r.get("daily_max_loss_jpy",0),0) and s["equity_jpy"] <= -abs(as_int(r.get("daily_max_loss_jpy",0),0)):
        return True,"daily_max_loss"
    if as_int(r.get("max_consecutive_losses",0),0) and s["consec_losses"] >= as_int(r.get("max_consecutive_losses",0),0):
        return True,"max_consecutive_losses"
    mxdd = as_int(r.get("max_drawdown_pct",0),0)
    if mxdd and s["peak_equity_jpy"]>0:
        dd = 100*abs(s["max_dd_jpy"])/s["peak_equity_jpy"]
        if dd >= float(mxdd):
            return True,"max_drawdown_pct"
    return False,""

def get_last_price(pair:str)->float:
    base=150.00
    bump=(dt.datetime.utcnow().minute % 5)*0.005
    return round(base + bump, 3)

def _normalize_timeframes(cfg: Dict[str, Any]) -> Dict[str, str]:
    tf = cfg.get("timeframes")
    if isinstance(tf, dict):
        return {str(k): str(v) for k,v in tf.items()}
    if isinstance(tf, list):
        return {f"t{i}": str(v) for i, v in enumerate(tf)}
    single = cfg.get("timeframe")
    if single:
        return {"primary": str(single)}
    return {"primary": "M15"}


def _create_strategy(cfg: Dict[str, Any]) -> StrategyBase:
    strategy_id = str(cfg.get("strategy_id") or DEFAULT_STRATEGY_ID)
    context = StrategyContext(
        strategy_id=strategy_id,
        symbol=str(cfg.get("symbol") or cfg.get("pair") or "USDJPY"),
        timeframes=_normalize_timeframes(cfg),
        config=cfg,
    )
    return create_strategy(strategy_id, context)


def _build_portfolio_strategies(cfg: Dict[str, Any], portfolio_entries: List[Dict[str, float]]) -> List[Tuple[str, float, StrategyBase]]:
    strategies: List[Tuple[str, float, StrategyBase]] = []
    base_lot = float(cfg.get("lot") or 0.1)
    valid = [entry for entry in portfolio_entries if entry.get("weight", 0) > 0]
    total_weight = sum(entry["weight"] for entry in valid)
    entries = valid if total_weight > 0 else []
    if entries:
        for entry in entries:
            sid = entry["id"]
            normalized_weight = entry["weight"] / total_weight
            strategy_cfg = dict(cfg)
            strategy_cfg["strategy_id"] = sid
            strategy_cfg["lot"] = round(base_lot * normalized_weight, 6)
            try:
                strategy = _create_strategy(strategy_cfg)
            except Exception as exc:
                print(f"[portfolio] skip strategy {sid}: {exc}")
                continue
            strategies.append((sid, normalized_weight, strategy))
    if not strategies:
        try:
            fallback_strategy = _create_strategy(cfg)
            strategies = [(cfg.get("strategy_id", DEFAULT_STRATEGY_ID), 1.0, fallback_strategy)]
        except Exception as exc:
            raise RuntimeError(f"Failed to build fallback strategy: {exc}") from exc
    return strategies


def run_once():
    cfg = read_cfg()
    portfolio_cfg = load_portfolio_config()
    strategy_entries = _build_portfolio_strategies(cfg, portfolio_cfg)
    primary_sid = strategy_entries[0][0]
    s = read_state()
    ensure_csv_headers(primary_sid)

    if as_str(os.getenv("PAPERTRADE_HALT",""),"").lower() in ("1","true","yes"):
        write_metrics(s, primary_sid); return "HALT"

    pair = cfg["pair"]
    price = get_last_price(pair)
    model = as_str(cfg["gpt"].get("model","gpt-4o"), "gpt-4o")
    max_tokens = as_int(cfg["gpt"].get("max_tokens",300), 300)

    now_ts = dt.datetime.utcnow()
    for sid, weight, strategy in strategy_entries:
        entry_decision = strategy.decide_entry(
            {"price": price, "timestamp": now_ts, "model": model, "max_tokens": max_tokens}
        )
        dec_payload = entry_decision.get("raw_decision") or {}
        append_decision({
            "ts":dt.datetime.utcnow().isoformat()+"Z",
            "pair":pair,
            "price":price,
            "strategy_id":sid,
            "gpt":dec_payload,
        })

        side = entry_decision.get("action","NO_ENTRY")
        decision_reason = entry_decision.get("reason","")
        if side in ("BUY","SELL"):
            fill = price
            exit_info = strategy.decide_exit({"entry_price": fill, "side": side, "timestamp": dt.datetime.utcnow()})
            exitp = exit_info.get("exit_price", fill)
            pnl = float(exit_info.get("pnl_jpy", 0.0))
            exit_reason = exit_info.get("reason") or decision_reason
            with open(TRADES,"a",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["time","side","entry","exit","pnl_jpy","reason","strategy_id"])
                w.writerow({
                    "time":dt.datetime.utcnow().isoformat()+"Z",
                    "side":side,
                    "entry":fill,
                    "exit":exitp,
                    "pnl_jpy":pnl,
                    "reason":exit_reason,
                    "strategy_id":sid,
                })

            s["trades"] += 1
            s["equity_jpy"] += pnl
            s["peak_equity_jpy"] = max(s["peak_equity_jpy"], s["equity_jpy"])
            s["max_dd_jpy"] = min(s["max_dd_jpy"], s["equity_jpy"]-s["peak_equity_jpy"])
            s["consec_losses"] = 0 if pnl>=0 else s["consec_losses"]+1
            write_state(s)

    ks, kreason = kill_switch(s, cfg)
    write_metrics(s, primary_sid)
    return "KILL" if ks else "OK"

if __name__ == "__main__":
    try:
        st = run_once()
        print(f"## papertrade-live (impl)\n- time: {dt.datetime.utcnow().isoformat()}Z\n- status: {st}\n- artifacts: metrics.csv / trades.csv / decisions.jsonl")
    except Exception as e:
        if not OUTDIR.exists(): OUTDIR.mkdir(parents=True, exist_ok=True)
        if not TRADES.exists():
            with open(TRADES,"w",newline="",encoding="utf-8") as f:
                csv.DictWriter(f,fieldnames=["time","side","entry","exit","pnl_jpy","reason","strategy_id"]).writeheader()
        if not METRICS.exists():
            with open(METRICS,"w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["metric","value","strategy_id"]); w.writeheader()
                w.writerows([
                    {"metric":"net_jpy","value":"0","strategy_id":DEFAULT_STRATEGY_ID},
                    {"metric":"win_rate_pct","value":"0","strategy_id":DEFAULT_STRATEGY_ID},
                    {"metric":"max_drawdown_pct","value":"0","strategy_id":DEFAULT_STRATEGY_ID},
                    {"metric":"trades","value":"0","strategy_id":DEFAULT_STRATEGY_ID},
                ])
        with open(DECISIONS,"a",encoding="utf-8") as f:
            f.write(json.dumps({"ts":dt.datetime.utcnow().isoformat()+"Z","error":type(e).__name__,"msg":str(e)[:200]})+"\n")
        raise



