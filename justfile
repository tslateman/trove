# Trove: a registry for Claude Code skills

bundle := "bundles/tslateman.yaml"
out := "out"
port := "8787"

# Show available recipes
default:
    @just --list

# Install dependencies
setup:
    uv sync --all-groups

# --- Registry ---

# Index skills and report token cost per source
scan:
    uv run trove --bundle {{ bundle }} scan

# Index skills and list every one with its token cost
scan-all:
    uv run trove --bundle {{ bundle }} scan --verbose

# Generate marketplace.json, pinning each source to a commit sha
build:
    uv run trove --bundle {{ bundle }} --out {{ out }} build

# Generate marketplace.json without reaching the network
build-offline:
    uv run trove --bundle {{ bundle }} --out {{ out }} build --no-pin

# Generate catalog.json and the static site
catalog:
    uv run trove --bundle {{ bundle }} --out {{ out }} catalog

# Build everything the registry publishes
dist: build catalog

# Build everything without reaching the network
dist-offline: build-offline catalog

# Compare token estimates against Claude Code, e.g. `just calibrate skills skills@local`
calibrate source plugin:
    uv run trove --bundle {{ bundle }} calibrate {{ source }} {{ plugin }}

# Report bundle fields that disagree with their source plugin.json
drift:
    uv run trove --bundle {{ bundle }} drift

# Report skills that no plugin ships
orphans: catalog
    @jq -r '.orphans[]' {{ out }}/catalog.json | grep . || echo "none"

# Report skills whose frontmatter fails a strict YAML parse
lint-skills: catalog
    @jq -r '.skills[] | select(.strictYaml | not) | "\(.source)/\(.path)"' {{ out }}/catalog.json | grep . || echo "none"

# --- Browse ---

# Build the catalog and serve it
serve: catalog
    uv run trove --out {{ out }} serve --port {{ port }}

# Open the served catalog in a browser
open:
    open http://127.0.0.1:{{ port }}/

# --- Checks ---

# Run the test suite
test:
    uv run pytest -q

# Drive the catalog headless and assert it renders
verify: catalog
    #!/usr/bin/env bash
    set -euo pipefail
    uv run trove --out {{ out }} serve --port {{ port }} >/dev/null 2>&1 &
    server=$!
    trap 'kill $server 2>/dev/null || true' EXIT
    until curl -sf -o /dev/null http://127.0.0.1:{{ port }}/catalog.json; do sleep 0.2; done
    uv run --with playwright python scripts/verify_ui.py --port {{ port }} --out {{ out }}

# Capture catalog screenshots in both themes
shots dir="shots": catalog
    #!/usr/bin/env bash
    set -euo pipefail
    uv run trove --out {{ out }} serve --port {{ port }} >/dev/null 2>&1 &
    server=$!
    trap 'kill $server 2>/dev/null || true' EXIT
    until curl -sf -o /dev/null http://127.0.0.1:{{ port }}/catalog.json; do sleep 0.2; done
    uv run --with playwright python scripts/verify_ui.py --port {{ port }} --out {{ out }} --shots {{ dir }}
    echo "wrote {{ dir }}/catalog-light.png and {{ dir }}/catalog-dark.png"

# Format markdown
fmt:
    prettier --write '*.md'

# Check formatting without writing
fmt-check:
    prettier --check '*.md'

# Everything CI should run
check: fmt-check test drift verify

# --- Housekeeping ---

# Remove build output
clean:
    rm -rf {{ out }} shots .pytest_cache
