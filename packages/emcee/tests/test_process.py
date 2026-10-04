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
from emcee.process import (_resolve_bed, ad_hoc_bed, ad_hoc_speech, process_package,
                           resolve_assignment, speech_for)
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
        "presenter": None,  # house narrator: key present, null
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


def _voice_and_read_presenter(tmp_path, monkeypatch, config_kwargs, profile):
    monkeypatch.setattr(
        "emcee.process.provider_for",
        lambda settings, task: FakeProvider(completes=[_good_notes_json()]),
    )
    save_presenter(tmp_path / "home", _presenter(id="casey"))
    pkg = Package(build_package(tmp_path / "station", voiced=False, profile=profile))
    config = EmceeConfig(root=tmp_path / "home", **config_kwargs)
    process_package(config, pkg, FakeSpeechProvider())
    return json.loads(pkg.manifest_path.read_text())["dj_audio"]


def test_process_package_records_assigned_presenter(tmp_path, monkeypatch):
    dj_audio = _voice_and_read_presenter(
        tmp_path, monkeypatch,
        {"assign": {"profiles": {"prime-dead": Assignment(presenter="casey", title="T")}}},
        "prime-dead")
    assert dj_audio["presenter"] == "casey"


def test_process_package_records_default_presenter(tmp_path, monkeypatch):
    dj_audio = _voice_and_read_presenter(
        tmp_path, monkeypatch, {"assign": {"default": "casey"}}, "unmatched")
    assert dj_audio["presenter"] == "casey"


def test_process_package_records_null_presenter_for_house(tmp_path, monkeypatch):
    dj_audio = _voice_and_read_presenter(tmp_path, monkeypatch, {}, None)
    assert "presenter" in dj_audio and dj_audio["presenter"] is None


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


# ---------------------------------------------------------------------------
# Ad-hoc narration (`emcee say`): voice + bed resolution
# ---------------------------------------------------------------------------
# `say` reuses the station's voice and bed configuration but lets the command
# line override either, so an ad-hoc read is not forced through whatever the
# station happens to be set up to broadcast.


def test_ad_hoc_speech_falls_back_to_the_house_voice():
    config = EmceeConfig(tts=TTSConfig(backend="voxtral", voice="house-preset",
                                       api_key="k"))

    speech = ad_hoc_speech(config)

    assert speech.voice == "house-preset"


def test_ad_hoc_speech_prefers_an_explicit_preset_over_the_house_voice():
    config = EmceeConfig(tts=TTSConfig(backend="voxtral", voice="house-preset",
                                       api_key="k"))

    speech = ad_hoc_speech(config, voice="other-preset")

    assert speech.voice == "other-preset"


def test_ad_hoc_speech_clones_the_given_reference_clip(tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"REFERENCE-AUDIO-BYTES")
    config = EmceeConfig(tts=TTSConfig(backend="voxtral", voice="house-preset",
                                       api_key="k"))

    speech = ad_hoc_speech(config, clone_ref=str(ref))

    # Clone mode ignores the house preset entirely (VoxtralProvider stamps a
    # content-hash voice id for a cloned reference).
    assert speech.voice.startswith("clone:")


def test_ad_hoc_speech_uses_a_presenters_own_voice():
    config = EmceeConfig(tts=TTSConfig(backend="voxtral", voice="house-preset",
                                       api_key="k"))

    speech = ad_hoc_speech(config, presenter=_presenter(voice="waldo-preset"))

    assert speech.voice == "waldo-preset"


def test_ad_hoc_speech_rejects_more_than_one_voice_source(tmp_path):
    config = EmceeConfig(tts=TTSConfig(backend="voxtral", api_key="k"))

    with pytest.raises(EmceeError, match="mutually exclusive"):
        ad_hoc_speech(config, voice="a-preset", presenter=_presenter())


