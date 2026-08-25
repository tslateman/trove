from __future__ import annotations

import json

from .fetch import Workspace, list_remote_refs, resolve_sha
from .models import Bundle, PluginSpec, Source
from .resolve import effective, source_manifest

__all__ = [
    "SCHEMA",
    "build_marketplace",
    "dumps",
    "list_remote_refs",
    "plugin_entry",
    "resolve_sha",
    "verify_curated_paths",
]

SCHEMA = "https://anthropic.com/claude-code/marketplace.schema.json"


def plugin_entry(spec: PluginSpec, source: Source, sha: str | None, root=None) -> dict:
    resolved = effective(spec, source_manifest(source, root))
    if not resolved["description"]:
        raise ValueError(
            f"plugin {spec.name!r} has no description: source {spec.source_key!r} has no "
            "plugin.json to inherit one from, so the bundle must declare it"
        )
    entry: dict = {
        "name": spec.name,
        "description": resolved["description"],
        "source": source.marketplace_source(sha),
    }
    if resolved["display_name"]:
        entry["displayName"] = resolved["display_name"]
    if resolved["version"]:
        entry["version"] = resolved["version"]
    if spec.category:
        entry["category"] = spec.category
    if spec.tags:
        entry["tags"] = spec.tags
    if resolved["homepage"]:
        entry["homepage"] = resolved["homepage"]
    if spec.skills:
        entry["skills"] = [f"./{selection}" for selection in spec.selections]
    return entry


def build_marketplace(
    bundle: Bundle, pin: bool = True, workspace: Workspace | None = None
) -> dict:
    workspace = workspace if workspace is not None else Workspace()
    roots = {key: workspace.root(source) for key, source in bundle.sources.items()}
    verify_curated_paths(bundle, roots)

    shas = {}
    if pin:
        for key, source in bundle.sources.items():
            shas[key] = workspace.sha(source)

    manifest = {
        "$schema": SCHEMA,
        "name": bundle.name,
        "description": bundle.description,
        "owner": bundle.owner,
        "plugins": [
            plugin_entry(
                spec,
                bundle.sources[spec.source_key],
                shas.get(spec.source_key),
                roots.get(spec.source_key),
            )
            for spec in bundle.plugins
        ],
    }
    if bundle.renames:
        manifest["renames"] = bundle.renames
    return manifest


def verify_curated_paths(bundle: Bundle, roots: dict | None = None) -> None:
    from .scan import scan_source

    scanned: dict[str, set[str]] = {}
    for spec in bundle.plugins:
        if not spec.skills:
            continue
        source = bundle.sources[spec.source_key]
        root = (roots or {}).get(spec.source_key) or source.local
        if root is None:
            continue
        if spec.source_key not in scanned:
            scanned[spec.source_key] = {s.rel_path for s in scan_source(source, root)}
        found = scanned[spec.source_key]
        missing = [
            selection
            for selection in spec.selections
            if not any(
                path.startswith(selection)
                if selection.endswith("/")
                else path == selection
                for path in found
            )
        ]
        if missing:
            raise ValueError(
                f"plugin {spec.name!r} curates paths that match no skill in "
                f"{spec.source_key!r}: {', '.join(missing)}"
            )


def dumps(manifest: dict) -> str:
    return json.dumps(manifest, indent=2) + "\n"
