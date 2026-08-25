# Troubleshooting

Every message below is verbatim. Each one names a bundle mistake rather than a
Trove bug, so the fix is in your bundle or your environment.

## The build stops

### `bundle bundles/local.yaml does not exist. Copy bundles/example.yaml to it, or name another with --bundle`

Every recipe reads `bundles/local.yaml` by default, and that file is
gitignored, so a fresh clone has none. Make one:

```bash
cp bundles/example.yaml bundles/local.yaml
```

Then point its sources at your repos. To keep a bundle elsewhere, pass
`--bundle path/to/it.yaml`, or `just --set bundle path/to/it.yaml <recipe>`.

### `plugin 'p' names unknown source 'nope'`

A plugin's `source:` does not match any key under `sources:`. The key is the
name on the left of the colon, not the repo:

```yaml
sources:
  skills: # <- this is the key
    repo: your-org/skills

plugins:
  - name: p
    source: skills # <- must match
```

A plugin with no `source:` defaults to its own `name`.

### `plugin 'p' curates paths that match no skill in 's': skills/review/nope`

A `skills:` entry points at a directory that holds no `SKILL.md`. Paths are
relative to the source root, so they usually start with `skills/`.

List what the source actually ships:

```bash
uv run trove --bundle bundles/mine.yaml scan --verbose
```

The right-hand column is the exact string a `skills:` entry needs. A trailing
slash takes a whole subtree.

### `plugin 'skills' has no description: source 'skills' has no plugin.json to inherit one from, so the bundle must declare it`

A plugin publishes a description or it does not build. Trove reads one from the
source's `.claude-plugin/plugin.json`, which it cannot do when fetching is off.

Either drop `--offline` and `--no-pin` so the source can be fetched, or declare
the description in the bundle:

```yaml
plugins:
  - name: skills
    source: skills
    description: What a teammate is installing
```

### `source 's': local path /tmp/nope does not exist. Create the checkout, remove `local:` to fetch the remote, or drop --offline`

The bundle declares a `local:` checkout that is not there. The message lists the
three fixes. Removing `local:` is usually right: the source is then fetched, and
the bundle stops depending on one machine's directory layout.

A relative `local:` resolves against the bundle file, not your working
directory.

Outside `--offline`, a missing `local:` is not fatal. Trove prints which source
fell back and to which remote, then fetches it.

### `cannot reach https://github.com/o/repo.git (ref 'HEAD'): ERROR: Repository not found.`

Trove could not resolve the source. Check the three usual causes:

- A typo in `repo:`. The value is `owner/name`, with no `.git` and no URL.
- A private repo. Trove runs git with `GIT_TERMINAL_PROMPT=0` so it fails fast
  instead of hanging on a password prompt. Configure git credentials or an SSH
  remote with `url:` instead of `repo:`.
- No network. Use `--offline` to work from local checkouts only.

### `https://github.com/o/s.git: ref 'release' matches both refs/tags/release and refs/heads/release`

A tag and a branch share a name, so `ref:` is ambiguous. Trove refuses to guess.
Qualify it:

```yaml
ref: refs/tags/release # or refs/heads/release
```

## Nothing gets indexed

### `s: no local checkout and fetching is off`

`--offline` is on and the source has no `local:` path. Drop `--offline`, or add
a checkout.

### `s: checkout has no shipped skills`

The source resolved but holds no `SKILL.md` that Trove will count. Three
reasons, in order of likelihood:

1. **The plugin ships agents, commands, or hooks rather than skills.** The
   catalog indexes skills only, so these report zero. This is a known gap.
2. **The skills live under a dot-directory.** A repo's own `.claude/skills/`
   holds skills it consumes, not skills it ships, so Trove skips it.
3. **`local:` points at the wrong level.** It must point at the plugin root, the
   directory a `skills:` path is relative to, not at the repo's `skills/`
   directory.

### A skill is missing from the catalog

Check the orphans. A skill that no plugin selects is reported rather than
silently catalogued:

```bash
just orphans
```

A curated plugin ships only the paths it lists, so anything outside that list is
an orphan until some plugin claims it.

## The catalog looks wrong

### A skill is flagged `yaml`

Its frontmatter fails a strict YAML parse. The usual cause is an unquoted `": "`
inside a description:

```yaml
description: Apply Strunk's rules to prose: docs, commits, UI text.
```

Claude Code tolerates this, so Trove still indexes the skill using a line-wise
parser. The flag is a nudge, not a failure. Quote the value to clear it:

```yaml
description: "Apply Strunk's rules to prose: docs, commits, UI text."
```

List every flagged skill:

```bash
just lint
```

### A skill is flagged `trigger`

Its description says what the skill does and never says when to reach for it.
Claude Code chooses from the description alone, so a skill without a trigger
clause is one it will not fire.

```yaml
description: Reflect on recent work and surface what comes next
```

Add the case that should invoke it:

```yaml
description: Reflect on recent work and surface what comes next.
  Use when the user asks for a retro or a debrief.
```

### Two sources ship the same skill name

The stack picker keys selections by skill name, so the entries collapse into
one. This is a known gap tracked in the [ROADMAP](../ROADMAP.md).

### An estimate disagrees with Claude Code

Check it rather than trust it:

```bash
just calibrate skills skills@local
```

The constants were fitted by least squares over 55 skills, with a mean absolute
error of 2.4% on always-on and 1.0% on invoke. A larger error means Claude Code
changed how it counts. The constants live in `src/trove/models.py`.

Note that the on-invoke number covers `SKILL.md` only. A skill carrying
`references/` and `scripts/` costs more than the catalog shows.

## Commands fail to run

### `<out> has no index.html — run \`trove catalog\` first`

`serve` needs a built site. Run `just catalog`, or `just serve`, which builds
first.

### `cannot bind 127.0.0.1:8787 (Address already in use)`

A preview server is already there.

```bash
just stop                    # stop every trove server this project started
just --set port 8788 serve   # or use another port
```

### `just verify` crashes Chromium

`verify` and `shots` need a Chromium build that Playwright manages separately:

```bash
uv run --with playwright playwright install chromium
```

A `SIGSEGV` from an installed Chromium is a local Playwright problem rather than
a catalog failure. Confirm by running `just test`, which needs no browser.

### `just fmt` cannot find prettier

`fmt` shells out to `prettier`, which this project does not manage. Install it
with your package manager of choice, or skip `fmt` and run `just test`.
