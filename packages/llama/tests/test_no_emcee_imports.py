"""llama must never import emcee directly: the delivered package on disk (and
the station lock file) is the only contract between them.

Mirrors emcee's guard (`packages/emcee/tests/test_no_llama_imports.py`) with
the names swapped (regex + anchor-asserting `_offenders` helper), applied to
BOTH `src` and `tests`.
"""

import re
from pathlib import Path

FORBIDDEN = re.compile(
    r"^\s*(?:from|import)\s+emcee\b"
    r"|(?:__import__|import_module)\s*\(\s*['\"]emcee\b",
    re.M,
)


def _offenders(root: Path) -> list[str]:
    py_files = sorted(root.rglob("*.py"))
    assert py_files, f"no .py files found under {root} — path anchor broke"
    return [str(p) for p in py_files if FORBIDDEN.search(p.read_text())]


def test_llama_src_never_imports_emcee():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "src") == []


def test_llama_tests_never_import_emcee():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "tests") == []
