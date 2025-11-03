from dataclasses import dataclass

@dataclass
class Decision:
    side: str      # "BUY" | "SELL" | "NONE"
    tp_pips: float
    sl_pips: float
    reason: str

    @staticmethod
    def none(msg: str = "no_entry") -> "Decision":
        return Decision("NONE", 0.0, 0.0, msg)
