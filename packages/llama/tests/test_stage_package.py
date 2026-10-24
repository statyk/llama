import json
import logging
from pathlib import Path

import pytest

from llama.errors import LlamaError
from llama.models import Briefing, ResearchVetting, Show, Track, VettingResult
from llama.stages import package as package_stage
from llama.stages.package import run_package
from llama.workspace import ShowWorkspace, write_artifact


class StubIA:
    def __init__(self):
        self.downloads = []
        self.md = {"files": [
            {"name": "d1t01.mp3", "md5": "m1"}, {"name": "d2t01.mp3", "md5": "m2"},
        ]}

    def metadata(self, identifier):
        return self.md

    def download_file(self, identifier, filename, dest, md5=None):
        self.downloads.append((filename, md5))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 64)
        return dest


def make_show():
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium",
        tracks=[
            Track(index=1, set="1", title="Morning Dew", filename="d1t01.mp3",
                  duration_sec=600.0, title_source="tags"),
            Track(index=2, set="2", title="Dark Star", filename="d2t01.mp3",
                  duration_sec=1800.0, title_source="tags"),
        ],
        set_breaks=[1],
    )


def _briefing(**kw) -> Briefing:
    base = dict(context="Peak-era Dead on the summer '73 run.",
                significance="A standout show from a strong year.",
                per_set={"1": ["Opens hot"], "2": ["The big jam"]},
                notable_moments=["A monster Dark Star"],
                review_sentiment="Widely praised, including by non-attendees.",
                non_attendee_sentiment=True,
                cautions=[],
                mentioned_songs=[])
    base.update(kw)
    return Briefing(**base)


def write_briefing(sws: ShowWorkspace, **kw) -> Briefing:
    b = _briefing(**kw)
    write_artifact(sws.briefing_json, b)
    write_artifact(sws.briefing_md, "# Briefing: Grateful Dead — 1973-06-10\n")
    return b


def setup(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    write_briefing(sws)
    return sws, show


def test_package_layout_and_manifest(tmp_path: Path):
    sws, show = setup(tmp_path)
    ia = StubIA()
    pkg = run_package(sws, ia, show, profile="prime-dead")
    assert (pkg / "manifest.json").exists()
    assert (pkg / "playlist.m3u").exists()
    assert (pkg / "audio" / "01 - Morning Dew.mp3").exists()
    assert ia.downloads == [("d1t01.mp3", "m1"), ("d2t01.mp3", "m2")]  # md5s passed through
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["tracks"][0]["filename"] == "01 - Morning Dew.mp3"
    assert m["set_breaks"] == [{"after_track": 1}]
    # dummy bytes are unreadable audio -> falls back to metadata duration, no mismatch flag
    assert m["tracks"][0]["duration_sec"] == 600.0
    assert m["source"]["profile"] == "prime-dead"  # emcee reads this to assign presenter/title
    assert json.loads(sws.show.read_text())["needs_review"] is False


def test_package_never_writes_dj_notes_or_dj_audio(tmp_path: Path):
    # llama never generates a DJ script anymore -- that's emcee's job,
    # downstream of the manifest this stage writes. The fields stay in the
    # schema (passthrough) but llama's own packages never populate them.
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show)
    assert not (pkg / "dj-notes.md").exists()
    assert not (pkg / "dj-audio").exists()
    assert not (pkg / "broadcast.m3u").exists()
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["dj_notes"] is None
    assert m["dj_audio"] is None


def test_duration_mismatch_flags_needs_review(tmp_path: Path, monkeypatch):
    sws, show = setup(tmp_path)
    monkeypatch.setattr(package_stage, "read_duration", lambda path: 100.0)
    run_package(sws, StubIA(), show)
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert any("duration mismatch" in f for f in saved["review_flags"])


def test_package_skips_when_manifest_exists(tmp_path: Path):
    sws, show = setup(tmp_path)
    ia = StubIA()
    run_package(sws, ia, show)
    run_package(sws, ia, show)
    assert len(ia.downloads) == 2  # no re-downloads on second call


