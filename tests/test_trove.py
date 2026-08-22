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
