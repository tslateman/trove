from __future__ import annotations

from pathlib import Path

import yaml

from . import frontmatter
from .fetch import local_root
from .models import Skill, Source


def read_metadata(text: str) -> tuple[dict[str, str], str]:
    fields, body = frontmatter.split(text)
    strict = strict_yaml_parse(text)
    if isinstance(strict, dict):
        for key in ("name", "description"):
            value = strict.get(key)
            if isinstance(value, str):
                fields[key] = value
    return fields, body


def strict_yaml_parse(text: str):
    if not text.startswith("---"):
        return None
    raw = text.partition("---")[2].partition("\n---")[0]
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return None


def strict_yaml_ok(text: str) -> bool:
    if not text.startswith("---"):
        return True
    raw = text.partition("---")[2].partition("\n---")[0]
    try:
        yaml.safe_load(raw)
    except yaml.YAMLError:
        return False
    return True


EXCLUDED_DIRS = {"node_modules", "tests"}


def is_shipped(rel_path: str) -> bool:
    return not any(
        part.startswith(".") or part in EXCLUDED_DIRS for part in Path(rel_path).parts
    )


def category_for(rel_path: str, source_key: str) -> tuple[str, bool]:
    """Return (category, is_fallback). is_fallback is True when the path has no
    real subfolder to name a category from, so the source key stands in for one.
    """
    parts = list(Path(rel_path).parts)
    if parts and parts[0] == "skills":
        parts.pop(0)
    if len(parts) >= 2:
        return parts[0], False
    return source_key, True


def bundled(skill_dir: Path) -> tuple[int, int]:
    """Count the files shipped beside SKILL.md and the chars of the text ones.

    A binary ships but never loads as text, so it counts as a file and
    contributes nothing to the estimate.
    """
    files = 0
    chars = 0
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name == "SKILL.md":
            continue
        rel = path.relative_to(skill_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        files += 1
        try:
            chars += len(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
    return files, chars


def scan_source(source: Source, root: Path | None = None) -> list[Skill]:
    if root is None:
        if source.local is None:
            return []
        root = local_root(source.key, source.local)
    skills = []
    for skill_file in sorted(root.rglob("SKILL.md")):
        rel_dir = skill_file.parent.relative_to(root).as_posix()
        if not is_shipped(rel_dir):
            continue
        text = skill_file.read_text(encoding="utf-8-sig")
        meta, body = read_metadata(text)
        name = meta.get("name") or skill_file.parent.name
        description = meta.get("description", "").strip()
        files, chars = bundled(skill_file.parent)
        category, category_is_fallback = category_for(rel_dir, source.key)
        skills.append(
            Skill(
                name=name,
                description=description,
                rel_path=rel_dir,
                source_key=source.key,
                category=category,
                category_is_fallback=category_is_fallback,
                body_chars=len(body),
                frontmatter_chars=len(name) + len(description),
                strict_yaml=strict_yaml_ok(text),
                bundled_files=files,
                bundled_chars=chars,
            )
        )
    return skills
