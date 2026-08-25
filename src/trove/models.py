from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .lint import findings

CHARS_PER_TOKEN_FRONTMATTER = 3.03
FRONTMATTER_OVERHEAD = 4.3
CHARS_PER_TOKEN_BODY = 2.92
BODY_OVERHEAD = 1.0


@dataclass(frozen=True)
class Source:
    key: str
    repo: str | None = None
    url: str | None = None
    ref: str | None = None
    path: str | None = None
    local: Path | None = None

    @property
    def clone_url(self) -> str:
        if self.url:
            return self.url
        return f"https://github.com/{self.repo}.git"

    def marketplace_source(self, sha: str | None) -> dict:
        source = "git-subdir" if self.path else "url"
        entry: dict = {"source": source, "url": self.clone_url}
        if self.path:
            entry["path"] = self.path
        if self.ref:
            entry["ref"] = self.ref
        if sha:
            entry["sha"] = sha
        return entry


@dataclass
class Skill:
    name: str
    description: str
    rel_path: str
    source_key: str
    category: str
    body_chars: int
    frontmatter_chars: int
    strict_yaml: bool = True

    @property
    def tokens_always_on(self) -> int:
        return round(self.frontmatter_chars / CHARS_PER_TOKEN_FRONTMATTER + FRONTMATTER_OVERHEAD)

    @property
    def tokens_on_invoke(self) -> int:
        return round(self.body_chars / CHARS_PER_TOKEN_BODY + BODY_OVERHEAD)

    @property
    def lint(self) -> list[str]:
        return findings(self.name, self.description, self.strict_yaml)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "path": self.rel_path,
            "source": self.source_key,
            "category": self.category,
            "tokensAlwaysOn": self.tokens_always_on,
            "tokensOnInvoke": self.tokens_on_invoke,
            "lint": self.lint,
        }


@dataclass
class PluginSpec:
    name: str
    source_key: str
    description: str | None = None
    category: str | None = None
    display_name: str | None = None
    version: str | None = None
    homepage: str | None = None
    tags: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)

    @property
    def selections(self) -> list[str]:
        return [path.removeprefix("./") for path in self.skills]

    @property
    def selected_paths(self) -> list[str]:
        return [selection.rstrip("/") for selection in self.selections]

    def selects(self, rel_path: str) -> bool:
        if not self.skills:
            return True
        return any(
            rel_path.startswith(selection) if selection.endswith("/") else rel_path == selection
            for selection in self.selections
        )


@dataclass
class Bundle:
    name: str
    description: str
    owner: dict
    sources: dict[str, Source]
    plugins: list[PluginSpec]
    renames: dict[str, str] = field(default_factory=dict)
