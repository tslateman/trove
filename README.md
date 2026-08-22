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
uv sync --all-groups
```

## Use

```bash
uv run trove scan            # index skills, report token cost per source
uv run trove build           # bundle.yaml -> marketplace.json, sha-pinned
uv run trove catalog         # catalog.json + the static site
uv run trove serve           # browse at http://127.0.0.1:8787
uv run trove calibrate skills skills@local   # check estimates against Claude Code
```

## The bundle

One file describes sources and the plugins composed from them.

```yaml
name: tslateman
sources:
  skills:
    repo: tslateman/skills
    local: ~/dev/skills # optional, enables scanning before a remote exists

plugins:
  - name: review-kit
    source: skills
    description: Language review skills only
    tags: [review, linting]
    skills: # cherry-pick — no fork needed
      - skills/review/python-review
      - skills/review/go-review

renames:
  duet: skills # deprecate without breaking installs
```

`trove build` resolves each source to a commit sha via `git ls-remote` and emits
a `marketplace.json` a teammate consumes in two commands:

```
claude plugin marketplace add <your-registry>
claude plugin install review-kit@tslateman
```

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

## Frontmatter

SKILL.md frontmatter is parsed line-wise, not as strict YAML, because Claude
Code tolerates unquoted `": "` inside a description and real skills rely on it.
Skills whose frontmatter fails a strict YAML parse are flagged `lint` in the UI
so the registry can nudge without breaking.

## Known limits

- The catalog indexes skills only. Plugins shipping agents, commands, or hooks
  report zero skills.
- `local:` paths are required for scanning. A source with only a remote is
  buildable but not catalogable.
- Eval scores and invocation counts are not wired up yet.

## Development

```bash
uv run pytest
```

## License

MIT
