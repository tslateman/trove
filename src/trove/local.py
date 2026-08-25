from __future__ import annotations

import json
from pathlib import Path

from .fetch import Workspace
from .models import Bundle
from .resolve import effective, source_manifest

DEFAULT_MARKETPLACE = (
    Path.home() / ".claude" / "plugins" / "marketplaces" / "local" / ".claude-plugin" / "marketplace.json"
)
SYNCED_FIELDS = ("description", "version")


def plan(
    bundle: Bundle, manifest: dict, workspace: Workspace | None = None
) -> tuple[list[tuple[str, str, str, str]], list[str], list[str]]:
    workspace = workspace if workspace is not None else Workspace()
    known = {}
    unsourced = []
    for spec in bundle.plugins:
        source = bundle.sources[spec.source_key]
        upstream = source_manifest(source, workspace.root(source))
        if not upstream:
            unsourced.append(spec.name)
            continue
        known[spec.name] = effective(spec, upstream)
    changes = []
    for entry in manifest.get("plugins", []):
        resolved = known.get(entry.get("name"))
        if resolved is None:
            continue
        for field in SYNCED_FIELDS:
            value = resolved[field]
            if value and entry.get(field) != value:
                changes.append((entry["name"], field, entry.get(field, ""), value))
    listed = {entry.get("name") for entry in manifest.get("plugins", [])}
    absent = sorted(name for name in known if name not in listed)
    return changes, absent, sorted(unsourced)


def apply(manifest: dict, changes: list[tuple[str, str, str, str]]) -> dict:
    by_name = {entry.get("name"): entry for entry in manifest.get("plugins", [])}
    for name, field, _, new in changes:
        by_name[name][field] = new
    return manifest
