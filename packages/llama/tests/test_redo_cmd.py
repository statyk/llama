"""`llama redo`: the single re-execution verb -- positional show, selector
batch, and `--run SESSION` session scope (absorbing the old
`run --stage X --force` run-wide re-execution). Plan B Task 6."""
import json
import shutil
from pathlib import Path

import pytest
from herder import TaskFailed
from helpers import (audio_files, delivered_gd73, fake_audio, fake_source, packaged_gd73,
                     reuse_gd73, stub_stages, tree_bytes)
from typer.testing import CliRunner

import llama.cli as cli
import llama.pipeline as pipeline
from llama.config import load_config
from llama.errors import LlamaError
from llama.ia_client import IAError
from llama.ledger import Ledger
from llama.locks import Locked, file_lock
from llama.show_unit import ShowChanged
from llama.workspace import atomic_write_bytes
from llama.models import Criteria, Provenance, QualityAssessment, Show, ShortlistEntry, Track
from llama.workspace import (
    RunWorkspace, ShowWorkspace, read_model, read_model_list, write_artifact,
)

from test_catalog import build
from test_cli_commands import _approved_run, _seed_show, make_entries

runner = CliRunner()


# ---------------------------------------------------------------------------
# Three-form grammar: positional show | --run SESSION | selectors -- exactly one.
# ---------------------------------------------------------------------------

def test_redo_batch_requires_target(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--from", "package"])
    assert r.exit_code != 0
    assert "a show" in r.output.lower() and "--run" in r.output


def test_redo_voice_flag_is_gone(tmp_path: Path):
    # Per-show voice override moved to emcee entirely (voice command too).
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "someshow", "--from", "package", "--voice"])
    assert r.exit_code != 0
    assert "no such option" in r.output.lower()


def test_voice_command_is_gone(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "voice", "someshow"])
    assert r.exit_code != 0
    assert "no such command" in r.output.lower()


def test_voiced_and_broadcast_ready_selectors_are_gone(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    for flag in ("--voiced", "--unvoiced", "--broadcast-ready"):
        r = runner.invoke(cli.app, ["--config", cfg, "redo", flag, "--from", "package"])
        assert r.exit_code != 0, flag
        assert "no such option" in r.output.lower(), (flag, r.output)


def test_redo_rejects_name_and_selector_together(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "someshow", "--packaged", "--from", "package"])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_redo_rejects_name_and_run_together(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "someshow", "--run", "r1", "--from", "package"])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_redo_rejects_run_and_other_selector_together(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", "r1", "--held", "--from", "package"])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_redo_state_enum_rejects_typo_listing_legal_values(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--state", "helx", "--from", "package"])
    assert r.exit_code != 0
    assert "not one of" in r.output
    for legal in ["held", "packaged", "delivered"]:
        assert legal in r.output


# ---------------------------------------------------------------------------
# Stage validation per form.
# ---------------------------------------------------------------------------

def test_redo_without_run_rejects_run_level_stage_naming_the_rule(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "someshow", "--from", "search"])
    assert r.exit_code != 0
    assert "unknown stage" in r.output.lower()
    assert "--run" in r.output   # names the rule: search/winnow need --run


def test_redo_run_rejects_bogus_stage(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", str(ws.dir), "--from", "bogus"])
    assert r.exit_code != 0
    assert "unknown stage" in r.output.lower()


def test_redo_run_accepts_search_and_winnow(tmp_path: Path, monkeypatch):
    # A run-level stage is valid with --run and never a "give a show" error.
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append(1))
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", str(ws.dir), "--from", "winnow"])
    assert r.exit_code == 0, r.output
    assert calls


# ---------------------------------------------------------------------------
# `--run` with a run-level stage (search|winnow) -- the old `run --stage X
# --force` run-wide re-execution.
# ---------------------------------------------------------------------------

def test_redo_run_search_confirms_on_approvals_and_declines(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append(1))
    cfg, ws = _approved_run(tmp_path)
    write_artifact(ws.candidates, [])
    result = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", str(ws.dir), "--from", "search"],
                           input="n\n")
    assert result.exit_code == 1
    assert not calls
    assert ws.candidates.exists() and ws.shortlist.exists()   # nothing wiped on decline
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert entries[0].approved is True


def test_redo_run_search_confirms_on_approvals_and_accepts(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append(1))
    cfg, ws = _approved_run(tmp_path)
    write_artifact(ws.candidates, [])
    result = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", str(ws.dir), "--from", "search"],
                           input="y\n")
    assert result.exit_code == 0, result.output
    assert calls
    assert not ws.candidates.exists()
    assert not ws.shortlist.exists()


