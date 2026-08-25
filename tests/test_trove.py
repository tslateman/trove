from pathlib import Path

import pytest

from trove import frontmatter
from trove.build import build_marketplace, plugin_entry
from trove.loader import load_bundle
from trove.models import PluginSpec, Skill, Source
from trove.scan import category_for, is_shipped, scan_source, strict_yaml_ok

UNQUOTED_COLON = """---
name: prose
description: Apply Strunk's rules to prose: docs, commits, UI text.
---
body text
"""

FOLDED = """---
name: review-kit
description: >-
  Language review skills only,
  spanning five languages.
---
body
"""


def test_parses_description_containing_unquoted_colon():
    meta, body = frontmatter.split(UNQUOTED_COLON)
    assert meta["name"] == "prose"
    assert meta["description"].endswith("docs, commits, UI text.")
    assert body.strip() == "body text"


def test_strict_yaml_flags_the_same_file_as_invalid():
    assert strict_yaml_ok(UNQUOTED_COLON) is False


def test_parses_folded_block_scalar():
    meta, _ = frontmatter.split(FOLDED)
    assert meta["description"] == "Language review skills only, spanning five languages."
    assert strict_yaml_ok(FOLDED) is True


def test_missing_frontmatter_returns_whole_body():
    meta, body = frontmatter.split("no frontmatter here")
    assert meta == {}
    assert body == "no frontmatter here"


@pytest.mark.parametrize(
    "path,source,expected",
    [
        ("skills/craft/tidy", "skills", "craft"),
        ("skills/adr", "duet", "duet"),
        ("adr", "duet", "duet"),
        ("skills/review/go-review", "skills", "review"),
    ],
)
def test_category_falls_back_to_source_when_layout_is_flat(path, source, expected):
    assert category_for(path, source) == expected


@pytest.mark.parametrize(
    "path,shipped",
    [
        ("skills/craft/tidy", True),
        (".claude/skills/gitnexus/gitnexus-cli", False),
        ("node_modules/pkg/skills/x", False),
        ("skills/.hidden/x", False),
        ("tests/fixtures/demo-repo/skills/craft/demo-craft", False),
    ],
)
def test_consumer_side_skills_are_excluded(path, shipped):
    assert is_shipped(path) is shipped


def test_token_estimate_tracks_calibrated_fit():
    skill = Skill(
        name="prose",
        description="x" * 184,
        rel_path="skills/writing/prose",
        source_key="skills",
        category="writing",
        body_chars=4833,
        frontmatter_chars=189,
    )
    assert skill.tokens_always_on == pytest.approx(70, abs=4)
    assert skill.tokens_on_invoke == pytest.approx(1655, rel=0.05)


def test_curated_plugin_emits_relative_skill_paths():
    spec = PluginSpec(
        name="review-kit",
        source_key="skills",
        description="d",
        skills=["skills/review/go-review", "./skills/review/tidy"],
    )
    entry = plugin_entry(spec, Source(key="skills", repo="o/skills"), sha="abc")
    assert entry["skills"] == ["./skills/review/go-review", "./skills/review/tidy"]
    assert entry["source"]["sha"] == "abc"


def test_source_without_path_is_a_url_source():
    entry = Source(key="s", repo="o/r", ref="v1").marketplace_source("sha1")
    assert entry == {
        "source": "url",
        "url": "https://github.com/o/r.git",
        "ref": "v1",
        "sha": "sha1",
    }


def test_source_with_path_is_a_git_subdir_source():
    entry = Source(key="s", repo="o/r", path="plugins/x").marketplace_source(None)
    assert entry["source"] == "git-subdir"
    assert entry["path"] == "plugins/x"
    assert "sha" not in entry


def test_bundle_rejects_plugin_naming_unknown_source(tmp_path):
    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        "name: t\nsources:\n  a: {repo: o/a}\n"
        "plugins:\n  - {name: p, source: missing, description: d}\n"
    )
    with pytest.raises(KeyError, match="missing"):
        load_bundle(bundle)


def test_a_bundle_that_does_not_exist_names_the_starter_to_copy(tmp_path):
    with pytest.raises(ValueError, match="bundles/example.yaml"):
        load_bundle(tmp_path / "local.yaml")


