# Trove: a registry for Claude Code skills

bundle := "bundles/local.yaml"
out := "out"
port := "8787"
gif_filter := "fps=10,scale=1000:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=5"

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

# Generate catalog.json from local checkouts only, without fetching
catalog-offline:
    uv run trove --bundle {{ bundle }} --out {{ out }} --offline catalog

# Build everything the registry publishes
dist: build catalog

# Build everything without reaching the network
dist-offline: build-offline catalog-offline

# Report what the fetched-source cache holds
cache:
    uv run trove cache

# Empty the fetched-source cache
cache-clear:
    uv run trove cache --clear

# Compare token estimates against Claude Code, e.g. `just calibrate skills skills@local`
calibrate source plugin:
    uv run trove --bundle {{ bundle }} calibrate {{ source }} {{ plugin }}

# Preview what sync-local would change in the local marketplace
sync-local-check:
    uv run trove --bundle {{ bundle }} sync-local --dry-run

# Update the local marketplace from each source plugin.json
sync-local:
    uv run trove --bundle {{ bundle }} sync-local

# Report bundle fields that disagree with their source plugin.json
drift:
    uv run trove --bundle {{ bundle }} drift

# Report skills that no plugin ships
orphans: catalog
    @jq -r '.orphans[]' {{ out }}/catalog.json | grep . || echo "none"

# Report skill names that more than one source ships, with each source's always-on price
twins: catalog
    @jq -r '[.skills[] | {name, source, tokensAlwaysOn}] | group_by(.name) | map(select(length > 1)) | .[] | "\(.[0].name)\t" + (map("\(.source) +\(.tokensAlwaysOn)") | join("  "))' {{ out }}/catalog.json | column -t -s $'\t' | grep . || echo "none"

# Report skills that discovery cannot use
lint:
    uv run trove --bundle {{ bundle }} lint

# --- Browse ---

# Build the catalog and serve it
serve: catalog
    uv run trove --out {{ out }} serve --port {{ port }}

# Stop every trove preview server this project started
stop:
    @pkill -f 'trove --out' && echo "stopped" || echo "none running"

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
    if lsof -nP -iTCP:{{ port }} -sTCP:LISTEN >/dev/null 2>&1; then
      echo "port {{ port }} is already serving — run 'just stop', or pass --set port NNNN" >&2
      exit 1
    fi
    uv run trove --out {{ out }} serve --port {{ port }} >/dev/null 2>&1 &
    server=$!
    trap 'kill $server 2>/dev/null || true' EXIT
    until curl -sf -o /dev/null http://127.0.0.1:{{ port }}/catalog.json; do
      kill -0 $server 2>/dev/null || { echo "preview server exited before answering" >&2; exit 1; }
      sleep 0.2
    done
    uv run --with playwright python scripts/verify_ui.py --port {{ port }} --out {{ out }}

# Capture catalog screenshots in both themes
shots dir="shots": catalog
    #!/usr/bin/env bash
    set -euo pipefail
    if lsof -nP -iTCP:{{ port }} -sTCP:LISTEN >/dev/null 2>&1; then
      echo "port {{ port }} is already serving — run 'just stop', or pass --set port NNNN" >&2
      exit 1
    fi
    uv run trove --out {{ out }} serve --port {{ port }} >/dev/null 2>&1 &
    server=$!
    trap 'kill $server 2>/dev/null || true' EXIT
    until curl -sf -o /dev/null http://127.0.0.1:{{ port }}/catalog.json; do
      kill -0 $server 2>/dev/null || { echo "preview server exited before answering" >&2; exit 1; }
      sleep 0.2
    done
    uv run --with playwright python scripts/verify_ui.py --port {{ port }} --out {{ out }} --shots {{ dir }}
    echo "wrote {{ dir }}/catalog-light.png and {{ dir }}/catalog-dark.png"

# Record an mp4 walkthrough of the catalog, e.g. `just demo scripts/demo-twins.yml out/demo-twins.mp4`
demo storyboard="scripts/demo.yml" video="out/demo.mp4": catalog
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v shot-scraper >/dev/null; then
      echo "demo needs shot-scraper — uv tool install shot-scraper && shot-scraper install" >&2
      exit 1
    fi
    if lsof -nP -iTCP:{{ port }} -sTCP:LISTEN >/dev/null 2>&1; then
      echo "port {{ port }} is already serving — run 'just stop', or pass --set port NNNN" >&2
      exit 1
    fi
    uv run trove --out {{ out }} serve --port {{ port }} >/dev/null 2>&1 &
    server=$!
    trap 'kill $server 2>/dev/null || true' EXIT
    until curl -sf -o /dev/null http://127.0.0.1:{{ port }}/catalog.json; do
      kill -0 $server 2>/dev/null || { echo "preview server exited before answering" >&2; exit 1; }
      sleep 0.2
    done
    sed 's|127.0.0.1:8787|127.0.0.1:{{ port }}|' {{ storyboard }} > {{ out }}/demo.yml
    mp4="{{ video }}"
    shot-scraper video {{ out }}/demo.yml -o "${mp4%.mp4}.webm" --mp4
    echo "wrote $mp4"

# Re-record every README gif from its storyboard against the public registry
gifs: 
    #!/usr/bin/env bash
    set -euo pipefail
    command -v ffmpeg >/dev/null || { echo "gifs needs ffmpeg on PATH" >&2; exit 1; }
    for story in demo demo-curated demo-mixing demo-atlas demo-bundled demo-lint; do
      just --set bundle bundles/registry.yaml --set port {{ port }} demo "scripts/$story.yml" "{{ out }}/$story.mp4"
      ffmpeg -y -loglevel error -i "{{ out }}/$story.mp4" -vf "{{ gif_filter }}" "docs/$story.gif"
    done
    just --set bundle bundles/twins.yaml --set port {{ port }} demo scripts/demo-twins.yml {{ out }}/demo-twins.mp4
    ffmpeg -y -loglevel error -i {{ out }}/demo-twins.mp4 -vf "{{ gif_filter }}" docs/demo-twins.gif
    ls -la docs/*.gif

# Format markdown
fmt:
    prettier --write '*.md' 'docs/*.md'

# Check formatting without writing
fmt-check:
    prettier --check '*.md' 'docs/*.md'

# Everything CI should run
check: fmt-check test drift verify

# --- Housekeeping ---

# Remove build output
clean:
    rm -rf {{ out }} shots .pytest_cache