def test_redo_run_search_no_approvals_skips_prompt(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append(1))
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    write_artifact(ws.shortlist, make_entries())    # no approvals recorded
    result = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", str(ws.dir), "--from", "search"])
    assert result.exit_code == 0, result.output
    assert calls


def test_redo_run_winnow_deletes_only_shortlist(tmp_path: Path, monkeypatch):
    # Preserved quirk from the old code (cli.py:414-419 today): the
    # approvals-loss confirm only ever fired for stage in (None, "search"),
    # never "winnow" -- even though winnow also discards the shortlist.
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append(1))
    cfg, ws = _approved_run(tmp_path)
    write_artifact(ws.candidates, [])
    result = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", str(ws.dir), "--from", "winnow"])
    assert result.exit_code == 0, result.output   # no prompt despite recorded approvals
    assert ws.candidates.exists()                 # search-level artifact untouched
    assert not ws.shortlist.exists()
    assert calls


# ---------------------------------------------------------------------------
# `--run` with a show-level stage: batch over that session's shows (selector
# form with only the run filter).
# ---------------------------------------------------------------------------

def test_redo_run_batches_exactly_that_runs_shows(tmp_path: Path, monkeypatch):
    from test_catalog import build

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "inrun", stages={"select", "gather", "research", "vet", "package"},
          run="r1")
    build(tmp_path, "otherrun", stages={"select", "gather", "research", "vet", "package"},
          run="r2")
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", "r1", "--from", "package", "--yes"])
    assert r.exit_code == 0, r.output
    assert calls == ["inrun"]


def test_redo_run_show_level_batch_drops_held_with_note(tmp_path: Path, monkeypatch):
    from test_catalog import build

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "package"},
          run="r1")
    build(tmp_path, "heldpkg", stages={"select", "gather", "research", "vet", "package"},
          run="r1", needs_review=True)
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", "r1", "--from", "package", "--yes"])
    assert r.exit_code == 0, r.output
    assert calls == ["ready"]
    assert "held" in r.output.lower()
    assert "1" in r.output   # HELD_NOTE.format(n=1)


# ---------------------------------------------------------------------------
# Selector batch (no --run): shared cli_select layer, held opt-in, plan/--yes.
# ---------------------------------------------------------------------------

def test_redo_batch_packaged_plans_and_confirms(tmp_path, monkeypatch):
    from test_pipeline import FakeIA, fake_providers
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--auto",
                            "--name", "r"])

    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--packaged", "--from", "package"],
                      input="y\n")
    assert r.exit_code == 0, r.output
    assert calls == ["gratefuldead-1973-06-10"]


def test_redo_selector_batch_drops_held_unless_flag(tmp_path, monkeypatch):
    from test_catalog import build

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "package"})
    build(tmp_path, "heldpkg", stages={"select", "gather", "research", "vet", "package"},
          needs_review=True)
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)

    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--artist", "Grateful Dead",
                                "--from", "package", "--yes"])
    assert r.exit_code == 0, r.output
    assert calls == ["ready"]
    assert "held" in r.output.lower()

    # --held is sugar for states={"held"} (like --packaged is for
    # states={"packaged"}): combine both to actually widen the batch to
    # "held or packaged" rather than narrowing to held-only.
    calls.clear()
    r2 = runner.invoke(cli.app, ["--config", cfg, "redo", "--packaged", "--held",
                                 "--from", "package", "--yes"])
    assert r2.exit_code == 0, r2.output
    assert sorted(calls) == ["heldpkg", "ready"]
    assert "excluded" not in r2.output.lower()   # HELD_NOTE absent: nothing was dropped


def test_redo_batch_plans_and_yes_skips_confirmation(tmp_path, monkeypatch):
    from test_catalog import build

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "package"})
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)

    # no --yes, decline: nothing runs
    declined = runner.invoke(cli.app, ["--config", cfg, "redo", "--packaged", "--from", "package"],
                             input="n\n")
    assert declined.exit_code == 0, declined.output
    assert not calls
    assert "1 show(s) to redo --from package:" in declined.output
    assert "ready" in declined.output

    # --yes skips the prompt
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--packaged", "--from", "package", "--yes"])
    assert r.exit_code == 0, r.output
    assert calls == ["ready"]


def test_redo_batch_continues_past_failure(tmp_path, monkeypatch):
    from llama.errors import LlamaError
    from test_catalog import build

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "aready", stages={"select", "gather", "research", "vet", "package"})
    build(tmp_path, "bready", stages={"select", "gather", "research", "vet", "package"})
    processed = []

    def fake_redo_show(config, ia, ledger, entry, from_stage, **kw):
        if entry.slug == "aready":
            raise LlamaError("boom")
        processed.append(entry.slug)
        return entry.ws.package_dir

    monkeypatch.setattr(cli, "_redo_show", fake_redo_show)
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--packaged", "--from", "package", "--yes"])
    assert r.exit_code == 0, r.output
    assert "FAILED aready" in r.output
    assert processed == ["bready"]


