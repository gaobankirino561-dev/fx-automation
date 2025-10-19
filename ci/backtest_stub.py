#!/usr/bin/env python3
import json
open("metrics.json","w",encoding="utf-8").write(
  json.dumps({"net_profit":-1,"win_rate":0.30,"max_drawdown":0.50,"trades":5}, ensure_ascii=False))
print("[stub] wrote metrics.json")
