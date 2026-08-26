from __future__ import annotations

from .fetch import Workspace
from .models import Bundle, Source
from .resolve import effective, source_manifest
from .scan import scan_source


GITHUB = "https://github.com/"
RAW_GITHUB = "https://raw.githubusercontent.com"


def body_base(key: str, source: Source, sha: str | None) -> str | None:
    """Where a skill's files resolve from, joined with `<skill path>/<file>`.

    A pinned GitHub source resolves to raw git at that commit, which any host
    can serve. Anything else resolves to `trove serve`, which answers `/body/`
    from the checkout on disk.
    """
    if sha and source.clone_url.startswith(GITHUB) and (source.repo or source.url):
        repo = source.clone_url.removeprefix(GITHUB).removesuffix(".git")
        prefix = f"{source.path}/" if source.path else ""
        return f"{RAW_GITHUB}/{repo}/{sha}/{prefix}"
    if source.local is not None and source.local.exists():
        return f"body/{key}/"
    return None


def source_entry(key: str, source: Source, sha: str | None) -> dict:
    entry = source.marketplace_source(sha) if (source.repo or source.url) else {}
    base = body_base(key, source, sha)
    if base:
        entry["body"] = base
    reachable_only_here = base is None or base.startswith("body/")
    if source.local is not None and reachable_only_here:
        entry["local"] = str(source.local)
    return entry


def resolve_pins(bundle: Bundle, workspace: Workspace) -> dict[str, str]:
    """Pin what the catalog can reach.

    A source it cannot reach still catalogs from the checkout it resolved,
    so an unreachable remote costs a pin rather than the whole run. `build`
    resolves its own pins and stays fatal, since a manifest without one
    points at a moving ref.
    """
    pins = {}
    for key, source in bundle.sources.items():
        if workspace.cache is None or not (source.repo or source.url):
            continue
        try:
            pins[key] = workspace.sha(source)
        except (RuntimeError, ValueError):
            workspace.notes.append(
                f"{key}: cannot reach {source.clone_url}, so its bodies resolve "
                "from the checkout instead of a pinned commit"
            )
    return pins


def build_catalog(bundle: Bundle, workspace: Workspace | None = None) -> dict:
    workspace = workspace if workspace is not None else Workspace()
    roots = {key: workspace.root(source) for key, source in bundle.sources.items()}
    shas = resolve_pins(bundle, workspace)

    plugins_by_source: dict[str, list] = {}
    for spec in bundle.plugins:
        plugins_by_source.setdefault(spec.source_key, []).append(spec)

    resolved = {
        spec.name: effective(
            spec,
            source_manifest(
                bundle.sources[spec.source_key], roots.get(spec.source_key)
            ),
        )
        for spec in bundle.plugins
    }
    records = []
    orphans = []
    for key, source in bundle.sources.items():
        owners = plugins_by_source.get(key, [])
        for skill in scan_source(source, roots.get(key)):
            selecting = [spec for spec in owners if spec.selects(skill.rel_path)]
            if not selecting:
                orphans.append(f"{key}:{skill.rel_path}")
                continue
            record = skill.to_dict()
            record["plugins"] = [spec.name for spec in selecting]
            record["tags"] = sorted(
                {tag for spec in selecting if spec.skills for tag in spec.tags}
            )
            record["homepage"] = next(
                (
                    h
                    for h in (resolved[spec.name]["homepage"] for spec in selecting)
                    if h
                ),
                None,
            )
            records.append(record)

    records.sort(key=lambda r: (r["category"], r["name"]))
    return {
        "registry": bundle.name,
        "description": bundle.description,
        "owner": bundle.owner,
        "sources": {
            key: source_entry(key, source, shas.get(key))
            for key, source in bundle.sources.items()
        },
        "plugins": [
            {
                "name": spec.name,
                "description": resolved[spec.name]["description"],
                "version": resolved[spec.name]["version"],
                "category": spec.category,
                "tags": spec.tags,
                "homepage": resolved[spec.name]["homepage"],
                "source": spec.source_key,
                "curated": bool(spec.skills),
                "skills": sum(1 for r in records if spec.name in r["plugins"]),
            }
            for spec in bundle.plugins
        ],
        "skills": records,
        "orphans": sorted(orphans),
        "totals": {
            "skills": len(records),
            "alwaysOn": sum(r["tokensAlwaysOn"] for r in records),
            "orphans": len(orphans),
        },
    }
