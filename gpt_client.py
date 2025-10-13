from __future__ import annotations

import json
import math
import os
import threading
import time
from dataclasses import dataclass
from hashlib import sha256
from config_loader import CONFIG
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI
from openai._exceptions import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    OpenAIError,
    RateLimitError,
)

_MODEL_CFG = CONFIG.get("model", {})
_DEFAULT_MODEL = str(_MODEL_CFG.get("default", "gpt-4o-mini"))
_DEFAULT_TEMPERATURE = float(_MODEL_CFG.get("temperature", 0.0))
_MODEL_FALLBACKS = [str(m) for m in _MODEL_CFG.get("fallbacks", ["gpt-4o", "gpt-4o-mini"])]
_CACHE_CFG = CONFIG.get("cache", {})
_CACHE_PATH = Path(_CACHE_CFG.get("path", "gpt_cache.json"))
_INCLUDE_MODEL_IN_KEY = bool(_CACHE_CFG.get("include_model_in_key", True))
_RETRY_CFG = CONFIG.get("retry", {})
_DEFAULT_ATTEMPTS = int(_RETRY_CFG.get("max_attempts", 3))
_BACKOFF_SECONDS = [float(x) for x in _RETRY_CFG.get("backoff_seconds", [1.0, 2.0, 4.0])]

_LOCK = threading.Lock()
_CACHE_DATA: Dict[str, Any] | None = None
_CLIENTS: Dict[str, OpenAI] = {}

_DECISION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string", "enum": ["BUY", "SELL", "NO_ENTRY"]},
        "tp_pips": {"type": "number", "minimum": 0},
        "sl_pips": {"type": "number", "minimum": 0},
        "reason": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
    },
    "required": ["decision", "tp_pips", "sl_pips", "reason", "confidence"],
}

_SYS_PROMPT = (
    "あなたはプロのアルゴトレーダー。厳格なリスク管理と再現性を最優先。"
    "出力は必ず有効なJSONのみ。横ばいノイズ拡張スプレッドデータ不足ではNO_ENTRYを優先。"
    'スキーマ: {"decision":"BUY|SELL|NO_ENTRY","tp_pips":number,'
    '"sl_pips":number,"reason":string,"confidence":0-100}'
)


@dataclass
class _CacheEntry:
    payload: Dict[str, Any]
    model: str
    ts: float


def _clone(data: Any) -> Any:
    return json.loads(json.dumps(data, ensure_ascii=False))


def _load_cache() -> Dict[str, Any]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        with _CACHE_PATH.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    tmp_path = _CACHE_PATH.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=2, sort_keys=True)
    tmp_path.replace(_CACHE_PATH)


def _get_cache() -> Dict[str, Any]:
    global _CACHE_DATA
    if _CACHE_DATA is None:
        _CACHE_DATA = _load_cache()
    return _CACHE_DATA


def _norm_key(text: str, model: str) -> str:
    normalized = " ".join(text.strip().split())
    model_tag = model.strip() or "<unknown-model>"
    key_source = f"{model_tag}::{normalized}" if _INCLUDE_MODEL_IN_KEY else normalized
    digest = sha256(key_source.encode("utf-8")).hexdigest()
    return f"{digest}:{key_source}"


def _fallback(reason: str) -> Dict[str, Any]:
    cleaned = " ".join(reason.strip().split()) or "fallback:no_entry"
    return {
        "decision": "NO_ENTRY",
        "tp_pips": 0.0,
        "sl_pips": 0.0,
        "reason": cleaned[:200],
        "confidence": 0.0,
    }


def _get_client(model: str) -> OpenAI:
    with _LOCK:
        client = _CLIENTS.get(model)
        if client is not None:
            return client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        client = OpenAI(api_key=api_key, max_retries=0)
        _CLIENTS[model] = client
        return client


def _build_response_format(schema: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "json_schema", "json_schema": {"name": "decision_payload", "schema": _clone(schema)}}


def _is_model_not_available(error: Exception) -> bool:
    text = str(error).lower()
    if "model" not in text:
        return False
    return any(token in text for token in ("does not exist", "model_not_found", "do not have access"))


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        text = content.strip()
        if not text:
            raise ValueError("empty content")
        return text
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text")
                if isinstance(value, str):
                    parts.append(value)
        joined = "".join(parts).strip()
        if not joined:
            raise ValueError("no text parts")
        return joined
    raise ValueError(f"unsupported content type: {type(content)!r}")


