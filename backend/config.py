"""Rule configuration loader (PRD Section 9, Phase 2 amendment 2026-09-02).

Reads `rules.yaml` exactly once, at import time, and validates it before any rule can
consult it. Two properties matter:

1. **No defaults.** Every lookup goes through `_require`, which raises on a missing
   key. A detection rule that silently falls back to a plausible-looking threshold is
   worse than one that refuses to start -- the demo would run, the numbers would be
   wrong, and nothing would say so.

2. **Path-independent.** The file is resolved relative to this module, not the process
   cwd, so `python verify.py`, `uvicorn main:app` from the repo root, and an import
   from a test directory all read the same file.
"""

from __future__ import annotations

import os

import yaml

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules.yaml")

RULE_IDS = ["EG-001", "EG-002", "EG-003", "EG-004", "EG-005", "NS-001", "NS-002", "ML-001"]


class ConfigError(RuntimeError):
    """Raised when rules.yaml is missing, malformed, or incomplete."""


def _load(path: str = CONFIG_PATH) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise ConfigError(f"rule config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"rule config is not valid YAML: {path}\n{exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"rule config must be a mapping at the top level: {path}")
    return data


def _require(mapping: dict, key: str, where: str):
    if key not in mapping:
        raise ConfigError(f"missing required key '{key}' in {where} ({CONFIG_PATH})")
    return mapping[key]


_RAW = _load()

WEIGHTS: dict[str, int] = {
    rule_id: int(_require(_require(_RAW, "weights", "rules.yaml"), rule_id, "weights"))
    for rule_id in RULE_IDS
}

_RULES = _require(_RAW, "rules", "rules.yaml")


def rule(rule_id: str) -> dict:
    """The configuration block for one rule."""
    block = _require(_RULES, rule_id, "rules")
    if not isinstance(block, dict):
        raise ConfigError(f"rules.{rule_id} must be a mapping, got {type(block).__name__}")
    return block


def param(rule_id: str, key: str):
    """One configured parameter, with the rule id in the error if it is absent."""
    return _require(rule(rule_id), key, f"rules.{rule_id}")


def severities(rule_id: str) -> tuple[str, ...]:
    """Severity list as a tuple -- membership tests, not accidental mutation."""
    return tuple(param(rule_id, "severities"))


def dispositions(rule_id: str) -> tuple[str, ...]:
    return tuple(param(rule_id, "dispositions"))
