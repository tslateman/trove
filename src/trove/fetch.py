from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .models import Source

GIT_ENV = {"GIT_TERMINAL_PROMPT": "0"}
SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def default_cache() -> Path:
    root = os.environ.get("XDG_CACHE_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".cache"
    return base / "trove" / "sources"


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **GIT_ENV},
    )


def _git_checked(
    *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    result = _git(*args, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result


def list_remote_refs(source: Source, ref: str) -> dict[str, str]:
    result = _git("ls-remote", "--", source.clone_url, ref, f"refs/tags/{ref}^{{}}")
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


def slug(url: str) -> str:
    return SLUG.sub("-", url).strip("-")[:80] or "source"


def materialize(source: Source, sha: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.parent / f".{dest.name}.partial"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        _git_checked("init", "--quiet", str(staging))
        fetched = _git(
            "fetch", "--depth", "1", "--quiet", "--", source.clone_url, sha, cwd=staging
        )
        if fetched.returncode != 0:
            _git_checked(
                "fetch",
                "--depth",
                "1",
                "--quiet",
                "--",
                source.clone_url,
                source.ref or "HEAD",
                cwd=staging,
            )
        _git_checked("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=staging)
        os.replace(staging, dest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def checkout(source: Source, cache: Path, sha: str) -> Path:
    dest = cache / slug(source.clone_url) / sha
    if not (dest / ".git").exists():
        materialize(source, sha, dest)
    return dest / source.path if source.path else dest


def local_root(key: str, local: Path) -> Path:
    if not local.exists():
        raise ValueError(
            f"source {key!r}: local path {local} does not exist. Create the checkout, "
            "remove `local:` to fetch the remote, or drop --offline"
        )
    return local


@dataclass
class Workspace:
    """Resolves a source to the plugin root a skill path is relative to.

    A `cache` of None disables fetching, which is what `--offline` and
    `build --no-pin` pass so no command reaches the network unasked.
    """

    cache: Path | None = None
    notes: list[str] = field(default_factory=list)
    _shas: dict[str, str] = field(default_factory=dict)

    def sha(self, source: Source) -> str:
        if source.key not in self._shas:
            self._shas[source.key] = resolve_sha(source)
        return self._shas[source.key]

    def root(self, source: Source) -> Path | None:
        if source.local is not None and source.local.exists():
            return source.local
        if self.cache is None or not (source.repo or source.url):
            return local_root(source.key, source.local) if source.local is not None else None
        if source.local is not None:
            self.notes.append(
                f"{source.key}: local path {source.local} does not exist, "
                f"fetching {source.clone_url} instead"
            )
        return checkout(source, self.cache, self.sha(source))