def test_unpinned_build_emits_manifest_without_shas(tmp_path):
    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        "name: t\ndescription: d\nowner: {name: o}\n"
        "sources:\n  a: {repo: o/a}\n"
        "plugins:\n  - {name: p, source: a, description: d}\nrenames: {old: p}\n"
    )
    manifest = build_marketplace(load_bundle(bundle), pin=False)
    assert manifest["plugins"][0]["source"] == {
        "source": "url",
        "url": "https://github.com/o/a.git",
    }
    assert manifest["renames"] == {"old": "p"}


def test_scan_skips_repo_local_claude_skills(tmp_path):
    shipped = tmp_path / "skills" / "craft" / "tidy"
    consumer = tmp_path / ".claude" / "skills" / "vendor"
    for d in (shipped, consumer):
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("---\nname: %s\ndescription: d\n---\nbody\n" % d.name)
    found = scan_source(Source(key="s", repo="o/s", local=tmp_path))
    assert [s.name for s in found] == ["tidy"]


def _bundle_with_curated_plugin(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for rel in ("skills/review/go-review", "skills/draw/excalidraw"):
        d = repo / rel
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\nname: %s\ndescription: d\n---\nbody\n" % Path(rel).name
        )
    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        f"name: t\ndescription: d\nowner: {{name: o}}\n"
        f"sources:\n  s: {{repo: o/s, local: {repo}}}\n"
        "plugins:\n"
        "  - name: kit\n    source: s\n    description: d\n    tags: [review, linting]\n"
        "    skills: [skills/review/go-review]\n"
    )
    return bundle


def test_skills_no_plugin_ships_are_reported_as_orphans(tmp_path):
    from trove.catalog import build_catalog

    catalog = build_catalog(load_bundle(_bundle_with_curated_plugin(tmp_path)))
    assert [r["name"] for r in catalog["skills"]] == ["go-review"]
    assert catalog["orphans"] == ["s:skills/draw/excalidraw"]


def test_catalog_carries_the_source_a_skill_body_resolves_from(tmp_path):
    from trove.catalog import build_catalog

    bundle = load_bundle(_bundle_with_curated_plugin(tmp_path))
    entry = build_catalog(bundle)["sources"]["s"]
    assert entry["source"] == "url"
    assert entry["url"] == "https://github.com/o/s.git"


def test_curated_plugin_tags_reach_only_the_skills_it_selects(tmp_path):
    from trove.catalog import build_catalog

    catalog = build_catalog(load_bundle(_bundle_with_curated_plugin(tmp_path)))
    assert catalog["skills"][0]["tags"] == ["linting", "review"]
    assert catalog["plugins"][0]["skills"] == 1


def test_whole_repo_plugin_does_not_stamp_its_tags_on_every_skill(tmp_path):
    from trove.catalog import build_catalog

    bundle = _bundle_with_curated_plugin(tmp_path)
    bundle.write_text(
        bundle.read_text().replace(
            "    skills: [skills/review/go-review]\n", ""
        )
    )
    catalog = build_catalog(load_bundle(bundle))
    assert {r["name"] for r in catalog["skills"]} == {"go-review", "excalidraw"}
    assert all(r["tags"] == [] for r in catalog["skills"])


def test_cli_reports_config_errors_without_a_traceback(tmp_path, capsys):
    from trove.cli import main

    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        "name: t\nsources:\n  a: {repo: o/a}\n"
        "plugins:\n  - {name: p, source: nope, description: d}\n"
    )
    code = main(["--bundle", str(bundle), "--out", str(tmp_path), "build", "--no-pin"])
    assert code == 1
    err = capsys.readouterr().err
    assert err.startswith("trove: ")
    assert "Traceback" not in err


# --- fixes from the pre-publish review ---

