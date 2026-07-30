"""Tests for `emcee.process`: presenter assignment resolution, voice/bed
resolution (`speech_for`), and the `process_package` orchestrator.

Also carries the `interleave_broadcast`/`broadcast_m3u_text` parity tests
ported from llama's `test_manifest.py` (the functions live in `emcee.audio`,
but Task 8's plan groups them here alongside the orchestrator that calls
them).
"""

import json
from pathlib import Path

import pytest
from herder import FakeProvider

from emcee.audio import broadcast_m3u_text, interleave_broadcast, m3u_text
from emcee.config import Assignment, EmceeConfig, TTSConfig
from emcee.errors import EmceeError
from emcee.models import DJAudioBlock
from emcee.package_io import Package
from emcee.presenters import Presenter, save_presenter
from emcee.process import _resolve_bed, process_package, resolve_assignment, speech_for
from emcee.tts.bed import Bed
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.provider import SpeechError

from tests.helpers import build_package

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _presenter(**overrides) -> Presenter:
    d = dict(id="waldo", name="Waldo", sex="male", voice="waldo-preset",
             character="Laid-back, knowledgeable.")
    d.update(overrides)
    return Presenter(**d)


def _good_notes_json(**overrides) -> str:
    # Matches build_package's default fixture (sets=("1", "2"), encore=True):
    # tracks are Morning Dew/Sugaree (set 1), Jack Straw/China Cat Sunflower
    # (set 2), I Know You Rider (encore) -- all valid mentioned_songs.
    d = {
        "context": "Spring '73 tour",
        "set_intros": {
            "1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
            "2": "China Cat Sunflower leads set two.",
        },
        "outro": "I Know You Rider sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"],
    }
    d.update(overrides)
    return json.dumps(d)


# ---------------------------------------------------------------------------
# resolve_assignment: profile match -> [assign] default -> neutral
# ---------------------------------------------------------------------------


def test_resolve_assignment_matches_profile(tmp_path):
    save_presenter(tmp_path, _presenter(id="casey"))
    config = EmceeConfig(
        root=tmp_path,
        assign={"profiles": {"prime-dead": Assignment(presenter="casey", title="The Primal Dead Hour")}},
    )
    manifest = Package(build_package(tmp_path / "station", profile="prime-dead")).manifest()

    presenter, title = resolve_assignment(config, manifest)

    assert presenter is not None and presenter.id == "casey"
    assert title == "The Primal Dead Hour"


def test_resolve_assignment_falls_back_to_default_when_profile_unmatched(tmp_path):
    save_presenter(tmp_path, _presenter(id="waldo"))
    config = EmceeConfig(root=tmp_path, assign={"default": "waldo"})
    # Profile stamped in the manifest has no [assign.profiles.*] entry.
    manifest = Package(build_package(tmp_path / "station", profile="some-other-profile")).manifest()

    presenter, title = resolve_assignment(config, manifest)

    assert presenter is not None and presenter.id == "waldo"
    assert title is None


def test_resolve_assignment_falls_back_to_default_when_no_profile_stamped(tmp_path):
    save_presenter(tmp_path, _presenter(id="waldo"))
    config = EmceeConfig(root=tmp_path, assign={"default": "waldo"})
    manifest = Package(build_package(tmp_path / "station", profile=None)).manifest()

    presenter, title = resolve_assignment(config, manifest)

    assert presenter is not None and presenter.id == "waldo"
    assert title is None


def test_resolve_assignment_neutral_when_nothing_configured(tmp_path):
    config = EmceeConfig(root=tmp_path)
    manifest = Package(build_package(tmp_path / "station", profile="prime-dead")).manifest()

    presenter, title = resolve_assignment(config, manifest)

    assert presenter is None
    assert title is None


# ---------------------------------------------------------------------------
# speech_for: presenter-owns-its-voice precedence + bed folding
# ---------------------------------------------------------------------------


def test_speech_for_presenter_voice_wins_and_house_clone_never_bleeds_in(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "emcee.process.speech_provider_for",
        lambda config, voice, clone_ref=None: calls.append((voice, clone_ref)) or "sentinel",
    )
    presenter = _presenter(voice="presenter-preset")  # voice set, voice_clone None
    config = EmceeConfig(tts=TTSConfig(voice="house-voice", voice_clone="house-clone.wav"))

    speech, bed = speech_for(config, presenter)

    assert speech == "sentinel"
    assert calls == [("presenter-preset", None)]  # house voice_clone did NOT bleed in
    assert bed is None


