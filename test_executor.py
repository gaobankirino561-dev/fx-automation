import unittest

from executor import TradeExecutor
from position_entities import Order


class TradeExecutorTest(unittest.TestCase):
    def test_submit_creates_position(self) -> None:
        executor = TradeExecutor()
        order = Order(side="BUY", price=150.0, tp_pips=5, sl_pips=5, size=0.2)
        fill = executor.submit(order, now_price=150.0, now_ts=1)
        self.assertEqual(fill.result, "OPENED")
        positions = executor.positions()
        self.assertEqual(len(positions), 1)
        self.assertAlmostEqual(positions[0].tp, 150.05)

    def test_step_hits_tp(self) -> None:
        executor = TradeExecutor()
        order = Order(side="BUY", price=150.0, tp_pips=5, sl_pips=5)
        executor.submit(order, now_price=150.0, now_ts=1)
        fills = executor.step(now_price=150.05, now_ts=2)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].result, "TP")
        self.assertEqual(len(executor.positions()), 0)

    def test_step_handles_multiple_positions(self) -> None:
        executor = TradeExecutor()
        buy_order = Order(side="BUY", price=150.0, tp_pips=5, sl_pips=5)
        sell_order = Order(side="SELL", price=151.0, tp_pips=10, sl_pips=5)
        executor.submit(buy_order, now_price=150.0, now_ts=1)
        executor.submit(sell_order, now_price=151.0, now_ts=1)
        fills = executor.step(now_price=151.1, now_ts=2)
        self.assertEqual(len(fills), 2)
        results = {fill.position.side: fill.result for fill in fills}
        self.assertEqual(results.get("BUY"), "TP")
        self.assertEqual(results.get("SELL"), "SL")
        self.assertEqual(len(executor.positions()), 0)

    def test_close_all_manual(self) -> None:
        executor = TradeExecutor()
        order = Order(side="SELL", price=150.0, tp_pips=5, sl_pips=5, size=2.0)
        executor.submit(order, now_price=150.0, now_ts=1)
        fills = executor.close_all(now_price=149.5, now_ts=10)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].result, "MANUAL_CLOSE")
        self.assertAlmostEqual(fills[0].pnl, 100.0)
        self.assertEqual(len(executor.positions()), 0)

    def test_buy_tp_after_multiple_steps(self) -> None:
        executor = TradeExecutor()
        order = Order(side="BUY", price=150.0, tp_pips=5, sl_pips=5, size=0.5)
        executor.submit(order, now_price=150.0, now_ts=1)
        self.assertEqual(executor.step(now_price=150.02, now_ts=2), [])
        fills = executor.step(now_price=150.05, now_ts=3)
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.result, "TP")
        self.assertGreater(fill.pnl, 0.0)
        self.assertEqual(len(executor.positions()), 0)

    def test_sell_tp_after_multiple_steps(self) -> None:
        executor = TradeExecutor()
        order = Order(side="SELL", price=150.0, tp_pips=5, sl_pips=5, size=0.3)
        executor.submit(order, now_price=150.0, now_ts=1)
        self.assertEqual(executor.step(now_price=149.98, now_ts=2), [])
        fills = executor.step(now_price=149.95, now_ts=3)
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.result, "TP")
        self.assertGreater(fill.pnl, 0.0)
        self.assertEqual(len(executor.positions()), 0)

    def test_sl_trigger_for_buy(self) -> None:
        executor = TradeExecutor()
        order = Order(side="BUY", price=150.0, tp_pips=5, sl_pips=5, size=0.4)
        executor.submit(order, now_price=150.0, now_ts=1)
        fills = executor.step(now_price=149.95, now_ts=2)
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.result, "SL")
        self.assertLess(fill.pnl, 0.0)
        self.assertEqual(len(executor.positions()), 0)

    def test_sl_trigger_for_sell(self) -> None:
        executor = TradeExecutor()
        order = Order(side="SELL", price=150.0, tp_pips=5, sl_pips=5, size=0.4)
        executor.submit(order, now_price=150.0, now_ts=1)
        fills = executor.step(now_price=150.05, now_ts=2)
        self.assertEqual(len(fills), 1)
        fill = fills[0]
        self.assertEqual(fill.result, "SL")
        self.assertLess(fill.pnl, 0.0)
        self.assertEqual(len(executor.positions()), 0)


if __name__ == "__main__":
    unittest.main()
