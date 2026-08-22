"""Drive the built catalog in a headless browser and assert it renders.

Usage: python scripts/verify_ui.py [--port PORT] [--shots DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CACHE = Path.home() / "Library" / "Caches" / "ms-playwright"


def find_browser() -> str | None:
    candidates = sorted(CACHE.glob("chromium*/**/chrome-headless-shell"))
    candidates += sorted(CACHE.glob("chromium*/**/Chromium"))
    return str(candidates[-1]) if candidates else None


def launch(playwright, executable: str | None):
    if executable:
        return playwright.chromium.launch(executable_path=executable)
    return playwright.chromium.launch()


def check(page, url: str, expected_skills: int, shots: Path | None, theme: str) -> list[str]:
    problems: list[str] = []
    console: list[str] = []
    page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console.append(str(e)))

    page.goto(url, wait_until="networkidle")
    page.wait_for_selector(".card", timeout=8000)

    cards = page.locator(".card").count()
    if cards != expected_skills:
        problems.append(f"[{theme}] rendered {cards} cards, catalog has {expected_skills}")
    if page.locator("#f-cat button").count() == 0:
        problems.append(f"[{theme}] no category facets rendered")
    if console:
        problems.append(f"[{theme}] console errors: {console}")

    page.locator(".card .pick").first.click()
    page.wait_for_selector(".stack:not(.hidden)", timeout=3000)
    if "always-on" not in page.locator("#budgettext").inner_text():
        problems.append(f"[{theme}] budget readout missing after picking a skill")
    snippet = page.locator("#snippet").inner_text()
    picked = page.locator(".card.picked h4").first.inner_text()
    for fragment in ("- name:", "source:", "skills:"):
        if fragment not in snippet:
            problems.append(f"[{theme}] bundle snippet is missing {fragment!r}")
    if picked not in snippet:
        problems.append(f"[{theme}] bundle snippet omits the picked skill {picked!r}")

    page.fill("#q", "zzzznomatch")
    page.wait_for_timeout(200)
    if page.locator(".card").count() != 0:
        problems.append(f"[{theme}] search did not filter to zero on a nonsense query")

    if shots:
        page.fill("#q", "")
        page.wait_for_timeout(200)
        page.screenshot(path=str(shots / f"catalog-{theme}.png"))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--shots", type=Path)
    args = parser.parse_args()

    catalog = json.loads((args.out / "catalog.json").read_text())
    expected = catalog["totals"]["skills"]
    url = f"http://127.0.0.1:{args.port}/"
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)

    problems: list[str] = []
    with sync_playwright() as p:
        browser = launch(p, find_browser())
        for theme in ("light", "dark"):
            page = browser.new_page(viewport={"width": 1340, "height": 940}, color_scheme=theme)
            problems += check(page, url, expected, args.shots, theme)
            page.close()
        browser.close()

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(f"ui ok: {expected} skills rendered in both themes, picking and search verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