# ---------------------------------------------------------------------------
# Positional show: implicit held opt-in (spec §2), --redo-research renamed.
# ---------------------------------------------------------------------------

def test_redo_positional_held_show_runs(tmp_path, monkeypatch):
    from test_catalog import build

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "heldpkg", stages={"select", "gather", "research", "vet", "package"},
          needs_review=True)
    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "heldpkg", "--from", "package"])
    assert r.exit_code == 0, r.output
    assert calls == ["heldpkg"]


def test_redo_research_flag_renamed(tmp_path, monkeypatch):
    from test_catalog import build

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "package"})
    captured = {}
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: captured.update(k) or a[3].ws.package_dir)

    r = runner.invoke(cli.app, ["--config", cfg, "redo", "ready", "--from", "gather", "--redo-research"])
    assert r.exit_code == 0, r.output
    assert captured.get("with_research") is True

    r2 = runner.invoke(cli.app, ["--config", cfg, "redo", "ready", "--from", "gather", "--with-research"])
    assert r2.exit_code != 0
    assert "no such option" in r2.output.lower()


def test_redo_without_provenance_errors(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = ShowWorkspace(tmp_path / "shows" / "orphan-1970-01-01")
    write_artifact(sws.show, Show(
        performance_id="orphan/1970-01-01", identifier="x", artist="orphan",
        date="1970-01-01", tracks=[Track(index=1, set="1", title="T",
                                         filename="a.mp3", title_source="tags")]))
    result = runner.invoke(cli.app, ["--config", cfg, "redo", "orphan", "--from", "vet"])
    assert result.exit_code == 1
    assert "provenance.json" in result.output and "reprocess" in result.output


# ---------------------------------------------------------------------------
# Full-pipeline integration: positional redo and --run show-level batches
# actually rerun the pipeline correctly (moved from test_pipeline.py's old
# `run --stage X --force` coverage).
# ---------------------------------------------------------------------------

def test_redo_requires_from_and_reruns_tail(tmp_path: Path, monkeypatch):
    from test_pipeline import FakeIA, fake_providers

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg,
        "get", "GD 1973", "--auto", "--name", "redorun"])
    assert result.exit_code == 0, result.output
    sws = ShowWorkspace(tmp_path / "shows" / "gratefuldead-1973-06-10")
    research_before = sws.research.read_text()

    missing = runner.invoke(cli.app, ["--config", cfg, "redo", "gratefuldead"])
    assert missing.exit_code != 0

    result = runner.invoke(cli.app, ["--config", cfg, "redo", "gratefuldead", "--from", "gather"])
    assert result.exit_code == 0, result.output
    assert sws.show.exists() and (sws.package_dir / "manifest.json").exists()
    assert sws.research.read_text() == research_before   # preserved by default


def test_redo_from_select_keeps_winnow_assessment(tmp_path: Path, monkeypatch):
    from test_pipeline import FakeIA, fake_providers

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg,
        "get", "GD 1973", "--auto", "--name", "redosel"])
    assert result.exit_code == 0, result.output
    sws = ShowWorkspace(tmp_path / "shows" / "gratefuldead-1973-06-10")

    prov = read_model(sws.provenance, Provenance)
    assert prov.assessment is not None and prov.assessment.quality_score == 9.5
    prov.assessment.recording_complaints = ["hiss on side two (badtaper)"]
    write_artifact(sws.provenance, prov)

    result = runner.invoke(cli.app, ["--config", cfg, "redo", "gratefuldead", "--from", "select"])
    assert result.exit_code == 0, result.output

    prov = read_model(sws.provenance, Provenance)
    assert prov.assessment is not None
    assert prov.assessment.quality_score == 9.5
    assert prov.assessment.recording_complaints == ["hiss on side two (badtaper)"]
    assert prov.assessment.rationale == prov.dossier


