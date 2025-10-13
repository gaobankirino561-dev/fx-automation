import importlib
import sys
import unittest


class AdapterWithoutMT5Test(unittest.TestCase):
    def setUp(self) -> None:
        sys.modules.pop("MetaTrader5", None)
        sys.modules.pop("mt5_adapter", None)
        self.adapter = importlib.import_module("mt5_adapter")
        self.adapter.mt5 = None  # force fallback path

    def test_init_without_mt5(self) -> None:
        self.assertEqual(
            self.adapter.init(),
            {"ok": False, "reason": "MT5_NOT_AVAILABLE"},
        )

    def test_get_bars_without_mt5(self) -> None:
        result = self.adapter.get_bars("EURUSD", "M15", 10)
        self.assertEqual(result, {"ok": False, "reason": "MT5_NOT_AVAILABLE"})

    def test_get_quote_without_mt5(self) -> None:
        result = self.adapter.get_quote("EURUSD")
        self.assertEqual(result, {"ok": False, "reason": "MT5_NOT_AVAILABLE"})


if __name__ == "__main__":
    unittest.main()



