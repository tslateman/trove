from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
from pathlib import Path
from urllib.parse import unquote

from .build import build_marketplace, dumps
from .catalog import build_catalog
from . import installed, local
from .fetch import Workspace, default_cache
from .frontmatter import split as split_frontmatter
from .lint import FINDINGS
from .loader import load_bundle
from .promote import promote
from .resolve import drift, source_manifest
from .scan import scan_source

DEFAULT_BUNDLE = Path("bundles/local.yaml")
DEFAULT_OUT = Path("out")


def workspace_for(args: argparse.Namespace, offline: bool = False) -> Workspace:
    return Workspace(cache=None if offline or args.offline else args.cache)


def report(workspace: Workspace) -> None:
    for note in workspace.notes:
        print(note, file=sys.stderr)
    workspace.notes.clear()


def cmd_scan(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    workspace = workspace_for(args)
    total = 0
    for key, source in bundle.sources.items():
        root = workspace.root(source)
        report(workspace)
        if root is None:
            print(f"{key}: no local checkout and fetching is off", file=sys.stderr)
            continue
        skills = scan_source(source, root)
        if not skills:
            print(f"{key}: checkout has no shipped skills", file=sys.stderr)
            continue
        always = sum(s.tokens_always_on for s in skills)
        total += always
        print(f"{key}: {len(skills)} skills, ~{always:,} tok always-on")
        if args.verbose:
            print(f"  {'skill':<34} {'always':>5} {'fires':>7} {'bundled':>9}  path")
            for s in skills:
                bundled = (
                    f"{s.bundled_files}f ≤{s.tokens_bundled_max}"
                    if s.bundled_files
                    else ""
                )
                print(
                    f"  {s.name:<34} {s.tokens_always_on:>5} {s.tokens_on_invoke:>7} "
                    f"{bundled:>9}  {s.rel_path}"
                )
    print(f"\ntotal always-on: ~{total:,} tok")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    workspace = workspace_for(args, offline=args.no_pin)
    manifest = build_marketplace(bundle, pin=not args.no_pin, workspace=workspace)
    report(workspace)
    out = args.out / ".claude-plugin" / "marketplace.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(manifest), encoding="utf-8")
    print(f"wrote {out} ({len(manifest['plugins'])} plugins)")
    return 0


DOC_ROOT = Path("docs")
# Reading order for the guides Trove ships: orientation, then the task pages,
# then what you look up. A registry's own pages sit between the two groups.
DOC_FIRST = (
    "README.md",
    "getting-started.md",
    "cli.md",
    "troubleshooting.md",
    "sharing-a-skill.md",
)
DOC_LAST = ("glossary.md", "landscape.md", "ROADMAP.md")
# Pages that live at the repo root rather than in docs/.
ROOT_PAGES = ("README.md", "ROADMAP.md")


def doc_order(path: Path) -> tuple[int, int, str]:
    if path.name in DOC_FIRST:
        return 0, DOC_FIRST.index(path.name), path.name
    if path.name in DOC_LAST:
        return 2, DOC_LAST.index(path.name), path.name
    return 1, 0, path.name


# A page is an AI draft until a human writes `status: verified` into it.
DRAFT = "draft"


def doc_entry(path: Path) -> dict:
    """A page's own heading and review status, read from the page itself."""
    meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
    title = next(
        (line[2:].strip() for line in body.splitlines() if line.startswith("# ")),
        path.stem.replace("-", " ").capitalize(),
    )
    return {
        "file": path.name,
        "title": title,
        # `label:` names the page in the rail when its own heading is the wrong
        # length for a nav item, as a repo README's heading usually is.
        "label": meta.get("label", title),
        "status": meta.get("status", DRAFT),
    }


def ship_docs(out: Path, root: Path) -> list[dict]:
    """Copy the registry's guides beside the catalog so the page can read them.

    A build with no `docs/` beside it ships none, and the Docs tab then carries
    only what the page itself knows.
    """
    source = root / DOC_ROOT
    if not source.is_dir():
        return []
    target = out / DOC_ROOT
    shutil.copytree(source, target, dirs_exist_ok=True)
    for name in ROOT_PAGES:
        page = root / name
        if page.is_file():
            shutil.copy2(page, target / name)
    pages = [doc_entry(path) for path in sorted(target.glob("*.md"), key=doc_order)]
    (target / "index.json").write_text(
        json.dumps(pages, indent=2) + "\n", encoding="utf-8"
    )
    return pages


def cmd_catalog(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    workspace = workspace_for(args)
    catalog = build_catalog(bundle, workspace=workspace)
    report(workspace)
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "catalog.json"
    target.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    shutil.copytree(Path(__file__).parent / "web", args.out, dirs_exist_ok=True)
    pages = ship_docs(args.out, Path.cwd())
    print(
        f"wrote {target}: {catalog['totals']['skills']} skills, "
        f"~{catalog['totals']['alwaysOn']:,} tok always-on"
        + (f", {len(pages)} doc page(s)" if pages else "")
    )
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    workspace = workspace_for(args)
    roots = {key: workspace.root(source) for key, source in bundle.sources.items()}
    report(workspace)

    flagged = 0
    for key, source in bundle.sources.items():
        for skill in scan_source(source, roots[key]):
            if not skill.lint:
                continue
            flagged += 1
            print(f"{key}/{skill.rel_path}")
            for code in skill.lint:
                print(f"  {code}: {FINDINGS[code]}")
    if flagged:
        print(f"\n{flagged} skill(s) flagged")
        print("each finding and its fix: docs/troubleshooting.md", file=sys.stderr)
        return 1
    print("no findings: every skill names itself and says when it fires")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    if args.source not in bundle.sources:
        raise ValueError(
            f"bundle names no source {args.source!r}; it has {sorted(bundle.sources)}"
        )
    source = bundle.sources[args.source]
    skill_dir = (
        args.source_dir or Path.home() / ".claude" / "skills" / args.name
    ).expanduser()
    dest, skill = promote(skill_dir, source, args.into)
    root = dest.parent
    while root != root.parent and not (root / ".git").exists():
        root = root.parent
    rel = dest.relative_to(root) if (root / ".git").exists() else dest

    print(f"copied {skill_dir} -> {dest}")
    if skill.lint:
        for code in skill.lint:
            print(f"  {code}: {FINDINGS[code]}")
        print("  fix these before pushing, or discovery skips the skill for everyone")
    else:
        print("  lint: clean")
    print(
        f"  +{skill.tokens_always_on} tok always-on, "
        f"{skill.tokens_on_invoke:,} when it fires"
    )

    whole = [
        p.name for p in bundle.plugins if p.source_key == source.key and not p.skills
    ]
    curated = [
        p.name for p in bundle.plugins if p.source_key == source.key and p.skills
    ]
    print("\nnext:")
    print(f"  git -C {root} add {rel}")
    print(f"  git -C {root} commit -m 'Add {skill.name}' && git -C {root} push")
    if curated:
        print(
            f"  # to ship it from {', '.join(curated)}, add {skill.rel_path} under "
            f"skills: in {args.bundle}"
        )
    if whole:
        print(
            f"  # {', '.join(whole)} ships the whole source, so the next build carries it"
        )
    if not whole and not curated:
        print(
            f"  # no plugin in {args.bundle} ships source {source.key!r} yet; add one"
        )
    print("  just dist")
    for name in whole:
        print(
            f"  claude plugin install {name}@{bundle.name}"
            f"   # teammates; already installed: claude plugin update {name}@{bundle.name}"
        )
    print(
        f"  rm -r {skill_dir}   # once the plugin copy is installed, or you become your own twin"
    )
    return 1 if skill.lint else 0


def cmd_installed(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    workspace = workspace_for(args)
    catalog = build_catalog(bundle, workspace=workspace)
    report(workspace)
    state = installed.survey(catalog, args.marketplace)
    name = state["marketplace"]

    if not state["available"]:
        print(f"cannot read this machine: {state['reason']}", file=sys.stderr)
        return 1

    where = "configured" if state["configured"] else "not a marketplace on this machine"
    print(f"marketplace {name!r} ({where})\n")
    print(f"{'plugin':<28}{'offered':>9}{'installed':>11}  state")
    for plugin in catalog["plugins"]:
        record = state["plugins"].get(plugin["name"])
        offered = plugin["version"] or "—"
        if record is None:
            print(f"{plugin['name']:<28}{offered:>9}{'—':>11}  not installed")
            continue
        marks = ["enabled" if record["enabled"] else "installed, disabled"]
        if record["update"]:
            marks.append("update")
        if len(set(record["scopes"])) > 1:
            marks.append("both scopes")
        print(
            f"{plugin['name']:<28}{offered:>9}{record['version'] or '—':>11}  "
            f"{', '.join(marks)}"
        )

    totals, charged = state["totals"], installed.cost(catalog, state)
    print(
        f"\n{totals['plugins']} of {len(catalog['plugins'])} plugins installed, "
        f"{totals['enabled']} enabled"
    )
    print(
        f"~{charged['alwaysOn']:,} tok always-on from the {charged['enabledSkills']} "
        f"skills enabled here, of ~{catalog['totals']['alwaysOn']:,} offered"
    )
    if not state["plugins"]:
        print("\nnothing from this registry is installed. To fix the reading:")
        hint = state.get("suggest")
        if hint:
            print(
                f"  # your machine ships {hint['matches']} of these plugin names under "
                f"{hint['marketplace']!r}"
            )
            print(
                f"  trove --bundle {args.bundle} installed --marketplace {hint['marketplace']}"
            )
            print(
                f"  # to keep it: add `marketplace: {hint['marketplace']}` to {args.bundle}"
            )
        else:
            add = installed.local_marketplace(args.out)
            print(
                f"  just dist   # writes {args.out}/.claude-plugin/marketplace.json"
                if not add
                else ""
            )
            print(f"  claude plugin marketplace add {add or args.out.resolve()}")
            print(f"  claude plugin install {catalog['plugins'][0]['name']}@{name}")
    return 0


def cmd_drift(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    workspace = workspace_for(args)
    found = 0
    for spec in bundle.plugins:
        source = bundle.sources[spec.source_key]
        manifest = source_manifest(source, workspace.root(source))
        report(workspace)
        if not manifest:
            print(f"{spec.name}: no plugin.json to compare against", file=sys.stderr)
            continue
        for field, declared, upstream in drift(spec, manifest):
            found += 1
            print(f"{spec.name}.{field}")
            print(f"  bundle: {declared}")
            print(f"  source: {upstream}")
    if found:
        print(f"\n{found} field(s) restate the source and disagree with it")
        return 1
    print("no drift: every restated field matches its source plugin.json")
    return 0


def cmd_sync_local(args: argparse.Namespace) -> int:
    if not args.marketplace.exists():
        raise RuntimeError(f"no local marketplace at {args.marketplace}")

    bundle = load_bundle(args.bundle)
    manifest = json.loads(args.marketplace.read_text(encoding="utf-8"))
    workspace = workspace_for(args)
    changes, absent, unsourced = local.plan(bundle, manifest, workspace=workspace)
    report(workspace)

    for name in unsourced:
        print(
            f"{name}: skipped, its source has no plugin.json to sync from",
            file=sys.stderr,
        )
    for name in absent:
        print(
            f"{name}: not in the local marketplace — add it with `claude plugin install`",
            file=sys.stderr,
        )

    if not changes:
        print(f"{args.marketplace.name}: already matches every source plugin.json")
        return 0

    for name, field, old, new in changes:
        print(f"{name}.{field}")
        print(f"  was: {old}")
        print(f"  now: {new}")

    if args.dry_run:
        print(f"\n{len(changes)} change(s) — rerun without --dry-run to write them")
        return 0

    backup = args.marketplace.with_suffix(".json.bak")
    backup.write_text(args.marketplace.read_text(encoding="utf-8"), encoding="utf-8")
    updated = local.apply(manifest, changes)
    temp = args.marketplace.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temp.replace(args.marketplace)
    print(
        f"\nwrote {len(changes)} change(s) to {args.marketplace} (backup at {backup.name})"
    )
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    source = bundle.sources[args.source]
    workspace = workspace_for(args)
    estimated = {
        s.name: s.tokens_always_on for s in scan_source(source, workspace.root(source))
    }
    report(workspace)
    if not estimated:
        print(f"no skills indexed for {args.source}", file=sys.stderr)
        return 1

    result = subprocess.run(
        ["claude", "plugin", "details", args.plugin],
        capture_output=True,
        text=True,
        check=True,
    )
    actual = {}
    for line in result.stdout.splitlines():
        match = re.match(r"\s{2}(\S+)\s+~([\d,]+)\s+~", line)
        if match:
            actual[match.group(1)] = int(match.group(2).replace(",", ""))

    shared = sorted(set(estimated) & set(actual))
    if not shared:
        print("no overlapping components", file=sys.stderr)
        return 1

    print(f"{'skill':<34}{'est':>6}{'actual':>8}{'delta':>8}")
    errors = []
    for name in shared:
        est, act = estimated[name], actual[name]
        errors.append(abs(est - act) / act if act else 0)
        print(f"{name:<34}{est:>6}{act:>8}{est - act:>+8}")
    mean = sum(errors) / len(errors)
    print(f"\n{len(shared)} compared, mean absolute error {mean:.1%}")
    return 0


BODY_PREFIX = "/body/"
INSTALLED_PATH = "/installed.json"


class PreviewHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(
        self,
        *args,
        roots: dict[str, Path] | None = None,
        marketplace: str | None = None,
        **kwargs,
    ):
        self.roots = roots or {}
        self.marketplace = marketplace
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        """Answer `/installed.json` from this machine.

        It is computed per request and never written into the build, so a
        published catalog carries no trace of who installed what.
        """
        clean = self.path.split("?", 1)[0].split("#", 1)[0]
        if clean == INSTALLED_PATH:
            return self.send_installed()
        return super().do_GET()

    def send_installed(self) -> None:
        site = Path(self.directory)
        try:
            catalog = json.loads((site / "catalog.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            payload = {
                "available": False,
                "reason": f"cannot read catalog.json beside the page: {exc}",
                "plugins": {},
                "totals": {"plugins": 0, "enabled": 0},
            }
        else:
            payload = installed.survey(catalog, self.marketplace)
            add = installed.local_marketplace(site)
            if add:
                payload["add"] = add
        body = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def translate_path(self, path: str) -> str:
        """Answer `/body/<source>/<rest>` from that source's checkout.

        The rest of the path goes through the base class against a swapped
        directory, so its traversal defenses apply unchanged.
        """
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean.startswith(BODY_PREFIX):
            key, _, rest = clean[len(BODY_PREFIX) :].partition("/")
            root = self.roots.get(unquote(key))
            if root is not None:
                served, self.directory = self.directory, str(root)
                try:
                    return super().translate_path("/" + rest)
                finally:
                    self.directory = served
        return super().translate_path(path)

    def send_head(self):
        del self.headers["If-Modified-Since"]
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()


def body_roots(path: Path) -> dict[str, Path]:
    """Checkouts `serve` answers `/body/` from. A bundle it cannot read serves none."""
    if not path.exists():
        return {}
    return {
        key: source.local
        for key, source in load_bundle(path).sources.items()
        if source.local is not None and source.local.exists()
    }


def cmd_serve(args: argparse.Namespace) -> int:
    if not (args.out / "index.html").exists():
        raise RuntimeError(f"{args.out} has no index.html — run `trove catalog` first")
    roots = body_roots(args.bundle)
    handler = partial(
        PreviewHandler,
        directory=str(args.out),
        roots=roots,
        marketplace=args.marketplace,
    )
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        raise RuntimeError(
            f"cannot bind 127.0.0.1:{args.port} ({exc.strerror}) — another server is already "
            "there; stop it or choose another port"
        ) from exc
    print(f"serving {args.out.resolve()} at http://127.0.0.1:{args.port}")
    print("  /installed.json -> what `claude plugin list` reports for this registry")
    for key, root in sorted(roots.items()):
        print(f"  /body/{key}/ -> {root}")
    server.serve_forever()
    return 0


def cmd_cache(args: argparse.Namespace) -> int:
    if args.clear:
        shutil.rmtree(args.cache, ignore_errors=True)
        print(f"cleared {args.cache}")
        return 0
    if not args.cache.exists():
        print(f"{args.cache} (empty)")
        return 0
    checkouts = sorted(p for p in args.cache.glob("*/*") if p.is_dir())
    size = sum(f.stat().st_size for f in args.cache.rglob("*") if f.is_file())
    print(f"{args.cache}: {len(checkouts)} checkout(s), {size / 1_048_576:.1f} MiB")
    for path in checkouts:
        print(f"  {path.parent.name}/{path.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trove")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--cache",
        type=Path,
        default=default_cache(),
        help="where fetched sources are checked out",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="never fetch; index only sources with a local checkout",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="index skills and report token cost")
    scan.add_argument("-v", "--verbose", action="store_true")
    scan.set_defaults(func=cmd_scan)

    build = sub.add_parser("build", help="emit marketplace.json from the bundle")
    build.add_argument(
        "--no-pin", action="store_true", help="skip git ls-remote sha resolution"
    )
    build.set_defaults(func=cmd_build)

    catalog = sub.add_parser("catalog", help="emit catalog.json and the static site")
    catalog.set_defaults(func=cmd_catalog)

    sync = sub.add_parser(
        "sync-local", help="update the local marketplace from each source plugin.json"
    )
    sync.add_argument("--marketplace", type=Path, default=local.DEFAULT_MARKETPLACE)
    sync.add_argument("--dry-run", action="store_true")
    sync.set_defaults(func=cmd_sync_local)

    lint = sub.add_parser("lint", help="report skills that discovery cannot use")
    lint.set_defaults(func=cmd_lint)

    drift_cmd = sub.add_parser(
        "drift", help="report bundle fields that disagree with the source plugin.json"
    )
    drift_cmd.set_defaults(func=cmd_drift)

    promote_cmd = sub.add_parser(
        "promote", help="copy a personal skill into a source checkout and lint it"
    )
    promote_cmd.add_argument("name", help="skill directory name under ~/.claude/skills")
    promote_cmd.add_argument(
        "--source", required=True, help="bundle source key to promote into"
    )
    promote_cmd.add_argument(
        "--from",
        dest="source_dir",
        type=Path,
        help="skill directory, when not under ~/.claude/skills",
    )
    promote_cmd.add_argument(
        "--into",
        help="directory under the source root; default: skills/ if it exists, else the root",
    )
    promote_cmd.set_defaults(func=cmd_promote)

    installed_cmd = sub.add_parser(
        "installed", help="report which of the bundle's plugins this machine has"
    )
    installed_cmd.add_argument(
        "--marketplace",
        help="name this registry was added under, when it differs from the bundle name",
    )
    installed_cmd.set_defaults(func=cmd_installed)

    calibrate = sub.add_parser(
        "calibrate", help="compare estimates against claude plugin details"
    )
    calibrate.add_argument("source")
    calibrate.add_argument("plugin")
    calibrate.set_defaults(func=cmd_calibrate)

    serve = sub.add_parser("serve", help="serve the built site")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument(
        "--marketplace",
        help="name this registry was added under, when it differs from the bundle name",
    )
    serve.set_defaults(func=cmd_serve)

    cache = sub.add_parser("cache", help="report or clear the fetched-source cache")
    cache.add_argument("--clear", action="store_true")
    cache.set_defaults(func=cmd_cache)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"trove: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