def test_redo_preserves_profile_stamp(tmp_path: Path, monkeypatch):
    """A profile-driven show's provenance.profile must survive `redo` --
    _redo_show replays process_show with profile=prov.profile; a refactor
    that drops that kwarg would silently reset it to None."""
    from test_pipeline import FakeIA, fake_providers

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, ["--config", cfg,
        "get", "GD 1973", "--auto", "--name", "redoprofile"])
    assert result.exit_code == 0, result.output
    sws = ShowWorkspace(tmp_path / "shows" / "gratefuldead-1973-06-10")

    # Seed a profile stamp as if this show had originated from a profile run
    # (the CLI `get` call above was one-off, so profile starts None).
    prov = read_model(sws.provenance, Provenance)
    assert prov.profile is None
    prov.profile = "prime-dead"
    write_artifact(sws.provenance, prov)

    result = runner.invoke(cli.app, ["--config", cfg, "redo", "gratefuldead", "--from", "select"])
    assert result.exit_code == 0, result.output

    prov = read_model(sws.provenance, Provenance)
    assert prov.profile == "prime-dead"  # survived the redo, not reset to None


def test_redo_run_package_never_writes_a_dj_script(tmp_path: Path, monkeypatch):
    # llama never writes a script -- that's emcee's job now, so a repackage
    # via --run must leave dj_notes null regardless.
    import llama.pipeline as pipeline
    from test_pipeline import JB_OFF, FakeIA, fake_providers

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    cfg = str(tmp_path / "config.toml")

    first = runner.invoke(cli.app, ["--config", cfg,
        "get", "GD 1973", "--auto", "--name", "replay"])
    assert first.exit_code == 0, first.output

    replay = runner.invoke(cli.app, ["--config", cfg,
        "redo", "--run", "replay", "--from", "package", "--yes"])
    assert replay.exit_code == 0, replay.output

    pkg = tmp_path / "shows" / "gratefuldead-1973-06-10" / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_notes"] is None
    assert manifest["set_breaks"] == [{"after_track": 3}, {"after_track": 5}]
    assert not (pkg / "dj-notes.md").exists()


def test_redo_from_package_regenerates_missing_briefing(tmp_path: Path, monkeypatch):
    """A pre-existing workspace with no briefing.json (e.g. deleted by hand)
    self-heals on the next redo: process_show finds the briefing artifact
    missing and regenerates it, even though --from package doesn't drop the
    brief stage's artifacts."""
    import llama.pipeline as pipeline
    from test_pipeline import JB_OFF, FakeIA, fake_providers

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    cfg = str(tmp_path / "config.toml")

    first = runner.invoke(cli.app, ["--config", cfg,
        "get", "GD 1973", "--auto", "--name", "selfheal"])
    assert first.exit_code == 0, first.output

    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    assert (show_dir / "briefing.json").exists()
    (show_dir / "briefing.json").unlink()
    (show_dir / "briefing.md").unlink()

    replay = runner.invoke(cli.app, ["--config", cfg,
        "redo", "--run", "selfheal", "--from", "package", "--yes"])
    assert replay.exit_code == 0, replay.output
    assert (show_dir / "briefing.json").exists()
    assert (show_dir / "briefing.md").exists()


def test_redo_synthesize_stage_is_gone(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--run", "anyrun",
                                "--from", "synthesize", "--yes"])
    assert r.exit_code != 0
    assert "unknown stage" in r.output.lower()


def test_redo_run_rebuilds_only_chosen_show_from_stage_onward(tmp_path: Path, monkeypatch):
    from test_pipeline import FakeIA, fake_providers
    from herder import FakeProvider

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    cfg = str(tmp_path / "config.toml")

    first = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--auto",
                                    "--name", "stageforce"])
    assert first.exit_code == 0, first.output
    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    (show_dir / "research.md").write_text("OLD SENTINEL")

    fresh = fake_providers(None)
    fresh["interpret"] = FakeProvider()
    fresh["score_reviews"] = FakeProvider()
    fresh["light_research"] = FakeProvider()
    monkeypatch.setattr(cli, "make_providers", lambda config: fresh)
    replay = runner.invoke(cli.app, ["--config", cfg,
        "redo", "--run", "stageforce", "--from", "research", "--yes"])
    assert replay.exit_code == 0, replay.output
    assert (show_dir / "research.md").read_text() != "OLD SENTINEL"   # re-researched
    assert (show_dir / "package" / "manifest.json").exists()          # repackaged


# ---------------------------------------------------------------------------
# `run` no longer accepts `--stage`/`--force`: absorbed by `redo --run`.
# ---------------------------------------------------------------------------

def test_run_no_longer_accepts_stage_or_force(tmp_path: Path, monkeypatch):
    # Belt-and-suspenders mocking: on unmodified code these options still
    # parse and would fall through to a real _execute() (real network) --
    # keep this offline regardless of which side of the change it runs on.
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))

    r1 = runner.invoke(cli.app, ["--config", cfg, "run", "resume", str(ws.dir), "--stage", "search"])
    assert r1.exit_code != 0
    assert "no such option" in r1.output.lower()

    r2 = runner.invoke(cli.app, ["--config", cfg, "run", "resume", str(ws.dir), "--force"])
    assert r2.exit_code != 0
    assert "no such option" in r2.output.lower()


