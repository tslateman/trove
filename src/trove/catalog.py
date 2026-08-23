from __future__ import annotations

from .models import Bundle
from .resolve import effective, source_manifest
from .scan import scan_source


def selects(spec, skill) -> bool:
    if not spec.skills:
        return True
    return skill.rel_path in spec.selected_paths


def build_catalog(bundle: Bundle) -> dict:
    plugins_by_source: dict[str, list] = {}
    for spec in bundle.plugins:
        plugins_by_source.setdefault(spec.source_key, []).append(spec)

    resolved = {
        spec.name: effective(spec, source_manifest(bundle.sources[spec.source_key]))
        for spec in bundle.plugins
    }
    records = []
    orphans = []
    for key, source in bundle.sources.items():
        owners = plugins_by_source.get(key, [])
        for skill in scan_source(source):
            selecting = [spec for spec in owners if selects(spec, skill)]
            if not selecting:
                orphans.append(f"{key}:{skill.rel_path}")
                continue
            record = skill.to_dict()
            record["plugins"] = [spec.name for spec in selecting]
            record["tags"] = sorted(
                {tag for spec in selecting if spec.skills for tag in spec.tags}
            )
            record["homepage"] = next(
                (h for h in (resolved[spec.name]["homepage"] for spec in selecting) if h), None
            )
            records.append(record)

    records.sort(key=lambda r: (r["category"], r["name"]))
    return {
        "registry": bundle.name,
        "description": bundle.description,
        "owner": bundle.owner,
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
