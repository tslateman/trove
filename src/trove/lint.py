from __future__ import annotations

import re

NAME_MAX = 64
LISTING_MAX = 1536

KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TRIGGER = re.compile(
    r"\b(?:use\s+(?:when|for|on|to|after|before|during|it)"
    r"|when(?:ever)?\b"
    r"|after\b"
    r"|trigger|invoke|do not use|don't use)",
    re.IGNORECASE,
)

FINDINGS = {
    "yaml": "frontmatter fails a strict YAML parse",
    "description": "no description, so nothing can choose this skill",
    "trigger": "the description never says when to use the skill",
    "name": f"the name is not kebab-case within {NAME_MAX} characters",
    "listing": (
        f"the description passes {LISTING_MAX} characters, "
        "which is where Claude Code truncates it"
    ),
}


def findings(name: str, description: str, strict_yaml: bool) -> list[str]:
    """What a skill gets wrong at discovery time.

    Every rule is mechanical. Claude Code chooses a skill from its name and
    description alone, so each finding names something that stops it from
    being chosen, or from being read the way its author wrote it.
    """
    found = []
    if not strict_yaml:
        found.append("yaml")
    if not description:
        found.append("description")
    elif not TRIGGER.search(description):
        found.append("trigger")
    if not KEBAB.match(name) or len(name) > NAME_MAX:
        found.append("name")
    if len(description) > LISTING_MAX:
        found.append("listing")
    return found
