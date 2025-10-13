import unittest

import gpt_client
from pathlib import Path


class GPTClientFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_fallbacks = gpt_client._MODEL_FALLBACKS
        gpt_client._MODEL_FALLBACKS = ["fallback-model"]
        self.original_ask = gpt_client._ask_with_model
        gpt_client._get_cache().clear()
        try:
            Path(gpt_client._CACHE_PATH).unlink()
        except FileNotFoundError:
            pass

        def fake_ask(prompt: str, model: str, cache_key: str):
            if model == "primary-model":
                return None, "model not found", True
            payload = {
                "decision": "NO_ENTRY",
                "tp_pips": 0.0,
                "sl_pips": 0.0,
                "reason": "fallback",
                "confidence": 0.0,
            }
            return payload, None, False

        gpt_client._ask_with_model = fake_ask  # type: ignore[assignment]

    def tearDown(self) -> None:
        gpt_client._MODEL_FALLBACKS = self.original_fallbacks
        gpt_client._ask_with_model = self.original_ask  # type: ignore[assignment]

    def test_model_fallback_used(self) -> None:
        result = gpt_client.ask_decision("dummy summary", model="primary-model")
        self.assertEqual(result["reason"], "fallback")


if __name__ == "__main__":
    unittest.main()





