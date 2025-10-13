import unittest

from position_entities import (
    Order,
    Fill,
    Position,
    close_position,
    open_position,
    update_position,
)


class PositionEntitiesTest(unittest.TestCase):
    def test_open_position_buy(self) -> None:
        order = Order(side="BUY", price=150.0, tp_pips=10, sl_pips=5, size=0.5)
        fill = open_position(order, now_price=150.2, now_ts=123456)
        self.assertEqual(fill.result, "OPENED")
        position = fill.position
        self.assertEqual(position.side, "BUY")
        self.assertAlmostEqual(position.entry, 150.2)
        self.assertAlmostEqual(position.tp, 150.3)
        self.assertAlmostEqual(position.sl, 150.15)
        self.assertEqual(position.open_time, 123456)

    def test_open_position_sell(self) -> None:
        order = Order(side="SELL", price=150.0, tp_pips=15, sl_pips=5)
        fill = open_position(order, now_price=149.9, now_ts=42)
        position = fill.position
        self.assertAlmostEqual(position.tp, 149.75)
        self.assertAlmostEqual(position.sl, 149.95)

    def test_update_position_buy_tp(self) -> None:
        order = Order(side="BUY", price=150.0, tp_pips=5, sl_pips=5)
        fill = open_position(order, now_price=150.0, now_ts=1)
        position = fill.position
        result = update_position(position, now_price=150.05, now_ts=2)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.result, "TP")
        self.assertAlmostEqual(result.pnl, 5 * position.size)

    def test_update_position_sell_sl(self) -> None:
        order = Order(side="SELL", price=150.0, tp_pips=5, sl_pips=5, size=2.0)
        fill = open_position(order, now_price=150.0, now_ts=1)
        position = fill.position
        result = update_position(position, now_price=150.05, now_ts=2)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.result, "SL")
        self.assertAlmostEqual(result.pnl, -5 * position.size)

    def test_update_position_no_trigger(self) -> None:
        order = Order(side="BUY", price=150.0, tp_pips=5, sl_pips=5)
        fill = open_position(order, now_price=150.0, now_ts=1)
        position = fill.position
        result = update_position(position, now_price=150.02, now_ts=2)
        self.assertIsNone(result)

    def test_close_position_manual(self) -> None:
        order = Order(side="BUY", price=150.0, tp_pips=5, sl_pips=5, size=2.0)
        fill = open_position(order, now_price=150.0, now_ts=1)
        position = fill.position
        manual = close_position(position, exit_price=149.9, now_ts=5, result="MANUAL_CLOSE")
        self.assertEqual(manual.result, "MANUAL_CLOSE")
        self.assertAlmostEqual(manual.pnl, -20.0)


if __name__ == "__main__":
    unittest.main()
