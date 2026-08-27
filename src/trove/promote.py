"""Move a skill from a personal directory into the repo that should own it."""

from __future__ import annotations

import shutil
from pathlib import Path

from .fetch import local_root
from .models import Skill, Source
from .scan import scan_source

IGNORED = shutil.ignore_patterns(
    "__pycache__", ".ruff_cache", ".pytest_cache", ".DS_Store", "*.pyc"
)


def destination(root: Path, name: str, into: str | None) -> Path:
    """Where a promoted skill lands: under `skills/` when the source keeps one,
    else beside the other skills at the root."""
    if into is None:
        into = "skills" if (root / "skills").is_dir() else "."
    return root / into / name


def promote(
    skill_dir: Path, source: Source, into: str | None = None
) -> tuple[Path, Skill]:
    """Copy `skill_dir` into the source's local checkout and return where it
    landed with the scanner's view of it, lint findings included."""
    if not (skill_dir / "SKILL.md").is_file():
        raise ValueError(
            f"{skill_dir} has no SKILL.md, so there is no skill to promote"
        )
    if source.local is None:
        raise ValueError(
            f"source {source.key!r} has no `local:` checkout to promote into; "
            "clone it and name the path in the bundle"
        )
    root = local_root(source.key, source.local)
    dest = destination(root, skill_dir.name, into)
    if dest.exists():
        raise ValueError(
            f"{dest} already exists: source {source.key!r} already ships a skill "
            f"named {skill_dir.name!r}"
        )
    shutil.copytree(skill_dir, dest, ignore=IGNORED)
    rel = dest.relative_to(root).as_posix()
    scanned = {s.rel_path: s for s in scan_source(source, root)}
    if rel not in scanned:
        raise ValueError(
            f"copied to {dest}, but the scanner does not ship that path; "
            "pass --into a directory it indexes"
        )
    return dest, scanned[rel]