import json
import subprocess


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo_with_ambiguous_refs(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    _git("init", "-q", "-b", "main", cwd=work)
    _git("config", "user.email", "t@example.com", cwd=work)
    _git("config", "user.name", "T", cwd=work)
    (work / "f").write_text("x")
    _git("add", "-A", cwd=work)
    _git("commit", "-qm", "one", cwd=work)
    _git("branch", "feature/main", cwd=work)
    _git("branch", "release", cwd=work)
    _git("tag", "-a", "release", "-m", "tagged", cwd=work)
    _git("tag", "-a", "v1", "-m", "tagged", cwd=work)
    return work


def test_resolve_sha_ignores_refname_sort_order(tmp_path):
    from trove.build import resolve_sha

    work = _repo_with_ambiguous_refs(tmp_path)
    expected = subprocess.run(
        ["git", "rev-parse", "main"], cwd=work, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert resolve_sha(Source(key="s", url=str(work), ref="main")) == expected


def test_resolve_sha_refuses_a_tag_and_branch_collision(tmp_path):
    from trove.build import resolve_sha

    work = _repo_with_ambiguous_refs(tmp_path)
    with pytest.raises(ValueError, match="matches both"):
        resolve_sha(Source(key="s", url=str(work), ref="release"))


def test_resolve_sha_peels_an_annotated_tag_to_its_commit(tmp_path):
    from trove.build import resolve_sha

    work = _repo_with_ambiguous_refs(tmp_path)
    sha = resolve_sha(Source(key="s", url=str(work), ref="v1"))
    kind = subprocess.run(
        ["git", "cat-file", "-t", sha], cwd=work, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert kind == "commit"


def test_ls_remote_treats_a_dash_leading_url_as_a_path_not_a_flag(tmp_path):
    from trove.build import resolve_sha

    marker = tmp_path / "PWNED"
    source = Source(key="s", url=f"--upload-pack=touch {marker}", ref="HEAD")
    with pytest.raises(RuntimeError):
        resolve_sha(source)
    assert not marker.exists()


@pytest.mark.parametrize("raw", ["x/y", "./x/y", "x/y/", "./x/y/"])
def test_curated_paths_normalize_to_one_shape(raw):
    assert PluginSpec(name="p", source_key="s", description="d", skills=[raw]).selected_paths == ["x/y"]


def test_curated_path_normalization_is_a_prefix_strip_not_a_charset_strip():
    spec = PluginSpec(name="p", source_key="s", description="d", skills=[".claude/skills/x"])
    assert spec.selected_paths == [".claude/skills/x"]


def test_build_refuses_a_curated_path_that_matches_no_skill(tmp_path):
    from trove.build import build_marketplace

    repo = tmp_path / "repo" / "skills" / "review" / "here"
    repo.mkdir(parents=True)
    (repo / "SKILL.md").write_text("---\nname: here\ndescription: d\n---\nbody\n")
    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        f"name: t\ndescription: d\nowner: {{name: o}}\n"
        f"sources:\n  s: {{repo: o/s, local: {tmp_path / 'repo'}}}\n"
        "plugins:\n  - name: k\n    source: s\n    description: d\n"
        "    skills: [skills/review/here, skills/review/gone]\n"
    )
    with pytest.raises(ValueError, match="gone"):
        build_marketplace(load_bundle(bundle), pin=False)


def test_scan_raises_when_a_declared_local_path_is_missing(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        scan_source(Source(key="s", repo="o/s", local=tmp_path / "nope"))


def test_relative_local_resolves_against_the_bundle_file(tmp_path):
    repo = tmp_path / "repos" / "s" / "skills" / "c" / "one"
    repo.mkdir(parents=True)
    (repo / "SKILL.md").write_text("---\nname: one\ndescription: d\n---\nbody\n")
    conf = tmp_path / "conf"
    conf.mkdir()
    bundle = conf / "b.yaml"
    bundle.write_text(
        "name: t\nsources:\n  s: {repo: o/s, local: ../repos/s}\n"
        "plugins:\n  - {name: p, source: s, description: d}\n"
    )
    loaded = load_bundle(bundle)
    assert [s.name for s in scan_source(loaded.sources["s"])] == ["one"]


def test_a_utf8_bom_does_not_hide_the_frontmatter(tmp_path):
    d = tmp_path / "skills" / "c" / "bom"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "﻿---\nname: bom\ndescription: A described skill.\n---\nbody\n", encoding="utf-8"
    )
    skill = scan_source(Source(key="s", repo="o/s", local=tmp_path))[0]
    assert skill.name == "bom"
    assert skill.description == "A described skill."


def test_single_quoted_yaml_escapes_are_decoded_not_passed_through(tmp_path):
    d = tmp_path / "skills" / "c" / "q"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: q\ndescription: 'keeps a project''s map honest: parallel readers'\n---\nbody\n"
    )
    skill = scan_source(Source(key="s", repo="o/s", local=tmp_path))[0]
    assert skill.description == "keeps a project's map honest: parallel readers"


def test_tolerant_parser_still_wins_when_strict_yaml_fails(tmp_path):
    d = tmp_path / "skills" / "c" / "loose"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: loose\ndescription: Apply rules to prose: docs, commits.\n---\nbody\n"
    )
    skill = scan_source(Source(key="s", repo="o/s", local=tmp_path))[0]
    assert skill.description == "Apply rules to prose: docs, commits."
    assert skill.strict_yaml is False


