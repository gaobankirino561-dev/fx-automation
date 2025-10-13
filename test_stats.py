import unittest

from stats import summarize_pips


class TestStats(unittest.TestCase):
    def test_basic(self) -> None:
        p = [10, -8, 12, -5, 7]
        s = summarize_pips(p)
        self.assertEqual(s["trades"], 5)
        self.assertAlmostEqual(s["win_rate"], 60.0, places=1)
        self.assertAlmostEqual(s["gross_profit"], 29.0, places=1)
        self.assertAlmostEqual(s["gross_loss"], 13.0, places=1)
        self.assertAlmostEqual(s["profit_factor"], 2.23, places=2)
        self.assertAlmostEqual(s["net_pips"], 16.0, places=1)


if __name__ == "__main__":
    unittest.main()
