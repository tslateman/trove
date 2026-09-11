import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEP_SIGNATURES = {
    "fmt-check": r"prettier\S*\s+--check",
    "test": r"pytest",
    "drift": r"trove\b.*\bdrift",
    "verify": r"verify_ui\.py",
}


def check_recipe_chain():
    justfile = (ROOT / "justfile").read_text()
    match = re.search(r"^check:\s*(.+)$", justfile, re.MULTILINE)
    assert match, "justfile has no `check:` recipe"
    return match.group(1).split()


def test_every_check_dependency_runs_in_ci():
    chain = check_recipe_chain()
    workflow = (ROOT / ".github/workflows/check.yml").read_text()
    missing = [step for step in chain if not re.search(STEP_SIGNATURES[step], workflow)]
    assert not missing, (
        f"justfile's `check` recipe runs {chain}, but "
        f".github/workflows/check.yml is missing: {missing}"
    )
