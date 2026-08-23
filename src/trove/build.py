from __future__ import annotations

import json
import os
import subprocess

from .models import Bundle, PluginSpec, Source
from .resolve import effective, source_manifest

SCHEMA = "https://anthropic.com/claude-code/marketplace.schema.json"


def list_remote_refs(source: Source, ref: str) -> dict[str, str]:
    result = subprocess.run(
        ["git", "ls-remote", "--", source.clone_url, ref, f"refs/tags/{ref}^{{}}"],
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"cannot reach {source.clone_url} (ref {ref!r}): {result.stderr.strip()}"
        )
    refs = {}
    for line in result.stdout.strip().splitlines():
        sha, _, name = line.partition("\t")
        if name:
            refs[name] = sha
    return refs


def resolve_sha(source: Source) -> str:
    ref = source.ref or "HEAD"
    refs = list_remote_refs(source, ref)
    if not refs:
        raise ValueError(f"{source.clone_url} has no ref {ref!r}")

    tag = refs.get(f"refs/tags/{ref}^{{}}") or refs.get(f"refs/tags/{ref}")
    head = refs.get(f"refs/heads/{ref}")
    if tag and head:
        raise ValueError(
            f"{source.clone_url}: ref {ref!r} matches both refs/tags/{ref} and "
            f"refs/heads/{ref} — qualify it in the bundle"
        )
    for candidate in (refs.get(ref), tag, head, refs.get(f"{ref}^{{}}")):
        if candidate:
            return candidate
    raise ValueError(
        f"{source.clone_url}: ref {ref!r} is ambiguous across {sorted(refs)}"
    )


def plugin_entry(spec: PluginSpec, source: Source, sha: str | None) -> dict:
    resolved = effective(spec, source_manifest(source))
    if not resolved["description"]:
        raise ValueError(
            f"plugin {spec.name!r} has no description: source {spec.source_key!r} has no local "
            "checkout to inherit one from, so the bundle must declare it"
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
    if spec.selected_paths:
        entry["skills"] = [f"./{path}" for path in spec.selected_paths]
    return entry


def build_marketplace(bundle: Bundle, pin: bool = True) -> dict:
    verify_curated_paths(bundle)
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


def verify_curated_paths(bundle: Bundle) -> None:
    from .scan import scan_source

    scanned: dict[str, set[str]] = {}
    for spec in bundle.plugins:
        if not spec.skills:
            continue
        source = bundle.sources[spec.source_key]
        if source.local is None:
            continue
        if spec.source_key not in scanned:
            scanned[spec.source_key] = {s.rel_path for s in scan_source(source)}
        missing = [p for p in spec.selected_paths if p not in scanned[spec.source_key]]
        if missing:
            raise ValueError(
                f"plugin {spec.name!r} curates paths that match no skill in "
                f"{spec.source_key!r}: {', '.join(missing)}"
            )


def dumps(manifest: dict) -> str:
    return json.dumps(manifest, indent=2) + "\n"
