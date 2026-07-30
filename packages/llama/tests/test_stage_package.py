import json
import logging
import wave
from pathlib import Path

import numpy as np
import pytest

from llama.errors import LlamaError
from llama.models import Briefing, DJNotes, ResearchVetting, Show, Track, VettingResult
from llama.speech_text import Lexicon
from llama.stages import package as package_stage
from llama.stages.package import run_package
from llama.tts.bed import Bed
from llama.tts.fake import SILENT_MP3, FakeSpeechProvider
from llama.tts.provider import SpeechError
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


def make_notes():
    return DJNotes(context="from the notes", outro="o",
                   set_intros={"1": "a", "2": "b"})


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
    write_artifact(sws.dj_notes_md, "# notes")
    write_briefing(sws)
    return sws, show


def test_package_layout_and_manifest(tmp_path: Path):
    sws, show = setup(tmp_path)
    ia = StubIA()
    pkg = run_package(sws, ia, show, make_notes(), profile="prime-dead")
    assert (pkg / "manifest.json").exists()
    assert (pkg / "playlist.m3u").exists()
    assert (pkg / "dj-notes.md").read_text() == "# notes"
    assert (pkg / "audio" / "01 - Morning Dew.mp3").exists()
    assert ia.downloads == [("d1t01.mp3", "m1"), ("d2t01.mp3", "m2")]  # md5s passed through
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["tracks"][0]["filename"] == "01 - Morning Dew.mp3"
    assert m["set_breaks"] == [{"after_track": 1}]
    # dummy bytes are unreadable audio -> falls back to metadata duration, no mismatch flag
    assert m["tracks"][0]["duration_sec"] == 600.0
    assert m["source"]["profile"] == "prime-dead"  # emcee reads this to assign presenter/title
    assert json.loads(sws.show.read_text())["needs_review"] is False


def test_duration_mismatch_flags_needs_review(tmp_path: Path, monkeypatch):
    sws, show = setup(tmp_path)
    monkeypatch.setattr(package_stage, "read_duration", lambda path: 100.0)
    run_package(sws, StubIA(), show, make_notes())
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is True
    assert any("duration mismatch" in f for f in saved["review_flags"])


def test_package_skips_when_manifest_exists(tmp_path: Path):
    sws, show = setup(tmp_path)
    ia = StubIA()
    run_package(sws, ia, show, make_notes())
    run_package(sws, ia, show, make_notes())
    assert len(ia.downloads) == 2  # no re-downloads on second call


def test_package_logs_downloads(tmp_path: Path, caplog):
    sws, show = setup(tmp_path)
    with caplog.at_level(logging.INFO, logger="llama"):
        run_package(sws, StubIA(), show, make_notes())
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
    pkg = run_package(sws, StubIA(), show, make_notes())
    assert (pkg / "research.md").read_text() == "## Reputation\nLegendary."
    assert (pkg / "reviews.md").read_text() == "- Wow: great tape"
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["schema_version"] == 3
    assert m["research"] == "research.md" and m["reviews"] == "reviews.md"
    assert m["research_vetted"] is True
    assert m["show"]["context"] == "Peak 1973, RFK"  # vetting wins over notes.context


def test_package_without_script(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)  # no dj-notes.md written
    write_artifact(sws.research, "r")
    write_vetting(sws)
    write_briefing(sws)
    pkg = run_package(sws, StubIA(), show, notes=None)
    assert not (pkg / "dj-notes.md").exists()
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["dj_notes"] is None
    assert m["set_breaks"] == [{"after_track": 1}]
    assert (pkg / "reviews.md").read_text() == "(no reviews)"


def test_package_without_vetting_falls_back_to_notes_context(tmp_path: Path):
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show, make_notes())
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["show"]["context"] == make_notes().context
    assert m["research"] is None and m["research_vetted"] is False


