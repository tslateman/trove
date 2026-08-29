# Changelog

Notable changes to Trove. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the version
numbers follow [semantic versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.1 - 2026-08-29

### Added

- The changelog ships in the Docs tab, beside the roadmap.
- The landscape survey records the wider field: the platforms a July 2026
  survey names, and what it says about directories that advertise their size.

### Changed

- A task list renders as checkboxes. The roadmap tracks twenty items with
  `- [ ]` and `- [x]`, and the viewer printed the brackets as text.
- Always-on counts read in body text rather than green.

### Fixed

- A list item written across several lines stays one bullet. The roadmap,
  written that way throughout, had been breaking into bullets and stray
  paragraphs.
- Form controls follow the page theme. The page declared no `color-scheme`, so
  checkboxes and text fields rendered light against the dark theme.

## 0.1.0 - 2026-08-28

First public release. Trove reads skills from the repos that own them, prices
each one in tokens, and publishes a catalog and a Claude Code marketplace from
a bundle.

### Added

- **Build a marketplace from repos.** A bundle names sources and the plugins
  they compose; `trove build` writes `marketplace.json` with every plugin
  pinned to a commit sha. No publish step, and no second copy of a skill.
- **Price a skill in tokens.** Every skill carries what its frontmatter charges
  in each session, what its body charges when it fires, and a ceiling for the
  files it bundles. `trove calibrate` checks the estimate against Claude Code.
- **A catalog to read before installing.** A sortable ledger with category
  tiles, a stack tray for costing a set of picks, an Atlas tab mapping the
  registry as a radial tree and word cloud, and the guides carried inside the
  catalog rather than linked out of it.
- **Read a skill without installing it.** The `skills/trove` reader answers
  list, get, and file-get from `catalog.json` and the pinned shas beside it,
  for 111 tokens always-on.
- **Tell installed from offered.** `trove installed` and the preview server's
  `/installed.json` read `claude plugin list --json`. On a published build the
  visitor pastes or drops that answer into the page, which joins it against the
  registry in the browser and never uploads it.
- **Curate what ships.** Select a subtree with a trailing slash, `promote` a
  personal skill into the repo that should own it, and `sync-local` to update
  Claude Code's local marketplace.
- **Fetch a source with no checkout.** Sources resolve from the remote and
  cache under `~/.cache/trove/sources`, so a bundle builds without cloning
  every repo by hand.
- **Report what a registry should not ship.** `trove lint` names the skills
  discovery cannot use, `trove drift` names bundle fields that disagree with
  the source's `plugin.json`, and the catalog flags a name that more than one
  source ships.
- **Publish on push.** `publish.yml` rebuilds the catalog and deploys it to
  Cloudflare Pages.
