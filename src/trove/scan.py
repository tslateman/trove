from __future__ import annotations

from pathlib import Path

import yaml

from . import frontmatter
from .models import Skill, Source


def strict_yaml_ok(text: str) -> bool:
    if not text.startswith("---"):
        return True
    raw = text.partition("---")[2].partition("\n---")[0]
    try:
        yaml.safe_load(raw)
    except yaml.YAMLError:
        return False
    return True


EXCLUDED_DIRS = {"node_modules"}


def is_shipped(rel_path: str) -> bool:
    return not any(
        part.startswith(".") or part in EXCLUDED_DIRS for part in Path(rel_path).parts
    )


def category_for(rel_path: str, source_key: str) -> str:
    parts = list(Path(rel_path).parts)
    if parts and parts[0] == "skills":
        parts.pop(0)
    if len(parts) >= 2:
        return parts[0]
    return source_key


def scan_source(source: Source) -> list[Skill]:
    root = source.local
    if root is None or not root.exists():
        return []
    skills = []
    for skill_file in sorted(root.rglob("SKILL.md")):
        rel_dir = skill_file.parent.relative_to(root).as_posix()
        if not is_shipped(rel_dir):
            continue
        text = skill_file.read_text(encoding="utf-8")
        meta, body = frontmatter.split(text)
        name = meta.get("name") or skill_file.parent.name
        description = meta.get("description", "").strip()
        skills.append(
            Skill(
                name=name,
                description=description,
                rel_path=rel_dir,
                source_key=source.key,
                category=category_for(rel_dir, source.key),
                body_chars=len(body),
                frontmatter_chars=len(name) + len(description),
                strict_yaml=strict_yaml_ok(text),
            )
        )
    return skills
