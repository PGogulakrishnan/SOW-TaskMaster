"""Smoke tests for LLM utilities and config wiring."""

import os
import sys

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.llm_utils import parse_json
import config

# ── parse_json ─────────────────────────────────────────────────────────────
assert parse_json('{"a": 1}') == {"a": 1}
assert parse_json('Here is it: {"a": 1} thanks') == {"a": 1}
assert parse_json('```json\n{"x": [1, 2]}\n```') == {"x": [1, 2]}
assert parse_json('prose only, no json') is None
assert parse_json('') is None


# ── config ────────────────────────────────────────────────────────────────
assert config.GEMINI_MODEL  # model name always set
assert config.USE_REAL_LLM in (True, False)

print("OK: config.model =", config.GEMINI_MODEL)
print("OK: config.use_real_llm =", config.USE_REAL_LLM)
print("ALL llm_utils/config tests passed")