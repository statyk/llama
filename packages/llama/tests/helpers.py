"""Shared test builders. Plain module (no `tests/__init__.py`, so `tests` is not
an importable package under this suite's pytest rootdir-insertion mode) — import
individual helpers with `from tests.helpers import ...` is NOT supported; instead
each test file that needs a helper here does `import helpers` after pytest adds
`tests/` itself to `sys.path` for the module under collection. See
`tests/test_deliver_gate.py` for usage.
"""
from pathlib import Path

from llama.models import Show, Track
from llama.workspace import ShowWorkspace, write_artifact


def build_ready(root: Path, slug: str = "gratefuldead-1973-06-10", *,
                needs_review: bool = False, drop_audio: bool = False) -> ShowWorkspace:
    """A packaged, deliverable show, with knobs to break one condition at a
    time (held for review / a manifest track's audio missing on disk).
    Voice/DJ artifacts (script, dj_audio, broadcast.m3u) are out of scope for
    llama's deliver gate post-cut and are not written here."""
    ws = ShowWorkspace(root / "shows" / slug)
    write_artifact(ws.show, Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10",
        tracks=[Track(index=1, set="1", title="Morning Dew", filename="a.mp3",
                      title_source="tags")],
        needs_review=needs_review,
        review_flags=["held for a reason"] if needs_review else []))
    manifest = {"schema_version": 3,
                "briefing": {"file": "briefing.md", "json": "briefing.json",
                            "narration": "full", "vetted": False},
                "show": {"artist": "Grateful Dead", "date": "1973-06-10",
                        "venue": "Some Venue", "city": None, "context": ""},
                "source": {"performance_id": "GratefulDead/1973-06-10"},
                "tracks": [{"index": 1, "set": "1", "title": "Morning Dew",
                            "filename": "01 - Morning Dew.mp3"}],
                "set_breaks": [], "total_duration_sec": 0, "set_durations_sec": {}}
    write_artifact(ws.package_dir / "manifest.json", manifest)
    if not drop_audio:
        write_artifact(ws.package_dir / "audio" / "01 - Morning Dew.mp3", "x")
    return ws
