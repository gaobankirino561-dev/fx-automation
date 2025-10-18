import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from gate.metrics import compute_metrics
from gate.sample import SAMPLE_TRADES


def test_compute_metrics_thresholds():
    metrics = compute_metrics(SAMPLE_TRADES)
    assert metrics.net_pnl > 0
    assert metrics.win_rate >= 0.45
    assert metrics.max_dd_pct <= 0.20
    assert metrics.trades >= 30
