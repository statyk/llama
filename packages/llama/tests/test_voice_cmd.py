"""`llama voice`: TTS as a first-class verb, pure sugar over `redo --from
package --voice/--no-voice`. Plan B Task 7."""
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.workspace import write_artifact

from test_catalog import build

runner = CliRunner()


def _cfg(tmp_path: Path) -> str:
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return cfg


PACKAGED_STAGES = {"select", "gather", "research", "vet", "synthesize", "package"}


# ---------------------------------------------------------------------------
# Bare invocation, single show, --off.
# ---------------------------------------------------------------------------

def test_voice_bare_invocation_errors(tmp_path: Path):
    cfg = _cfg(tmp_path)
    r = runner.invoke(cli.app, ["--config", cfg, "voice"])
    assert r.exit_code != 0
    assert "give a show or a selector (e.g. --unvoiced)" in r.output


def test_voice_rejects_name_and_selector_together(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "ready", stages=PACKAGED_STAGES)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "ready", "--unvoiced"])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_voice_single_show_defaults_voice_on(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    build(tmp_path, "ready", stages=PACKAGED_STAGES)
    captured = {}
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: captured.update(args=a, kwargs=k) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "ready"])
    assert r.exit_code == 0, r.output
    assert captured["args"][3].slug == "ready"
    assert captured["args"][4] == "package"
    assert captured["kwargs"]["voice"] is True


def test_voice_single_show_off_disables_voice(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    build(tmp_path, "ready", stages=PACKAGED_STAGES)
    captured = {}
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: captured.update(args=a, kwargs=k) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "ready", "--off"])
    assert r.exit_code == 0, r.output
    assert captured["args"][4] == "package"
    assert captured["kwargs"]["voice"] is False


def test_voice_single_show_without_provenance_errors(tmp_path: Path):
    from llama.models import Show, Track
    from llama.workspace import ShowWorkspace

    cfg = _cfg(tmp_path)
    sws = ShowWorkspace(tmp_path / "shows" / "orphan-1970-01-01")
    write_artifact(sws.show, Show(
        performance_id="orphan/1970-01-01", identifier="x", artist="orphan",
        date="1970-01-01", tracks=[]))
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "orphan"])
    assert r.exit_code == 1
    assert "provenance.json" in r.output and "reprocess" in r.output


# ---------------------------------------------------------------------------
# Selector batch: plan/confirm, held opt-in, voice/--off, FAILED isolation.
# ---------------------------------------------------------------------------

def test_voice_selector_batch_voice_on_by_default(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    build(tmp_path, "ready", stages=PACKAGED_STAGES)
    captured = {}
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: captured.update(args=a, kwargs=k) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "--packaged", "--yes"])
    assert r.exit_code == 0, r.output
    assert captured["args"][4] == "package"
    assert captured["kwargs"]["voice"] is True


def test_voice_selector_batch_off(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    build(tmp_path, "ready", stages=PACKAGED_STAGES)
    captured = {}
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: captured.update(kwargs=k) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "--packaged", "--yes", "--off"])
    assert r.exit_code == 0, r.output
    assert captured["kwargs"]["voice"] is False


def test_voice_unvoiced_yes_hits_exactly_unvoiced_packaged_shows(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    build(tmp_path, "unvoiced1", stages=PACKAGED_STAGES)
    voiced_ws = build(tmp_path, "voiced1", stages=PACKAGED_STAGES)
    write_artifact(voiced_ws.package_dir / "manifest.json",
                   {"schema_version": 2, "dj_audio": {"set_intros": {"1": "x"}, "outro": "o"}})
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "--unvoiced", "--yes"])
    assert r.exit_code == 0, r.output
    assert calls == ["unvoiced1"]


def test_voice_batch_drops_held_unless_flag(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    build(tmp_path, "ready", stages=PACKAGED_STAGES)
    build(tmp_path, "heldpkg", stages=PACKAGED_STAGES, needs_review=True)
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)

    r = runner.invoke(cli.app, ["--config", cfg, "voice", "--artist", "Grateful Dead", "--yes"])
    assert r.exit_code == 0, r.output
    assert calls == ["ready"]
    assert "held" in r.output.lower()
    assert "note: 1 held show(s) excluded (add --held to include them)" in r.output

    calls.clear()
    r2 = runner.invoke(cli.app, ["--config", cfg, "voice", "--packaged", "--held", "--yes"])
    assert r2.exit_code == 0, r2.output
    assert sorted(calls) == ["heldpkg", "ready"]
    assert "excluded" not in r2.output.lower()


def test_voice_batch_plans_and_yes_skips_confirmation(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    build(tmp_path, "ready", stages=PACKAGED_STAGES)
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)

    declined = runner.invoke(cli.app, ["--config", cfg, "voice", "--packaged"], input="n\n")
    assert declined.exit_code == 0, declined.output
    assert not calls
    assert "1 show(s) to redo --from package:" in declined.output
    assert "ready" in declined.output

    r = runner.invoke(cli.app, ["--config", cfg, "voice", "--packaged", "--yes"])
    assert r.exit_code == 0, r.output
    assert calls == ["ready"]


