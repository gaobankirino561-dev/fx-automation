"""
Deterministic sample trade list (no external data/AI).
Used to keep the CI gate fully reproducible.
"""

PNL_YEN = [
    # Early phase: alternate wins/losses to keep drawdown tight
    +500, -400, +500, -400, +500, -400, +500, -400, +500, -400,
    +500, -400, +500, -400, +500, -400, +500, -400, +500, -400,
    # Mid phase: bias towards wins to push the equity peak higher
    +500, +500, -400, +500, +500, -400, +500, +500, -400, +500,
    # Late phase: still interleaving losses but finishing on strength
    -400, -400, +500, -400, +500, -400, +500, +500, -400, +500,
]

SAMPLE_TRADES = PNL_YEN
