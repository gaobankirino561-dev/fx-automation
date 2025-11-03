from __future__ import annotations
import os, json
from openai import OpenAI

def judge(prompt: str, model: str="gpt-4o", max_tokens: int=300) -> dict:
    if not os.getenv("OPENAI_API_KEY",""):
        return {"decision":"NO_ENTRY","reason":"no OPENAI_API_KEY"}
    try:
        client = OpenAI()
        msgs=[
            {"role":"system","content":"Reply ONLY JSON like {\"decision\":\"BUY|SELL|NO_ENTRY\",\"reason\":\"...\"}"},
            {"role":"user","content":prompt}
        ]
        out = client.chat.completions.create(model=model, messages=msgs, max_tokens=max_tokens, temperature=0)
        txt = out.choices[0].message.content.strip()
        try:
            obj = json.loads(txt)
        except Exception:
            obj = {"decision":"NO_ENTRY","reason":txt[:200]}
        if obj.get("decision") not in ("BUY","SELL","NO_ENTRY"):
            obj["decision"]="NO_ENTRY"
        return obj
    except Exception as e:
        return {"decision":"NO_ENTRY","reason":f"gpt error: {type(e).__name__}"}
