"""Helpers for reading structured output from model replies."""

from __future__ import annotations

import json
import re
from typing import Any

from bot_v.llm.client import LLMError, is_error

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in an LLM reply.

    Tolerates ```json fences and text before/after the JSON. Raises
    ``LLMError`` for LLM error strings and ``ValueError`` if no JSON is found.
    """
    if is_error(text):
        raise LLMError(text)
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError(f"no JSON found in model reply: {text[:200]!r}")
    return json.JSONDecoder().raw_decode(text[min(starts):])[0]
