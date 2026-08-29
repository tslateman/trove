---
status: draft
label: Landscape
---

# The skill registry landscape

Six registries, six answers to how a skill reaches a session. This page records
what each one does and what each one measures. The first four were surveyed on
2026-08-27; APM and the JFrog registry were added 2026-08-29. Trove's own
mechanics are in the [README](../README.md).

## The registries this compares against

| Product       | The answer it gives                                                          |
| ------------- | ---------------------------------------------------------------------------- |
| **Trove**     | Generate a marketplace from repos that already own their skills              |
| **PostHog**   | Never land the skill on disk; serve it from a store over MCP                 |
| **Tessl**     | A package manager with a manifest, plus scoring attached                     |
| **skills.sh** | GitHub is the registry; `npx skills add` copies the folder in                |
| **APM**       | A package manager for agent primitives, installed from any git repo          |
| **JFrog**     | An enterprise registry that scans and signs a skill before an agent pulls it |

## Getting a skill into a session

|                         | Trove                                                       | PostHog                  | Tessl                                      | skills.sh                            | APM                                              | JFrog                                                                 |
| ----------------------- | ----------------------------------------------------------- | ------------------------ | ------------------------------------------ | ------------------------------------ | ------------------------------------------------ | --------------------------------------------------------------------- |
| Source of truth         | Upstream git repo                                           | PostHog database         | Tessl registry                             | Any public git repo                  | Any git repo, or a local path                    | JFrog AI Catalog                                                      |
| Install                 | `claude plugin install` from a generated `marketplace.json` | Never; served per call   | `tessl install workspace/plugin[@version]` | `npx skills add owner/repo`          | `apm install owner/repo#ref`                     | Not documented publicly                                               |
| Lands at                | Claude Code's plugin directory                              | Nowhere                  | `.tessl/plugins/` or `~/.tessl/`           | `.claude/skills/`, project or global | Every harness it detects, plus `.agents/skills/` | Not documented                                                        |
| Pinned by               | Commit sha, resolved at build                               | Immutable version number | Version in `tessl.json`                    | No pin syntax documented             | `apm.lock.yaml`, versions and content hashes     | "Automatically versioned"; no pin syntax documented                   |
| Publish step            | None — a bundle composes what repos already own             | Web UI or `skill-create` | `tessl skill publish`, lints first         | None; install telemetry surfaces it  | None; installs from the repo                     | Upload, scanned and signed on the way in                              |
| Read without installing | Yes, via `skills/trove`                                     | Yes                      | No                                         | No                                   | Not documented                                   | Semantic search over the catalog; install-free reading not documented |
| Runtime dependency      | None installed; the reader adds catalog host and GitHub     | PostHog uptime           | None after install                         | None after install                   | None documented                                  | Not documented                                                        |

## What the catalog tells you before you commit

|                   | Trove                           | PostHog | Tessl                           | skills.sh                     | APM                                                                             | JFrog                                                                          |
| ----------------- | ------------------------------- | ------- | ------------------------------- | ----------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Does it work      | Planned                         | —       | Quality rubric and a judged A/B | —                             | —                                                                               | —                                                                              |
| Is it safe        | Planned                         | —       | Snyk score and install policies | "Read them before installing" | Scans every primitive for hidden Unicode; a critical finding blocks the install | Scans for vulnerabilities and malicious behaviour, then signs what it approves |
| What does it cost | Tokens, always-on and on invoke | —       | —                               | —                             | —                                                                               | —                                                                              |
| Does it fire      | Planned                         | —       | —                               | —                             | —                                                                               | —                                                                              |

Tessl measures behavior; the other five publish no behavior measurement.
`tessl scenario generate` builds validated scenarios, the agent solves each one
twice — once without the skill and once with it — and a judge scores both
against a per-scenario rubric. The published example reads 71% to 92%. The
multiplier on registry cards, such as `1.40x`, is undefined in the docs; treat
it as unverified.

## Context cost

Claude Code budgets the skill listing at `skillListingBudgetFraction`, 1% of
the model's context window by default, and caps each entry at 1,536 characters
(`skillListingMaxDescChars`). Names always survive; when the listing overflows,
descriptions drop, least-invoked first. Every skill installed spends part of
that budget in every session, whether or not it fires.

Measured with `trove`'s own estimator:

| Subject                                       | Always-on | On invoke |
| --------------------------------------------- | --------- | --------- |
| Trove reader, `skills/trove`                  | 111       | 1,451     |
| PostHog bridge, `skills-store`                | 82        | 3,819     |
| Every skill in the published registry, all 58 | 7,641     | —         |

Both front a whole registry for the price of one skill. PostHog's runs
against a database and puts the store's uptime in the path of every session that
fires a skill; Trove's resolves raw git at a pinned sha and needs no server.
Tessl and skills.sh document no read-without-install mode, so every skill
installed there keeps its always-on slice.

## What Trove lacks

Tessl scores what Trove's roadmap lists as open. Publishing runs quality scoring,
`tessl eval run` runs standalone, and `tessl review run security` runs a Snyk
scan. Trove's eval and security items are unstarted.

## The wider field

This page compares six registries closely. The field is larger. A survey
published 2026-07-06 names Agensi and skild.sh beside the six above, and
reports browse-only directories
advertising roughly 12,000, 21,000, and 2 million skills. It calls those counts
self-reported and "almost always indexing artifacts", then answers them: "A big
number tells you nothing about whether the one skill you actually need installs
cleanly."

Read it for the shape of the field rather than its ranking. The scorecard it
carries places its own author's product first.

## Sources

- [Tessl CLI commands](https://docs.tessl.io/reference/cli-commands.md),
  [eval scenarios](https://docs.tessl.io/improving-your-skills/evaluate-skill-quality-using-scenarios.md),
  [registry](https://tessl.io/registry)
- [PostHog Skills](https://posthog.com/docs/skills),
  [skills-store SKILL.md](https://github.com/PostHog/ai-plugin/blob/main/skills/skills-store/SKILL.md)
- [Vercel on Agent Skills](https://vercel.com/kb/guide/agent-skills-creating-installing-and-sharing-reusable-agent-context),
  [skills.sh: npm for Agent Skills](https://dev.to/stevengonsalvez/skillssh-npm-for-agent-skills-35jc)
- [Claude Code skills, on the listing budget](https://code.claude.com/docs/en/skills)
- [Agent Skills specification](https://agentskills.io/specification)
- [APM install reference](https://microsoft.github.io/apm/consumer/install-packages/),
  [APM](https://microsoft.github.io/apm/)
- [JFrog Agent Skills Registry](https://jfrog.com/ai-catalog/skills-registry/)
- Nicolas Dao,
  [The honest landscape](https://happyskills.ai/blog/claude-skills-marketplace/#the-honest-landscape),
  2026-07-06
