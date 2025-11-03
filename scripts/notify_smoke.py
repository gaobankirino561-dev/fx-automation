from notifiers.notify import notify


notify(
    "papertrade_smoke",
    {
        "pair": "USDJPY",
        "side": "TEST",
        "price": "-",
        "pnl_jpy": 0,
        "reason": "skeleton ok",
    },
)
print("notify smoke done")
