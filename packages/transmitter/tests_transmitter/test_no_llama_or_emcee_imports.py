"""transmitter's only input is the package directory: it never imports llama
or emcee (spec "Architecture"). Checks both src and tests."""

import re
from pathlib import Path

FORBIDDEN = re.compile(
    r"^\s*(?:from|import)\s+(?:llama|emcee)\b"
    r"|(?:__import__|import_module)\s*\(\s*['\"](?:llama|emcee)\b",
    re.M,
)


def _offenders(root: Path) -> list[str]:
    py_files = sorted(root.rglob("*.py"))
    assert py_files, f"no .py files found under {root} — path anchor broke"
    return [str(p) for p in py_files if FORBIDDEN.search(p.read_text())]


def test_pattern_catches_both_forms():
    assert FORBIDDEN.search("import emcee\n")
    assert FORBIDDEN.search("from llama.catalog import x\n")
    # split so this file's own source does not match the pattern it scans for
    assert FORBIDDEN.search("importlib.import_" + "module('emcee.station')\n")
    assert not FORBIDDEN.search("import llama_thing\n")


def test_src_never_imports_llama_or_emcee():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "src") == []


def test_tests_never_import_llama_or_emcee():
    root = Path(__file__).resolve().parents[1]
    assert _offenders(root / "tests_transmitter") == []
