from __future__ import annotations

import re

KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$")
BLOCK_MARKER = re.compile(r"^[|>][+-]?$")


def _clean(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse(raw: str) -> dict[str, str]:
    fields: dict[str, list[str]] = {}
    key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        match = KEY.match(line)
        if match and not line.startswith((" ", "\t")):
            key = match.group(1)
            value = match.group(2)
            fields[key] = [] if BLOCK_MARKER.match(value.strip()) else [value]
        elif key is not None:
            fields[key].append(line.strip())
    return {k: _clean(" ".join(v).strip()) for k, v in fields.items()}


def split(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    rest = text.partition("---")[2]
    raw, delim, body = rest.partition("\n---")
    if not delim:
        return {}, text
    return parse(raw), body