# ---------------------------------------------------------------------------
# A redo re-judges the flags of the stages it re-runs: a briefing-guard hold
# used to survive `redo --from brief` (process_show skipped at the post-vet
# needs_review check, after the briefing had already been deleted). The stale
# flag is replaced only when the re-run succeeds.
# ---------------------------------------------------------------------------

def _held_packaged_show(tmp_path: Path, monkeypatch, flags: list[str]) -> Path:
    import llama.pipeline as pipeline
    from test_pipeline import JB_OFF, FakeIA, fake_providers

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    first = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "GD 1973", "--auto", "--name", "held"])
    assert first.exit_code == 0, first.output
    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    show = read_model(show_dir / "show.json", Show)
    assert not show.needs_review
    show.review_flags = list(flags)
    show.needs_review = True
    write_artifact(show_dir / "show.json", show)
    return show_dir


def test_redo_from_brief_clears_a_briefing_guard_hold(tmp_path: Path, monkeypatch):
    show_dir = _held_packaged_show(tmp_path, monkeypatch,
                                   ["briefing claims 2 sets but structure has 1"])
    r = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "redo", "gratefuldead-1973-06-10", "--from", "brief"])
    assert r.exit_code == 0, r.output
    show = read_model(show_dir / "show.json", Show)
    assert show.review_flags == [] and not show.needs_review
    assert (show_dir / "briefing.json").exists()
    assert (show_dir / "package" / "manifest.json").exists()


def test_redo_keeps_flags_of_stages_it_does_not_rerun(tmp_path: Path, monkeypatch):
    # The venue hold stops the run before brief, so the briefing verdict is
    # never re-judged either: both stay (the stale one is harmless, the show
    # is held regardless, and the next brief replaces it).
    flags = ["venue mismatch: archive 'A' vs jerrybase 'B'", "briefing mentions unknown song: X"]
    show_dir = _held_packaged_show(tmp_path, monkeypatch, flags)
    r = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "redo", "gratefuldead-1973-06-10", "--from", "brief"])
    assert r.exit_code == 0, r.output
    show = read_model(show_dir / "show.json", Show)
    assert show.review_flags == flags and show.needs_review


def test_a_failed_redo_leaves_the_show_held(tmp_path: Path, monkeypatch):
    # The flag must outlive a re-run that fails: un-holding first would drop
    # the show off every held list (status --held, triage, reapply).
    from herder import TaskFailed

    flag = "briefing claims 2 sets but structure has 1"
    show_dir = _held_packaged_show(tmp_path, monkeypatch, [flag])

    class Boom:
        def __getattr__(self, name):
            raise TaskFailed("brief failed")

    from test_pipeline import fake_providers
    broken = fake_providers(None)
    broken["brief"] = Boom()
    monkeypatch.setattr(cli, "make_providers", lambda config: broken)
    r = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "redo", "--held", "--from", "brief", "--yes"])
    assert "brief failed" in r.output, r.output
    show = read_model(show_dir / "show.json", Show)
    assert show.review_flags == [flag] and show.needs_review


def test_redo_from_package_clears_a_duration_hold(tmp_path: Path, monkeypatch):
    show_dir = _held_packaged_show(tmp_path, monkeypatch,
        ["duration mismatch on 01.mp3: file 10s vs metadata 300s"])
    r = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "redo", "gratefuldead-1973-06-10", "--from", "package"])
    assert r.exit_code == 0, r.output
    show = read_model(show_dir / "show.json", Show)
    assert show.review_flags == [] and not show.needs_review


def test_redo_from_package_keeps_a_briefing_flag(tmp_path: Path, monkeypatch):
    # package does not re-run the briefing guard, so its verdict stands.
    flag = "briefing claims 2 sets but structure has 1"
    show_dir = _held_packaged_show(tmp_path, monkeypatch, [flag])
    r = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "redo", "gratefuldead-1973-06-10", "--from", "package"])
    assert r.exit_code == 0, r.output
    assert read_model(show_dir / "show.json", Show).review_flags == [flag]


def test_failed_redo_from_brief_restores_every_file(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_brief", lambda *a, **k: (_ for _ in ()).throw(TaskFailed("boom")))
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "brief"])
    assert r.exit_code == 1 and isinstance(r.exception, TaskFailed)
    assert tree_bytes(ws.dir) == before            # provenance.json's processed_at included