def test_voice_batch_continues_past_failure(tmp_path: Path, monkeypatch):
    from llama.errors import LlamaError

    cfg = _cfg(tmp_path)
    build(tmp_path, "aready", stages=PACKAGED_STAGES)
    build(tmp_path, "bready", stages=PACKAGED_STAGES)
    processed = []

    def fake_redo_show(config, ia, ledger, entry, from_stage, **kw):
        if entry.slug == "aready":
            raise LlamaError("boom")
        processed.append(entry.slug)
        return entry.ws.package_dir

    monkeypatch.setattr(cli, "_redo_show", fake_redo_show)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "--packaged", "--yes"])
    assert r.exit_code == 0, r.output
    assert "FAILED aready" in r.output
    assert processed == ["bready"]


# ---------------------------------------------------------------------------
# Help text owns the stamped-voice replay rules.
# ---------------------------------------------------------------------------

def test_voice_help_mentions_stamped():
    r = runner.invoke(cli.app, ["voice", "--help"])
    assert r.exit_code == 0
    assert "stamped" in r.output.lower()


# ---------------------------------------------------------------------------
# --fresh: per-segment TTS re-roll (delete the named clip so the package
# redo re-synthesizes only it; cached clips stay untouched).
# ---------------------------------------------------------------------------

def _voiced_show(tmp_path: Path, slug: str):
    """A packaged show with two DJ clips on disk."""
    ws = build(tmp_path, slug, stages=PACKAGED_STAGES)
    audio = ws.package_dir / "dj-audio"
    audio.mkdir(parents=True, exist_ok=True)
    (audio / "set1-intro.mp3").write_bytes(b"old-intro")
    (audio / "99-outro.mp3").write_bytes(b"old-outro")
    (audio / "segments.json").write_text("{}")
    return ws


def test_voice_fresh_rerolls_only_named_clip(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _voiced_show(tmp_path, "ready")
    captured = {}
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: captured.update(args=a, kwargs=k) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "ready", "--fresh", "set1-intro"])
    assert r.exit_code == 0, r.output
    # only the named clip is deleted (so package re-synthesizes just it); the rest stay
    assert not (ws.package_dir / "dj-audio" / "set1-intro.mp3").exists()
    assert (ws.package_dir / "dj-audio" / "99-outro.mp3").exists()
    # dispatched the normal package redo with voice on
    assert captured["args"][4] == "package"
    assert captured["kwargs"]["voice"] is True
    assert "set1-intro" in r.output


def test_voice_fresh_multiple_clips(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _voiced_show(tmp_path, "ready")
    monkeypatch.setattr(cli, "_redo_show", lambda *a, **k: a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "ready",
                                "--fresh", "set1-intro", "--fresh", "99-outro"])
    assert r.exit_code == 0, r.output
    assert not (ws.package_dir / "dj-audio" / "set1-intro.mp3").exists()
    assert not (ws.package_dir / "dj-audio" / "99-outro.mp3").exists()


def test_voice_fresh_unknown_clip_lists_available(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _voiced_show(tmp_path, "ready")
    called = []
    monkeypatch.setattr(cli, "_redo_show", lambda *a, **k: called.append(1) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "ready", "--fresh", "set3-intro"])
    assert r.exit_code != 0
    assert "set3-intro" in r.output
    assert "set1-intro" in r.output and "99-outro" in r.output   # lists the real stems
    assert (ws.package_dir / "dj-audio" / "set1-intro.mp3").exists()   # nothing deleted
    assert not called                                                  # no redo dispatched


def test_voice_fresh_rejects_off(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _voiced_show(tmp_path, "ready")
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "ready", "--fresh", "set1-intro", "--off"])
    assert r.exit_code != 0
    assert "off" in r.output.lower()


def test_voice_fresh_rejects_selector(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _voiced_show(tmp_path, "ready")
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "--packaged", "--fresh", "set1-intro"])
    assert r.exit_code != 0
    assert "single show" in r.output.lower()


def test_voice_fresh_on_show_without_dj_audio_errors(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "bare", stages=PACKAGED_STAGES)   # packaged but no dj-audio/
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "bare", "--fresh", "set1-intro"])
    assert r.exit_code != 0
    assert "dj audio" in r.output.lower()


def test_voice_fresh_duplicate_stem_is_ok(tmp_path: Path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _voiced_show(tmp_path, "ready")
    monkeypatch.setattr(cli, "_redo_show", lambda *a, **k: a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "ready",
                                "--fresh", "set1-intro", "--fresh", "set1-intro"])
    assert r.exit_code == 0, r.output   # a repeated stem must not crash on the second unlink
    assert not (ws.package_dir / "dj-audio" / "set1-intro.mp3").exists()


def test_voice_fresh_without_show_asks_for_single_show(tmp_path: Path):
    # bare `voice --fresh X` (no name, no selector) must hit the fresh-specific
    # "name a single show" error, not the generic bare-invocation message.
    cfg = _cfg(tmp_path)
    _voiced_show(tmp_path, "ready")
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "--fresh", "set1-intro"])
    assert r.exit_code != 0
    assert "single show" in r.output.lower()
