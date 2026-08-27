# Share a skill you wrote for yourself

A skill under `~/.claude/skills/<name>/` works on one machine. Nothing indexes
it, and Claude Code has no command that pushes it anywhere. Sharing it means
moving it into a repo the team can read and letting Trove publish that repo.
This page is the copy-and-paste path from one to the other.

The commands assume the registry checkout is the working directory and that
the team repo is already a source in `bundles/local.yaml` with a `local:`
checkout. If it is not, clone it and add it; the
[getting started guide](getting-started.md#step-1-describe-your-registry)
shows the shape.

## 1. Price and lint it while it is still yours

Declare your personal skills directory as a source with no remote. Trove
indexes a `local:` path on its own, so nothing is published by this step:

```yaml
# bundles/local.yaml
sources:
  personal:
    local: ~/.claude/skills
```

Then read what the skill costs and whether discovery can use it:

```bash
just scan-all | grep <name>
just lint
```

`lint` names anything that stops the skill from being chosen: frontmatter that
fails a strict YAML parse, or a description that never says when to use the
skill. Fix those now. A skill that never fires for you will never fire for a
teammate either.

Drop the `personal` source again once you are done pricing; it is a scan
target, never something to ship.

## 2. Move it into the repo that should own it

```bash
just promote <name> <source>
```

This copies `~/.claude/skills/<name>/` into the source's checkout (under
`skills/` when the repo keeps one, else at the root), leaves caches behind,
lints the copy, prices it, and prints the commands that follow. Pass a
different origin with `--from <dir>`, and a target directory with
`--into skills/<group>` for a repo that groups its skills.

The command refuses to overwrite: if the source already ships that name, you
have a twin, and the [README](../README.md#twins) says how to read one.

## 3. Push, build, install

`promote` prints these with the real paths filled in:

```bash
git -C <checkout> add skills/<name>
git -C <checkout> commit -m 'Add <name>' && git -C <checkout> push
just dist
```

A plugin that ships the whole source carries the new skill on the next build.
A curated plugin needs its path added under `skills:` in the bundle first.

Teammates add the registry once and install the plugin:

```bash
claude plugin marketplace add <registry url or owner/repo>
claude plugin install <plugin>@<registry>
```

After a rebuild, an existing install moves to the new pin with
`claude plugin update <plugin>@<registry>`. The skill arrives as
`/<plugin>:<name>`, namespaced, so it never collides with a personal skill of
the same name.

## 4. Delete the personal copy

```bash
rm -r ~/.claude/skills/<name>
```

Keep it and you become your own twin: Claude Code lists `/<name>` and
`/<plugin>:<name>` both, and the always-on budget pays for the description
twice. The Claude Code docs cover the underlying mechanics:
[plugins](https://code.claude.com/docs/en/plugins),
[marketplaces](https://code.claude.com/docs/en/plugin-marketplaces), and
[skills](https://code.claude.com/docs/en/skills).
