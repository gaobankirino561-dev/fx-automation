import unittest

from indicators import IndicatorSnapshot
from summarizer import summarize_indicators


class SummarizerTest(unittest.TestCase):
    def test_snapshot_summary_matches_expected_format(self) -> None:
        snapshot = IndicatorSnapshot(atr=0.2857142857, rsi=82.5806451613, sma=156.5535714286)
        summary = summarize_indicators(snapshot)
        expected = "ATR(14): 0.286 (elevated volatility) | RSI(14): 82.6 (overbought bias) | SMA(14): 156.554"
        self.assertEqual(summary, expected)

    def test_type_validation(self) -> None:
        with self.assertRaises(TypeError):
            summarize_indicators("not snapshot")


if __name__ == "__main__":
    unittest.main()



