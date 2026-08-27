# Getting started

Trove turns one bundle file into a Claude Code marketplace, and prices every
skill in it before you install anything.

This page takes you from an empty directory to a published registry a teammate
can install in two commands.

## Prerequisites

- Python 3.11 or later, and [uv](https://docs.astral.sh/uv/)
- `git`, to resolve and fetch sources
- [`just`](https://just.systems), which every example below uses
- Claude Code, to install what you publish

```bash
git clone https://github.com/tslateman/trove
cd trove
just setup
```

## See it work first

The repo ships a hermetic fixture registry. Run it before you write anything:

```bash
just --set bundle bundles/demo.yaml scan
```

```
demo: 3 skills, ~118 tok always-on

total always-on: ~118 tok
```

Three skills cost 118 tokens of context in every session, whether or not they
ever fire.

## Step 1: Describe your registry

A bundle names the repos you draw from and the plugins you compose out of them.
Twelve lines is enough:

```yaml
# bundles/local.yaml
name: mine
description: My skills, priced before I install them
owner:
  name: Your Name

sources:
  skills:
    repo: your-org/skills

plugins:
  - name: skills
    source: skills
    category: development
```

`sources` are the repos. `plugins` are what a teammate installs. A plugin with
no `skills:` list ships everything its source holds.

You do not need a checkout. Trove fetches a source it has not seen, so the same
bundle builds on your laptop and in CI. See [Fetching](../README.md#fetching).

Write it to `bundles/local.yaml`. Every recipe reads that path by default, and
`.gitignore` keeps it out of the repo, so your registry stays yours:

```bash
cp bundles/example.yaml bundles/local.yaml
```

`example.yaml` is a commented starter covering whole-repo sources, monorepo
subdirectories, cherry-picked subsets, and renames.

## Step 2: Price the skills

```bash
just scan
```

```
skills: 56 skills, ~7,329 tok always-on

total always-on: ~7,329 tok
```

Add `--verbose` for the per-skill breakdown:

```bash
just scan-all
```

```
skills: 56 skills, ~7,329 tok always-on
  create-verification-skill            102    2130  skills/craft/create-verification-skill
  deprecate                            174    1731  skills/craft/deprecate
  domain-model                         201    1666  skills/craft/domain-model
  improve-codebase-architecture         87    1991  skills/craft/improve-codebase-architecture
```

The two columns are the two prices a skill charges:

| Column    | What it costs                                                |
| --------- | ------------------------------------------------------------ |
| always-on | name and description, paid in every session                  |
| on invoke | the `SKILL.md` body, paid each time the skill actually fires |

Install decisions turn on the first column. A skill that never fires still
spends it. See [Token estimates](../README.md#token-estimates) for how the
numbers are fitted and how to re-check them.

## Step 3: Browse the catalog

```bash
just serve
```

Open http://127.0.0.1:8787. Search by name, description, or tag. Pick skills to
build a stack, then copy the generated bundle YAML.

Press `just stop` when you are done.

## Step 4: Pin and publish

```bash
just build
```

```
wrote out/.claude-plugin/marketplace.json (1 plugins)
```

Every source resolves to a commit sha:

```json
{
  "source": "url",
  "url": "https://github.com/your-org/skills.git",
  "sha": "e28569421862eb10f34bbe2db5fe3f4d7e4b5e7b"
}
```

The sha is what makes an install reproducible. A teammate who installs today and
one who installs next month get the same bytes until you rebuild.

`just dist` runs `build` and `catalog` together and leaves `out/` ready to
publish. Serve that directory from anywhere: GitHub Pages, an object store, or
a static host.

This repo ships the deploy step as
[`.github/workflows/publish.yml`](../.github/workflows/publish.yml): every push
to main rebuilds `out/` and deploys it to GitHub Pages, reading
`bundles/registry.yaml` when one is committed and falling back to the demo
bundle until then. To reuse it, copy the workflow, point it at your bundle, and
enable Pages under Settings → Pages → Source: GitHub Actions.

## Step 5: Install

```bash
claude plugin marketplace add https://your-registry.example.com
claude plugin install skills@mine
```

`claude plugin details skills@mine` reports what Claude Code thinks the plugin
costs. Compare it against Trove's estimate with
[`trove calibrate`](cli.md#calibrate).

## Step 6: Curate a subset

Cherry-pick without forking:

```yaml
plugins:
  - name: review-kit
    source: skills
    description: Language review skills only
    tags: [review, linting]
    skills:
      - skills/review/python-review
      - skills/review/go-review
      - skills/draw/ # a trailing slash takes the whole subtree
```

Trove verifies each path against the source at build time. A path that matches
no skill fails the build rather than shipping a manifest that points at nothing.

## Keep the metadata honest

A plugin inherits `description`, `version`, `homepage`, and `displayName` from
its source's `.claude-plugin/plugin.json`. Edit the description in the repo that
owns the plugin, and the change reaches your registry with no bundle edit.

Declare a field in the bundle only when you mean to override it. Two commands
keep that honest:

```bash
just drift             # bundle fields that disagree with their source
just sync-local-check  # what Claude Code's local marketplace has drifted to
```

## Next

- [CLI reference](cli.md) for every command and flag
- [Troubleshooting](troubleshooting.md) for what the errors mean
- [The bundle](../README.md#the-bundle) for the full file format
- [ROADMAP](../ROADMAP.md) for what Trove does not do yet