def _source_with_manifest(tmp_path: Path, **manifest) -> Source:
    root = tmp_path / "repo"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest))
    return Source(key="s", repo="o/s", local=root)


def test_plugin_metadata_is_inherited_from_the_source_manifest(tmp_path):
    from trove.build import plugin_entry

    source = _source_with_manifest(
        tmp_path, name="s", version="0.6.0", description="upstream text"
    )
    entry = plugin_entry(PluginSpec(name="s", source_key="s"), source, sha=None)
    assert entry["version"] == "0.6.0"
    assert entry["description"] == "upstream text"


def test_a_bundle_value_overrides_the_source_manifest(tmp_path):
    from trove.build import plugin_entry

    source = _source_with_manifest(tmp_path, version="0.6.0", description="upstream text")
    spec = PluginSpec(name="kit", source_key="s", description="a curated subset")
    entry = plugin_entry(spec, source, sha=None)
    assert entry["description"] == "a curated subset"
    assert entry["version"] == "0.6.0"


def test_drift_reports_a_restated_field_that_disagrees(tmp_path):
    from trove.resolve import drift, source_manifest

    manifest = source_manifest(_source_with_manifest(tmp_path, version="0.6.0", description="up"))
    spec = PluginSpec(name="s", source_key="s", description="down", version="0.5.0")
    assert sorted(f for f, _, _ in drift(spec, manifest)) == ["description", "version"]


def test_drift_exempts_a_curated_plugins_own_description(tmp_path):
    from trove.resolve import drift, source_manifest

    manifest = source_manifest(_source_with_manifest(tmp_path, version="0.6.0", description="up"))
    spec = PluginSpec(
        name="kit", source_key="s", description="a curated subset", skills=["skills/a/b"]
    )
    assert [f for f, _, _ in drift(spec, manifest)] == []


def test_build_refuses_a_plugin_with_no_description_anywhere(tmp_path):
    from trove.build import plugin_entry

    with pytest.raises(ValueError, match="no description"):
        plugin_entry(PluginSpec(name="p", source_key="s"), Source(key="s", repo="o/s"), sha=None)


def _serve(directory: Path, roots: dict | None = None):
    from functools import partial
    from http.server import ThreadingHTTPServer
    import threading
    from trove.cli import PreviewHandler

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        partial(PreviewHandler, directory=str(directory), roots=roots or {}),
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_preview_server_forbids_browser_caching(tmp_path):
    from urllib.request import urlopen

    (tmp_path / "index.html").write_text("<p>one</p>")
    server = _serve(tmp_path)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
        with urlopen(url) as first:
            assert "no-store" in first.headers["Cache-Control"]

        (tmp_path / "index.html").write_text("<p>two</p>")
        with urlopen(url) as second:
            assert second.read() == b"<p>two</p>"
    finally:
        server.shutdown()


def test_preview_server_ignores_a_conditional_request(tmp_path):
    from urllib.request import Request, urlopen

    (tmp_path / "index.html").write_text("<p>one</p>")
    server = _serve(tmp_path)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
        request = Request(url, headers={"If-Modified-Since": "Mon, 01 Jan 2035 00:00:00 GMT"})
        with urlopen(request) as response:
            assert response.status == 200
            assert response.read() == b"<p>one</p>"
    finally:
        server.shutdown()


def test_serve_refuses_a_port_that_is_already_serving(tmp_path):
    from trove.cli import main

    (tmp_path / "index.html").write_text("<p>one</p>")
    server = _serve(tmp_path)
    try:
        port = server.server_address[1]
        code = main(["--out", str(tmp_path), "serve", "--port", str(port)])
        assert code == 1
    finally:
        server.shutdown()


def test_serve_refuses_a_directory_with_no_catalog(tmp_path):
    from trove.cli import main

    assert main(["--out", str(tmp_path), "serve", "--port", "0"]) == 1


def test_a_trailing_slash_curates_a_whole_subtree():
    spec = PluginSpec(name="p", source_key="s", description="d", skills=["./skills/review/"])
    assert spec.selects("skills/review/go-review")
    assert spec.selects("skills/review/tidy")
    assert not spec.selects("skills/craft/tidy")


def test_no_trailing_slash_still_means_one_exact_skill():
    spec = PluginSpec(name="p", source_key="s", description="d", skills=["skills/review/go"])
    assert spec.selects("skills/review/go")
    assert not spec.selects("skills/review/go-review")


