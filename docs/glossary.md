---
status: draft
---

# Glossary

Trove reads skills from the repos that own them, prices each one in tokens, and
publishes a Claude Code marketplace. This page defines the words the catalog and
the commands use, in the order you meet them. The
[getting started guide](getting-started.md) builds a registry with them.

## What a registry is made of

### Skill

A directory holding `SKILL.md`: frontmatter that names the skill and says when
it fires, plus a body Claude Code reads once it does. The unit this catalog
indexes.

### Source

A repo Trove reads skills from, named once in the bundle. A source is fetched
by commit, or read from a `local:` checkout while you edit it.
[Fetching](../README.md#fetching) covers what that costs and where it lands.

### Catalog

What this page belongs to: the index Trove builds from every source, one row
per skill, with its cost and the plugins that ship it. `catalog.json` holds it,
and the site you are reading renders it.

### Plugin

What Claude Code installs. In a bundle it is a name over one source, either the
whole repo or a chosen set of paths. A plugin's skills arrive namespaced as
`/<plugin>:<skill>`, which is why two plugins can ship the same name safely.

### Bundle

One YAML file naming your sources and the plugins composed from them. Every
Trove command reads it, and `bundles/local.yaml` is the one they read by
default. It is the only file you edit to change what the registry offers.
[Step 1](getting-started.md#step-1-describe-your-registry) writes the first one,
and [The bundle](../README.md#the-bundle) is the full format.

### Registry

A bundle plus what it publishes: the `marketplace.json` teammates add and the
catalog you are reading now.

### Marketplace

The manifest Claude Code adds and installs from. A machine files it under a
name, which is why `marketplace:` exists in the bundle: it records that name
when it differs from the bundle's own.

## What it costs

### Always-on

The tokens a skill's name and description charge in every session, whether or
not it fires. The only price you pay for a skill you never use.

### When it fires

The body's cost, paid the moment Claude Code chooses the skill. Cost tables
label this column `on invoke`.

### Bundled files

The files beside `SKILL.md`. Each is read only if the body sends the session
there, so the number shown is a ceiling rather than a bill.

### Stack

The skills you pick on this page. The tray prices them together and emits a
plugin block to paste under `plugins:` in your bundle.

## What the catalog reports

### Curated

A plugin that cherry-picks paths out of its source instead of shipping the
whole repo. A curated subset earns its own description.

### Pin

The commit sha a build resolves for each source, so an install is reproducible
and `claude plugin update` is what moves it.

### Twin

A skill name that more than one source ships. Both load, and both charge their
always-on price, so a twin is a bill rather than a conflict.
[Twins](../README.md#twins) says how to read one and how to retire it.

### Orphan

A skill in a source that no plugin in the bundle ships. It is indexed and
unpublished, usually because a curated plugin's paths missed it.

### Lint finding

Frontmatter that stops Claude Code from choosing or reading the skill: a
description that never says when it fires, a name the spec refuses, or YAML
that fails a strict parse. Each finding has a fix in
[Troubleshooting](troubleshooting.md#the-catalog-looks-wrong).

## How to read these pages

### AI draft

A page Claude wrote that no human has checked yet. It is the default: a page
carries this status until someone edits `status:` in its frontmatter.

### Verified

A page a human has read and stands behind. The badge in the corner of each
page says which of the two you are reading.

## What this machine has

### Installed

A plugin this machine holds, reported by `claude plugin list`. The catalog
offers; the machine installs. The badge on a row says which.

### Enabled

An installed plugin Claude Code actually loads. A disabled plugin costs
nothing and ships nothing, which is why the badge tells the two apart.

### Promote

Moving a skill out of `~/.claude/skills/` and into the repo that should own it,
so the registry can publish it. `just promote <name> <source>` copies it, lints
the copy, and prints the commands that follow.
[Share a skill](sharing-a-skill.md) is the whole path.