def test_ad_hoc_bed_defaults_to_the_station_bed():
    config = EmceeConfig(tts=TTSConfig(bed="/station/bed.wav", bed_gain_db=-18.0))

    bed = ad_hoc_bed(config, None)

    assert bed == Bed(Path("/station/bed.wav"), -18.0)


def test_ad_hoc_bed_prefers_a_presenters_own_bed():
    config = EmceeConfig(tts=TTSConfig(bed="/station/bed.wav", bed_gain_db=-18.0))

    bed = ad_hoc_bed(config, _presenter(bed="/waldo/bed.wav"))

    # The presenter owns the bed FILE; gain stays station-level, matching
    # `_resolve_bed`.
    assert bed == Bed(Path("/waldo/bed.wav"), -18.0)


def test_ad_hoc_bed_path_overrides_presenter_and_station():
    config = EmceeConfig(tts=TTSConfig(bed="/station/bed.wav", bed_gain_db=-18.0))

    bed = ad_hoc_bed(config, _presenter(bed="/waldo/bed.wav"),
                     bed_path=Path("/cli/bed.wav"))

    assert bed == Bed(Path("/cli/bed.wav"), -18.0)


def test_ad_hoc_bed_no_bed_wins_over_every_other_source():
    config = EmceeConfig(tts=TTSConfig(bed="/station/bed.wav"))

    bed = ad_hoc_bed(config, _presenter(bed="/waldo/bed.wav"),
                     bed_path=Path("/cli/bed.wav"), no_bed=True)

    assert bed is None


def test_ad_hoc_bed_gain_override_replaces_the_station_gain():
    config = EmceeConfig(tts=TTSConfig(bed="/station/bed.wav", bed_gain_db=-18.0))

    bed = ad_hoc_bed(config, None, gain_db=-6.0)

    assert bed == Bed(Path("/station/bed.wav"), -6.0)


def test_ad_hoc_bed_is_none_when_nothing_configures_one():
    assert ad_hoc_bed(EmceeConfig(), None) is None


def test_assignment_for_three_rules_and_labels():
    from emcee.config import AssignConfig, Assignment, EmceeConfig
    from emcee.process import AssignmentView, assignment_for, presenter_label

    cfg = EmceeConfig(assign=AssignConfig(
        default="dflt", profiles={"dead": Assignment(presenter="billyg", title="Host")}))
    hit = assignment_for(cfg, "dead")
    assert hit == AssignmentView("billyg", "Host", "profile")
    assert presenter_label(hit) == "billyg"
    miss = assignment_for(cfg, "phish")
    assert miss == AssignmentView("dflt", None, "default")
    assert presenter_label(miss) == "dflt (default)"
    assert assignment_for(cfg, None).source == "default"
    house = assignment_for(EmceeConfig(), "dead")
    assert house == AssignmentView(None, None, "house")
    assert presenter_label(house) == "house"


from herder import TaskFailed

from emcee.tts.provider import SpeechBlocked

CLEAN_S1 = "China Cat Sunflower leads set two."
BLOCKED_S2 = "The climax comes a little early tonight."
SEG2 = f"{CLEAN_S1} {BLOCKED_S2}"
SET1 = "Tonight: the Dead at RFK. Opens with Morning Dew."


def _arm(monkeypatch, rephrases, notes_json=None):
    """Route provider_for: scriptwrite -> one script, rephrase -> `rephrases`
    queue. Returns (rephrase FakeProvider, list of tasks requested)."""
    script = FakeProvider(completes=[notes_json or _good_notes_json(
        set_intros={"1": SET1, "2": SEG2})])
    rephrase = FakeProvider(completes=[json.dumps({"text": t}) if isinstance(t, str) else t
                                       for t in rephrases])
    requested: list[str] = []

    def fake_provider_for(settings, task):
        requested.append(task)
        return {"scriptwrite": script, "rephrase": rephrase}[task]

    monkeypatch.setattr("emcee.process.provider_for", fake_provider_for)
    return rephrase, requested


