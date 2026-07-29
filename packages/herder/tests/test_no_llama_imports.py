"""herder is the shared layer: it must never depend on any consuming app."""

import re
from pathlib import Path

FORBIDDEN = re.compile(r"^\s*(?:from|import)\s+llama\b", re.M)


def test_herder_never_imports_llama():
    src = Path(__file__).resolve().parents[1] / "src"
    offenders = [str(p) for p in sorted(src.rglob("*.py")) if FORBIDDEN.search(p.read_text())]
    assert offenders == []
