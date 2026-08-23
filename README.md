# Trove

A registry for Claude Code skills. Author skills in whatever repo owns them,
compose them into bundles, publish a marketplace, and browse the catalog with
token cost on every card.

Skills are cheap to write and expensive to keep. Every installed skill spends
context in every session before it fires. Trove makes that price visible at the
moment you decide to install.

## Why

Claude Code already distributes plugins well: `marketplace.json` carries
categories, tags, version and sha pinning, a `renames` map for deprecation, and
a `skills[]` field that cherry-picks individual skill directories out of a repo.
What it lacks is the layer that decides what belongs in a session.

Trove is that layer. It generates the marketplace instead of hand-editing it,
and it prices every skill so a bundle can be held to a budget.

## Install

```bash
just setup
```

`just verify` and `just shots` additionally need a Chromium build:

```bash
uv run --with playwright playwright install chromium
```

`just fmt` shells out to `prettier`, which is not managed by this project.

## Use

```bash
just scan          # index skills, report token cost per source
just build         # bundle.yaml -> marketplace.json, sha-pinned
just catalog       # catalog.json + the static site
just serve         # browse at http://127.0.0.1:8787
just dist          # build and catalog together, ready to publish

just drift         # bundle fields that disagree with their source plugin.json
just sync-local-check  # preview local-marketplace updates
just sync-local        # apply them
just orphans       # skills no plugin ships
just lint-skills   # skills whose frontmatter fails a strict YAML parse
just calibrate skills skills@local   # check estimates against Claude Code
```

`just --list` shows the rest. Every recipe takes its bundle from the `bundle`
variable, so `just --set bundle bundles/team.yaml catalog` targets another one.

Three bundles ship with the repo: `tslateman.yaml` is the real registry,
`example.yaml` is a commented starter to copy, and `demo.yaml` points at a
fixture repo under `tests/fixtures` so CI and `just verify` have a hermetic
target.

## The bundle

One file describes sources and the plugins composed from them.

```yaml
name: tslateman
sources:
  skills:
    repo: tslateman/skills
    ref: v0.5.0 # optional; resolved to a commit sha at build time
    local: ~/dev/skills # optional, enables scanning before a remote exists

plugins:
  # description, version, homepage and displayName are inherited from the
  # source's .claude-plugin/plugin.json when the bundle omits them.
  - name: skills
    source: skills
    category: development
    tags: [review, craft]

  - name: review-kit
    source: skills
    description: Language review skills only # a curated subset earns its own
    tags: [review, linting]
    skills: # cherry-pick — no fork needed
      - skills/review/python-review
      - skills/review/go-review
      - skills/draw/ # a trailing slash takes the whole subtree

renames:
  duet: skills # deprecate without breaking installs
```

`local` points at the plugin root — the directory a `skills:` path is relative
to. A relative `local` resolves against the bundle file, not the working
directory. It is optional: a source with only a remote builds fine but reports
no skills in the catalog.

A plugin inherits `description`, `version`, `homepage`, and `displayName` from
its source's `plugin.json`, so the repo that owns a plugin owns its metadata and
a version bump reaches the registry by itself. Declare a field in the bundle
only to override it deliberately — a curated subset needs its own description.
`trove drift` reports any restated field that disagrees with its source, and
`just check` runs it. A source with no local checkout cannot inherit, so the
bundle must declare a description for it or the build fails.

`ref` accepts a tag or a branch. Build resolves it to a commit sha, preferring
an annotated tag's target over the tag object, and refuses to guess when a tag
and a branch share the name.

`trove build` resolves each source to a commit sha via `git ls-remote` and emits
a `marketplace.json` a teammate consumes in two commands:

```bash
claude plugin marketplace add <your-registry>
claude plugin install review-kit@tslateman
```

## Editing a plugin's description

Edit `.claude-plugin/plugin.json` in the repo that owns the plugin — nowhere
else. `trove build` and `trove catalog` read it, so a description or version
change reaches the registry with no bundle edit.

Claude Code's local marketplace keeps its own copy, which drifts silently.
`trove sync-local` rewrites the entries your bundle names and leaves every
other entry byte-identical. It previews with `--dry-run`, writes a `.bak`
first, and refuses to touch a plugin whose source has no local checkout, since
there is no `plugin.json` to sync from and the bundle value would be a guess.

## Token estimates

`scan` and `catalog` report two numbers per skill:

| Number    | Meaning                                           |
| --------- | ------------------------------------------------- |
| always-on | name + description, paid in every session         |
| on invoke | the SKILL.md body, paid each time the skill fires |

Constants were fit by least squares against `claude plugin details` over 55
skills. `trove calibrate` re-runs that comparison and prints the error.

| Estimate  | Mean absolute error |
| --------- | ------------------- |
| always-on | 2.4%                |
| on invoke | 1.0%                |

Re-run `calibrate` when Claude Code changes how it counts; the constants live in
`src/trove/models.py`.

## What the scanner refuses to count

- Anything under a dot-directory. A repo's own `.claude/skills/` holds skills it
  _consumes_, not skills it _ships_.
- Skills no plugin selects. These are reported as `orphans` in `catalog.json`
  rather than silently catalogued.

Two shapes fail the build instead of shipping quietly: a `local` path that is
declared but missing, and a `skills:` entry that matches no scanned skill. Both
otherwise produce a manifest pointing at nothing.

## Frontmatter

Frontmatter is read strictly first. When the block is valid YAML, its `name` and
`description` win, so quoted escapes decode the way the author meant. When the
strict parse fails, a line-wise parser takes over, because Claude Code tolerates
an unquoted `": "` inside a description and real skills rely on it. Either way
the skill is indexed; one that fails the strict parse is flagged `lint` in the
UI so the registry can nudge without breaking.

## Known limits

- The catalog indexes skills only. Plugins shipping agents, commands, or hooks
  report zero skills.
- `local:` paths are required for scanning. A source with only a remote is
  buildable but not catalogable.
- Eval scores and invocation counts are not wired up yet.
- The stack picker keys selections by skill name, so two sources shipping the
  same skill name collapse into one entry.

## Development

```bash
just test      # unit tests
just verify    # drive the built catalog headless, assert it renders
just check     # formatting, tests, and the UI check
just shots     # catalog screenshots in both themes
```

`just verify` serves the site and drives it in headless Chromium. It fails if
the card count drifts from the catalog, a console error fires, the budget
readout goes missing, the generated bundle omits a picked skill, the page
scrolls sideways at 390px, both themes paint the same background, or a hostile
skill name survives into the DOM as a live element.

CI runs the same suite plus a wheel build that asserts the catalog page is
packaged (`.github/workflows/check.yml`).

## License

MIT
