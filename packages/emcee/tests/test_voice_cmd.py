"""Tests for `emcee voice`: script + voice + broadcast-assemble ONE
delivered package, including `--fresh`'s per-clip re-roll (ported from
llama's `packages/llama/tests/test_voice_cmd.py` fresh cases, adapted to
emcee's single-package call shape -- no selectors, no batch).

Task 9. Shares a basename with llama's own `test_voice_cmd.py`;
`packages/emcee/tests/__init__.py` disambiguates the two, so it must not be
touched or renamed away.
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
# voice: one package, single path argument
# ---------------------------------------------------------------------------


def test_voice_processes_a_single_unvoiced_package(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    _arm_fake_llm(monkeypatch)
    pkg_dir = build_package(station, slug="showA", voiced=False)

    result = runner.invoke(app, ["voice", str(pkg_dir)])

    assert result.exit_code == 0, result.output
    assert (pkg_dir / "dj-notes.md").exists()
    assert (pkg_dir / "dj-audio" / "set1-intro.mp3").exists()
    assert (pkg_dir / "dj-audio" / "99-outro.mp3").exists()
    assert (pkg_dir / "broadcast.m3u").exists()
    manifest = json.loads((pkg_dir / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None
    assert manifest["dj_audio"] is not None
    assert f"voiced: {pkg_dir}" in result.output


def test_voice_missing_manifest_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    empty_dir = tmp_path / "not-a-package"
    empty_dir.mkdir()

    result = runner.invoke(app, ["voice", str(empty_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)


def test_voice_v2_package_raises_unsupported_and_is_untouched(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    v2_dir = tmp_path / "v2-show"
    v2_dir.mkdir()
    (v2_dir / "manifest.json").write_text(json.dumps({"schema_version": 2}))
    before = (v2_dir / "manifest.json").read_text()

    result = runner.invoke(app, ["voice", str(v2_dir)])

    assert result.exit_code == 1
    assert (v2_dir / "manifest.json").read_text() == before


# ---------------------------------------------------------------------------
# --fresh: per-segment TTS re-roll (delete the named clip so reprocessing
# re-synthesizes only it; the untouched sibling clip's on-disk bytes never
# change because its cached hash key still matches).
# ---------------------------------------------------------------------------


def _fully_voiced_package(tmp_path, station, monkeypatch, slug="showA"):
    """Voice a package for real once (seeds a correct dj-audio/segments.json
    cache), then stamp both clips with identifiable placeholder bytes so a
    later untouched-vs-changed comparison is unambiguous (FakeSpeechProvider
    always returns the same static SILENT_MP3 bytes for every real
    synthesis, so comparing "did this clip's bytes change" only works if we
    first overwrite it with bytes a real re-synth could never reproduce)."""
    _arm_fake_llm(monkeypatch)
    pkg_dir = build_package(station, slug=slug, voiced=False)
    r = runner.invoke(app, ["voice", str(pkg_dir)])
    assert r.exit_code == 0, r.output
    audio_dir = pkg_dir / "dj-audio"
    (audio_dir / "set1-intro.mp3").write_bytes(b"stale-set1-take")
    (audio_dir / "99-outro.mp3").write_bytes(b"stale-99-take")
    return pkg_dir


def test_voice_fresh_rerolls_only_named_clip(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    audio_dir = pkg_dir / "dj-audio"

    _arm_fake_llm(monkeypatch)
    result = runner.invoke(app, ["voice", str(pkg_dir), "--fresh", "set1-intro"])

    assert result.exit_code == 0, result.output
    assert "set1-intro" in result.output
    # named clip re-rendered: no longer the stale placeholder bytes
    assert (audio_dir / "set1-intro.mp3").read_bytes() != b"stale-set1-take"
    # sibling clip untouched: still byte-identical to its stale placeholder
    assert (audio_dir / "99-outro.mp3").read_bytes() == b"stale-99-take"


def test_voice_fresh_multiple_clips_rerolls_both(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    audio_dir = pkg_dir / "dj-audio"

    _arm_fake_llm(monkeypatch)
    result = runner.invoke(
        app, ["voice", str(pkg_dir), "--fresh", "set1-intro", "--fresh", "99-outro"])

    assert result.exit_code == 0, result.output
    assert (audio_dir / "set1-intro.mp3").read_bytes() != b"stale-set1-take"
    assert (audio_dir / "99-outro.mp3").read_bytes() != b"stale-99-take"


def test_voice_fresh_duplicate_stem_is_ok(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    audio_dir = pkg_dir / "dj-audio"

    _arm_fake_llm(monkeypatch)
    result = runner.invoke(
        app, ["voice", str(pkg_dir), "--fresh", "set1-intro", "--fresh", "set1-intro"])

    assert result.exit_code == 0, result.output  # a repeated stem must not double-unlink
    assert (audio_dir / "set1-intro.mp3").read_bytes() != b"stale-set1-take"


def test_voice_fresh_unknown_stem_lists_available_and_deletes_nothing(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    audio_dir = pkg_dir / "dj-audio"

    result = runner.invoke(app, ["voice", str(pkg_dir), "--fresh", "set3-intro"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "set3-intro" in str(result.exception)
    assert "set1-intro" in str(result.exception) and "99-outro" in str(result.exception)
    # nothing was deleted
    assert (audio_dir / "set1-intro.mp3").read_bytes() == b"stale-set1-take"
    assert (audio_dir / "99-outro.mp3").read_bytes() == b"stale-99-take"


def test_voice_fresh_on_unvoiced_package_errors(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = build_package(station, slug="bare", voiced=False)  # no dj-audio/ at all

    result = runner.invoke(app, ["voice", str(pkg_dir), "--fresh", "set1-intro"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "no dj audio" in str(result.exception).lower()


# ---------------------------------------------------------------------------
# Stale-ready judgment call: re-voicing an already-"ready" package that
# fails mid-synthesis must degrade the manifest to "pending" (dj_notes/
# dj_audio cleared), not leave it looking "ready" while dj-notes.md has
# already been overwritten with the new (unrecorded) script.
# ---------------------------------------------------------------------------


def test_voice_failure_on_already_ready_package_degrades_manifest_to_pending(tmp_path, monkeypatch):
    from emcee.package_io import Package
    from emcee.station import readiness

    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    pkg = Package(pkg_dir)
    ok_before, _ = readiness(pkg)
    assert ok_before is True  # sanity: genuinely ready before the failing re-voice

    def flaky_process_package(config, p, speech, force=False):
        raise RuntimeError("synthetic mid-pipeline blowup")

    import emcee.cli as cli_mod
    monkeypatch.setattr(cli_mod, "process_package", flaky_process_package)

    result = runner.invoke(app, ["voice", str(pkg_dir)])

    assert result.exit_code == 1
    manifest = json.loads((pkg_dir / "manifest.json").read_text())
    assert manifest["dj_notes"] is None
    assert manifest["dj_audio"] is None
    ok_after, reasons_after = readiness(pkg)
    assert ok_after is False  # now honestly "pending", not stale "ready"
    assert reasons_after


# ---------------------------------------------------------------------------
# Fix 1 (whole-branch review, Important): resolve_assignment/speech_for can
# both fail on configuration alone -- no [tts] voice configured, or an
# [assign] default naming a presenter with no TOML file -- with no manifest
# write ever attempted. The pre-clear must run only AFTER both have already
# succeeded, so a config typo alone never takes a genuinely ready package
# off air.
# ---------------------------------------------------------------------------


def _write_config_no_voice(root: Path) -> None:
    """Like _write_config, but deliberately omits [tts] voice -- speech_for
    has nothing to resolve and raises EmceeError."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.toml").write_text('[tts]\nbackend = "fake"\n')