def test_subtree_curation_survives_into_the_manifest(tmp_path):
    from trove.build import build_marketplace

    for rel in ("skills/review/one", "skills/craft/two"):
        d = tmp_path / "repo" / rel
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {Path(rel).name}\ndescription: d\n---\nbody\n")
    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        f"name: t\ndescription: d\nowner: {{name: o}}\n"
        f"sources:\n  s: {{repo: o/s, local: {tmp_path / 'repo'}}}\n"
        "plugins:\n  - name: k\n    source: s\n    description: d\n"
        "    skills: ['./skills/review/']\n"
    )
    manifest = build_marketplace(load_bundle(bundle), pin=False)
    assert manifest["plugins"][0]["skills"] == ["./skills/review/"]


def test_a_subtree_prefix_matching_nothing_still_fails(tmp_path):
    from trove.build import build_marketplace

    d = tmp_path / "repo" / "skills" / "review" / "one"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: one\ndescription: d\n---\nbody\n")
    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        f"name: t\ndescription: d\nowner: {{name: o}}\n"
        f"sources:\n  s: {{repo: o/s, local: {tmp_path / 'repo'}}}\n"
        "plugins:\n  - name: k\n    source: s\n    description: d\n"
        "    skills: ['./skills/nope/']\n"
    )
    with pytest.raises(ValueError, match="skills/nope/"):
        build_marketplace(load_bundle(bundle), pin=False)


def _local_bundle(tmp_path: Path, *, checkout: bool, override: str = "") -> Path:
    repo = tmp_path / "repo"
    if checkout:
        (repo / ".claude-plugin").mkdir(parents=True)
        (repo / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "p", "version": "2.0.0", "description": "upstream text"})
        )
    bundle = tmp_path / "b.yaml"
    local_line = f"local: {repo}, " if checkout else ""
    bundle.write_text(
        f"name: t\ndescription: d\nowner: {{name: o}}\n"
        f"sources:\n  s: {{repo: o/s, {local_line}ref: main}}\n"
        f"plugins:\n  - {{name: p, source: s{override}}}\n"
    )
    return bundle


def _marketplace(tmp_path: Path) -> dict:
    return {
        "name": "local",
        "plugins": [
            {"name": "p", "description": "stale", "version": "0.0.1", "source": "./plugins/p"},
            {"name": "untouched", "description": "keep me", "version": "9.9.9", "source": "./plugins/untouched"},
        ],
    }


def test_sync_local_proposes_the_upstream_values(tmp_path):
    from trove.local import plan

    changes, absent, unsourced = plan(load_bundle(_local_bundle(tmp_path, checkout=True)), _marketplace(tmp_path))
    assert sorted((n, f, new) for n, f, _, new in changes) == [
        ("p", "description", "upstream text"),
        ("p", "version", "2.0.0"),
    ]
    assert unsourced == []


def test_sync_local_syncs_a_deliberate_bundle_override(tmp_path):
    from trove.local import plan

    bundle = _local_bundle(tmp_path, checkout=True, override=", description: a curated subset")
    changes, _, _ = plan(load_bundle(bundle), _marketplace(tmp_path))
    assert ("p", "description", "stale", "a curated subset") in changes


def test_sync_local_refuses_to_sync_a_source_with_no_checkout(tmp_path):
    from trove.local import plan

    changes, _, unsourced = plan(load_bundle(_local_bundle(tmp_path, checkout=False)), _marketplace(tmp_path))
    assert changes == []
    assert unsourced == ["p"]


def test_sync_local_reports_a_plugin_the_marketplace_does_not_list(tmp_path):
    from trove.local import plan

    manifest = {"name": "local", "plugins": []}
    _, absent, _ = plan(load_bundle(_local_bundle(tmp_path, checkout=True)), manifest)
    assert absent == ["p"]


def test_sync_local_leaves_unrelated_entries_alone(tmp_path):
    from trove.local import apply, plan

    manifest = _marketplace(tmp_path)
    changes, _, _ = plan(load_bundle(_local_bundle(tmp_path, checkout=True)), manifest)
    updated = apply(manifest, changes)
    other = next(e for e in updated["plugins"] if e["name"] == "untouched")
    assert other == {
        "name": "untouched",
        "description": "keep me",
        "version": "9.9.9",
        "source": "./plugins/untouched",
    }
    synced = next(e for e in updated["plugins"] if e["name"] == "p")
    assert synced["source"] == "./plugins/p"


