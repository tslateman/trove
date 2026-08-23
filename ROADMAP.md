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
      An expensive skill that earns its place looks different from an expensive
      skill nobody triggers.
- [ ] **Rank the catalog on evidence.** Once both signals exist, sort and filter
      on them. Alphabetical order is a placeholder for having nothing to say.

The blocker is a scoring source. Trove indexes and serves; it does not run
skills. Either an external runner writes results Trove reads, or Trove grows a
runner. Settle that before designing the schema.

## Known gaps

Documented in the README under Known limits; repeated here as work.

- [ ] Index plugins that ship agents, commands, or hooks. Today they report zero
      skills.
- [ ] Catalog a source that has only a remote. Scanning requires a `local:` path,
      so a remote-only source is buildable but invisible.
- [ ] Key the stack picker by source and name. Two sources shipping the same
      skill name currently collapse into one entry.
