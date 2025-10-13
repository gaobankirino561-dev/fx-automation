import unittest

from indicators import IndicatorSnapshot, atr, build_snapshot, rsi, simple_moving_average


class IndicatorSnapshotTest(unittest.TestCase):
    highs = [
        155.82,
        156.16,
        156.09,
        156.35,
        156.30,
        156.29,
        156.38,
        156.83,
        156.99,
        156.88,
        156.86,
        156.83,
        156.94,
        156.97,
        156.95,
    ]
    lows = [
        155.50,
        155.56,
        155.80,
        156.00,
        156.15,
        156.05,
        156.16,
        156.15,
        156.55,
        156.68,
        156.70,
        156.72,
        156.69,
        156.81,
        156.81,
    ]
    closes = [
        155.90,
        156.09,
        156.03,
        156.31,
        156.26,
        156.25,
        156.32,
        156.80,
        156.85,
        156.71,
        156.73,
        156.75,
        156.82,
        156.92,
        156.91,
    ]

    def test_indicator_snapshot_matches_expected_values(self) -> None:
        expected = {"atr": 0.285714, "rsi": 82.580645, "sma": 156.553571}
        result = {
            "atr": round(atr(self.highs, self.lows, self.closes, 14), 6),
            "rsi": round(rsi(self.closes, 14), 6),
            "sma": round(simple_moving_average(self.closes, 14), 6),
        }
        self.assertEqual(result, expected)

        snapshot = build_snapshot(self.highs, self.lows, self.closes)
        self.assertIsInstance(snapshot, IndicatorSnapshot)
        self.assertAlmostEqual(snapshot.atr, expected["atr"], places=6)
        self.assertAlmostEqual(snapshot.rsi, expected["rsi"], places=6)
        self.assertAlmostEqual(snapshot.sma, expected["sma"], places=6)


if __name__ == "__main__":
    unittest.main()



