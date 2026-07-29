"""herder is the shared layer: it must never depend on any consuming app."""

import re
from pathlib import Path

FORBIDDEN = re.compile(r"^\s*(?:from|import)\s+llama\b", re.M)


def _offenders(root: Path) -> list[str]:
    py_files = sorted(root.rglob("*.py"))
    assert py_files, f"no .py files found under {root} — path anchor broke"
    return [str(p) for p in py_files if FORBIDDEN.search(p.read_text())]


def test_herder_never_imports_llama():
    src = Path(__file__).resolve().parents[1] / "src"
    assert _offenders(src) == []


def test_herder_tests_never_import_llama():
    tests = Path(__file__).resolve().parent
    assert _offenders(tests) == []
