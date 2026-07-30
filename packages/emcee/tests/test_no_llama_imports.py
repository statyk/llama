import re
from pathlib import Path

FORBIDDEN = re.compile(r"^\s*(import llama\b|from llama\b)", re.M)


def test_emcee_never_imports_llama():
    root = Path(__file__).resolve().parents[1]
    offenders = [
        str(p) for d in ("src", "tests") for p in (root / d).rglob("*.py")
        if FORBIDDEN.search(p.read_text())
    ]
    assert offenders == []
