---
status: draft
---

# Roadmap

What Trove does today is in the [README](README.md). This page is what it does
not do yet, and what it deliberately will not do.

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

## Serving

Fetching removed the local-checkout dependency, so the catalog can now be built
anywhere. Publishing it is a deploy step. The reader skill turned out to be one
too: `catalog.json` names each source's url and sha, and git serves the body, so
a session reaching a skill through the reader depends on the host of the catalog
and on GitHub, never on a Trove process. What remains is publishing the catalog
and reaching sources git does not serve publicly.

- [x] **Publish the catalog.** `publish.yml` rebuilds `out/` on every push to
      main and deploys it to Cloudflare Pages. It reads `bundles/registry.yaml`
      when the repo carries one and falls back to the demo bundle, so the
      pipeline runs before a public bundle exists. GitHub Pages was the first
      target and never deployed: a free plan hosts it only from a public repo.
      Cloudflare Pages takes the build by direct upload instead.
- [x] **Read surface over the index.** `skills/trove` answers list, get, and
      file-get from `catalog.json` plus the `sources` block, which now carries
      each source's url and pinned sha. Git hosts the immutable content, so the
      surface resolves rather than stores and needs no server.
- [x] **Price the reader.** The reader skill costs 111 tokens always-on. Installing
      every plugin in the published registry costs 7,853 across 62 skills. Break-even
      is two skills.
- [x] **Serve the bodies the reader points at.** `sources[].body` names one base
      per source: raw git at the pinned sha for a public GitHub source, and
      `body/<source>/` for everything else, which `trove serve` answers from the
      checkout on disk. A source with no checkout and no public pin still has
      nowhere to resolve from, so a private remote needs a fetching endpoint.
- [x] **Tell installed from offered.** `trove serve` answers `/installed.json`
      from `claude plugin list --json`, so the catalog filters by what this
      machine has, prices what it loads today, and tells a plugin that is
      installed from one that is enabled. `trove installed` prints the same
      reading. A published build has no endpoint and says how to get one.

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

- [x] **Exact-name twins.** `just twins` lists every skill name that more
      than one source ships, with each source's always-on price, and the
      catalog's twins filter shows the same set with the source on each row.
- [ ] **Near-duplicate detection.** Compare skills across sources by
      description and body, and report overlap that a shared name does not
      expose. Token cost makes the redundancy quantifiable once it is visible.
- [ ] **Staleness signal.** Surface last-changed date per skill and flag a
      source whose upstream has moved past its pin.

The stack-picker collision under Known gaps was this problem surfacing as a
bug; the picker now keys by source, but the redundancy it exposed remains
unmeasured.

## Known limits

Documented in the README under Known limits; repeated here as work.

- [ ] Index plugins that ship agents, commands, or hooks. Today they report zero
      skills.
- [ ] **Submit a skill from the catalog.** Adding a skill today means a terminal:
      `just promote`, a commit, and a push. The page knows the sources and the
      paths, so it could take a `SKILL.md` from a drop or a paste, lint and price
      it before anything is written, and hand back the branch or pull request
      that puts it in the repo that should own it. The open question is what a
      published catalog is allowed to write, and with whose credentials.
- [x] Catalog a source that has only a remote. Sources are fetched and cached by
      commit sha, so a bundle indexes the same everywhere, CI included.
- [x] Count a skill's bundled files. The card and `scan --verbose` now price
      the files beside `SKILL.md`; a binary counts as a file and adds nothing.
- [x] Key the stack picker by source and path. Two sources shipping the same
      skill name pick independently, and the UI check proves it with twins.
