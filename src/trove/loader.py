from __future__ import annotations

from pathlib import Path

import yaml

from .models import Bundle, PluginSpec, Source


def expand(value: str | None, base: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def load_bundle(path: Path) -> Bundle:
    if not path.exists():
        raise ValueError(
            f"bundle {path} does not exist. Copy bundles/example.yaml to it, "
            "or name another with --bundle"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    sources = {
        key: Source(
            key=key,
            repo=spec.get("repo"),
            url=spec.get("url"),
            ref=spec.get("ref"),
            path=spec.get("path"),
            local=expand(spec.get("local"), path.parent),
        )
        for key, spec in (data.get("sources") or {}).items()
    }

    plugins = []
    for spec in data.get("plugins") or []:
        source_key = spec.get("source", spec["name"])
        if source_key not in sources:
            raise KeyError(f"plugin {spec['name']!r} names unknown source {source_key!r}")
        plugins.append(
            PluginSpec(
                name=spec["name"],
                source_key=source_key,
                description=spec.get("description"),
                category=spec.get("category"),
                display_name=spec.get("displayName"),
                version=spec.get("version"),
                homepage=spec.get("homepage"),
                tags=spec.get("tags") or [],
                skills=spec.get("skills") or [],
            )
        )

    return Bundle(
        name=data["name"],
        description=data.get("description", ""),
        owner=data.get("owner") or {},
        sources=sources,
        plugins=plugins,
        renames=data.get("renames") or {},
    )
