from __future__ import annotations

import json
from pathlib import Path

from .models import PluginSpec, Source

INHERITABLE = ("description", "version", "homepage", "displayName")


def source_manifest(source: Source, root: Path | None = None) -> dict:
    root = root if root is not None else source.local
    if root is None:
        return {}
    manifest = root / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        return {}
    return json.loads(manifest.read_text(encoding="utf-8"))


def effective(spec: PluginSpec, manifest: dict) -> dict:
    return {
        "description": spec.description or manifest.get("description", ""),
        "version": spec.version or manifest.get("version"),
        "homepage": spec.homepage or manifest.get("homepage"),
        "display_name": spec.display_name or manifest.get("displayName"),
    }


def drift(spec: PluginSpec, manifest: dict) -> list[tuple[str, str, str]]:
    reported = []
    for field in ("description", "version"):
        if field == "description" and spec.skills:
            continue
        declared = getattr(spec, field)
        upstream = manifest.get(field)
        if declared and upstream and str(declared).strip() != str(upstream).strip():
            reported.append((field, str(declared), str(upstream)))
    return reported