def _validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload is not an object")

    keys = set(payload.keys())
    expected = set(_DECISION_SCHEMA["required"])  # type: ignore[index]
    missing = expected - keys
    if missing:
        raise ValueError(f"missing keys: {sorted(missing)}")
    extra = keys - set(_DECISION_SCHEMA["properties"].keys())  # type: ignore[index]
    if extra:
        raise ValueError(f"unexpected keys: {sorted(extra)}")

    decision = str(payload["decision"]).strip().upper()
    if decision not in {"BUY", "SELL", "NO_ENTRY"}:
        raise ValueError(f"invalid decision: {decision}")

    def _to_positive_number(field: str) -> float:
        value = payload[field]
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field} must be a number")
        if not math.isfinite(num) or num < 0:
            raise ValueError(f"{field} must be >= 0")
        return num

    tp_pips = _to_positive_number("tp_pips")
    sl_pips = _to_positive_number("sl_pips")

    reason_raw = payload["reason"]
    if not isinstance(reason_raw, str):
        raise ValueError("reason must be string")
    reason = " ".join(reason_raw.strip().split())
    if not reason:
        raise ValueError("reason cannot be empty")

    confidence_val = payload["confidence"]
    try:
        confidence = float(confidence_val)
    except (TypeError, ValueError):
        raise ValueError("confidence must be a number")
    if not math.isfinite(confidence) or confidence < 0 or confidence > 100:
        raise ValueError("confidence must be between 0 and 100")

    return {
        "decision": decision,
        "tp_pips": tp_pips,
        "sl_pips": sl_pips,
        "reason": reason,
        "confidence": confidence,
    }


def _load_from_cache(key: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        cache = _get_cache()
        entry = cache.get(key)
    if not isinstance(entry, dict):
        return None
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return None
    try:
        return _validate_payload(_clone(payload))
    except ValueError:
        with _LOCK:
            cache = _get_cache()
            cache.pop(key, None)
            _save_cache(cache)
        return None


def _store_in_cache(key: str, payload: Dict[str, Any], model: str) -> None:
    with _LOCK:
        cache = _get_cache()
        cache[key] = {
            "payload": _clone(payload),
            "model": model,
            "ts": time.time(),
        }
        _save_cache(cache)


def _ask_with_model(prompt: str, model: str, cache_key: str) -> tuple[Optional[Dict[str, Any]], Optional[str], bool]:
    client = _get_client(model)
    messages = [
        {"role": "system", "content": _SYS_PROMPT},
        {"role": "user", "content": prompt},
    ]

    attempts = _DEFAULT_ATTEMPTS
    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        print(f"[ask_decision] API Call attempt {attempt} for model={model}")
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=_DEFAULT_TEMPERATURE,
                response_format=_build_response_format(_DECISION_SCHEMA),
            )

            if not getattr(response, "choices", None):
                raise ValueError("no choices in response")

            message = response.choices[0].message  # type: ignore[index]
            raw_text = _extract_text(getattr(message, "content", None))
            data = json.loads(raw_text)
            validated = _validate_payload(data)
            _store_in_cache(cache_key, validated, model)
            return validated, None, False

        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if attempt < attempts:
                print(f"[ask_decision] Retry {attempt} due to validation error: {exc}")
            continue
        except (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError) as exc:
            last_error = exc
            if attempt < attempts:
                print(f"[ask_decision] Retry {attempt} due to API error: {exc}")
                index = min(attempt - 1, len(_BACKOFF_SECONDS) - 1)
                time.sleep(_BACKOFF_SECONDS[index])
                continue
            break
        except (BadRequestError, APIError, OpenAIError) as exc:
            if _is_model_not_available(exc):
                print(f"[ask_decision] Model unavailable ({model}): {exc}")
                return None, str(exc), True
            return None, str(exc), False

    reason = str(last_error) if last_error else "validation_failed"
    return None, reason, False




def ask_decision(summary: str, model: str = _DEFAULT_MODEL) -> Dict[str, Any]:
    if not isinstance(summary, str):
        raise TypeError("summary must be a string")
    prompt = " ".join(summary.strip().split())
    if not prompt:
        raise ValueError("summary must not be empty")

    configured = [m for m in _MODEL_FALLBACKS if m != model]
    if configured:
        fallback_chain = [model] + configured
    else:
        fallback_chain = [model] + [m for m in ("gpt-4o", "gpt-4o-mini") if m != model]

    last_reason: Optional[str] = None
    for index, active_model in enumerate(fallback_chain):
        cache_key = _norm_key(prompt, active_model)
        cached = _load_from_cache(cache_key)
        if cached is not None:
            print(f"[ask_decision] Cache Hit for key={cache_key}")
            return cached

        result, reason, allow_fallback = _ask_with_model(prompt, active_model, cache_key)
        if result is not None:
            if active_model != model:
                print(f"[ask_decision] Fallback model used: {active_model}")
            return result

        last_reason = reason or last_reason
        if allow_fallback and index < len(fallback_chain) - 1:
            next_model = fallback_chain[index + 1]
            print(f"[ask_decision] Model fallback to {next_model} (from {active_model})")
            continue
        break

    print("[ask_decision] Returning fallback NO_ENTRY")
    return _fallback(last_reason or "model_unavailable")





