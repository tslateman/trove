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


def _serve(directory: Path):
    from functools import partial
    from http.server import ThreadingHTTPServer
    import threading
    from trove.cli import PreviewHandler

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(PreviewHandler, directory=str(directory)))
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