def _setup(tmp_path):
    # Unchunked: these tests count whole-segment calls and exercise the
    # whole-passage block, which only exists unchunked. The chunked repair
    # path has its own test (test_chunked_repair_through_process_package).
    pkg = Package(build_package(tmp_path / "station", voiced=False))
    return pkg, EmceeConfig(root=tmp_path / "home", tts=TTSConfig(chunk=False))


def test_blocked_sentence_is_rephrased_and_package_succeeds(tmp_path, monkeypatch):
    revised = f"{CLEAN_S1} The peak arrives a little early tonight."
    rephrase, _ = _arm(monkeypatch, [revised])
    pkg, config = _setup(tmp_path)
    speech = FakeSpeechProvider(block="climax")

    process_package(config, pkg, speech)

    m = pkg.manifest()
    assert m["dj_notes"]["set_intros"]["2"] == revised
    notes_md = (pkg.dir / "dj-notes.md").read_text()
    assert "The peak arrives" in notes_md and "climax" not in notes_md
    assert speech.calls.count(SET1) == 1          # set 1 rendered once, then cached
    assert revised in speech.calls                # the revision is what was voiced
    assert f'"{BLOCKED_S2}"' in rephrase.calls[0][1]  # the located sentence, quoted, filled `blocked`


def test_force_still_renders_each_clip_once(tmp_path, monkeypatch):
    _arm(monkeypatch, [f"{CLEAN_S1} The peak arrives a little early tonight."])
    pkg, config = _setup(tmp_path)
    speech = FakeSpeechProvider(block="climax")

    process_package(config, pkg, speech, force=True)

    assert speech.calls.count(SET1) == 1


def test_reblocked_twice_raises_and_manifest_untouched(tmp_path, monkeypatch):
    rephrase, _ = _arm(monkeypatch, [f"{CLEAN_S1} The climax lands early tonight.",
                                     f"{CLEAN_S1} The climax hits early tonight."])
    pkg, config = _setup(tmp_path)
    before = pkg.manifest_path.read_text()

    with pytest.raises(EmceeError) as ei:
        process_package(config, pkg, FakeSpeechProvider(block="climax"))

    assert "set2-intro" in str(ei.value) and "sexual" in str(ei.value)
    assert any("also blocked" in d for d in ei.value.details)
    assert "also blocked" in rephrase.calls[1][1]
    assert pkg.manifest_path.read_text() == before


def test_guard_failing_rephrase_is_never_voiced(tmp_path, monkeypatch):
    bad = f"{CLEAN_S1} All three sets peak early tonight."   # guard: 3 sets vs 2
    good = f"{CLEAN_S1} The peak arrives a little early tonight."
    rephrase, _ = _arm(monkeypatch, [bad, good])
    pkg, config = _setup(tmp_path)
    speech = FakeSpeechProvider(block="climax")

    process_package(config, pkg, speech)

    assert not any("three sets" in c for c in speech.calls)
    assert "claim 3 sets" in rephrase.calls[1][1]
    assert "The peak arrives" in (pkg.dir / "dj-notes.md").read_text()
    assert pkg.manifest()["dj_notes"]["set_intros"]["2"] == good


def test_unchanged_rephrase_consumes_an_attempt(tmp_path, monkeypatch):
    good = f"{CLEAN_S1} The peak arrives a little early tonight."
    rephrase, _ = _arm(monkeypatch, [SEG2, good])
    pkg, config = _setup(tmp_path)

    process_package(config, pkg, FakeSpeechProvider(block="climax"))

    assert "unchanged" in rephrase.calls[1][1]
    assert pkg.manifest()["dj_notes"]["set_intros"]["2"] == good


