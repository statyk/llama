"""`llama redo`: the single re-execution verb -- positional show, selector
batch, and `--run SESSION` session scope (absorbing the old
`run --stage X --force` run-wide re-execution). Plan B Task 6."""
import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.models import Criteria, Provenance, QualityAssessment, Show, ShortlistEntry, Track
from llama.workspace import (
    RunWorkspace, ShowWorkspace, read_model, read_model_list, write_artifact,
)

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


def test_redo_rejects_name_and_selector_together(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "someshow", "--unvoiced", "--from", "package"])
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
    build(tmp_path, "inrun", stages={"select", "gather", "research", "vet", "synthesize", "package"},
          run="r1")
    build(tmp_path, "otherrun", stages={"select", "gather", "research", "vet", "synthesize", "package"},
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
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "synthesize", "package"},
          run="r1")
    build(tmp_path, "heldpkg", stages={"select", "gather", "research", "vet", "synthesize", "package"},
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

def test_redo_batch_unvoiced_plans_and_confirms(tmp_path, monkeypatch):
    from test_pipeline import FakeIA, fake_providers
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--auto", "--script",
                            "--name", "r"])

    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["--config", cfg, "redo", "--unvoiced", "--from", "package",
                                "--voice"], input="y\n")
    assert r.exit_code == 0, r.output
    assert calls == ["gratefuldead-1973-06-10"]


def test_redo_selector_batch_drops_held_unless_flag(tmp_path, monkeypatch):
    from test_catalog import build

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
    build(tmp_path, "heldpkg", stages={"select", "gather", "research", "vet", "synthesize", "package"},
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
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
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
    build(tmp_path, "aready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
    build(tmp_path, "bready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
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
    build(tmp_path, "heldpkg", stages={"select", "gather", "research", "vet", "synthesize", "package"},
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
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
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
        "get", "GD 1973", "--auto", "--script", "--name", "redorun"])
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
        "get", "GD 1973", "--auto", "--script", "--name", "redosel"])
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


def test_redo_run_package_keeps_cached_dj_notes(tmp_path: Path, monkeypatch):
    import llama.pipeline as pipeline
    from test_pipeline import JB_OFF, FakeIA, fake_providers

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    cfg = str(tmp_path / "config.toml")

    first = runner.invoke(cli.app, ["--config", cfg,
        "get", "GD 1973", "--auto", "--script", "--name", "replay"])
    assert first.exit_code == 0, first.output

    # Re-package via --run WITHOUT --script: cached dj-notes.json must still
    # drive the manifest.
    replay = runner.invoke(cli.app, ["--config", cfg,
        "redo", "--run", "replay", "--from", "package", "--no-script", "--yes"])
    assert replay.exit_code == 0, replay.output

    pkg = tmp_path / "shows" / "gratefuldead-1973-06-10" / "package"
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["dj_notes"] is not None
    assert manifest["set_breaks"] == [{"after_track": 3}, {"after_track": 5}]
    assert (pkg / "dj-notes.md").exists()


def test_redo_from_package_regenerates_missing_briefing(tmp_path: Path, monkeypatch):
    """A pre-existing workspace with dj-notes but no briefing.json (e.g. built
    before this stage existed) self-heals on the next redo: process_show finds
    the briefing artifact missing and regenerates it, even though --from
    package doesn't drop the brief stage's artifacts."""
    import llama.pipeline as pipeline
    from test_pipeline import JB_OFF, FakeIA, fake_providers

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    cfg = str(tmp_path / "config.toml")

    first = runner.invoke(cli.app, ["--config", cfg,
        "get", "GD 1973", "--auto", "--script", "--name", "selfheal"])
    assert first.exit_code == 0, first.output

    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    assert (show_dir / "dj-notes.json").exists()
    assert (show_dir / "briefing.json").exists()
    (show_dir / "briefing.json").unlink()
    (show_dir / "briefing.md").unlink()

    replay = runner.invoke(cli.app, ["--config", cfg,
        "redo", "--run", "selfheal", "--from", "package", "--no-script", "--yes"])
    assert replay.exit_code == 0, replay.output
    assert (show_dir / "briefing.json").exists()
    assert (show_dir / "briefing.md").exists()


def test_redo_run_synthesize_implies_script(tmp_path: Path, monkeypatch):
    import llama.pipeline as pipeline
    from test_pipeline import JB_OFF, FakeIA, fake_providers

    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n{JB_OFF}')
    monkeypatch.setattr(pipeline, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    cfg = str(tmp_path / "config.toml")

    first = runner.invoke(cli.app, ["--config", cfg,
        "get", "GD 1973", "--auto", "--no-script", "--name", "synthreplay"])
    assert first.exit_code == 0, first.output
    show_dir = tmp_path / "shows" / "gratefuldead-1973-06-10"
    assert not (show_dir / "dj-notes.json").exists()

    replay = runner.invoke(cli.app, ["--config", cfg,
        "redo", "--run", "synthreplay", "--from", "synthesize", "--yes"])
    assert replay.exit_code == 0, replay.output
    assert (show_dir / "dj-notes.json").exists()


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
