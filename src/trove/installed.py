"""What this machine has installed, beside what the registry offers.

Claude Code answers both questions itself: `claude plugin list --json` reports
every installed plugin with its scope and whether it is enabled, and
`claude plugin marketplace list --json` reports the registries it knows. Trove
asks the CLI rather than reading `~/.claude` so there is one derivation of
installed state, and it asks at request time so installing a plugin shows up on
the next reload.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

PLUGINS = ("claude", "plugin", "list", "--json")
MARKETPLACES = ("claude", "plugin", "marketplace", "list", "--json")
TIMEOUT = 20


def ask(command: tuple[str, ...]) -> list[dict]:
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=TIMEOUT, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(command)}` exited {result.returncode}: "
            f"{result.stderr.strip() or 'no output'}"
        )
    return json.loads(result.stdout)


def unreachable(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "no `claude` on PATH, so Trove cannot ask what is installed"
    if isinstance(exc, subprocess.TimeoutExpired):
        return f"`claude plugin list` did not answer within {TIMEOUT}s"
    if isinstance(exc, json.JSONDecodeError):
        return "`claude plugin list --json` did not answer JSON"
    return str(exc)


def marketplace_for(catalog: dict, override: str | None = None) -> str:
    """The name a machine files this registry under.

    A registry is installed under whatever `claude plugin marketplace add`
    named it, which is the marketplace manifest's name and need not match the
    bundle. `marketplace:` in the bundle records the difference.
    """
    return override or catalog.get("marketplace") or catalog["registry"]


def collect(
    entries: list[dict], marketplace: str, offered: set[str]
) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for entry in entries:
        name, _, market = str(entry.get("id", "")).rpartition("@")
        if market != marketplace or name not in offered:
            continue
        record = found.setdefault(
            name, {"enabled": False, "version": None, "scopes": [], "projects": []}
        )
        enabled = bool(entry.get("enabled"))
        # One plugin can be installed at both scopes. The version reported is
        # the one Claude Code loads, so an enabled entry wins the tie.
        if enabled or record["version"] is None:
            record["version"] = entry.get("version")
        record["enabled"] = record["enabled"] or enabled
        record["scopes"].append(entry.get("scope"))
        if entry.get("projectPath"):
            record["projects"].append(entry["projectPath"])
    return found


def suggest(entries: list[dict], offered: set[str], asked: str) -> dict | None:
    """Another marketplace that ships these plugin names, when the asked-for
    one explains nothing. A bundle whose name is not the marketplace name reads
    as "nothing installed" until someone names the difference."""
    names: dict[str, set[str]] = {}
    for entry in entries:
        name, _, market = str(entry.get("id", "")).rpartition("@")
        if market and market != asked and name in offered:
            names.setdefault(market, set()).add(name)
    if not names:
        return None
    market, matched = max(names.items(), key=lambda pair: len(pair[1]))
    return {"marketplace": market, "matches": len(matched)}


def survey(catalog: dict, marketplace: str | None = None) -> dict:
    """This machine's answer to what the catalog offers."""
    name = marketplace_for(catalog, marketplace)
    offered = {plugin["name"] for plugin in catalog.get("plugins", [])}
    try:
        entries = ask(PLUGINS)
        configured = [entry.get("name") for entry in ask(MARKETPLACES)]
    except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
        return {
            "marketplace": name,
            "available": False,
            "reason": unreachable(exc),
            "configured": False,
            "plugins": {},
            "totals": {"plugins": 0, "enabled": 0},
        }

    found = collect(entries, name, offered)
    for plugin in catalog.get("plugins", []):
        record = found.get(plugin["name"])
        if record is None:
            continue
        record["offered"] = plugin.get("version")
        record["update"] = bool(
            record["offered"] and record["version"] != record["offered"]
        )
    state = {
        "marketplace": name,
        "available": True,
        "configured": name in configured,
        "plugins": found,
        "totals": {
            "plugins": len(found),
            "enabled": sum(1 for r in found.values() if r["enabled"]),
        },
    }
    if not found:
        hint = suggest(entries, offered, name)
        if hint:
            state["suggest"] = hint
    return state


def cost(catalog: dict, state: dict) -> dict:
    """What the enabled half of this machine's install actually charges."""
    enabled = {name for name, r in state["plugins"].items() if r["enabled"]}
    live = [s for s in catalog["skills"] if set(s["plugins"]) & enabled]
    held = [s for s in catalog["skills"] if set(s["plugins"]) & set(state["plugins"])]
    return {
        "skills": len(held),
        "enabledSkills": len(live),
        "alwaysOn": sum(s["tokensAlwaysOn"] for s in live),
    }


def local_marketplace(site: Path) -> str | None:
    """The directory `claude plugin marketplace add` takes to register the
    build this catalog came from, when the build carries a manifest."""
    manifest = site / ".claude-plugin" / "marketplace.json"
    return str(site.resolve()) if manifest.is_file() else None
