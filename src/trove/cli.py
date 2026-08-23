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

from .build import build_marketplace, dumps
from .catalog import build_catalog
from .loader import load_bundle
from .resolve import drift, source_manifest
from .scan import scan_source

DEFAULT_BUNDLE = Path("bundles/tslateman.yaml")
DEFAULT_OUT = Path("out")


def cmd_scan(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    total = 0
    for key, source in bundle.sources.items():
        if source.local is None or not source.local.exists():
            print(f"{key}: no local checkout ({source.local})", file=sys.stderr)
            continue
        skills = scan_source(source)
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
    manifest = build_marketplace(bundle, pin=not args.no_pin)
    out = args.out / ".claude-plugin" / "marketplace.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps(manifest), encoding="utf-8")
    print(f"wrote {out} ({len(manifest['plugins'])} plugins)")
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    catalog = build_catalog(bundle)
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / "catalog.json"
    target.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    shutil.copytree(Path(__file__).parent / "web", args.out, dirs_exist_ok=True)
    print(
        f"wrote {target}: {catalog['totals']['skills']} skills, "
        f"~{catalog['totals']['alwaysOn']:,} tok always-on"
    )
    return 0


def cmd_drift(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    found = 0
    for spec in bundle.plugins:
        manifest = source_manifest(bundle.sources[spec.source_key])
        if not manifest:
            print(f"{spec.name}: no local checkout to compare against", file=sys.stderr)
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


def cmd_calibrate(args: argparse.Namespace) -> int:
    bundle = load_bundle(args.bundle)
    source = bundle.sources[args.source]
    estimated = {s.name: s.tokens_always_on for s in scan_source(source)}
    if not estimated:
        print(f"no local checkout for {args.source}", file=sys.stderr)
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


class PreviewHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_head(self):
        del self.headers["If-Modified-Since"]
        return super().send_head()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()


def cmd_serve(args: argparse.Namespace) -> int:
    if not (args.out / "index.html").exists():
        raise RuntimeError(f"{args.out} has no index.html — run `trove catalog` first")
    handler = partial(PreviewHandler, directory=str(args.out))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        raise RuntimeError(
            f"cannot bind 127.0.0.1:{args.port} ({exc.strerror}) — another server is already "
            "there; stop it or choose another port"
        ) from exc
    print(f"serving {args.out.resolve()} at http://127.0.0.1:{args.port}")
    server.serve_forever()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="trove")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="index skills and report token cost")
    scan.add_argument("-v", "--verbose", action="store_true")
    scan.set_defaults(func=cmd_scan)

    build = sub.add_parser("build", help="emit marketplace.json from the bundle")
    build.add_argument("--no-pin", action="store_true", help="skip git ls-remote sha resolution")
    build.set_defaults(func=cmd_build)

    catalog = sub.add_parser("catalog", help="emit catalog.json and the static site")
    catalog.set_defaults(func=cmd_catalog)

    drift_cmd = sub.add_parser("drift", help="report bundle fields that disagree with the source plugin.json")
    drift_cmd.set_defaults(func=cmd_drift)

    calibrate = sub.add_parser("calibrate", help="compare estimates against claude plugin details")
    calibrate.add_argument("source")
    calibrate.add_argument("plugin")
    calibrate.set_defaults(func=cmd_calibrate)

    serve = sub.add_parser("serve", help="serve the built site")
    serve.add_argument("--port", type=int, default=8787)
    serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"trove: {exc.args[0] if exc.args else exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
