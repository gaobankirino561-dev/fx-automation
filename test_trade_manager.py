import unittest

from trade_manager import TradeManager


class TradeManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = TradeManager()

    def test_submit_buy_creates_position(self) -> None:
        result = self.manager.submit_market_order("USDJPY", "BUY", 0.5, price=150.0)
        self.assertTrue(result["ok"])
        order = result["order"]
        self.assertEqual(order["side"], "BUY")
        self.assertAlmostEqual(order["price"], 150.0)
        position = result["position"]
        self.assertIsNotNone(position)
        self.assertAlmostEqual(position["volume"], 0.5)
        self.assertAlmostEqual(position["avg_price"], 150.0)

    def test_partial_close_preserves_average(self) -> None:
        first = self.manager.submit_market_order("USDJPY", "BUY", 1.0, price=150.0)
        self.assertTrue(first["ok"])
        second = self.manager.submit_market_order("USDJPY", "SELL", 0.4, price=151.0)
        self.assertTrue(second["ok"])
        position = second["position"]
        self.assertIsNotNone(position)
        self.assertAlmostEqual(position["volume"], 0.6)
        self.assertAlmostEqual(position["avg_price"], 150.0)

    def test_flip_direction_uses_latest_price(self) -> None:
        self.manager.submit_market_order("USDJPY", "BUY", 1.0, price=150.0)
        result = self.manager.submit_market_order("USDJPY", "SELL", 2.0, price=151.0)
        self.assertTrue(result["ok"])
        position = result["position"]
        self.assertIsNotNone(position)
        self.assertAlmostEqual(position["volume"], -1.0)
        self.assertAlmostEqual(position["avg_price"], 151.0)

    def test_price_required_if_quote_missing(self) -> None:
        outcome = self.manager.submit_market_order("USDJPY", "BUY", 0.1)
        self.assertFalse(outcome["ok"])
        self.assertEqual(outcome["reason"], "PRICE_UNAVAILABLE")
        self.assertEqual(self.manager.get_positions(), {})


if __name__ == "__main__":
    unittest.main()
