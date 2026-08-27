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


def launch(playwright):
    """Prefer the build the installed Playwright expects; fall back to any cached one."""
    if Path(playwright.chromium.executable_path).exists():
        return playwright.chromium.launch()
    executable = find_browser()
    if executable:
        return playwright.chromium.launch(executable_path=executable)
    return playwright.chromium.launch()


XSS_PROBE = """() => {
  const probe = '<img src=x onerror="window.__pwned=1">';
  state.data.skills.push({name: probe, description: probe, category: probe, tags: [probe],
    path: 'probe', source: 'probe', tokensAlwaysOn: 1, tokensOnInvoke: 1,
    bundledFiles: 1, tokensBundledMax: 1, categoryIsFallback: false, lint: [probe], plugins: [probe]});
  render();
  const injected = document.querySelectorAll('main img, #stack img').length;
  state.data.skills.pop();
  render();
  return injected;
}"""

TWIN_PROBE = """() => {
  const base = {name: 'twin', description: 'd', category: 'twin-probe', tags: [],
    tokensAlwaysOn: 1, tokensOnInvoke: 1, bundledFiles: 0, tokensBundledMax: 0,
    lint: [], plugins: []};
  const a = Object.assign({}, base, {source: 'one', path: 'skills/a/twin'});
  const b = Object.assign({}, base, {source: 'two', path: 'skills/b/twin'});
  state.data.skills.push(a, b);
  const saved = [...state.picked];
  state.picked.clear();
  render();
  [...document.querySelectorAll('.row')]
    .find(c => c.querySelector('h4').textContent === 'twin')
    .querySelector('.pick').click();
  const picked = document.querySelectorAll('.row.picked').length;
  state.picked.clear();
  saved.forEach(k => state.picked.add(k));
  state.data.skills.pop();
  state.data.skills.pop();
  render();
  return picked;
}"""

ALWAYS_ON_COLUMN = (
    "() => [...document.querySelectorAll('.row .num.on')]"
    ".map(n => parseInt(n.textContent.replace('+', ''), 10))"
)


