from typing import List, Tuple
import random

# Return list of (open, high, low, close)

def gen_synth_bars(n: int = 96, seed: int = 1729) -> List[Tuple[float, float, float, float]]:
    random.seed(seed)
    price = 150.00
    out: List[Tuple[float, float, float, float]] = []
    for i in range(n):
        drift = (0.02 if (i % 24) < 12 else -0.02)
        noise = random.uniform(-0.05, 0.05)
        o = price
        c = max(1e-6, o + drift + noise)
        lo = min(o, c) - random.uniform(0.00, 0.05)
        hi = max(o, c) + random.uniform(0.00, 0.05)
        out.append((round(o, 3), round(hi, 3), round(lo, 3), round(c, 3)))
        price = c
    return out
