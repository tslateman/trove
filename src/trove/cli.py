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
from . import local
from .fetch import Workspace, default_cache
from .lint import FINDINGS
from .loader import load_bundle
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
            for s in skills:
                print(f"  {s.name:<34} {s.tokens_always_on:>5} {s.tokens_on_invoke:>7}  {s.rel_path}")
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


def cmd_catalog(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    workspace = workspace_for(args)
    catalog = build_catalog(bundle, workspace=workspace)
    report(workspace)
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "catalog.json"
    target.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    shutil.copytree(Path(__file__).parent / "web", args.out, dirs_exist_ok=True)
    print(
        f"wrote {target}: {catalog['totals']['skills']} skills, "
        f"~{catalog['totals']['alwaysOn']:,} tok always-on"
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
        return 1
    print("no findings: every skill names itself and says when it fires")
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
        print(f"{name}: not in the local marketplace — add it with `claude plugin install`", file=sys.stderr)

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
    temp.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(args.marketplace)
    print(f"\nwrote {len(changes)} change(s) to {args.marketplace} (backup at {backup.name})")
    return 0


def cmd_calibrate(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    source = bundle.sources[args.source]
    workspace = workspace_for(args)
    estimated = {s.name: s.tokens_always_on for s in scan_source(source, workspace.root(source))}
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


class PreviewHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def __init__(self, *args, roots: dict[str, Path] | None = None, **kwargs):
        self.roots = roots or {}
        super().__init__(*args, **kwargs)

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
    handler = partial(PreviewHandler, directory=str(args.out), roots=roots)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        raise RuntimeError(
            f"cannot bind 127.0.0.1:{args.port} ({exc.strerror}) — another server is already "
            "there; stop it or choose another port"
        ) from exc
    print(f"serving {args.out.resolve()} at http://127.0.0.1:{args.port}")
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
    build.add_argument("--no-pin", action="store_true", help="skip git ls-remote sha resolution")
    build.set_defaults(func=cmd_build)

    catalog = sub.add_parser("catalog", help="emit catalog.json and the static site")
    catalog.set_defaults(func=cmd_catalog)

    sync = sub.add_parser("sync-local", help="update the local marketplace from each source plugin.json")
    sync.add_argument("--marketplace", type=Path, default=local.DEFAULT_MARKETPLACE)
    sync.add_argument("--dry-run", action="store_true")
    sync.set_defaults(func=cmd_sync_local)

    lint = sub.add_parser("lint", help="report skills that discovery cannot use")
    lint.set_defaults(func=cmd_lint)

    drift_cmd = sub.add_parser("drift", help="report bundle fields that disagree with the source plugin.json")
    drift_cmd.set_defaults(func=cmd_drift)

    calibrate = sub.add_parser("calibrate", help="compare estimates against claude plugin details")
    calibrate.add_argument("source")
    calibrate.add_argument("plugin")
    calibrate.set_defaults(func=cmd_calibrate)

    serve = sub.add_parser("serve", help="serve the built site")
    serve.add_argument("--port", type=int, default=8787)
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
