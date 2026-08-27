# CLI reference

```
trove [--bundle BUNDLE] [--out OUT] [--cache CACHE] [--offline] <command>
```

Every `just` recipe wraps one of these. `just --list` shows the recipes; this
page documents what they call.

## Global options

| Option          | Default                  | Effect                                                |
| --------------- | ------------------------ | ----------------------------------------------------- |
| `--bundle PATH` | `bundles/local.yaml`     | The bundle to read                                    |
| `--out PATH`    | `out`                    | Where `build`, `catalog`, and `serve` write and read  |
| `--cache PATH`  | `~/.cache/trove/sources` | Where fetched sources are checked out                 |
| `--offline`     | off                      | Never fetch; index only sources with a local checkout |

`XDG_CACHE_HOME` moves the default cache. `--cache` overrides both.

Recipes take their bundle from the `bundle` variable, so
`just --set bundle bundles/team.yaml catalog` targets another one.

## scan

Index every source and report token cost.

```bash
trove scan [-v|--verbose]
```

```
skills: 56 skills, ~7,329 tok always-on

total always-on: ~7,329 tok
```

`--verbose` lists each skill under a header row: what it charges every session,
what its body charges when it fires, the files it bundles with the ceiling they
would add if all were read, and its path. Sources with nothing to index report
on stderr and do not stop the run.

Recipes: `just scan`, `just scan-all`.

## build

Emit `marketplace.json`, resolving each source to a commit sha.

```bash
trove build [--no-pin]
```

Writes `<out>/.claude-plugin/marketplace.json`. This is the file
`claude plugin marketplace add` consumes.

`--no-pin` skips sha resolution and implies `--offline`, so the command reaches
the network for nothing. A remote-only source cannot inherit a description under
`--no-pin`, so the bundle must declare one.

Build fails rather than shipping a manifest that points at nothing. Two shapes
stop it: a `local` path that is declared but missing, and a `skills:` entry that
matches no scanned skill.

Recipes: `just build`, `just build-offline`.

## catalog

Emit `catalog.json` and copy the static site next to it.

```bash
trove catalog
```

```
wrote out/catalog.json: 56 skills, ~7,329 tok always-on
```

`catalog.json` carries every skill with its token costs, category, tags, owning
plugins, and lint state, plus the orphans no plugin ships. A skill name that
more than one source ships is a twin; `just twins` lists each pair with the
always-on price per side, and the site's Shipped twice filter shows the same
set.

Recipes: `just catalog`, `just catalog-offline`, `just dist`, `just orphans`,
`just twins`.

## serve

Serve the built site on localhost.

```bash
trove serve [--port PORT]
```

Defaults to port 8787. The handler sends no-cache headers and ignores
conditional requests, so a rebuild shows up on reload. It refuses a port that is
already serving.

`serve` also answers `/body/<source>/<path>` from that source's checkout on
disk, which is how the `skills/trove` reader reads a skill whose source git does
not serve publicly. It reads the routes from `--bundle`, so a source needs a
`local:` path to get one, and a bundle it cannot read serves the site alone. A
request cannot climb out of the checkout it names.

```bash
curl http://127.0.0.1:8787/body/drafts/skills/craft/tidy/SKILL.md
```

Recipes: `just serve`, `just open`, `just stop`.

## lint

Report skills that discovery cannot use.

```bash
trove lint
```

```
skills/skills/writing/prose
  yaml: frontmatter fails a strict YAML parse
  trigger: the description never says when to use the skill

1 skill(s) flagged
```

Exits 1 when anything is flagged, so it gates in CI. It is not part of
`just check`, since a finding is about a skill in someone else's repo rather
than about this build. The rules are listed in the
[README](../README.md#what-the-linter-checks).

Recipe: `just lint`.

## drift

Report bundle fields that disagree with their source `plugin.json`.

```bash
trove drift
```

Exits 1 when any restated field disagrees, so `just check` fails on drift. It
compares `description` and `version`, and it exempts a curated plugin's own
description, since a curated subset needs its own wording.

Recipe: `just drift`.

## promote

Copy a skill from your personal directory into a source's local checkout, lint
the copy, and print the commands that follow.

```bash
trove promote <name> --source <key> [--from <dir>] [--into <subdir>]
```

`<name>` is a directory under `~/.claude/skills/`; `--from` names another
origin. The copy lands under `skills/` when the checkout keeps one, else at the
root, and `--into` overrides that. Caches (`__pycache__`, `.ruff_cache`) stay
behind. The command refuses a name the source already ships, and exits 1 when
the copy carries a lint finding. See [Share a skill](sharing-a-skill.md) for
the whole path from one machine to the team.

Recipe: `just promote <name> <source>`.

## sync-local

Update Claude Code's local marketplace from each source `plugin.json`.

```bash
trove sync-local [--dry-run] [--marketplace PATH]
```

Claude Code keeps its own copy of plugin metadata, which drifts silently.
`sync-local` rewrites only the entries your bundle names and leaves every other
entry byte-identical. It writes a `.bak` first, and it skips a plugin whose
source ships no `plugin.json`.

Recipes: `just sync-local-check`, `just sync-local`.

## calibrate

Compare Trove's estimates against Claude Code's own count.

```bash
trove calibrate <source> <plugin>
```

```bash
just calibrate skills skills@local
```

Runs `claude plugin details <plugin>`, matches component names against the
scanned source, and prints the per-skill delta with a mean absolute error. Run
it when Claude Code changes how it counts. The fitted constants live in
`src/trove/models.py`.

## cache

Report or empty the fetched-source cache.

```bash
trove cache [--clear]
```

```
/Users/you/.cache/trove/sources: 5 checkout(s), 1.9 MiB
  https-github.com-your-org-monorepo.git/eb4f0760911698f76a8f825e0bf2fb202c53f7d0
  https-github.com-your-org-skills.git/e28569421862eb10f34bbe2db5fe3f4d7e4b5e7b
```

Checkouts are keyed by commit sha, so a warm cache is safe to keep and cheap to
discard.

Recipes: `just cache`, `just cache-clear`.

## Development recipes

| Recipe        | What it does                                          |
| ------------- | ----------------------------------------------------- |
| `just test`   | The unit tests                                        |
| `just verify` | Serves the catalog and drives it in headless Chromium |
| `just check`  | Formatting, tests, drift, and the UI check            |
| `just shots`  | Catalog screenshots in both themes                    |
| `just demo`   | Records an mp4 walkthrough of the catalog             |
| `just fmt`    | Formats markdown with `prettier`                      |
| `just clean`  | Removes build output                                  |

`just verify` and `just shots` need a Chromium build:

```bash
uv run --with playwright playwright install chromium
```

`just demo` needs `shot-scraper`, which brings its own Chromium:

```bash
uv tool install shot-scraper && shot-scraper install
```

It writes `out/demo.mp4` by default; pass a path to write elsewhere.