def test_speech_for_presenter_voice_clone_used_as_voice_and_clone_ref(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "emcee.process.speech_provider_for",
        lambda config, voice, clone_ref=None: calls.append((voice, clone_ref)) or "sentinel",
    )
    presenter = _presenter(voice=None, voice_clone="/refs/casey.wav")

    speech_for(EmceeConfig(root=tmp_path), presenter)

    assert calls == [("/refs/casey.wav", "/refs/casey.wav")]


def test_speech_for_no_presenter_falls_back_to_house_voice(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "emcee.process.speech_provider_for",
        lambda config, voice, clone_ref=None: calls.append((voice, clone_ref)) or "sentinel",
    )
    config = EmceeConfig(tts=TTSConfig(voice="house-voice", voice_clone="house-clone.wav"))

    speech_for(config, None)

    assert calls == [("house-voice", "house-clone.wav")]


def test_speech_for_raises_when_no_voice_resolvable_at_all(tmp_path):
    # Match on wording unique to speech_for's own message, not just
    # "[tts] voice" -- speech_provider_for's voxtral branch also raises a
    # SpeechError (an EmceeError subclass) containing "[tts] voice" when no
    # voice is configured, so a looser match/guard-removal mutation would
    # slip past undetected if speech_for's own `if not voice:` guard were
    # ever deleted (control would reach speech_provider_for instead and
    # still raise *an* EmceeError matching the loose pattern).
    with pytest.raises(EmceeError, match="give the profile a presenter") as exc_info:
        speech_for(EmceeConfig(root=tmp_path), None)
    assert type(exc_info.value) is EmceeError


def test_speech_for_folds_in_presenter_bed(monkeypatch):
    monkeypatch.setattr("emcee.process.speech_provider_for", lambda *a, **k: "sentinel")
    presenter = _presenter(bed="/beds/casey.wav")
    config = EmceeConfig(tts=TTSConfig(voice="house-voice", bed="/beds/house.wav", bed_gain_db=-15.0))

    _, bed = speech_for(config, presenter)

    assert bed == Bed(Path("/beds/casey.wav"), -15.0)  # gain is always the station's


def test_resolve_bed_falls_back_to_house_bed_when_presenter_has_none(tmp_path):
    presenter = _presenter()  # no bed override
    config = EmceeConfig(root=tmp_path, tts=TTSConfig(bed="/beds/house.wav", bed_gain_db=-20.0))
    assert _resolve_bed(config, presenter) == Bed(Path("/beds/house.wav"), -20.0)


def test_resolve_bed_none_when_neither_set(tmp_path):
    assert _resolve_bed(EmceeConfig(root=tmp_path), _presenter()) is None


# ---------------------------------------------------------------------------
# process_package: manifest written LAST -- a mid-pipeline failure must
# leave the manifest byte-for-byte unchanged (no partial "looks ready" state)
# ---------------------------------------------------------------------------