def check(
    page, url: str, expected_skills: int, shots: Path | None, theme: str
) -> tuple[list[str], str]:
    problems: list[str] = []
    console: list[str] = []
    page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console.append(str(e)))

    page.goto(url, wait_until="networkidle")
    page.wait_for_selector(".row", timeout=8000)

    rows = page.locator(".row").count()
    if rows != expected_skills:
        problems.append(
            f"[{theme}] rendered {rows} rows, catalog has {expected_skills}"
        )

    served = page.evaluate("() => state.data.skills.map(s => [s.name, s.description])")
    rendered = page.evaluate(
        "() => [...document.querySelectorAll('.row')].map("
        "c => [c.querySelector('h4').textContent, c.querySelector('p').textContent])"
    )
    if served[: len(rendered)] != rendered:
        first = next((i for i, (a, b) in enumerate(zip(served, rendered)) if a != b), 0)
        problems.append(
            f"[{theme}] row {first} renders {rendered[first]!r} but the catalog says "
            f"{served[first]!r} — the page is stale or mis-binding"
        )
    if page.locator("#f-cat button").count() < 2:
        problems.append(f"[{theme}] no category tiles rendered beside All")

    page.locator(".row .pick").first.click()
    page.wait_for_selector(".stack:not(.hidden)", timeout=3000)
    if "1" not in page.locator("#stackcount").inner_text():
        problems.append(f"[{theme}] stack count did not update after picking a skill")
    snippet = page.locator("#snippet").inner_text()
    picked = page.locator(".row.picked h4").first.inner_text()
    for fragment in ("- name:", "source:", "skills:"):
        if fragment not in snippet:
            problems.append(f"[{theme}] bundle snippet is missing {fragment!r}")
    if picked not in snippet:
        problems.append(f"[{theme}] bundle snippet omits the picked skill {picked!r}")

    page.click("#clear")
    page.wait_for_timeout(200)
    if page.locator(".stack:not(.hidden)").count():
        problems.append(f"[{theme}] the stack tray stayed open after Clear")

    page.locator(".row .more").first.click()
    page.wait_for_timeout(100)
    if not page.locator(".row.open .detail").first.is_visible():
        problems.append(f"[{theme}] expanding a row did not reveal its detail")
    page.locator(".row .more").first.click()

    page.click("#listhead button[data-sort=on]")
    page.wait_for_timeout(100)
    costs = page.evaluate(ALWAYS_ON_COLUMN)
    if costs != sorted(costs, reverse=True):
        problems.append(
            f"[{theme}] sorting by always-on did not order the column: {costs[:5]}"
        )
    if "sort=on" not in page.url:
        problems.append(f"[{theme}] the sort did not reach the URL: {page.url}")
    page.click("#listhead button[data-sort=name]")
    page.wait_for_timeout(100)

    page.locator("#f-cat button").nth(1).click()
    page.wait_for_timeout(100)
    narrowed = page.locator(".row").count()
    if not (0 < narrowed < expected_skills) and expected_skills > 1:
        problems.append(
            f"[{theme}] a category tile did not narrow the list ({narrowed})"
        )
    if "cat=" not in page.url:
        problems.append(
            f"[{theme}] the category filter did not reach the URL: {page.url}"
        )
    page.locator("#f-cat button").nth(0).click()
    page.wait_for_timeout(100)

    page.click("#t-atlas")
    page.wait_for_selector("#mapbox svg", timeout=5000)
    leaves = page.locator("#mapbox g.leaf").count()
    if leaves != expected_skills:
        problems.append(
            f"[{theme}] atlas rendered {leaves} leaves, catalog has {expected_skills}"
        )
    if page.locator("#mapbox g.cnode").count() == 0:
        problems.append(f"[{theme}] atlas rendered no branch nodes")
    page.locator("#mapbox g.leaf").first.click()
    page.wait_for_timeout(200)
    now_picked = page.locator("#mapbox g.leaf.sel").count()
    if now_picked != 1:
        problems.append(
            f"[{theme}] clicking an atlas leaf did not pick it, sel count {now_picked}"
        )
    page.click("#t-skills")
    page.wait_for_timeout(200)
    if page.locator("article.row.picked").count() == 0:
        problems.append(
            f"[{theme}] a pick made in the atlas did not carry over to Skills view"
        )
    page.click("#clear")
    page.wait_for_timeout(100)

    page.click("#t-plugins")
    page.wait_for_timeout(200)
    if not page.evaluate("document.getElementById('view-skills').hidden"):
        problems.append(
            f"[{theme}] the Skills section stayed visible on the Plugins tab"
        )
    if page.locator("#f-cat button").first.is_visible():
        problems.append(f"[{theme}] category tiles are still visible on Plugins")
    all_plugins = page.locator("article.row").count()
    page.fill("#q", "review")
    page.wait_for_timeout(200)
    filtered_plugins = page.locator("article.row").count()
    if not (0 < filtered_plugins < all_plugins):
        problems.append(
            f"[{theme}] search did not narrow the Plugins list ({all_plugins} -> {filtered_plugins})"
        )
    page.fill("#q", "")
    page.wait_for_timeout(200)
    page.locator("article.row .tolist").first.click()
    page.wait_for_timeout(200)
    if page.evaluate("document.getElementById('view-skills').hidden"):
        problems.append(
            f"[{theme}] a plugin's skill count did not jump to the Skills list"
        )
    if "plugin=" not in page.url:
        problems.append(
            f"[{theme}] jumping from a plugin did not filter by it: {page.url}"
        )
    if page.locator("#f-plug button[aria-pressed=true]").count() != 1:
        problems.append(f"[{theme}] the plugin chip did not light up after the jump")
    page.click("#showing-reset")
    page.wait_for_timeout(100)

    page.fill("#q", "zzzznomatch")
    page.wait_for_timeout(200)
    if page.locator(".row").count() != 0:
        problems.append(f"[{theme}] search did not filter to zero on a nonsense query")
    if not page.locator("#empty").is_visible():
        problems.append(f"[{theme}] the empty state did not show on a nonsense query")
    page.fill("#q", "")
    page.wait_for_timeout(200)

    injected = page.evaluate(XSS_PROBE)
    if injected:
        problems.append(
            f"[{theme}] a hostile skill name/category/tag produced {injected} live element(s) — "
            "an interpolation is missing escapeHtml"
        )

    twin_picked = page.evaluate(TWIN_PROBE)
    if twin_picked != 1:
        problems.append(
            f"[{theme}] picking one of two same-named skills marked {twin_picked} rows — "
            "the picker is keying on name alone"
        )

    background = page.evaluate("getComputedStyle(document.body).backgroundColor")
    if console:
        problems.append(f"[{theme}] console errors: {console}")

    if shots:
        page.locator(".row .pick").nth(0).click()
        page.locator(".row .pick").nth(1).click()
        page.locator(".row .more").nth(2).click()
        page.wait_for_timeout(300)
        page.screenshot(path=str(shots / f"catalog-{theme}.png"))
        page.click("#clear")
    return problems, background


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
    backgrounds = {}
    with sync_playwright() as p:
        browser = launch(p)
        for theme in ("light", "dark"):
            page = browser.new_page(
                viewport={"width": 1340, "height": 940}, color_scheme=theme
            )
            found, backgrounds[theme] = check(page, url, expected, args.shots, theme)
            problems += found
            page.close()

        narrow = browser.new_page(viewport={"width": 390, "height": 800})
        narrow.goto(url, wait_until="networkidle")
        narrow.wait_for_selector(".row")
        narrow.locator(".row .pick").first.click()
        narrow.wait_for_selector(".stack:not(.hidden)", timeout=3000)
        overflow = narrow.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        if overflow > 0:
            problems.append(f"[390px] page scrolls sideways by {overflow}px")
        if shots := args.shots:
            narrow.screenshot(path=str(shots / "catalog-narrow.png"), full_page=True)
        narrow.close()
        browser.close()

    if backgrounds["light"] == backgrounds["dark"]:
        problems.append(
            f"both themes painted body {backgrounds['light']} — the dark palette is not applying"
        )

    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    print(
        f"ui ok: {expected} skills, both themes distinct, no sideways scroll at 390px, "
        "picking, sorting, filtering, search, and hostile-input escaping verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