def test_whole_passage_block_is_not_rephrased(tmp_path, monkeypatch):
    rephrase, requested = _arm(monkeypatch, [])
    pkg, config = _setup(tmp_path)
    before = pkg.manifest_path.read_text()

    with pytest.raises(SpeechBlocked) as ei:
        process_package(config, pkg, FakeSpeechProvider(block="two. The climax"))

    assert ei.value.whole_passage is True and ei.value.segment == "set2-intro"
    assert "rephrase" not in requested and rephrase.calls == []
    assert pkg.manifest_path.read_text() == before


def test_containment_failing_rephrase_is_never_voiced(tmp_path, monkeypatch):
    rejected = "Jack Straw arrives a little early tonight."
    bad = f"{CLEAN_S1} {rejected}"   # names a track the segment did not; script_guard can't see it
    good = f"{CLEAN_S1} The peak arrives a little early tonight."
    rephrase, _ = _arm(monkeypatch, [bad, good])
    pkg, config = _setup(tmp_path)
    speech = FakeSpeechProvider(block="climax")

    process_package(config, pkg, speech)

    assert not any("Jack Straw" in c for c in speech.calls)
    second_prompt = rephrase.calls[1][1]
    assert "names a track the original did not: Jack Straw" in second_prompt
    # Attempt 2 rephrases the ADOPTED text, never the rejected candidate.
    assert SEG2 in second_prompt and rejected not in second_prompt
    assert pkg.manifest()["dj_notes"]["set_intros"]["2"] == good


def test_two_blocked_segments_each_get_their_own_budget(tmp_path, monkeypatch):
    outro = "I Know You Rider sends us off. The climax of the night was early."
    notes = _good_notes_json(set_intros={"1": SET1, "2": SEG2}, outro=outro)
    bad2 = f"{CLEAN_S1} All three sets peak early tonight."   # guard rejects: attempt 1
    rev2 = f"{CLEAN_S1} The peak arrives a little early tonight."
    rev_outro = "I Know You Rider sends us off. The peak of the night came early."
    # Three attempts in all (two for set 2, one for the outro): a single
    # package-wide budget of 2 would raise on the outro.
    _arm(monkeypatch, [bad2, rev2, rev_outro], notes_json=notes)
    pkg, config = _setup(tmp_path)

    process_package(config, pkg, FakeSpeechProvider(block="climax"))

    m = pkg.manifest()
    assert m["dj_notes"]["set_intros"]["2"] == rev2
    assert m["dj_notes"]["outro"] == rev_outro


def test_rephrase_llm_failure_leaves_manifest_untouched(tmp_path, monkeypatch):
    script = FakeProvider(completes=[_good_notes_json(set_intros={"1": SET1, "2": SEG2})])
    rephrase = FakeProvider(completes=["not json", "still not json", "nope"])
    monkeypatch.setattr("emcee.process.provider_for",
                        lambda settings, task: {"scriptwrite": script, "rephrase": rephrase}[task])
    pkg, config = _setup(tmp_path)
    before = pkg.manifest_path.read_text()

    with pytest.raises(EmceeError) as ei:
        process_package(config, pkg, FakeSpeechProvider(block="climax"))

    assert "set2-intro" in str(ei.value) and "rephrase task failed" in str(ei.value)
    assert isinstance(ei.value.__cause__, TaskFailed)
    assert any(BLOCKED_S2 in d for d in ei.value.details)
    assert pkg.manifest_path.read_text() == before


def test_chunked_repair_through_process_package(tmp_path, monkeypatch, capsys):
    revised = f"{CLEAN_S1} The peak arrives a little early tonight."
    _, requested = _arm(monkeypatch, [revised])
    pkg, _ = _setup(tmp_path)
    config = EmceeConfig(root=tmp_path / "home", tts=TTSConfig(chunk=True))

    process_package(config, pkg, FakeSpeechProvider(block="climax"), force=True)

    out = capsys.readouterr().out
    assert "rephrased" in out and "blocked:" in out and "revised:" in out
    assert pkg.manifest()["dj_notes"]["set_intros"]["2"] == revised
    assert requested.count("rephrase") == 1
