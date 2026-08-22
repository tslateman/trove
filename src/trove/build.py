from __future__ import annotations

import json
import os
import subprocess

from .models import Bundle, PluginSpec, Source

SCHEMA = "https://anthropic.com/claude-code/marketplace.schema.json"


def resolve_sha(source: Source) -> str:
    ref = source.ref or "HEAD"
    result = subprocess.run(
        ["git", "ls-remote", source.clone_url, ref],
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"cannot reach {source.clone_url} (ref {ref!r}): {result.stderr.strip()}"
        )
    lines = result.stdout.strip().splitlines()
    if not lines:
        raise ValueError(f"{source.clone_url} has no ref {ref!r}")
    return lines[0].split()[0]


def plugin_entry(spec: PluginSpec, source: Source, sha: str | None) -> dict:
    entry: dict = {
        "name": spec.name,
        "description": spec.description,
        "source": source.marketplace_source(sha),
    }
    if spec.display_name:
        entry["displayName"] = spec.display_name
    if spec.version:
        entry["version"] = spec.version
    if spec.category:
        entry["category"] = spec.category
    if spec.tags:
        entry["tags"] = spec.tags
    if spec.homepage:
        entry["homepage"] = spec.homepage
    if spec.skills:
        entry["skills"] = [f"./{path.lstrip('./')}" for path in spec.skills]
    return entry


def build_marketplace(bundle: Bundle, pin: bool = True) -> dict:
    shas = {}
    if pin:
        for key, source in bundle.sources.items():
            shas[key] = resolve_sha(source)

    manifest = {
        "$schema": SCHEMA,
        "name": bundle.name,
        "description": bundle.description,
        "owner": bundle.owner,
        "plugins": [
            plugin_entry(spec, bundle.sources[spec.source_key], shas.get(spec.source_key))
            for spec in bundle.plugins
        ],
    }
    if bundle.renames:
        manifest["renames"] = bundle.renames
    return manifest


def dumps(manifest: dict) -> str:
    return json.dumps(manifest, indent=2) + "\n"
