"""Tests for `emcee run`: scan the station, process every "pending" package,
skip "ready"/"unsupported" ones, and survive per-package failures -- including
a structurally malformed (but valid-JSON) v3 manifest that would otherwise
escape the EmceeError taxonomy as a bare KeyError/AttributeError/TypeError.

Task 9. Uses `backend = "fake"` for TTS (llama's test convention) and
monkeypatches `emcee.process.provider_for` for the LLM, the established
injection seam (see test_process.py).
"""

import json
from pathlib import Path

from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.cli import app
from emcee.errors import EmceeError

from herder import FakeProvider

from tests.helpers import build_package

runner = CliRunner()


def _write_config(root: Path, station_root: Path | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = ['[tts]', 'backend = "fake"', 'voice = "test-voice"', '']
    if station_root is not None:
        lines = ['[station]', f'root = "{station_root}"', ''] + lines
    (root / "config.toml").write_text("\n".join(lines))


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


def _arm_fake_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        process_mod, "provider_for",
        lambda settings, task: FakeProvider(completes=[_good_notes_json()]),
    )


# ---------------------------------------------------------------------------
# [station] root resolution
# ---------------------------------------------------------------------------


def test_run_missing_station_root_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=None)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_run_nonexistent_station_root_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=tmp_path / "does-not-exist")

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_run_station_root_pointing_at_a_file_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    a_file = tmp_path / "not-a-directory.txt"
    a_file.write_text("hi")
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=a_file)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_run_station_root_flag_overrides_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=None)

    result = runner.invoke(app, ["run", "--station-root", str(station)])

    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# run: process pending, skip ready, skip (and never touch) unsupported
# ---------------------------------------------------------------------------