def test_package_logs_downloads(tmp_path: Path, caplog):
    sws, show = setup(tmp_path)
    with caplog.at_level(logging.INFO, logger="llama"):
        run_package(sws, StubIA(), show)
    messages = [r.getMessage() for r in caplog.records]
    assert "downloading 1/2: d1t01.mp3" in messages
    assert "downloading 2/2: d2t01.mp3" in messages


def write_vetting(sws, context="Peak 1973, RFK", flags=None):
    write_artifact(sws.vetting, VettingResult(
        vetting=ResearchVetting(context=context), flags=flags or []))


def test_package_ships_research_reviews_and_vetting_context(tmp_path: Path):
    sws, show = setup(tmp_path)
    write_artifact(sws.research, "## Reputation\nLegendary.")
    write_artifact(sws.reviews, [{"reviewtitle": "Wow", "reviewbody": "great tape"}])
    write_vetting(sws)
    pkg = run_package(sws, StubIA(), show)
    assert (pkg / "research.md").read_text() == "## Reputation\nLegendary."
    assert (pkg / "reviews.md").read_text() == "- Wow: great tape"
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["schema_version"] == 3
    assert m["research"] == "research.md" and m["reviews"] == "reviews.md"
    assert m["research_vetted"] is True
    assert m["show"]["context"] == "Peak 1973, RFK"


def test_package_context_defaults_empty_without_vetting(tmp_path: Path):
    # context now comes solely from the vet stage's context -- no notes.context
    # fallback (llama never generates notes anymore).
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show)
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["show"]["context"] == ""
    assert m["research"] is None and m["research_vetted"] is False


def test_package_copies_briefing_and_emits_v3(tmp_path: Path):
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show, force=True)
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["schema_version"] == 3
    assert manifest["briefing"]["json"] == "briefing.json"
    assert manifest["briefing"]["narration"] == "full"
    assert (pkg / "briefing.md").exists() and (pkg / "briefing.json").exists()


def test_package_manifest_briefing_reflects_the_real_briefing(tmp_path: Path):
    sws, show = setup(tmp_path)
    write_briefing(sws, narration="vague", per_set={}, mentioned_songs=[])
    write_vetting(sws)                      # flags=[] -> vetted True
    pkg = run_package(sws, StubIA(), show, force=True)
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["briefing"]["narration"] == "vague"
    assert m["briefing"]["vetted"] is True
    assert (pkg / "briefing.json").read_text() == sws.briefing_json.read_text()


def test_package_hard_fails_without_briefing(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    with pytest.raises(LlamaError, match="no briefing"):
        run_package(sws, StubIA(), show, force=True)


def test_purged_audio_is_refetched_on_repackage(tmp_path: Path):
    """After deliver purges the library audio, `redo --from package` (which
    drops only manifest.json) must re-download every track."""
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show)
    for p in (sws.package_dir / "audio").iterdir():
        p.unlink()
    (sws.package_dir / "manifest.json").unlink()
    ia = StubIA()
    run_package(sws, ia, show)
    assert [f for f, _ in ia.downloads] == ["d1t01.mp3", "d2t01.mp3"]
    assert (sws.package_dir / "audio" / "01 - Morning Dew.mp3").exists()


def test_build_package_returns_its_flags_and_never_writes_show_json(tmp_path: Path, monkeypatch):
    # llama reapply (spec slice 6) writes show.json once and last itself, so
    # the extracted body reports package-stage flags instead of writing them.
    from llama.stages.package import build_package
    sws, show = setup(tmp_path)
    before = sws.show.read_bytes()
    monkeypatch.setattr(package_stage, "read_duration", lambda path: 100.0)
    pkg, flags = build_package(sws, StubIA(), show)
    assert pkg == sws.package_dir and (pkg / "manifest.json").exists()
    assert flags == ["duration mismatch on 01 - Morning Dew.mp3: file 100s vs metadata 600s",
                     "duration mismatch on 02 - Dark Star.mp3: file 100s vs metadata 1800s"]
    assert sws.show.read_bytes() == before
    assert build_package(sws, StubIA(), show) == (pkg, [])   # an existing manifest short-circuits


# --- re-using existing audio (spec 5.4) --------------------------------------

