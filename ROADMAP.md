# Trove Roadmap

Intent, not schedule. For status, read git.

## Quality signals

Trove prices a skill in tokens so the cost is visible at install time. Cost is
half the decision. The other half is whether the skill works, and today the
catalog says nothing about it — `eval_score` and `invocations` are placeholders
the UI never fills.

- [ ] **Eval scores per skill.** A skill carries a graded result from running
      against its own test prompts. The card shows it beside the token cost, so
      a browser weighs one against the other instead of guessing.
- [ ] **Invocation counts.** How often a skill actually fires in real sessions.
      An installed skill spends context whether or not it ever triggers, so the
      count answers the only question that retires one.
- [ ] **Rank the catalog on evidence.** Once both signals exist, sort and filter
      on them. Alphabetical order is a placeholder for having nothing to say.

The blocker is a scoring source. Trove indexes and serves; it does not run
skills. Either an external runner writes results Trove reads, or Trove grows a
runner. Settle that before designing the schema.

## Security and governance

Nothing here exists today. Trove reads frontmatter, counts tokens, and pins a
sha; it never asks what a skill is allowed to do. A bundle can install a skill
that shells out, reads credentials, or reaches the network, and the catalog card
looks the same as one that rewrites a paragraph.

- [ ] **Static risk scan.** Parse each skill for what it reaches for — `Bash`
      invocations, network calls, credential paths, `allowed-tools` breadth —
      and surface a risk signal on the card next to the token cost.
- [ ] **Policy gating at build.** Let a bundle declare what it refuses to ship,
      and fail `just build` when a source violates it. Sha-pinning already makes
      a bundle reproducible; a policy makes it defensible.
- [ ] **Provenance in the catalog.** Show which source and commit a skill came
      from, and flag when a pinned sha moves under a bundle.
- [ ] **Install audit trail.** Record what a bundle installed, when, and at
      which sha, so a question asked after the fact has an answer.

Scope question to settle first: whether Trove enforces policy or only reports.
Reporting is honest and cheap. Enforcement makes Trove a gate, which is a
different product with a different failure mode.

## Duplication and staleness

Partly covered. `just drift` catches bundle fields that disagree with their
source `plugin.json`, and `just orphans` finds skills no plugin ships. Neither
sees two sources shipping the same capability, and nothing reports age.

- [ ] **Near-duplicate detection.** Compare skills across sources by name,
      description, and body, and report overlap. Token cost makes the redundancy
      quantifiable once it is visible.
- [ ] **Staleness signal.** Surface last-changed date per skill and flag a
      source whose upstream has moved past its pin.

Related: the stack-picker collision under Known gaps is the same problem
surfacing as a bug.

## Known gaps

Documented in the README under Known limits; repeated here as work.

- [ ] Index plugins that ship agents, commands, or hooks. Today they report zero
      skills.
- [ ] Catalog a source that has only a remote. Scanning requires a `local:` path,
      so a remote-only source is buildable but invisible.
- [ ] Key the stack picker by source and name. Two sources shipping the same
      skill name currently collapse into one entry.
