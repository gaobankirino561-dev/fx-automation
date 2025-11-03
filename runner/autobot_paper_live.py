import os, csv, json, math, pathlib, datetime as dt, traceback
from typing import Any
import yaml

OUTDIR = pathlib.Path("artifacts") / "papertrade_live"
OUTDIR.mkdir(parents=True, exist_ok=True)
STATE = OUTDIR / "state.json"
TRADES = OUTDIR / "trades.csv"
METRICS = OUTDIR / "metrics.csv"
DECISIONS = OUTDIR / "decisions.jsonl"

def read_cfg(path="papertrade/config_live.yaml")->dict:
    with open(path,"r",encoding="utf-8") as f:
        return yaml.safe_load(f)

def read_state()->dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"equity_jpy":0.0,"wins":0,"losses":0,"trades":0,
            "max_dd_jpy":0.0,"peak_equity_jpy":0.0,"consec_losses":0,
            "last_reset_date": None}

def write_state(s:dict)->None:
    STATE.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding="utf-8")

def ensure_csv_headers():
    if not TRADES.exists():
        with open(TRADES,"w",newline="",encoding="utf-8") as f:
            csv.DictWriter(f,fieldnames=["time","side","entry","exit","pnl_jpy","reason"]).writeheader()

def append_decision(obj:dict)->None:
    with open(DECISIONS,"a",encoding="utf-8") as f:
        f.write(json.dumps(obj,ensure_ascii=False)+"\n")

def write_metrics(s:dict):
    rows=[("net_jpy",s["equity_jpy"]),
          ("win_rate_pct",(100*s["wins"]/max(1,s["trades"])) if s["trades"] else 0),
          ("max_drawdown_pct",(100*abs(s["max_dd_jpy"])/max(1,s["peak_equity_jpy"])) if s["peak_equity_jpy"]>0 else 0),
          ("trades", s["trades"])]
    with open(METRICS,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["metric","value"]); w.writeheader()
        for k,v in rows:
            w.writerow({"metric":k,"value":str(round(v,4))})

def paper_entry(side:str, price:float, cfg:dict)->dict:
    # ATR等が無くても動くフォールバック幅（約0.2%）
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
    if r["daily_max_loss_jpy"] and s["equity_jpy"] <= -abs(r["daily_max_loss_jpy"]):
        return True,"daily_max_loss"
    if r["max_consecutive_losses"] and s["consec_losses"] >= int(r["max_consecutive_losses"]):
        return True,"max_consecutive_losses"
    if r["max_drawdown_pct"] and s["peak_equity_jpy"]>0:
        dd = 100*abs(s["max_dd_jpy"])/s["peak_equity_jpy"]
        if dd >= float(r["max_drawdown_pct"]):
            return True,"max_drawdown_pct"
    return False,""

def get_last_price(pair:str)->float:
    # 依存が無くても動くダミー価格（UTC分で微小変動）
    base=150.00
    bump=(dt.datetime.utcnow().minute % 5)*0.005
    return round(base + bump, 3)

def run_once():
    import importlib
    cfg = read_cfg()
    s = read_state()
    ensure_csv_headers()

    # 緊急停止フラグ
    if os.getenv("PAPERTRADE_HALT","").lower() in ("1","true","yes"):
        write_metrics(s)
        return "HALT"

    pair = cfg["pair"]
    price = get_last_price(pair)
    model = cfg["gpt"]["model"]
    max_tokens = int(str(cfg["gpt"].get("max_tokens",300)))

    # GPT判定（無ければNO_ENTRYで継続）
    try:
        sg = importlib.import_module("trading.signal_gpt")
        prompt = f"{pair} price={price}. Decide BUY/SELL/NO_ENTRY for next 5-15min with short reason. Reply JSON."
        dec = sg.judge(prompt, model=model, max_tokens=max_tokens)
    except Exception as e:
        dec = {"decision":"NO_ENTRY","reason":f"signal_gpt missing: {type(e).__name__}"}

    append_decision({"ts":dt.datetime.utcnow().isoformat()+"Z","pair":pair,"price":price,"gpt":dec})

    side = dec.get("decision","NO_ENTRY")
    if side in ("BUY","SELL"):
        fill = price
        r = paper_entry(side, fill, cfg)
        # まずは配線確認のため同値決済（0円）
        exitp = fill
        pnl = 0.0
        with open(TRADES,"a",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=["time","side","entry","exit","pnl_jpy","reason"])
            w.writerow({"time":dt.datetime.utcnow().isoformat()+"Z","side":side,"entry":fill,"exit":exitp,"pnl_jpy":pnl,"reason":dec.get("reason","")})

        s["trades"] += 1
        s["equity_jpy"] += pnl
        s["peak_equity_jpy"] = max(s["peak_equity_jpy"], s["equity_jpy"])
        s["max_dd_jpy"] = min(s["max_dd_jpy"], s["equity_jpy"]-s["peak_equity_jpy"])
        s["consec_losses"] = 0 if pnl>=0 else s["consec_losses"]+1
        write_state(s)

    ks, kreason = kill_switch(s, cfg)
    write_metrics(s)
    return "KILL" if ks else "OK"

if __name__ == "__main__":
    try:
        st = run_once()
        print(f"## papertrade-live (impl)\n- time: {dt.datetime.utcnow().isoformat()}Z\n- status: {st}\n- artifacts: metrics.csv / trades.csv / decisions.jsonl")
    except Exception as e:
        # 落とさない：最低限の成果物は必ず残す
        if not OUTDIR.exists(): OUTDIR.mkdir(parents=True, exist_ok=True)
        if not TRADES.exists():
            with open(TRADES,"w",newline="",encoding="utf-8") as f:
                csv.DictWriter(f,fieldnames=["time","side","entry","exit","pnl_jpy","reason"]).writeheader()
        if not METRICS.exists():
            with open(METRICS,"w",newline="",encoding="utf-8") as f:
                w=csv.DictWriter(f,fieldnames=["metric","value"]); w.writeheader()
                w.writerows([{"metric":"net_jpy","value":"0"},{"metric":"win_rate_pct","value":"0"},{"metric":"max_drawdown_pct","value":"0"},{"metric":"trades","value":"0"}])
        with open(DECISIONS,"a",encoding="utf-8") as f:
            f.write(json.dumps({"ts":dt.datetime.utcnow().isoformat()+"Z","error":type(e).__name__,"msg":str(e)[:200]})+"\n")
        raise
