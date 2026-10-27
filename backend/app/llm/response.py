"""Capture one JSON object from model text without completing or guessing partial output."""

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_decoder = json.JSONDecoder()


def extract_text(content: object) -> str:
    """Join text blocks; reasoning and other non-text blocks are discarded."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _strict(text: str, _root_key: str) -> object:
    return json.loads(text)


def _embedded(text: str, root_key: str) -> object:
    """The first complete object, ignoring surrounding prose such as a preamble or note."""
    start = text.find("{")
    for _ in range(50):
        if start < 0:
            break
        try:
            value, _end = _decoder.raw_decode(text, start)
        except ValueError:
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict) and (root_key in value or len(value) == 1):
            return value
        start = text.find("{", start + 1)
    raise ValueError("No complete JSON object")


def _duplicated_root_brace(text: str, root_key: str) -> object:
    """Correct only a duplicated opening brace before the expected root key."""
    stripped = text.lstrip()
    root = f'{{"{root_key}"'
    if stripped.startswith('{"{') and stripped[3:].startswith(f'"{root_key}"'):
        candidate = stripped[0] + stripped[3:]
    elif stripped.startswith("{") and stripped[1:].lstrip().startswith(root):
        candidate = stripped[1:].lstrip()
    else:
        raise ValueError("Not a duplicated root brace")
    try:
        return json.loads(candidate)
    except ValueError:
        # A matching extra closing brace can accompany the duplicated opener.
        if candidate.rstrip().endswith("}}"):
            return json.loads(candidate.rstrip()[:-1])
        raise


def _unwrap(value: dict, root_key: str) -> dict:
    """Accept one level of wrapping, such as {"result": {"facts": [...]}}."""
    if root_key not in value and len(value) == 1:
        inner = next(iter(value.values()))
        if isinstance(inner, dict) and root_key in inner:
            return inner
    return value


def parse_json_object(text: str, root_key: str) -> dict:
    """Tolerate wrappers around one complete JSON object; raise ValueError otherwise."""
    whole = text.strip()
    steps = [(_strict, whole)]
    fenced = _FENCE.search(text)
    if fenced:
        inner = fenced.group(1)
        steps += [(parse, inner) for parse in (_strict, _embedded, _duplicated_root_brace)]
    steps += [(_embedded, whole), (_duplicated_root_brace, whole)]
    for parse, candidate in steps:
        try:
            value = parse(candidate, root_key)
        except ValueError:
            continue
        if isinstance(value, dict):
            return _unwrap(value, root_key)
    raise ValueError("No complete JSON object")