def test_package_failure_on_purged_audio_removes_new_audio_and_restores_manifest(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    for f in (ws.package_dir / "audio").iterdir():
        f.unlink()                                  # as `deliver` purges
    before = tree_bytes(ws.dir)
    from test_pipeline import FakeIA
    class SecondFails(FakeIA):
        n = 0
        def download_file(self, identifier, filename, dest, md5=None):
            SecondFails.n += 1
            if SecondFails.n == 2:
                raise IAError("download of x failed")
            return super().download_file(identifier, filename, dest, md5)
    monkeypatch.setattr(cli, "IAClient", SecondFails)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 1 and isinstance(r.exception, IAError)
    assert tree_bytes(ws.dir) == before and list((ws.package_dir / "audio").iterdir()) == []


def test_keyboard_interrupt_after_the_drop_restores_and_re_raises(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_brief", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    # through the function, not the runner: click turns KeyboardInterrupt into "Aborted!"
    config = load_config(cfg); ledger = Ledger(config.root / "ledger.jsonl")
    entry = cli._resolve_show(config, ledger, "gratefuldead")
    with pytest.raises(KeyboardInterrupt):
        cli._redo_show(config, cli.IAClient(), ledger, entry, "brief")
    assert tree_bytes(ws.dir) == before and not (ws.dir / ".txn").exists()


def test_a_redo_of_a_show_removed_while_it_waited_refuses_with_the_removed_message(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    config = load_config(cfg); ledger = Ledger(config.root / "ledger.jsonl")
    entry = cli._resolve_show(config, ledger, "gratefuldead")
    shutil.rmtree(ws.dir)                           # `llama rm` ran while this redo waited for the lock
    with pytest.raises(ShowChanged, match="gratefuldead-1973-06-10: the show was removed; nothing changed"):
        cli._redo_show(config, cli.IAClient(), ledger, entry, "brief")
    assert [p.name for p in ws.dir.iterdir()] == [".lock"]   # spec C2's documented husk


def test_a_leftover_txn_is_deleted_not_restored_by_the_next_redo(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    atomic_write_bytes(ws.dir / ".txn" / "files" / "show.json", b"STALE")
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 0, r.output
    assert ws.show.read_bytes() != b"STALE" and not (ws.dir / ".txn").exists()


def test_redo_runs_the_pipeline_inside_the_show_lock(tmp_path, monkeypatch):   # (pin)
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); seen = []
    def probe(*a, **k):
        try:
            with file_lock(ws.lock, blocking=False):
                seen.append("free")
        except Locked:
            seen.append("held")
        raise TaskFailed("stop")
    monkeypatch.setattr(pipeline, "run_brief", probe)
    runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "brief"])
    assert seen == ["held"]


def test_redo_batch_restores_a_failed_show_and_continues(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"; cfg.write_text(f'root = "{tmp_path}"\n')
    a = build(tmp_path, "aready", stages={"select", "gather", "research", "vet", "package"})
    build(tmp_path, "bready", stages={"select", "gather", "research", "vet", "package"})
    before, done = tree_bytes(a.dir), []
    def fake(config, ia, ledger, e, stage, **kw):
        write_artifact(e.ws.show, {"half": "written"})
        if e.slug == "aready":
            raise LlamaError("boom")
        done.append(e.slug)
        return e.ws.package_dir
    monkeypatch.setattr(cli, "_redo_show_locked", fake)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "--packaged", "--from", "package", "--yes"])
    assert r.exit_code == 0 and "FAILED aready: boom" in r.output and done == ["bready"]
    assert tree_bytes(a.dir) == before


def test_redo_from_gather_reuses_library_audio_after_an_insertion(tmp_path, monkeypatch):
    old = (("A", "a.mp3", 300.0), ("B", "b.mp3", 400.0))
    cfg, ws, ia = reuse_gd73(tmp_path, monkeypatch, old)
    new = (("Crowd", "s.mp3", 20.0), *old)
    ia.lengths["s.mp3"] = 20.0
    stub_stages(monkeypatch, new)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "gather"])
    assert r.exit_code == 0, r.output
    assert ia.downloads == ["s.mp3"]                      # only the new track is fetched
    names = audio_files(ws)
    assert sorted(names) == ["01 - Crowd.mp3", "02 - A.mp3", "03 - B.mp3"]   # no old-numbered file left
    assert {n: fake_source(ws.package_dir / "audio" / n) for n in names} == {
        "01 - Crowd.mp3": "s.mp3", "02 - A.mp3": "a.mp3", "03 - B.mp3": "b.mp3"}
    assert not (ws.dir / ".audio-aside").exists()