def test_package_synthesizes_dj_audio_and_manifest_block(tmp_path: Path):
    sws, show = setup(tmp_path)
    speech = FakeSpeechProvider()
    notes = make_notes()
    pkg = run_package(sws, StubIA(), show, notes, speech=speech)
    dj = pkg / "dj-audio"
    for name in ["set1-intro.mp3", "set2-intro.mp3", "99-outro.mp3"]:
        assert (dj / name).read_bytes() == SILENT_MP3
    assert not (dj / "00-intro.mp3").exists() and not (dj / "break1.mp3").exists()
    assert speech.calls == [notes.set_intros["1"], notes.set_intros["2"], notes.outro]
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["dj_audio"] == {
        "set_intros": {"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        "outro": "dj-audio/99-outro.mp3",
    }
    assert m["set_breaks"] == [{"after_track": 1}]


def test_package_segment_cache_skips_unchanged(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show, make_notes(), speech=FakeSpeechProvider())
    (sws.package_dir / "manifest.json").unlink()  # what redo --from package does
    second = FakeSpeechProvider()
    run_package(sws, StubIA(), show, make_notes(), speech=second)
    assert second.calls == []  # no re-spend on unchanged text


def test_package_changed_text_resynthesizes_only_that_segment(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show, make_notes(), speech=FakeSpeechProvider())
    (sws.package_dir / "manifest.json").unlink()
    notes = make_notes().model_copy(update={"outro": "a different outro"})
    second = FakeSpeechProvider()
    run_package(sws, StubIA(), show, notes, speech=second)
    assert second.calls == ["a different outro"]


def test_package_different_voice_resynthesizes(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show, make_notes(), speech=FakeSpeechProvider())
    (sws.package_dir / "manifest.json").unlink()
    second = FakeSpeechProvider()
    second.voice = "other-voice"  # cache key includes the voice
    run_package(sws, StubIA(), show, make_notes(), speech=second)
    assert len(second.calls) == 3  # set1-intro, set2-intro, outro


def test_package_force_rerenders_all_segments(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show, make_notes(), speech=FakeSpeechProvider())
    second = FakeSpeechProvider()
    run_package(sws, StubIA(), show, make_notes(), force=True, speech=second)
    assert len(second.calls) == 3  # set1-intro, set2-intro, outro


def test_package_shrinking_set_intros_prunes_orphan_clips(tmp_path: Path):
    sws, show = setup(tmp_path)
    notes = make_notes().model_copy(update={"set_intros": {"1": "a", "2": "b", "encore": "c"}})
    run_package(sws, StubIA(), show, notes, speech=FakeSpeechProvider())
    dj = sws.package_dir / "dj-audio"
    assert (dj / "set2-intro.mp3").exists()
    assert (dj / "setencore-intro.mp3").exists()
    (sws.package_dir / "manifest.json").unlink()  # what redo --from package does

    fewer_notes = notes.model_copy(update={"set_intros": {"1": "a", "2": "b"}})
    pkg = run_package(sws, StubIA(), show, fewer_notes, speech=FakeSpeechProvider())
    assert (dj / "set2-intro.mp3").exists()
    assert not (dj / "setencore-intro.mp3").exists()  # orphan from the shrunk re-synth is gone
    assert (dj / "segments.json").exists()             # sidecar untouched
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["dj_audio"]["set_intros"] == {"1": "dj-audio/set1-intro.mp3",
                                           "2": "dj-audio/set2-intro.mp3"}


def test_package_speech_failure_leaves_no_manifest(tmp_path: Path):
    sws, show = setup(tmp_path)
    with pytest.raises(SpeechError):
        run_package(sws, StubIA(), show, make_notes(),
                    speech=FakeSpeechProvider(fail=True))
    assert not (sws.package_dir / "manifest.json").exists()


def test_package_voice_without_notes_raises(tmp_path: Path):
    sws, show = setup(tmp_path)
    with pytest.raises(SpeechError):
        run_package(sws, StubIA(), show, notes=None, speech=FakeSpeechProvider())
    assert not (sws.package_dir / "manifest.json").exists()


def _notes_with(text: str) -> DJNotes:
    # One set-1 lead-in carrying the text under test, plus a plain outro.
    return DJNotes(context="", set_intros={"1": text}, outro="Goodnight.",
                   mentioned_songs=[])


def test_package_expands_segue_symbol_before_synthesis(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_briefing(sws)
    show = make_show()
    speech = FakeSpeechProvider()
    run_package(sws, StubIA(), show, _notes_with("We go Help on the Way > Slipknot now."),
                speech=speech)
    spoken = " ".join(speech.calls)
    assert ">" not in spoken
    assert "Help on the Way into Slipknot" in spoken


def test_package_applies_pronunciation_lexicon(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_briefing(sws)
    show = make_show()
    speech = FakeSpeechProvider()
    run_package(sws, StubIA(), show, _notes_with("They opened with Sugaree."),
                speech=speech, lexicon=Lexicon({"Sugaree": "Shugaree"}))
    assert any("Shugaree" in c for c in speech.calls)
    assert not any("Sugaree" in c and "Shugaree" not in c for c in speech.calls)


def test_package_leaves_human_notes_unnormalized(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_briefing(sws)
    # A human-readable dj-notes.md already on disk (as synthesize would write).
    write_artifact(sws.dj_notes_md, "## Set 1 lead-in\nHelp on the Way > Slipknot\n")
    show = make_show()
    pkg = run_package(sws, StubIA(), show, _notes_with("Help on the Way > Slipknot"),
                      speech=FakeSpeechProvider())
    # The packaged human script keeps the readable ">" form — only audio changed.
    assert ">" in (pkg / "dj-notes.md").read_text()


def test_package_normalization_changes_only_affected_cache_key(tmp_path: Path):
    # A clean segment keeps its cache across runs (normalize is identity on it).
    sws = ShowWorkspace(tmp_path / "s")
    write_briefing(sws)
    show = make_show()
    run_package(sws, StubIA(), show, _notes_with("A perfectly clean lead-in here."),
                speech=FakeSpeechProvider())
    second = FakeSpeechProvider()
    run_package(sws, StubIA(), show, _notes_with("A perfectly clean lead-in here."),
                speech=second)
    assert second.calls == []  # nothing re-synthesized


def _bed_file(tmp_path: Path, seconds: float = 1.0) -> Path:
    p = tmp_path / "bed.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(np.full(int(seconds * 24000), 500, dtype="<i2").tobytes())
    return p


def test_package_bed_active_produces_valid_mp3(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_briefing(sws)
    bed = Bed(_bed_file(tmp_path), -20.0)
    pkg = run_package(sws, StubIA(), make_show(), make_notes(),
                      speech=FakeSpeechProvider(), bed=bed)
    audio = list((pkg / "dj-audio").glob("*.mp3"))
    assert audio and all(f.stat().st_size > 0 for f in audio)


def test_package_bed_works_with_chunk(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_briefing(sws)
    bed = Bed(_bed_file(tmp_path), -20.0)
    pkg = run_package(sws, StubIA(), make_show(), make_notes(),
                      speech=FakeSpeechProvider(), bed=bed, chunk=True)
    assert list((pkg / "dj-audio").glob("*.mp3"))


def test_package_bed_gain_change_resynthesizes(tmp_path: Path):
    # Remove the manifest between runs (not force=True, which would bypass the
    # segment cache-key check this test exists to verify). Same gain -> cache
    # hit -> skipped; changed gain -> different key -> re-rendered.
    sws = ShowWorkspace(tmp_path / "s")
    write_briefing(sws)
    bedp = _bed_file(tmp_path)
    run_package(sws, StubIA(), make_show(), make_notes(),
                speech=FakeSpeechProvider(), bed=Bed(bedp, -20.0))

    (sws.package_dir / "manifest.json").unlink()
    same = FakeSpeechProvider()
    run_package(sws, StubIA(), make_show(), make_notes(),
                speech=same, bed=Bed(bedp, -20.0))
    assert same.calls == []                     # unchanged gain -> cache hit

    (sws.package_dir / "manifest.json").unlink()
    changed = FakeSpeechProvider()
    run_package(sws, StubIA(), make_show(), make_notes(),
                speech=changed, bed=Bed(bedp, -10.0))
    assert changed.calls                        # changed gain -> re-rendered


def test_package_no_bed_cache_key_unchanged(tmp_path: Path):
    # A no-bed run's segment key must be byte-identical to pre-feature behavior,
    # so a no-bed repackage still skips unchanged clips. Remove the manifest
    # between runs so the second run actually re-enters _synthesize_dj_audio and
    # exercises the segment cache (without unlink it would short-circuit on the
    # manifest-exists guard, making this trivially pass).
    sws = ShowWorkspace(tmp_path / "s")
    write_briefing(sws)
    run_package(sws, StubIA(), make_show(), make_notes(), speech=FakeSpeechProvider())
    (sws.package_dir / "manifest.json").unlink()
    second = FakeSpeechProvider()
    run_package(sws, StubIA(), make_show(), make_notes(), speech=second)
    assert second.calls == []


def test_package_bad_bed_hard_fails(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    write_briefing(sws)
    bad = tmp_path / "bad.wav"
    with wave.open(str(bad), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"\x00\x00\x00\x00")
    with pytest.raises(SpeechError, match="24kHz mono 16-bit"):
        run_package(sws, StubIA(), make_show(), make_notes(),
                    speech=FakeSpeechProvider(), bed=Bed(bad, -20.0))


def test_package_copies_briefing_and_emits_v3(tmp_path: Path):
    sws, show = setup(tmp_path)
    pkg = run_package(sws, StubIA(), show, make_notes(), force=True)
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["schema_version"] == 3
    assert manifest["briefing"]["json"] == "briefing.json"
    assert manifest["briefing"]["narration"] == "full"
    assert (pkg / "briefing.md").exists() and (pkg / "briefing.json").exists()


def test_package_manifest_briefing_reflects_the_real_briefing(tmp_path: Path):
    sws, show = setup(tmp_path)
    write_briefing(sws, narration="vague", per_set={}, mentioned_songs=[])
    write_vetting(sws)                      # flags=[] -> vetted True
    pkg = run_package(sws, StubIA(), show, make_notes(), force=True)
    m = json.loads((pkg / "manifest.json").read_text())
    assert m["briefing"]["narration"] == "vague"
    assert m["briefing"]["vetted"] is True
    assert (pkg / "briefing.json").read_text() == sws.briefing_json.read_text()


def test_package_hard_fails_without_briefing(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    write_artifact(sws.dj_notes_md, "# notes")
    with pytest.raises(LlamaError, match="no briefing"):
        run_package(sws, StubIA(), show, make_notes(), force=True)
