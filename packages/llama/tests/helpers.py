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


def tree_bytes(d: Path) -> dict[str, bytes]:
    """Every file under `d` (posix path relative to `d`) -> its bytes, except
    the top-level `.lock`."""
    return {p.relative_to(d).as_posix(): p.read_bytes()
            for p in sorted(d.rglob("*"))
            if p.is_file() and p.relative_to(d).as_posix() != ".lock"}


def packaged_gd73(tmp_path: Path, monkeypatch):
    """Run a real `get "GD 1973"` against the fake backend and FakeIA; returns
    (config path, ShowWorkspace) for the packaged gratefuldead-1973-06-10."""
    from typer.testing import CliRunner

    import llama.cli as cli
    import test_pipeline

    cfg = tmp_path / "config.toml"
    cfg.write_text(f'root = "{tmp_path}"\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", test_pipeline.fake_providers)
    monkeypatch.setattr(cli, "IAClient", test_pipeline.FakeIA)
    r = CliRunner().invoke(cli.app, ["--config", str(cfg), "get", "GD 1973",
                                     "--auto", "--name", "r"])
    assert r.exit_code == 0, r.output
    ws = ShowWorkspace(tmp_path / "shows" / "gratefuldead-1973-06-10")
    assert (ws.package_dir / "manifest.json").exists()
    return cfg, ws


# --- audio re-use (spec 5.4) -------------------------------------------------
# Fake audio whose bytes say which source file it is and how long it is, so a
# test can tell which audio landed under which packaged name. It survives
# `tag_audio` (an ID3 tag is prepended / replaced in front of it).

def fake_audio(source: str, secs: float) -> bytes:
    return f"FAKEAUDIO|{source}|{secs}|".encode()


def _fake_fields(path: Path) -> tuple[str, float] | None:
    import re
    m = re.search(rb"FAKEAUDIO\|([^|]*)\|([0-9.]+)\|", path.read_bytes())
    return (m.group(1).decode(), float(m.group(2))) if m else None


def fake_read_duration(path: Path) -> float | None:
    f = _fake_fields(path)
    return f[1] if f else None


def fake_source(path: Path) -> str | None:
    f = _fake_fields(path)
    return f[0] if f else None


def patch_fake_durations(monkeypatch) -> None:
    import llama.audio_reuse as audio_reuse
    from llama.stages import package as package_stage
    monkeypatch.setattr(audio_reuse, "read_duration", fake_read_duration)
    monkeypatch.setattr(package_stage, "read_duration", fake_read_duration)


class ReuseIA:
    """archive.org stub: cached metadata carries each file's md5 and `length`
    (omitted when None); a download writes `fake_audio` of that length."""

    def __init__(self, lengths: dict[str, float | None]):
        self.lengths = dict(lengths)
        self.downloads: list[str] = []

    def metadata(self, identifier):
        return {"files": [{"name": n, "md5": f"md5-{n}",
                           **({"length": str(s)} if s is not None else {})}
                          for n, s in self.lengths.items()]}

    def download_file(self, identifier, filename, dest, md5=None):
        self.downloads.append(filename)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(fake_audio(filename, self.lengths.get(filename) or 0.0))
        return dest


def reuse_show(*tracks) -> Show:
    """`tracks`: (title, filename, secs) or (title, filename, secs, short_kept),
    numbered from 1, all in set 1."""
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium",
        tracks=[Track(index=i, set="1", title=tr[0], filename=tr[1], duration_sec=tr[2],
                      title_source="tags", short_kept=bool(tr[3]) if len(tr) > 3 else False)
                for i, tr in enumerate(tracks, 1)])


def packaged_reuse_show(root: Path, show: Show, *, slug: str = "s") -> ShowWorkspace:
    """A show packaged by `build_package` from `ReuseIA` (call
    `patch_fake_durations` first): show.json, a briefing, package/ and its
    manifest, one fake audio file per track under its packaged name."""
    from llama.models import Briefing
    from llama.stages.package import build_package
    ws = ShowWorkspace(root / "shows" / slug)
    write_artifact(ws.show, show)
    write_artifact(ws.briefing_json, Briefing(context="c", significance="s"))
    write_artifact(ws.briefing_md, "# Briefing\n")
    ia = ReuseIA({t.filename: t.duration_sec for t in show.tracks})
    build_package(ws, ia, show)
    return ws


def audio_files(ws: ShowWorkspace) -> dict[str, bytes]:
    d = ws.package_dir / "audio"
    return {p.name: p.read_bytes() for p in sorted(d.iterdir()) if p.is_file()} if d.is_dir() else {}