from helpers import (  # noqa: E402
    ReuseIA,
    audio_files,
    fake_source,
    packaged_reuse_show,
    patch_fake_durations,
    reuse_show,
)
from llama.audio_reuse import ASIDE_DIR, plan_reuse  # noqa: E402
from llama.show_unit import show_unit  # noqa: E402
from llama.stages.package import build_package  # noqa: E402
from llama.workspace import drop_stage_artifacts  # noqa: E402


def _sources(ws) -> dict[str, str | None]:
    return {n: fake_source(ws.package_dir / "audio" / n) for n in audio_files(ws)}


def _repackage(ws, new, plan, lengths=None):
    """What a re-packaging unit does after `plan_reuse`: the re-gather writes
    the new show.json, the manifest is dropped, the package is rebuilt."""
    drop_stage_artifacts(ws, "package")
    write_artifact(ws.show, new)
    ia = ReuseIA(lengths or {t.filename: t.duration_sec for t in new.tracks})
    build_package(ws, ia, new, reuse=plan)
    return ia


def test_changed_list_sets_old_audio_aside_and_reuses_it_under_the_new_name(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    old = (("A", "a.mp3", 300.0), ("B", "b.mp3", 400.0), ("X", "x.mp3", 500.0))
    ws = packaged_reuse_show(tmp_path, reuse_show(*old))
    plan = plan_reuse(ws, None)
    new = reuse_show(old[0], old[1], ("Crowd", "s.mp3", 20.0, True), old[2])
    ia = _repackage(ws, new, plan)
    assert ia.downloads == ["s.mp3"]                     # only the new short file
    assert _sources(ws) == {"01 - A.mp3": "a.mp3", "02 - B.mp3": "b.mp3",
                            "03 - Crowd.mp3": "s.mp3", "04 - X.mp3": "x.mp3"}
    assert "03 - X.mp3" not in audio_files(ws)           # no old-numbered file left
    m = json.loads((ws.package_dir / "manifest.json").read_text())
    assert [t["filename"] for t in m["tracks"]] == list(_sources(ws))


def test_same_title_renumbered_never_inherits_the_wrong_audio(tmp_path, monkeypatch):
    # Old track 4 and new track 4 are both "Jam" but different source files,
    # with lengths inside the duration tolerance: left in place, the old
    # "04 - Jam.mp3" would ship as new track 4 and no flag would say so.
    patch_fake_durations(monkeypatch)
    old = (("A", "a.mp3", 300.0), ("B", "b.mp3", 400.0),
           ("Jam", "j1.mp3", 600.0), ("Jam", "j2.mp3", 602.0))
    ws = packaged_reuse_show(tmp_path, reuse_show(*old))
    plan = plan_reuse(ws, None)
    new = reuse_show(old[0], old[1], ("Crowd", "s.mp3", 20.0, True), old[2], old[3])
    ia = _repackage(ws, new, plan)
    assert ia.downloads == ["s.mp3"]
    assert _sources(ws) == {"01 - A.mp3": "a.mp3", "02 - B.mp3": "b.mp3",
                            "03 - Crowd.mp3": "s.mp3", "04 - Jam.mp3": "j1.mp3",
                            "05 - Jam.mp3": "j2.mp3"}
    assert json.loads(ws.show.read_text())["review_flags"] == []


def test_unchanged_list_and_matching_manifest_keeps_files_in_place(tmp_path, monkeypatch):
    # (pin) the library manifest's names equal the new packaged names: nothing
    # is set aside, copied or downloaded; the files are re-tagged where they are.
    patch_fake_durations(monkeypatch)
    old = (("A", "a.mp3", 300.0), ("B", "b.mp3", 400.0))
    ws = packaged_reuse_show(tmp_path, reuse_show(*old))
    audio = ws.package_dir / "audio"
    inodes = {p.name: p.stat().st_ino for p in audio.iterdir()}
    plan = plan_reuse(ws, None)
    import llama.audio_reuse as audio_reuse
    calls = []
    monkeypatch.setattr(audio_reuse, "set_aside", lambda *a: calls.append("set_aside"))
    monkeypatch.setattr(audio_reuse, "reuse_into", lambda *a, **k: calls.append("reuse_into"))
    ia = _repackage(ws, reuse_show(*old), plan)
    assert ia.downloads == [] and calls == []
    assert not (ws.dir / ASIDE_DIR).exists()
    assert {p.name: p.stat().st_ino for p in audio.iterdir()} == inodes
    assert _sources(ws) == {"01 - A.mp3": "a.mp3", "02 - B.mp3": "b.mp3"}


def test_audio_without_a_library_manifest_is_set_aside(tmp_path, monkeypatch):
    # Review Focus 6: a held re-gather already wrote the new list to show.json
    # and dropped the manifest, leaving old-numbered audio in package/audio/.
    patch_fake_durations(monkeypatch)
    old = (("A", "a.mp3", 300.0), ("B", "b.mp3", 400.0),
           ("Jam", "j1.mp3", 600.0), ("Jam", "j2.mp3", 602.0))
    ws = packaged_reuse_show(tmp_path, reuse_show(*old))
    new = reuse_show(old[0], old[1], ("Crowd", "s.mp3", 20.0, True), old[2], old[3])
    drop_stage_artifacts(ws, "package")
    write_artifact(ws.show, new)                          # the held re-gather
    with show_unit(ws, None):
        plan = plan_reuse(ws, None)                       # e.g. a later fix --overrule
        assert plan.library_names is None and plan.library == {}
        ia = ReuseIA({t.filename: t.duration_sec for t in new.tracks})
        build_package(ws, ia, new, reuse=plan)
        assert sorted(p.name for p in (ws.dir / ASIDE_DIR).iterdir()) == [
            "01 - A.mp3", "02 - B.mp3", "03 - Jam.mp3", "04 - Jam.mp3"]
    # none reused by name: every track downloads, new track 4 included
    assert ia.downloads == ["a.mp3", "b.mp3", "s.mp3", "j1.mp3", "j2.mp3"]
    assert _sources(ws)["04 - Jam.mp3"] == "j1.mp3"
    assert sorted(audio_files(ws)) == ["01 - A.mp3", "02 - B.mp3", "03 - Crowd.mp3",
                                       "04 - Jam.mp3", "05 - Jam.mp3"]
    assert not (ws.dir / ASIDE_DIR).exists()              # gone after success


def test_retitle_only_change_reuses_under_the_new_name(tmp_path, monkeypatch):
    patch_fake_durations(monkeypatch)
    old = (("A", "a.mp3", 300.0), ("B", "b.mp3", 400.0), ("X", "x.mp3", 500.0))
    ws = packaged_reuse_show(tmp_path, reuse_show(*old))
    plan = plan_reuse(ws, None)                           # pairs x.mp3 -> 03 - X.mp3
    ia = _repackage(ws, reuse_show(old[0], old[1], ("Y", "x.mp3", 500.0)), plan)
    assert ia.downloads == []
    assert _sources(ws) == {"01 - A.mp3": "a.mp3", "02 - B.mp3": "b.mp3", "03 - Y.mp3": "x.mp3"}
    assert "03 - X.mp3" not in audio_files(ws)


def test_build_package_without_reuse_never_sets_aside(tmp_path, monkeypatch):
    # (pin) reuse=None is today's behaviour: an old-numbered file stays where
    # it is and a name that already exists is not downloaded again.
    patch_fake_durations(monkeypatch)
    old = (("A", "a.mp3", 300.0), ("X", "x.mp3", 500.0))
    ws = packaged_reuse_show(tmp_path, reuse_show(*old))
    drop_stage_artifacts(ws, "package")
    new = reuse_show(old[0], ("Crowd", "s.mp3", 20.0, True), old[1])
    ia = ReuseIA({t.filename: t.duration_sec for t in new.tracks})
    build_package(ws, ia, new)
    assert ia.downloads == ["s.mp3", "x.mp3"]
    assert sorted(audio_files(ws)) == ["01 - A.mp3", "02 - Crowd.mp3", "02 - X.mp3", "03 - X.mp3"]
    assert not (ws.dir / ASIDE_DIR).exists()