def test_redo_that_picks_another_item_with_the_same_file_names_ships_no_old_audio(tmp_path, monkeypatch):
    old = (("A", "a.mp3", 300.0), ("B", "b.mp3", 400.0))
    cfg, ws, ia = reuse_gd73(tmp_path, monkeypatch, old)
    old_bytes = set(audio_files(ws).values())
    stub_stages(monkeypatch, old, identifier="gd73-other-taper")
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "gather"])
    assert r.exit_code == 0, r.output
    assert ia.downloads == ["a.mp3", "b.mp3"]              # every track fetched from the new item
    new = audio_files(ws)
    assert sorted(new) == ["01 - A.mp3", "02 - B.mp3"] and not (set(new.values()) & old_bytes)
    assert not (ws.dir / ".audio-aside").exists()


# ---------------------------------------------------------------------------
# Strict station reuse for delivered shows, the held-outcome anchor (bulk-apply Task 8).
# ---------------------------------------------------------------------------

SLUG = "gratefuldead-1973-06-10"
OLD2 = (("A", "a.mp3", 300.0), ("B", "b.mp3", 400.0))
HINT = "  if the station copy cannot be fixed: re-run this one show with --allow-download"


def _lines(r) -> list[str]:
    return r.output.splitlines()


def test_strict_redo_of_a_delivered_show_reuses_the_station_copy(tmp_path, monkeypatch):
    cfg, ws, ia, station = delivered_gd73(tmp_path, monkeypatch, OLD2)
    stub_stages(monkeypatch)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 0, r.output
    assert ia.downloads == []
    assert {n: fake_source(ws.package_dir / "audio" / n) for n in audio_files(ws)} == {
        "01 - A.mp3": "a.mp3", "02 - B.mp3": "b.mp3"}
    assert not ws.reuse_anchor.exists()           # written for the unit, removed by the build


def test_strict_refuses_a_paired_copy_failing_its_length_check(tmp_path, monkeypatch):
    cfg, ws, ia, station = delivered_gd73(tmp_path, monkeypatch, OLD2)
    (station / "audio" / "02 - B.mp3").write_bytes(fake_audio("b.mp3", 999.0))
    stub_stages(monkeypatch)
    before = tree_bytes(ws.dir)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 1, r.output
    assert _lines(r)[-2:] == [f"{SLUG}: station copy does not pair: b.mp3 failed its length check",
                              HINT]
    assert ia.downloads == []
    assert tree_bytes(ws.dir) == before           # the unit restored (no anchor left either)
    assert audio_files(ws) == {}


def test_strict_refuses_when_nothing_pairs(tmp_path, monkeypatch):
    cfg, ws, ia, station = delivered_gd73(tmp_path, monkeypatch, OLD2)
    m = json.loads((station / "manifest.json").read_text())
    m["tracks"][0]["title"] = "Retitled"
    (station / "manifest.json").write_text(json.dumps(m))
    stub_stages(monkeypatch)
    before = tree_bytes(ws.dir)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 1, r.output
    assert _lines(r)[-2:] == [f"{SLUG}: station copy does not pair: no copy pairs", HINT]
    assert ia.downloads == [] and tree_bytes(ws.dir) == before


@pytest.mark.parametrize("damage", ["missing", "not json"])
def test_strict_refuses_a_missing_or_unreadable_station_copy(tmp_path, monkeypatch, damage):
    from llama.station_mark import StationUnreadable
    cfg, ws, ia, station = delivered_gd73(tmp_path, monkeypatch, OLD2)
    if damage == "missing":
        shutil.rmtree(station)
        detail = f"no directory {station}"
    else:
        (station / "manifest.json").write_text("{")
        detail = f"invalid JSON in {station / 'manifest.json'}"
    stub_stages(monkeypatch)
    before = tree_bytes(ws.dir)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 1, r.output
    *_, refusal, hint = _lines(r)
    assert refusal.startswith(f"{SLUG}: station copy unreadable: {detail}") and hint == HINT
    assert ia.downloads == [] and tree_bytes(ws.dir) == before
    config = load_config(cfg); ledger = Ledger(config.root / "ledger.jsonl")
    with pytest.raises(StationUnreadable):
        cli._redo_show(config, ia, ledger, cli._resolve_show(config, ledger, "gratefuldead"),
                       "package")
    assert ia.downloads == [] and tree_bytes(ws.dir) == before