def test_sync_local_dry_run_writes_nothing(tmp_path):
    from trove.cli import main

    target = tmp_path / "marketplace.json"
    original = json.dumps(_marketplace(tmp_path), indent=2)
    target.write_text(original)
    code = main([
        "--bundle", str(_local_bundle(tmp_path, checkout=True)),
        "sync-local", "--marketplace", str(target), "--dry-run",
    ])
    assert code == 0
    assert target.read_text() == original


def test_sync_local_writes_a_backup_before_changing_anything(tmp_path):
    from trove.cli import main

    target = tmp_path / "marketplace.json"
    original = json.dumps(_marketplace(tmp_path), indent=2)
    target.write_text(original)
    assert main([
        "--bundle", str(_local_bundle(tmp_path, checkout=True)),
        "sync-local", "--marketplace", str(target),
    ]) == 0
    assert json.loads(target.read_text())["plugins"][0]["version"] == "2.0.0"
    assert target.with_suffix(".json.bak").read_text() == original


def test_sync_local_fails_when_the_marketplace_is_missing(tmp_path):
    from trove.cli import main

    assert main([
        "--bundle", str(_local_bundle(tmp_path, checkout=True)),
        "sync-local", "--marketplace", str(tmp_path / "nope.json"),
    ]) == 1


# --- fetching a source that has no local checkout ---


def _remote_repo(tmp_path: Path, name: str = "remote", subdir: str = "") -> Path:
    work = tmp_path / name
    root = work / subdir if subdir else work
    skill = root / "skills" / "craft" / "tidy"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: tidy\ndescription: Tidy things up.\n---\nbody\n")
    manifest = root / ".claude-plugin"
    manifest.mkdir(parents=True)
    (manifest / "plugin.json").write_text(
        json.dumps({"name": "remote", "version": "2.1.0", "description": "From the source"})
    )
    _git("init", "-q", "-b", "main", cwd=work)
    _git("config", "user.email", "t@example.com", cwd=work)
    _git("config", "user.name", "T", cwd=work)
    _git("add", "-A", cwd=work)
    _git("commit", "-qm", "one", cwd=work)
    return work


def test_a_source_with_only_a_remote_is_scanned_after_fetching(tmp_path):
    from trove.fetch import Workspace

    source = Source(key="s", url=str(_remote_repo(tmp_path)), ref="main")
    workspace = Workspace(cache=tmp_path / "cache")
    assert [s.name for s in scan_source(source, workspace.root(source))] == ["tidy"]


def test_offline_leaves_a_remote_only_source_unscanned(tmp_path):
    from trove.fetch import Workspace

    source = Source(key="s", url=str(_remote_repo(tmp_path)), ref="main")
    workspace = Workspace(cache=None)
    assert workspace.root(source) is None
    assert scan_source(source, workspace.root(source)) == []


def test_a_second_resolve_reuses_the_cached_checkout(tmp_path, monkeypatch):
    from trove import fetch
    from trove.fetch import Workspace

    source = Source(key="s", url=str(_remote_repo(tmp_path)), ref="main")
    workspace = Workspace(cache=tmp_path / "cache")
    first = workspace.root(source)

    def explode(*args, **kwargs):
        raise AssertionError("cached checkout was re-fetched")

    monkeypatch.setattr(fetch, "materialize", explode)
    assert Workspace(cache=tmp_path / "cache").root(source) == first


def test_a_missing_local_path_falls_back_to_the_remote_with_a_note(tmp_path):
    from trove.fetch import Workspace

    source = Source(
        key="s", url=str(_remote_repo(tmp_path)), ref="main", local=tmp_path / "gone"
    )
    workspace = Workspace(cache=tmp_path / "cache")
    assert [s.name for s in scan_source(source, workspace.root(source))] == ["tidy"]
    assert any("does not exist" in note and "fetching" in note for note in workspace.notes)


def test_a_missing_local_path_still_fails_when_fetching_is_off(tmp_path):
    from trove.fetch import Workspace

    source = Source(key="s", repo="o/s", local=tmp_path / "gone")
    with pytest.raises(ValueError, match="does not exist"):
        Workspace(cache=None).root(source)


def test_fetch_treats_a_dash_leading_url_as_a_path_not_a_flag(tmp_path):
    from trove.fetch import materialize

    marker = tmp_path / "PWNED"
    source = Source(key="s", url=f"--upload-pack=touch {marker}", ref="HEAD")
    with pytest.raises(RuntimeError):
        materialize(source, "HEAD", tmp_path / "dest")
    assert not marker.exists()


