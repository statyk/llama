import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_late_fixture_is_late_only():
    md = _load("gd1970-02-14_late_metadata.json")
    desc = md["metadata"].get("description", "")
    desc = "\n".join(desc) if isinstance(desc, list) else str(desc)
    assert "1970-02-14" in md["metadata"].get("title", "")
    # Late-show-only: closes on the late set-closer, never mentions the early one.
    assert "We Bid You Good Night" in desc
    assert "Turn On Your Lovelight" not in desc
    assert any(f.get("format") == "Flac" for f in md["files"])


def test_spans_fixture_covers_both_shows():
    md = _load("gd1970-02-14_spans_metadata.json")
    desc = md["metadata"].get("description", "")
    desc = "\n".join(desc) if isinstance(desc, list) else str(desc)
    # A complete-evening tape: both events' closers appear.
    assert "Turn On Your Lovelight" in desc
    assert "And We Bid You Good Night" in desc
    assert any(f.get("format") == "Flac" for f in md["files"])
