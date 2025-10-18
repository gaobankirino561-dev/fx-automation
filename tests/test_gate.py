from gate.backtest_sample import run_sample


def test_sample_metrics():
    metrics = run_sample()
    assert metrics["trades"] >= 30
    assert metrics["net_pnl"] > 0
    assert metrics["win_rate"] >= 0.45
    assert metrics["max_dd_pct"] <= 0.20