def test_process_package_writes_dj_notes_and_audio_and_manifest_last(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "emcee.process.provider_for",
        lambda settings, task: FakeProvider(completes=[_good_notes_json()]),
    )
    pkg_dir = build_package(tmp_path / "station", voiced=False)
    pkg = Package(pkg_dir)
    config = EmceeConfig(root=tmp_path / "home")

    process_package(config, pkg, FakeSpeechProvider())

    assert (pkg_dir / "dj-notes.md").exists()
    assert (pkg_dir / "dj-audio" / "set1-intro.mp3").exists()
    assert (pkg_dir / "dj-audio" / "99-outro.mp3").exists()
    assert (pkg_dir / "broadcast.m3u").exists()
    m = pkg.manifest()
    assert m["dj_notes"]["outro"] == "I Know You Rider sends us off. Thanks for listening."
    assert m["dj_audio"] == {
        "set_intros": {"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        "outro": "dj-audio/99-outro.mp3",
    }


def test_process_package_manifest_unchanged_on_tts_failure_after_script(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "emcee.process.provider_for",
        lambda settings, task: FakeProvider(completes=[_good_notes_json()]),
    )
    pkg_dir = build_package(tmp_path / "station", voiced=False)
    pkg = Package(pkg_dir)
    config = EmceeConfig(root=tmp_path / "home")
    before = pkg.manifest_path.read_text()

    with pytest.raises(SpeechError):
        process_package(config, pkg, FakeSpeechProvider(fail=True))

    # The manifest is byte-for-byte untouched -- proof the manifest write is
    # genuinely last: the script step ran and wrote dj-notes.md to disk
    # (proving we got PAST write_script), yet the manifest still has neither
    # block, so station.readiness reads this package as still `pending`
    # regardless of the dj-notes.md a failed run left behind.
    assert (pkg_dir / "dj-notes.md").exists()  # script step did run
    after = pkg.manifest_path.read_text()
    assert after == before
    m = json.loads(after)
    assert m.get("dj_notes") is None
    assert m.get("dj_audio") is None
    assert not (pkg_dir / "broadcast.m3u").exists()


def test_process_package_uses_resolved_presenter_for_the_script(tmp_path, monkeypatch):
    captured = {}

    def fake_write_script(pkg, provider, presenter, title):
        captured["presenter"] = presenter
        captured["title"] = title
        from emcee.models import ScriptNotes
        return ScriptNotes.model_validate_json(_good_notes_json())

    monkeypatch.setattr("emcee.process.write_script", fake_write_script)
    monkeypatch.setattr(
        "emcee.process.provider_for",
        lambda settings, task: FakeProvider(completes=[]),  # never called; write_script is patched
    )
    save_presenter(tmp_path / "home", _presenter(id="casey"))
    pkg_dir = build_package(tmp_path / "station", voiced=False, profile="prime-dead")
    pkg = Package(pkg_dir)
    config = EmceeConfig(
        root=tmp_path / "home",
        assign={"profiles": {"prime-dead": Assignment(presenter="casey", title="The Show")}},
    )

    process_package(config, pkg, FakeSpeechProvider())

    assert captured["presenter"].id == "casey"
    assert captured["title"] == "The Show"


# ---------------------------------------------------------------------------
# broadcast.m3u interleave -- parity with llama's test_manifest.py
# ---------------------------------------------------------------------------


def make_tracks() -> list[dict]:
    return [
        {"index": 1, "set": "1", "title": "Morning Dew", "filename": "01 - Morning Dew.mp3"},
        {"index": 2, "set": "2", "title": "Dark Star", "filename": "02 - Dark Star.mp3"},
        {"index": 3, "set": "encore", "title": "Johnny B. Goode",
         "filename": "03 - Johnny B. Goode.mp3"},
    ]


def make_dj_audio() -> DJAudioBlock:
    return DJAudioBlock(
        set_intros={"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        outro="dj-audio/99-outro.mp3",
    )


def test_m3u_text():
    # m3u_text is byte-identical to llama's port and has no src/ caller of
    # its own (only broadcast_m3u_text is used by process_package) but it's
    # part of the faithful manifest.py port range and deserves its own
    # coverage rather than riding along on broadcast_m3u_text's tests.
    text = m3u_text(["01 - Morning Dew.mp3", "02 - Dark Star.mp3"])
    lines = text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "audio/01 - Morning Dew.mp3"
    assert text.endswith("\n")


def test_interleave_broadcast_slots_leadins_and_outro():
    # Each set's lead-in precedes that set's first track; the encore (no
    # set_intros key) gets none; the outro closes.
    assert interleave_broadcast(make_tracks(), make_dj_audio()) == [
        "dj-audio/set1-intro.mp3",
        "audio/01 - Morning Dew.mp3",
        "dj-audio/set2-intro.mp3",
        "audio/02 - Dark Star.mp3",
        "audio/03 - Johnny B. Goode.mp3",  # encore: plays straight into the outro
        "dj-audio/99-outro.mp3",
    ]


def test_broadcast_m3u_text_wraps_interleaved_paths():
    text = broadcast_m3u_text(make_tracks(), make_dj_audio())
    lines = text.splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "dj-audio/set1-intro.mp3"
    assert lines[2] == "audio/01 - Morning Dew.mp3"
    assert lines[-1] == "dj-audio/99-outro.mp3"
    assert text.endswith("\n")
