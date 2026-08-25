---
name: trove
description: Read Claude Code skills from a Trove catalog without installing them — list what exists, find one for a task, read its instructions at a pinned commit, and check what it costs in context first. Use when asked what skills are available, which skill fits a job, what a skill does, or whether a skill is worth installing.
---

# Trove

A Trove catalog indexes skills across many repos, prices each one in tokens, and
pins every source to a commit. Reading from it costs one skill's context instead
of sixty.

## The disclosure contract

Three levels, each dearer than the last. Never skip down a level, and never
fetch ahead.

1. **Descriptions.** `catalog.json` holds every skill's name, description, and
   price. Read this to _choose_. When the question is which skill fits, the
   answer is here and you are done.
2. **Body.** One skill's `SKILL.md`, fetched at the pinned sha, after choosing.
   Fetch one. Stop unless the body names a file.
3. **Files.** `references/`, `scripts/`, `assets/`, one path at a time, only
   when the body sends you to that path.

Binding at every level:

- Compare descriptions, never bodies. Two bodies fetched to pick one wastes the
  loser in full.
- Fetch a named path, never a listing. A file you left unopened costs nothing.
- `tokensOnInvoke` is the price of level 2 and it sits beside the description.
  Read the price before paying it.
- Report the skill you found. Reciting its body back is the same context spent
  twice.

## Setup

```bash
CATALOG=${TROVE_CATALOG:-out/catalog.json}
catalog() { case "$CATALOG" in http*) curl -sf "$CATALOG";; *) cat "$CATALOG";; esac; }
```

## Level 1 — list

Search names and descriptions, cheapest first:

```bash
catalog | jq -r --arg q 'refactor' '
  .skills[]
  | select((.name + " " + .description) | test($q; "i"))
  | "\(.name)\t\(.tokensOnInvoke) tok\t\(.description)"' | sort -t$'\t' -k2 -n
```

What the registry holds, by plugin:

```bash
catalog | jq -r '.plugins[] | "\(.name)\t\(.skills) skills\t\(.description)"'
catalog | jq -r '.totals | "\(.skills) skills, \(.alwaysOn) tok always-on"'
```

The `tokensAlwaysOn` field is what a skill charges every session whether or not
it fires. `tokensOnInvoke` is what its body charges when it does. Claude Code
caps skill metadata at `skillListingBudgetFraction` of the context window, 1% by
default, so an always-on total is a budget, not a curiosity.

## Level 2 — get one body

Resolve the raw URL at the pinned sha, then fetch it:

```bash
url() { catalog | jq -r --arg n "$1" --arg f "${2:-SKILL.md}" '
  . as $c
  | $c.skills[] | select(.name == $n)
  | $c.sources[.source] as $src
  | (($src.path // "") | if . == "" then "" else . + "/" end) as $prefix
  | ($src.url | sub("^https://github.com/"; "") | sub("\\.git$"; "")) as $repo
  | "https://raw.githubusercontent.com/\($repo)/\($src.sha)/\($prefix)\(.path)/\($f)"'; }

curl -sf "$(url zoom-out)"
```

Read the body and follow it as instructions for the task. A source whose `url`
is not GitHub resolves the same way from a clone at `sha`.

## Level 3 — get one bundled file

Only when the body referenced it, and only that path:

```bash
curl -sf "$(url research references/patterns.md)"
```

## Installing instead

When a skill earns a place in every session, install its plugin rather than
reading it each time. The catalog names the owning plugin and the price the
install adds to the always-on budget:

```bash
catalog | jq -r --arg n 'zoom-out' '.skills[] | select(.name==$n)
  | "\(.plugins | join(", "))\t+\(.tokensAlwaysOn) tok always-on"'
```
