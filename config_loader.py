"""Minimal YAML configuration loader for FX project modules."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import ast

try:  # optional dependency
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback when PyYAML missing
    yaml = None  # type: ignore

_CONFIG_PATH = Path(__file__).with_name("config.yaml")


class ConfigError(RuntimeError):
    """Raised when the static configuration cannot be parsed."""


_DEF_NULLS = {"null", "none", ""}


def _parse_scalar(value: str):
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in _DEF_NULLS:
        return None
    if value.startswith("[") and value.endswith("]"):
        return ast.literal_eval(value)
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _fallback_yaml(text: str) -> dict[str, object]:
    root: dict[str, object] = {}
    stack: list[tuple[int, dict[str, object]]] = [(-2, root)]
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent % 2 != 0:
            raise ConfigError(f"invalid indentation: {raw_line!r}")
        line = raw_line.strip()
        key, sep, remainder = line.partition(":")
        if not sep:
            raise ConfigError(f"missing ':' in line: {raw_line!r}")
        key = key.strip()
        value = remainder.strip()
        while indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if value == "":
            nested: dict[str, object] = {}
            current[key] = nested
            stack.append((indent, nested))
        else:
            current[key] = _parse_scalar(value)
    return root


def _parse_yaml(text: str) -> dict[str, object]:
    if yaml is not None:
        try:
            data = yaml.safe_load(text) or {}
            if not isinstance(data, dict):
                raise TypeError("top-level YAML must be an object")
            return data
        except yaml.YAMLError as exc:  # pragma: no cover
            raise ConfigError(f"failed to parse config: {exc}") from exc
    return _fallback_yaml(text)


@lru_cache(maxsize=1)
def load_config(path: str | Path | None = None) -> dict[str, object]:
    target = Path(path) if path else _CONFIG_PATH
    if not target.exists():
        raise ConfigError(f"config file not found: {target}")
    text = target.read_text(encoding="utf-8")
    return _parse_yaml(text)


CONFIG = load_config()