def test_voice_failing_speech_for_leaves_a_ready_package_untouched(tmp_path, monkeypatch):
    from emcee.package_io import Package
    from emcee.station import readiness

    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)  # working config, so the fixture below can actually voice
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    pkg = Package(pkg_dir)
    before_manifest = (pkg_dir / "manifest.json").read_text()
    ok_before, _ = readiness(pkg)
    assert ok_before is True  # sanity: genuinely ready before the failing re-voice

    # Now reconfigure with a busted [tts] voice, as if a config typo landed.
    _write_config_no_voice(home)

    result = runner.invoke(app, ["voice", str(pkg_dir)])

    assert result.exit_code == 1
    assert "error: " in result.stderr
    # nothing was ever going to be overwritten -- the manifest must come out
    # byte-for-byte untouched, not pre-cleared to dj_notes/dj_audio = None
    assert (pkg_dir / "manifest.json").read_text() == before_manifest
    ok_after, reasons_after = readiness(pkg)
    assert ok_after is True  # still genuinely ready, not knocked off air
    assert reasons_after == []


def test_voice_failing_resolve_assignment_leaves_a_ready_package_untouched(tmp_path, monkeypatch):
    """The presenter-missing variant: [assign] default names a presenter
    with no TOML file on disk, so resolve_assignment itself raises before
    speech_for is ever reached."""
    from emcee.package_io import Package
    from emcee.station import readiness

    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    pkg_dir = _fully_voiced_package(tmp_path, station, monkeypatch)
    pkg = Package(pkg_dir)
    before_manifest = (pkg_dir / "manifest.json").read_text()
    ok_before, _ = readiness(pkg)
    assert ok_before is True

    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        '[tts]\nbackend = "fake"\nvoice = "test-voice"\n\n'
        '[assign]\ndefault = "waldo"\n'
    )

    result = runner.invoke(app, ["voice", str(pkg_dir)])

    assert result.exit_code == 1
    assert "error: " in result.stderr
    assert "waldo" in result.stderr
    assert (pkg_dir / "manifest.json").read_text() == before_manifest
    ok_after, reasons_after = readiness(pkg)
    assert ok_after is True
    assert reasons_after == []


# ---------------------------------------------------------------------------
# Fix 3 (whole-branch review, Important): voice must not traceback on a
# malformed-but-valid-JSON v3 manifest -- it gets the same broad handling
# `run` has, rendering a clean `error: <slug>: <message>` line and exiting 1.
# ---------------------------------------------------------------------------


def test_voice_malformed_manifest_missing_briefing_key_reports_cleanly(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home)
    _arm_fake_llm(monkeypatch)

    pkg_dir = build_package(station, slug="badbriefing", voiced=False)
    manifest = json.loads((pkg_dir / "manifest.json").read_text())
    del manifest["briefing"]
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest))

    result = runner.invoke(app, ["voice", str(pkg_dir)])

    assert result.exit_code == 1
    # no raw traceback: the KeyError was caught and rendered, not propagated
    assert result.exception is None or not isinstance(result.exception, KeyError)
    assert "error: badbriefing: KeyError: 'briefing'" in result.stderr