def test_run_processes_exactly_the_unvoiced_package(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    _arm_fake_llm(monkeypatch)

    unvoiced_dir = build_package(station, slug="unvoiced-show", voiced=False)
    voiced_dir = build_package(station, slug="voiced-show", voiced=True)
    v2_dir = station / "v2-show"
    v2_dir.mkdir(parents=True)
    (v2_dir / "manifest.json").write_text(json.dumps({"schema_version": 2}))
    before_v2 = (v2_dir / "manifest.json").read_text()
    before_voiced = (voiced_dir / "manifest.json").read_text()
    before_notes = (voiced_dir / "dj-notes.md").read_text()

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    # the unvoiced package got fully processed
    assert (unvoiced_dir / "dj-notes.md").exists()
    assert (unvoiced_dir / "dj-audio" / "set1-intro.mp3").exists()
    assert (unvoiced_dir / "dj-audio" / "99-outro.mp3").exists()
    assert (unvoiced_dir / "broadcast.m3u").exists()
    manifest = json.loads((unvoiced_dir / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None
    assert manifest["dj_audio"] is not None
    assert f"voiced: {unvoiced_dir.name}" in result.output

    # the already-voiced package was left completely alone
    assert (voiced_dir / "manifest.json").read_text() == before_voiced
    assert (voiced_dir / "dj-notes.md").read_text() == before_notes

    # the v2 package was reported and never modified
    assert (v2_dir / "manifest.json").read_text() == before_v2
    assert "v2-show" in result.output
    assert "unsupported" in result.output


def test_run_skips_all_ready_and_reports_zero_processed(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    _arm_fake_llm(monkeypatch)
    build_package(station, slug="already-ready", voiced=True)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert "voiced:" not in result.output


# ---------------------------------------------------------------------------
# Batch resilience: one failure must not stop the others.
# ---------------------------------------------------------------------------


def test_run_batch_continues_after_one_package_fails(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    _arm_fake_llm(monkeypatch)

    ok_dir = build_package(station, slug="okshow", voiced=False)
    fail_dir = build_package(station, slug="failshow", voiced=False)

    real_process_package = process_mod.process_package

    def flaky_process_package(config, pkg, speech, force=False):
        if pkg.dir.name == "failshow":
            raise RuntimeError("synthetic TTS blowup")
        return real_process_package(config, pkg, speech, force)

    import emcee.cli as cli_mod
    monkeypatch.setattr(cli_mod, "process_package", flaky_process_package)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    # asserted on stderr (not the mixed `.output`) specifically so a mutant
    # that drops `err=True` on the per-package error echo is caught -- both
    # streams get combined into `.output` regardless of routing, so only
    # `.stderr` actually pins where the line went.
    assert "error: failshow: RuntimeError: synthetic TTS blowup" in result.stderr
    # the other (good) package was still processed
    assert (ok_dir / "broadcast.m3u").exists()
    assert f"voiced: {ok_dir.name}" in result.output
    # the failed package was left without a broadcast.m3u (never completed)
    assert not (fail_dir / "broadcast.m3u").exists()


def test_run_malformed_but_valid_json_manifest_reported_and_batch_continues(tmp_path, monkeypatch):
    """A v3 manifest that is valid JSON but structurally wrong (a track dict
    missing "filename") makes `readiness()` raise a bare KeyError -- this
    must be caught broadly, reported as an `error: <slug>: ...` line, and
    must NOT abort processing of the other, well-formed package."""
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    _arm_fake_llm(monkeypatch)

    ok_dir = build_package(station, slug="okshow", voiced=False)

    bad_dir = station / "badshow"
    bad_dir.mkdir(parents=True)
    (bad_dir / "manifest.json").write_text(json.dumps({
        "schema_version": 3,
        "briefing": {"file": "briefing.md", "json": "briefing.json",
                     "narration": "full", "vetted": False},
        "show": {"artist": "X", "date": "1970-01-01", "venue": "V",
                 "city": None, "context": ""},
        "source": {"performance_id": "X/1970-01-01"},
        "tracks": [{"index": 1, "set": "1", "title": "Song"}],  # missing "filename"
        "set_breaks": [],
        "total_duration_sec": 0,
        "set_durations_sec": {},
    }))

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    assert result.exception is None or not isinstance(result.exception, KeyError)
    # asserted on stderr, not the mixed `.output` -- see the batch-continues
    # test above for why. Also asserts the exception TYPE is surfaced
    # (KeyError), not just its bare, unlabeled message ('filename').
    assert "error: badshow: KeyError: 'filename'" in result.stderr
    # the good package still got processed -- proof the batch continued
    assert (ok_dir / "broadcast.m3u").exists()
    assert f"voiced: {ok_dir.name}" in result.output


# ---------------------------------------------------------------------------
# The blessed call convention, pinned: resolve_assignment/speech_for MUST be
# resolved fresh INSIDE the per-package loop. Hoisting them above the loop
# is the one silent-wrong-audio failure mode in the whole package (see
# process.py's module docstring and process_package's docstring) -- a
# hoisted mutant would give every package in the batch the FIRST package's
# voice paired with THAT package's own (correctly re-derived-by-
# process_package) bed, an inconsistent pairing that raises no exception
# and exits 0.
#
# `FakeSpeechProvider.__init__` hardcodes `self.voice = "fake-voice"`
# (tts/fake.py), so the requested voice is only observable at the
# `speech_provider_for` call boundary -- not on the returned object under
# the real backend factory. We tag a fake provider with the voice it was
# asked for, and intercept `_synthesize_dj_audio` (the point where
# `process_package` brings `speech` and the package's own re-derived `bed`
# together) to record (package, voice, bed-file) triples.
# ---------------------------------------------------------------------------


def _hoist_probe_setup(tmp_path, monkeypatch):
    from emcee.config import Assignment
    from emcee.presenters import Presenter, save_presenter

    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    home.mkdir(parents=True)
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n'
        '[assign.profiles.pa]\npresenter = "alice"\n\n'
        '[assign.profiles.pb]\npresenter = "bob"\n'
    )
    save_presenter(home, Presenter(id="alice", name="Alice", sex="female",
                                   voice="alice-voice", character="warm",
                                   bed="/beds/alice.wav"))
    save_presenter(home, Presenter(id="bob", name="Bob", sex="male",
                                   voice="bob-voice", character="dry",
                                   bed="/beds/bob.wav"))
    build_package(station, slug="a-show", voiced=False, profile="pa")
    build_package(station, slug="b-show", voiced=False, profile="pb")
    _arm_fake_llm(monkeypatch)

    calls: list[tuple[str, str, str | None]] = []

    class TaggedProvider:
        def __init__(self, voice):
            self.voice = voice
            self.model = "tagged-model"

        def synthesize(self, *a, **k):
            raise AssertionError("synthesize should not run; _synthesize_dj_audio is faked")

        def close(self):
            pass

    def fake_synth(pkg_dir, notes, speech, force, chunk=False, lexicon=None, bed=None):
        from emcee.models import DJAudioBlock
        calls.append((pkg_dir.name, speech.voice, bed.path.name if bed is not None else None))
        return DJAudioBlock(
            set_intros={k: f"dj-audio/set{k}-intro.mp3" for k in notes.set_intros},
            outro="dj-audio/99-outro.mp3",
        )

    monkeypatch.setattr(process_mod, "_synthesize_dj_audio", fake_synth)
    monkeypatch.setattr(process_mod, "speech_provider_for",
                        lambda config, voice, clone_ref=None: TaggedProvider(voice))
    return calls


def test_run_never_pairs_one_packages_voice_with_anothers_bed(tmp_path, monkeypatch):
    calls = _hoist_probe_setup(tmp_path, monkeypatch)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    by_pkg = {name: (voice, bed) for name, voice, bed in calls}
    assert by_pkg == {
        "a-show": ("alice-voice", "alice.wav"),
        "b-show": ("bob-voice", "bob.wav"),
    }


def test_hoisting_resolve_assignment_and_speech_for_breaks_the_pairing(tmp_path, monkeypatch):
    """Sanity-checks the probe above: this pins the *mutant* shape the
    previous test guards against, proving the probe would actually catch a
    hoisted `resolve_assignment`/`speech_for` -- not just exercise a code
    path that happens not to fail. Does not touch cli.py; it directly
    replays the hoisted (wrong) call shape a mutation would produce, using
    the exact same production `resolve_assignment`/`speech_for`."""
    from emcee.config import load_config
    from emcee.package_io import Package
    from emcee.process import resolve_assignment, speech_for

    calls = _hoist_probe_setup(tmp_path, monkeypatch)
    config = load_config()
    root = config.station.root
    packages = [Package(root / "a-show"), Package(root / "b-show")]

    # The hoisted mutant: resolve ONCE from the first package, reuse for all.
    manifest = packages[0].manifest()
    presenter, _title = resolve_assignment(config, manifest)
    speech, _bed = speech_for(config, presenter)
    for pkg in packages:
        process_mod.process_package(config, pkg, speech, False)

    by_pkg = {name: (voice, bed) for name, voice, bed in calls}
    # b-show got alice's voice (from a-show's resolution) paired with its
    # OWN, correctly-re-derived bob.wav bed -- the exact silent mismatch
    # I1 warns about. No exception, but wrong audio.
    assert by_pkg["b-show"] == ("alice-voice", "bob.wav")
    assert by_pkg["b-show"] != ("bob-voice", "bob.wav")


# ---------------------------------------------------------------------------
# A raising speech.close() on an otherwise-successful package must not turn
# a completed package into a reported failure.
# ---------------------------------------------------------------------------


def _bad_notes_json_unknown_song() -> str:
    # set_intros satisfy the structural checks (covers both non-encore
    # sets); mentioned_songs names a song that isn't in the package's
    # tracks at all -- the one guard problem script_guard will report.
    return json.dumps({
        "context": "Spring '73 tour",
        "set_intros": {
            "1": "Tonight: the Dead at RFK.",
            "2": "Set two kicks off strong.",
        },
        "outro": "Thanks for listening.",
        "mentioned_songs": ["Fire on the Mountain"],
    })


def test_run_guard_failure_surfaces_detail_lines_on_stderr(tmp_path, monkeypatch):
    """Fix 2 (whole-branch review, Important): a scriptwrite guard failure's
    EmceeError.details -- the specific fact-check problems -- must reach the
    operator through `run`, not just the bare "failed after retry" message
    (spec sec 2: failures must be "logged with reasons"). Same rendering
    `main_cli` already gives HerderError/EmceeError: message, then each
    detail line indented underneath."""
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    bad = _bad_notes_json_unknown_song()
    monkeypatch.setattr(
        process_mod, "provider_for",
        lambda settings, task: FakeProvider(completes=[bad, bad]),  # both retry attempts fail
    )

    build_package(station, slug="badscript", voiced=False)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 1
    # the message itself: an EmceeError, so NOT type-prefixed
    assert "error: badscript: scriptwrite failed fact-checking after retry" in result.stderr
    assert "EmceeError:" not in result.stderr
    # the actual diagnosis -- previously silently lost -- now reaches stderr
    assert "dj notes mention unknown song: Fire on the Mountain" in result.stderr


def test_run_success_survives_a_raising_speech_close(tmp_path, monkeypatch):
    from emcee.tts.fake import FakeSpeechProvider

    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    _arm_fake_llm(monkeypatch)

    class CloseBlowsUpProvider(FakeSpeechProvider):
        def close(self):
            raise RuntimeError("close blew up")

    monkeypatch.setattr(process_mod, "speech_provider_for",
                        lambda config, voice, clone_ref=None: CloseBlowsUpProvider())

    pkg_dir = build_package(station, slug="closer", voiced=False)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""  # no error line for a package that actually succeeded
    manifest = json.loads((pkg_dir / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None
    assert manifest["dj_audio"] is not None
    assert (pkg_dir / "broadcast.m3u").exists()
    assert f"voiced: {pkg_dir.name}" in result.output
    assert "1 package(s) voiced" in result.output
    assert "with errors" not in result.output