def test_strict_refuses_without_a_delivery_path(tmp_path, monkeypatch):
    from llama.station_mark import StationUnreadable
    cfg, ws, ia, station = delivered_gd73(tmp_path, monkeypatch, OLD2)
    cfg.write_text(f'root = "{tmp_path}"\n[jerrybase]\nenabled = false\n')
    stub_stages(monkeypatch)
    config = load_config(cfg); ledger = Ledger(config.root / "ledger.jsonl")
    assert config.delivery_path is None
    with pytest.raises(StationUnreadable) as exc:
        cli._redo_show(config, ia, ledger, cli._resolve_show(config, ledger, "gratefuldead"),
                       "package")
    assert str(exc.value) == f"{SLUG}: station copy unreadable: no delivery_path in config"
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "package"])
    assert r.exit_code == 1
    assert _lines(r)[-2:] == [f"{SLUG}: station copy unreadable: no delivery_path in config", HINT]
    assert ia.downloads == []


@pytest.mark.parametrize("cmd", [["redo", "gratefuldead", "--from", "package"],
                                 ["fix", "gratefuldead", "--set-venue", "X"]])
def test_allow_download_lets_one_named_show_download(tmp_path, monkeypatch, cmd):
    cfg, ws, ia, station = delivered_gd73(tmp_path, monkeypatch, OLD2)
    shutil.rmtree(station)                         # the station copy is gone for good
    stub_stages(monkeypatch, OLD2)
    r = runner.invoke(cli.app, ["--config", str(cfg), *cmd])
    assert r.exit_code == 1 and _lines(r)[-1] == HINT, r.output
    assert ia.downloads == []
    r = runner.invoke(cli.app, ["--config", str(cfg), *cmd, "--allow-download"])
    assert r.exit_code == 0, r.output
    assert ia.downloads == ["a.mp3", "b.mp3"]
    assert (ws.package_dir / "manifest.json").exists()
    assert {n: fake_source(ws.package_dir / "audio" / n) for n in audio_files(ws)} == {
        "01 - A.mp3": "a.mp3", "02 - B.mp3": "b.mp3"}


@pytest.mark.parametrize("sel", [["--held"], ["--packaged"], ["--state", "delivered"],
                                 ["--run", "r"], []])
def test_allow_download_refuses_a_selector(tmp_path, monkeypatch, sel):
    cfg, ws, ia, station = delivered_gd73(tmp_path, monkeypatch, OLD2)
    stub_stages(monkeypatch)
    before, station_before = tree_bytes(ws.dir), tree_bytes(station)
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", *sel, "--from", "package",
                                "--allow-download", "--yes"])
    assert r.exit_code == 1
    assert r.output.strip() == "--allow-download takes one named show"
    assert tree_bytes(ws.dir) == before and tree_bytes(station) == station_before
    assert ia.downloads == []


def test_reselection_redo_is_not_strict(tmp_path, monkeypatch):   # (pin)
    cfg, ws, ia, station = delivered_gd73(tmp_path, monkeypatch, OLD2)
    monkeypatch.setattr(pipeline, "run_select_recording",
                        lambda show_ws, *a, **k: "gd73-other-taper")
    stub_stages(monkeypatch, OLD2, identifier="gd73-other-taper")
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "select"])
    assert r.exit_code == 0, r.output
    assert ia.downloads == ["a.mp3", "b.mp3"]       # a new recording: every file downloads


def test_held_redo_of_a_delivered_show_keeps_an_anchor_the_clear_reuses(tmp_path, monkeypatch):
    from llama.models import Briefing
    cfg, ws, ia, station = delivered_gd73(tmp_path, monkeypatch, OLD2)
    pre = [{"filename": t.filename, "title": t.title} for t in read_model(ws.show, Show).tracks]
    retitled = (("A2", "a.mp3", 300.0), ("B2", "b.mp3", 400.0))
    stub_stages(monkeypatch, retitled, hold=["research asserts wrong date: 1974-01-01"])
    r = runner.invoke(cli.app, ["--config", str(cfg), "redo", "gratefuldead", "--from", "gather"])
    assert r.exit_code == 0, r.output
    assert read_model(ws.show, Show).needs_review is True
    anchor = json.loads(ws.reuse_anchor.read_text())
    assert anchor["identifier"] == "gd73" and anchor["tracks"] == pre
    stub_stages(monkeypatch)
    write_artifact(ws.briefing_json, Briefing(context="c", significance="s"))
    write_artifact(ws.briefing_md, "# Briefing\n")
    r = runner.invoke(cli.app, ["--config", str(cfg), "fix", "gratefuldead", "--overrule"])
    assert r.exit_code == 0, r.output
    assert ia.downloads == []                        # the station copy paired through the anchor
    assert {n: fake_source(ws.package_dir / "audio" / n) for n in audio_files(ws)} == {
        "01 - A2.mp3": "a.mp3", "02 - B2.mp3": "b.mp3"}
    assert not ws.reuse_anchor.exists()
