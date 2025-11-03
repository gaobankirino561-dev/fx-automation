import json, os
from datetime import datetime, timezone
from typing import Dict
from trading.decision import Decision
try:
    from openai import OpenAI  # type: ignore
except Exception:
    OpenAI = None  # type: ignore

GPT_MAX_CALLS = int(os.getenv("GPT_MAX_CALLS", "3"))
GPT_MAX_TOKENS = int(os.getenv("GPT_MAX_TOKENS", "300"))
_gpt_call_count = 0


def decide_with_gpt(context: Dict) -> Decision:
    if not OpenAI or not os.getenv("OPENAI_API_KEY"):
        return Decision.none("no_api_key")
    global _gpt_call_count
    if _gpt_call_count >= GPT_MAX_CALLS:
        return Decision.none("max_calls")
    _gpt_call_count += 1
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o", temperature=0,
        messages=[
            {"role": "system", "content": "You are a trading decision assistant. Respond ONLY as compact JSON."},
            {"role": "user", "content": (
                "Return JSON: {side:(BUY|SELL|NONE), tp_pips:number, sl_pips:number, reason:string}. "
                "If no clear edge → side=NONE. Keep risk small."
            )},
        ],
        response_format={"type": "json_object"},
        max_tokens=GPT_MAX_TOKENS,
    )
    try:
        obj = json.loads(resp.choices[0].message.content)
        side = str(obj.get("side", "NONE")).upper()
        if side not in ("BUY", "SELL", "NONE"):
            side = "NONE"
        dec = Decision(side, float(obj.get("tp_pips", 0)), float(obj.get("sl_pips", 0)), str(obj.get("reason", "gpt")))
        try:
            p=os.getenv("DECISIONS_JSONL")
            if p:
                with open(p, "a", encoding="utf-8") as f:
                    rec = {
                        "ts_utc": datetime.now(timezone.utc).isoformat(),
                        "side": dec.side,
                        "tp_pips": dec.tp_pips,
                        "sl_pips": dec.sl_pips,
                        "reason": dec.reason,
                        "flags": {"no_api_key": (dec.reason == "no_api_key")},
                    }
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return dec
    except Exception:
        return Decision.none("gpt_parse_error")
