"""Shared test builders. Plain module (no `tests/__init__.py`, so `tests` is not
an importable package under this suite's pytest rootdir-insertion mode) — import
individual helpers with `from tests.helpers import ...` is NOT supported; instead
each test file that needs a helper here does `import helpers` after pytest adds
`tests/` itself to `sys.path` for the module under collection. See
`tests/test_broadcast_ready.py` and `tests/test_deliver_gate.py` for usage.
"""
from pathlib import Path

from llama.models import Show, Track
from llama.workspace import ShowWorkspace, write_artifact


def build_ready(root: Path, slug: str = "gratefuldead-1973-06-10", *,
                needs_review: bool = False, voiced: bool = True,
                broadcast_m3u: bool = True, drop_audio: bool = False,
                script: bool = True) -> ShowWorkspace:
    """A fully broadcast-ready show, with knobs to break one condition at a time."""
    ws = ShowWorkspace(root / "shows" / slug)
    write_artifact(ws.show, Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10",
        tracks=[Track(index=1, set="1", title="Morning Dew", filename="a.mp3",
                      title_source="tags")],
        needs_review=needs_review,
        review_flags=["held for a reason"] if needs_review else []))
    if script:
        write_artifact(ws.dj_notes_json, {"set_intros": {"1": "a"}, "outro": "o"})
    manifest = {"schema_version": 2,
                "show": {"artist": "Grateful Dead", "date": "1973-06-10",
                        "venue": "Some Venue", "city": None, "context": ""},
                "source": {"performance_id": "GratefulDead/1973-06-10"},
                "tracks": [{"index": 1, "set": "1", "title": "Morning Dew",
                            "filename": "01 - Morning Dew.mp3"}],
                "set_breaks": [], "total_duration_sec": 0, "set_durations_sec": {}}
    if voiced:
        manifest["dj_audio"] = {"set_intros": {"1": "dj-audio/set1-intro.mp3"},
                                "outro": "dj-audio/99-outro.mp3"}
    write_artifact(ws.package_dir / "manifest.json", manifest)
    if not drop_audio:
        write_artifact(ws.package_dir / "audio" / "01 - Morning Dew.mp3", "x")
    if broadcast_m3u:
        write_artifact(ws.package_dir / "broadcast.m3u", "#EXTM3U\n")
    return ws