def test_a_subdir_source_resolves_inside_the_fetched_checkout(tmp_path):
    from trove.fetch import Workspace

    work = _remote_repo(tmp_path, subdir="tooling/plugin")
    source = Source(key="s", url=str(work), ref="main", path="tooling/plugin")
    root = Workspace(cache=tmp_path / "cache").root(source)
    assert [s.name for s in scan_source(source, root)] == ["tidy"]


def test_a_remote_only_plugin_inherits_its_description_from_the_fetched_manifest(tmp_path):
    from trove.build import build_marketplace
    from trove.fetch import Workspace

    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        f"name: t\nsources:\n  s: {{url: {_remote_repo(tmp_path)}, ref: main}}\n"
        "plugins:\n  - {name: p, source: s}\n"
    )
    manifest = build_marketplace(
        load_bundle(bundle), pin=False, workspace=Workspace(cache=tmp_path / "cache")
    )
    entry = manifest["plugins"][0]
    assert entry["description"] == "From the source"
    assert entry["version"] == "2.1.0"


def test_curated_paths_are_verified_against_a_fetched_source(tmp_path):
    from trove.build import build_marketplace
    from trove.fetch import Workspace

    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        f"name: t\nsources:\n  s: {{url: {_remote_repo(tmp_path)}, ref: main}}\n"
        "plugins:\n  - name: p\n    source: s\n    description: d\n"
        "    skills: [skills/craft/absent]\n"
    )
    with pytest.raises(ValueError, match="match no skill"):
        build_marketplace(
            load_bundle(bundle), pin=False, workspace=Workspace(cache=tmp_path / "cache")
        )


def test_a_remote_only_source_reaches_the_catalog(tmp_path):
    from trove.catalog import build_catalog
    from trove.fetch import Workspace

    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        f"name: t\nsources:\n  s: {{url: {_remote_repo(tmp_path)}, ref: main}}\n"
        "plugins:\n  - {name: p, source: s}\n"
    )
    catalog = build_catalog(
        load_bundle(bundle), workspace=Workspace(cache=tmp_path / "cache")
    )
    assert [s["name"] for s in catalog["skills"]] == ["tidy"]
    assert catalog["plugins"][0]["description"] == "From the source"


def test_a_qualified_annotated_tag_peels_to_its_commit(tmp_path):
    from trove.fetch import resolve_sha

    work = _repo_with_ambiguous_refs(tmp_path)
    commit = subprocess.run(
        ["git", "rev-parse", "main"], cwd=work, capture_output=True, text=True, check=True
    ).stdout.strip()
    for ref in ("refs/tags/release", "refs/heads/release"):
        assert resolve_sha(Source(key="s", url=str(work), ref=ref)) == commit


# --- resolving a skill body ---


def _source(tmp_path: Path, **kwargs) -> Source:
    return Source(key=kwargs.pop("key", "s"), **kwargs)


def test_a_pinned_github_source_resolves_to_raw_git_at_that_commit():
    from trove.catalog import body_base

    source = Source(key="s", repo="o/s")
    assert body_base("s", source, "abc123") == (
        "https://raw.githubusercontent.com/o/s/abc123/"
    )


def test_a_subdir_source_carries_its_prefix_into_the_body_base():
    from trove.catalog import body_base

    source = Source(key="s", repo="o/s", path="tooling/plugin")
    assert body_base("s", source, "abc123").endswith("/abc123/tooling/plugin/")


def test_an_unpinned_source_falls_back_to_the_serve_route(tmp_path):
    from trove.catalog import body_base

    assert body_base("s", Source(key="s", repo="o/s", local=tmp_path), None) == "body/s/"


def test_a_source_git_does_not_serve_publicly_falls_back_to_the_serve_route(tmp_path):
    from trove.catalog import body_base

    source = Source(key="s", url="https://git.example.com/o/s.git", local=tmp_path)
    assert body_base("s", source, "abc123") == "body/s/"


def test_a_source_with_nothing_on_disk_and_no_pin_resolves_nowhere():
    from trove.catalog import body_base

    assert body_base("s", Source(key="s", repo="o/s"), None) is None


def test_a_local_only_source_carries_both_its_route_and_its_path(tmp_path):
    from trove.catalog import source_entry

    entry = source_entry("s", Source(key="s", local=tmp_path), None)
    assert entry == {"body": "body/s/", "local": str(tmp_path)}


