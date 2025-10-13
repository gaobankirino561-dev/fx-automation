import os
import unittest
from unittest.mock import patch

from config_loader import CONFIG
import decider


class DeciderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_default = CONFIG.get("model", {}).get("default", "gpt-4o-mini")
        CONFIG.setdefault("model", {})["default"] = "gpt-4o-mini"
        decider._MODEL_DEFAULT = "gpt-4o-mini"  # type: ignore[attr-defined]

    def tearDown(self) -> None:
        CONFIG.setdefault("model", {})["default"] = self._original_default
        decider._MODEL_DEFAULT = self._original_default  # type: ignore[attr-defined]

    def test_trading_parameters_from_config(self) -> None:
        params = decider.get_trading_parameters()
        trading_cfg = CONFIG.get('trading', {})
        self.assertEqual(params['spread_max'], trading_cfg.get('spread_max', 2.0))
        self.assertEqual(params['atr_min_M15'], trading_cfg.get('atr_min_M15', 0.05))
        self.assertEqual(params['tp_k_atr'], trading_cfg.get('tp_k_atr', 1.5))
        self.assertEqual(params['sl_k_atr'], trading_cfg.get('sl_k_atr', 0.9))
        self.assertEqual(params['round_digits'], trading_cfg.get('round_digits', 4))

    def test_decide_entry_delegates_to_ask_decision(self) -> None:
        captured = []

        def fake(summary: str, *, model: str = CONFIG.get("model", {}).get("default", "gpt-4o-mini")):
            captured.append((summary, model))
            return {"decision": "NO_ENTRY"}

        original = decider.ask_decision
        decider.ask_decision = fake  # type: ignore[assignment]
        try:
            result = decider.decide_entry("  sample   summary  ", model="gpt-4o-mini")
            result_default = decider.decide_entry("default summary")
        finally:
            decider.ask_decision = original  # type: ignore[assignment]

        self.assertEqual(result, {"decision": "NO_ENTRY"})
        self.assertEqual(result_default, {"decision": "NO_ENTRY"})
        self.assertEqual(captured[0], ("sample summary", "gpt-4o-mini"))
        default_model = CONFIG.get("model", {}).get("default", "gpt-4o-mini")
        self.assertEqual(captured[1], ("default summary", default_model))

    def test_input_validation(self) -> None:
        with self.assertRaises(TypeError):
            decider.decide_entry(123)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            decider.decide_entry("   ")

    def test_force_decision_via_environment(self) -> None:
        with patch.dict(os.environ, {
            "FX_FORCE_DECISION": "buy",
            "FX_FORCE_TP_PIPS": "3",
            "FX_FORCE_SL_PIPS": "2",
            "FX_FORCE_REASON": "forced-test",
        }):
            with patch.object(decider, "ask_decision", side_effect=AssertionError("should not call ask_decision")):
                result = decider.decide_entry(" summary text ")
        self.assertEqual(result["decision"], "BUY")
        self.assertEqual(result["tp_pips"], 3.0)
        self.assertEqual(result["sl_pips"], 2.0)
        self.assertEqual(result["reason"], "forced-test")
        self.assertEqual(result["confidence"], 100.0)


if __name__ == "__main__":
    unittest.main()
