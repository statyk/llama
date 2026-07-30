"""emcee is a consuming app: it must never import llama directly.

Mirrors herder's own guard (`packages/herder/tests/test_no_llama_imports.py`)
verbatim (regex + anchor-asserting `_offenders` helper), but applies it to
BOTH `src` and `tests` — emcee has no separate top-level tests-guard file
the way herder does, so both trees are checked here.
"""

import re
from pathlib import Path

FORBIDDEN = re.compile(
    r"^\s*(?:from|import)\s+llama\b"
    r"|(?:__import__|import_module)\s*\(\s*['\"]llama\b",
    re.M,
)


def _offenders(root: Path) -> list[str]:
    py_files = sorted(root.rglob("*.py"))
    assert py_files, f"no .py files found under {root} — path anchor broke"
    return [str(p) for p in py_files if FORBIDDEN.search(p.read_text())]


def test_emcee_src_never_imports_llama():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "src") == []


def test_emcee_tests_never_import_llama():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "tests") == []
