# The skill registry landscape

Four registries, four answers to how a skill reaches a session. This page
records what each one does and what each one measures.

## The four

| Product       | The answer it gives                                             |
| ------------- | --------------------------------------------------------------- |
| **Trove**     | Generate a marketplace from repos that already own their skills |
| **PostHog**   | Never land the skill on disk; serve it from a store over MCP    |
| **Tessl**     | A package manager with a manifest, plus scoring attached        |
| **skills.sh** | GitHub is the registry; `npx skills add` copies the folder in   |

## Getting a skill into a session

|                         | Trove                                                       | PostHog                  | Tessl                                      | skills.sh                            |
| ----------------------- | ----------------------------------------------------------- | ------------------------ | ------------------------------------------ | ------------------------------------ |
| Source of truth         | Upstream git repo                                           | PostHog database         | Tessl registry                             | Any public git repo                  |
| Install                 | `claude plugin install` from a generated `marketplace.json` | Never; served per call   | `tessl install workspace/plugin[@version]` | `npx skills add owner/repo`          |
| Lands at                | Claude Code's plugin directory                              | Nowhere                  | `.tessl/plugins/` or `~/.tessl/`           | `.claude/skills/`, project or global |
| Pinned by               | Commit sha, resolved at build                               | Immutable version number | Version in `tessl.json`                    | No pin syntax documented             |
| Publish step            | None — a bundle composes what repos already own             | Web UI or `skill-create` | `tessl skill publish`, lints first         | None; install telemetry surfaces it  |
| Read without installing | Yes, via `skills/trove`                                     | Yes, the only mode       | No                                         | No                                   |
| Runtime dependency      | Catalog host and GitHub                                     | PostHog uptime           | None after install                         | None after install                   |

## What the catalog tells you before you commit

|                   | Trove                               | PostHog | Tessl                           | skills.sh                     |
| ----------------- | ----------------------------------- | ------- | ------------------------------- | ----------------------------- |
| Does it work      | Planned                             | —       | Quality rubric and a judged A/B | —                             |
| Is it safe        | Planned                             | —       | Snyk score and install policies | "Read them before installing" |
| What does it cost | **Tokens, always-on and on invoke** | —       | —                               | —                             |
| Does it fire      | Planned                             | —       | —                               | Install counts                |

Tessl measures behavior; the other three do not.
`tessl scenario generate` builds validated scenarios, the agent solves each one
twice — once without the skill and once with it — and a judge scores both
against a per-scenario rubric. The published example reads 71% to 92%. The
multiplier on registry cards, such as `1.40x`, is undefined in the docs; treat
it as unverified.

## Context cost

Claude Code caps skill metadata at `skillListingBudgetFraction`, 1% of the
context window by default, and drops descriptions that overflow it. Every skill
installed spends part of that budget in every session, whether or not it fires.

Measured with `trove`'s own estimator:

| Subject                                       | Always-on | On invoke |
| --------------------------------------------- | --------- | --------- |
| Trove bridge, `skills/trove`                  | 111       | 1,107     |
| PostHog bridge, `skills-store`                | 82        | 3,819     |
| Every skill in the published registry, all 62 | 7,853     | —         |

Both bridges front a whole registry for the price of one skill. PostHog's runs
against a database and puts the store's uptime in the path of every session that
fires a skill; Trove's resolves raw git at a pinned sha and needs no server.
Tessl and skills.sh have no bridge, so every skill installed keeps its always-on
slice.

## What Trove lacks

Tessl scores what Trove's roadmap lists as open. Publishing runs quality scoring,
`tessl eval run` runs standalone, and `tessl review run security` runs a Snyk
scan. Trove's eval and security items are unstarted.

## Sources

- [Tessl CLI commands](https://docs.tessl.io/reference/cli-commands.md),
  [eval scenarios](https://docs.tessl.io/improving-your-skills/evaluate-skill-quality-using-scenarios.md),
  [registry](https://tessl.io/registry)
- [PostHog Skills](https://posthog.com/docs/skills),
  [skills-store SKILL.md](https://github.com/PostHog/ai-plugin/blob/main/skills/skills-store/SKILL.md)
- [Vercel on Agent Skills](https://vercel.com/kb/guide/agent-skills-creating-installing-and-sharing-reusable-agent-context),
  [skills.sh: npm for Agent Skills](https://dev.to/stevengonsalvez/skillssh-npm-for-agent-skills-35jc)
- [Claude Code's skill listing budget](https://claudefa.st/blog/guide/mechanics/skill-listing-budget)
- [Agent Skills specification](https://agentskills.io/specification)