def test_a_published_source_keeps_its_local_path_out_of_the_catalog(tmp_path):
    from trove.catalog import source_entry

    entry = source_entry("s", Source(key="s", repo="o/s", local=tmp_path), "abc123")
    assert "local" not in entry
    assert entry["body"].startswith("https://raw.githubusercontent.com/")


# --- serving a body from the checkout on disk ---


def _served_body(tmp_path: Path):
    checkout = tmp_path / "checkout"
    skill = checkout / "skills" / "craft" / "tidy"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: tidy\ndescription: d\n---\nbody\n")
    (skill / "references").mkdir()
    (skill / "references" / "notes.md").write_text("# notes\n")
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<p>catalog</p>")
    (tmp_path / "secret").write_text("do not serve me")
    return site, checkout


def test_serve_answers_a_body_from_the_sources_checkout(tmp_path):
    from urllib.request import urlopen

    site, checkout = _served_body(tmp_path)
    server = _serve(site, {"s": checkout})
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/body/s/skills/craft/tidy/SKILL.md"
        with urlopen(url) as response:
            assert b"name: tidy" in response.read()
    finally:
        server.shutdown()


def test_serve_answers_a_bundled_file_from_the_same_route(tmp_path):
    from urllib.request import urlopen

    site, checkout = _served_body(tmp_path)
    server = _serve(site, {"s": checkout})
    try:
        port = server.server_address[1]
        url = f"http://127.0.0.1:{port}/body/s/skills/craft/tidy/references/notes.md"
        with urlopen(url) as response:
            assert response.read() == b"# notes\n"
    finally:
        server.shutdown()


@pytest.mark.parametrize(
    "attack",
    [
        "/body/s/../secret",
        "/body/s/../../secret",
        "/body/s/%2e%2e/secret",
        "/body/s/skills/../../secret",
    ],
)
def test_serve_refuses_to_climb_out_of_a_sources_checkout(tmp_path, attack):
    from urllib.error import HTTPError
    from urllib.request import urlopen

    site, checkout = _served_body(tmp_path)
    server = _serve(site, {"s": checkout})
    try:
        port = server.server_address[1]
        with pytest.raises(HTTPError) as caught:
            urlopen(f"http://127.0.0.1:{port}{attack}")
        assert caught.value.code == 404
    finally:
        server.shutdown()


def test_serve_does_not_invent_a_route_for_an_unknown_source(tmp_path):
    from urllib.error import HTTPError
    from urllib.request import urlopen

    site, checkout = _served_body(tmp_path)
    server = _serve(site, {"s": checkout})
    try:
        port = server.server_address[1]
        with pytest.raises(HTTPError) as caught:
            urlopen(f"http://127.0.0.1:{port}/body/other/skills/craft/tidy/SKILL.md")
        assert caught.value.code == 404
    finally:
        server.shutdown()


def test_body_roots_names_every_checkout_that_is_on_disk(tmp_path):
    from trove.cli import body_roots

    checkout = tmp_path / "repo"
    (checkout / "skills").mkdir(parents=True)
    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        f"name: t\nsources:\n"
        f"  here: {{repo: o/s, local: {checkout}}}\n"
        f"  gone: {{repo: o/g}}\n"
        "plugins:\n  - {name: p, source: here, description: d}\n"
    )
    assert body_roots(bundle) == {"here": checkout}


def test_body_roots_is_empty_when_there_is_no_bundle_to_read(tmp_path):
    from trove.cli import body_roots

    assert body_roots(tmp_path / "absent.yaml") == {}


def test_a_source_the_catalog_cannot_reach_costs_a_pin_not_the_run(tmp_path):
    from trove.catalog import build_catalog
    from trove.fetch import Workspace

    repo = tmp_path / "repo" / "skills" / "craft" / "tidy"
    repo.mkdir(parents=True)
    (repo / "SKILL.md").write_text("---\nname: tidy\ndescription: d\n---\nbody\n")
    bundle = tmp_path / "b.yaml"
    bundle.write_text(
        f"name: t\nsources:\n  s: {{url: {tmp_path / 'nowhere.git'}, local: {tmp_path / 'repo'}}}\n"
        "plugins:\n  - {name: p, source: s, description: d}\n"
    )
    workspace = Workspace(cache=tmp_path / "cache")
    catalog = build_catalog(load_bundle(bundle), workspace=workspace)

    assert [s["name"] for s in catalog["skills"]] == ["tidy"]
    assert catalog["sources"]["s"]["body"] == "body/s/"
    assert any("cannot reach" in note for note in workspace.notes)
