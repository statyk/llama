import json
import tomllib
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.config import DEFAULT_CONFIG_TOML
from llama.ledger import Ledger
from llama.models import (
    Candidate, Criteria, LedgerEntry, Overrides, Provenance, QualityAssessment, RecordingSummary,
    Show, ShortlistEntry, Track,
)
from llama.workspace import (
    RunWorkspace, ShowWorkspace, read_model, read_model_list, read_overrides, write_artifact,
)

runner = CliRunner()


def make_entries():
    def entry(rank, pid):
        return ShortlistEntry(
            rank=rank,
            candidate=Candidate(performance_id=pid, collection="GratefulDead",
                                date=f"1973-06-{9 + rank:02d}", venue="V",
                                recordings=[RecordingSummary(identifier=f"id{rank}")]),
            assessment=QualityAssessment(performance_id=pid, quality_score=9.0,
                                         rationale="great show"),
        )
    return [entry(1, "GratefulDead/1973-06-10"), entry(2, "GratefulDead/1973-06-11")]


def test_review_approves_selected_ranks(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["review", str(ws.dir), "--config",
                                     str(tmp_path / "config.toml")], input="1\nn\n")
    assert result.exit_code == 0, result.output
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert entries[0].approved is True
    assert entries[1].approved is None       # unnamed ranks are left undecided
    assert f"llama run {ws.dir}" in result.output


def test_review_shortlist_shows_artist(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    entries = make_entries()
    entries[1].candidate.collection = "mekons"  # multi-artist profile
    write_artifact(ws.shortlist, entries)
    result = runner.invoke(cli.app, ["review", str(ws.dir), "--config",
                                     str(tmp_path / "config.toml")], input="\n")
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert any("GratefulDead" in ln and "1973-06-10" in ln for ln in lines)
    assert any("mekons" in ln and "1973-06-11" in ln for ln in lines)


LONG_RATIONALE = " ".join(f"w{i:03d}" for i in range(120))  # ~600 chars, unique tokens


def _long_rationale_entries():
    entries = make_entries()
    entries[0].assessment.rationale = LONG_RATIONALE
    return entries


def test_shortlist_wraps_long_rationale_and_truncates(capsys):
    cli._print_shortlist(_long_rationale_entries())
    out = capsys.readouterr().out
    assert "w040" in out                     # well past the old 80-char cutoff
    assert "w119" not in out                 # tail still clipped by default
    assert "…" in out                        # clipping is visible


def test_shortlist_full_shows_entire_rationale(capsys):
    cli._print_shortlist(_long_rationale_entries(), full=True)
    out = capsys.readouterr().out
    assert "w119" in out
    assert "…" not in out


def test_shortlist_short_rationale_has_no_ellipsis(capsys):
    cli._print_shortlist(make_entries())
    out = capsys.readouterr().out
    assert "great show" in out
    assert "…" not in out


def test_shortlist_entries_are_visually_separated(capsys):
    cli._print_shortlist(make_entries())
    lines = capsys.readouterr().out.splitlines()
    assert lines.count("") == 1              # one separator for two entries...
    assert lines[2] == ""                    # ...between the blocks, not trailing


def test_review_full_rationale_flag(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.shortlist, _long_rationale_entries())
    result = runner.invoke(cli.app, ["review", str(ws.dir), "--full-rationale",
                                     "--config", str(tmp_path / "config.toml")], input="\n")
    assert result.exit_code == 0, result.output
    assert "w119" in result.output


def test_zero_caps_are_rejected_before_they_poison_criteria(tmp_path: Path, monkeypatch):
    from llama.llm.fake import FakeProvider

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({"query": "x", "collection": "GratefulDead"})
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json] * 4)})
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    for flag in ("--year-cap", "--artist-cap"):
        result = runner.invoke(cli.app, ["find", "GD", flag, "0.0",
                                         "--run-name", "z", "--config", cfg])
        assert result.exit_code == 1, f"find {flag} 0.0 must be rejected"
        assert "must be above 0" in result.output
        result = runner.invoke(cli.app, ["profile", "add", "z", "GD", flag, "0.0",
                                         "--config", cfg])
        assert result.exit_code == 1, f"profile add {flag} 0.0 must be rejected"
        assert "must be above 0" in result.output


def test_find_and_profile_run_pass_full_rationale_to_execute(tmp_path: Path, monkeypatch):
    from llama.llm.fake import FakeProvider
    from llama.models import Criteria as C
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    captured = {}
    monkeypatch.setattr(cli, "_execute",
                        lambda *a, **k: captured.update(full_rationale=k.get("full_rationale")))

    criteria_json = json.dumps({"query": "x", "collection": "GratefulDead", "count": 1})
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    result = runner.invoke(cli.app, ["find", "GD classics", "--full-rationale",
                                     "--run-name", "fr", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert captured["full_rationale"] is True

    save_profile(tmp_path, Profile(name="classic", criteria=C(query="GD classics")))
    result = runner.invoke(cli.app, ["profile", "run", "classic", "--full-rationale",
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    assert captured["full_rationale"] is True


def test_run_passes_full_rationale_to_execute(tmp_path: Path, monkeypatch):
    from llama.models import Criteria as C

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, C(query="q"))
    captured = {}
    monkeypatch.setattr(cli, "_execute",
                        lambda *a, **k: captured.update(full_rationale=k.get("full_rationale")))
    result = runner.invoke(cli.app, ["run", str(ws.dir), "--full-rationale", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert captured["full_rationale"] is True


def test_review_empty_input_changes_nothing(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["review", str(ws.dir), "--config",
                                     str(tmp_path / "config.toml")], input="\n")
    assert result.exit_code == 0, result.output
    assert "unchanged" in result.output
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert all(e.approved is None for e in entries)


def test_review_can_continue_straight_into_processing(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append((a, k)))
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["review", str(ws.dir), "--config",
                                     str(tmp_path / "config.toml")], input="1\ny\n")
    assert result.exit_code == 0, result.output
    assert len(calls) == 1


def _flagged_show(tmp_path: Path) -> ShowWorkspace:
    from llama.models import Show

    sws = ShowWorkspace(tmp_path / "shows" / "mekons-1989-12-02")
    write_artifact(sws.show, Show(
        performance_id="Mekons/1989-12-02", identifier="mek89", artist="Mekons",
        date="1989-12-02", venue="Metro", needs_review=True,
        review_flags=["single-set structure for a long show"],
    ))
    return sws


def test_show_prints_flags(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _flagged_show(tmp_path)
    result = runner.invoke(cli.app, ["show", str(sws.dir), "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "needs-review: yes" in result.output
    assert "single-set structure for a long show" in result.output


def test_show_clear_overrules_the_hold(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _flagged_show(tmp_path)
    result = runner.invoke(cli.app, ["show", str(sws.dir), "--clear", "--config", cfg])
    assert result.exit_code == 0, result.output
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is False
    assert saved["review_flags"] == []
    assert "llama redo" in result.output     # points at the resume command


def test_show_errors_without_show_json(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = ShowWorkspace(tmp_path / "shows" / "bare-1970-01-01")
    write_artifact(sws.selection, "{}")      # a show dir that has no show.json yet
    result = runner.invoke(cli.app, ["show", "bare", "--config", cfg])
    assert result.exit_code == 1
    assert "no show.json" in result.output


def _held_show_dir(tmp_path):
    # minimal held, provenance-bearing show (reuse existing builders if present)
    from test_catalog import build
    ws = build(tmp_path, "gratefuldead-1973-06-10",
               stages={"select", "gather"}, needs_review=True)
    return ws


def test_show_vague_writes_overrides_clears_hold_prints_next(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = _held_show_dir(tmp_path)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--vague", "--config", cfg])
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.narration == "vague"
    from llama.models import Show
    assert read_model(ws.show, Show).needs_review is False
    assert "redo gratefuldead-1973-06-10 --from synthesize" in r.output


def test_show_vague_output_is_not_self_contradictory(tmp_path):
    # A resolution flag must not reprint the pre-action inspection: no stale
    # "needs-review: yes" and no "--clear" overrule hint after --vague already
    # cleared the hold. It confirms the change instead.
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _held_show_dir(tmp_path)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--vague", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert "needs-review: yes" not in r.output
    assert "--clear" not in r.output
    assert "narration = vague; hold cleared" in r.output


def test_show_exclude_writes_overrides_keeps_hold_prints_gather(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = _held_show_dir(tmp_path)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--exclude", "junk.mp3",
                                "--config", cfg])
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).exclude == ["junk.mp3"]
    from llama.models import Show
    assert read_model(ws.show, Show).needs_review is True   # NOT pre-cleared
    assert "--from gather" in r.output


def test_show_exclude_by_number_resolves_to_filename(tmp_path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"},
               needs_review=True)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--exclude", "1",
                                "--config", cfg])
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).exclude == ["a.mp3"]   # track 1's filename


def test_show_exclude_out_of_range_errors(tmp_path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"}, needs_review=True)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--exclude", "99", "--config", cfg])
    assert r.exit_code != 0
    assert "track 99" in r.output or "out of range" in r.output


def test_show_set_venue_and_title_write_overrides_route_gather(tmp_path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"},
               needs_review=True)
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--set-venue", "My Hall",
                                "--title", "1=Bertha", "--config", cfg])
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.venue == "My Hall" and ov.titles == {1: "Bertha"}
    assert "--from gather" in r.output


def test_show_set_breaks_and_clear(tmp_path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    runner.invoke(cli.app, ["show", "gratefuldead", "--set-breaks", "2,4", "--config", cfg])
    assert read_overrides(ws).set_breaks == [2, 4]
    runner.invoke(cli.app, ["show", "gratefuldead", "--clear-set-breaks", "--config", cfg])
    assert read_overrides(ws).set_breaks is None


def _approved_run(tmp_path: Path) -> tuple[str, RunWorkspace]:
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    entries = make_entries()
    entries[0].approved = True
    write_artifact(ws.shortlist, entries)
    return cfg, ws


def test_bare_force_with_approvals_asks_before_wiping(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append(1))
    cfg, ws = _approved_run(tmp_path)
    result = runner.invoke(cli.app, ["run", str(ws.dir), "--force", "--config", cfg],
                           input="n\n")
    assert result.exit_code == 1
    assert not calls
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert entries[0].approved is True       # nothing was wiped

    result = runner.invoke(cli.app, ["run", str(ws.dir), "--force", "--config", cfg],
                           input="y\n")
    assert result.exit_code == 0, result.output
    assert calls


def test_bare_force_without_approvals_does_not_prompt(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append(1))
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    write_artifact(ws.shortlist, make_entries())    # no approvals recorded
    result = runner.invoke(cli.app, ["run", str(ws.dir), "--force", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert calls


def test_drop_stage_artifacts_cascades_for_one_show(tmp_path: Path):
    from llama.workspace import drop_stage_artifacts

    sws = ShowWorkspace(tmp_path / "s")
    for path in [sws.selection, sws.show, sws.reviews, sws.vetting, sws.dj_notes_json]:
        write_artifact(path, "{}")
    write_artifact(sws.research, "research")
    write_artifact(sws.dj_notes_md, "notes")
    write_artifact(sws.package_dir / "manifest.json", "{}")

    drop_stage_artifacts(sws, "gather")
    assert sws.selection.exists()            # upstream stage untouched
    for path in [sws.show, sws.reviews, sws.research, sws.vetting,
                 sws.dj_notes_json, sws.dj_notes_md, sws.package_dir / "manifest.json"]:
        assert not path.exists(), path


def test_search_force_also_drops_stale_shortlist(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    cfg, ws = _approved_run(tmp_path)
    write_artifact(ws.candidates, [])
    result = runner.invoke(cli.app, ["run", str(ws.dir), "--stage", "search",
                                     "--force", "--config", cfg], input="y\n")
    assert result.exit_code == 0, result.output
    assert not ws.candidates.exists()
    assert not ws.shortlist.exists()


def test_ledger_commands(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    add = runner.invoke(cli.app, ["ledger", "add", "GratefulDead/1977-05-08",
                                  "--artist", "Grateful Dead", "--date", "1977-05-08",
                                  "--config", cfg])
    assert add.exit_code == 0
    listing = runner.invoke(cli.app, ["ledger", "list", "--config", cfg])
    assert "1977-05-08" in listing.output
    rm = runner.invoke(cli.app, ["ledger", "remove", "GratefulDead/1977-05-08", "--config", cfg])
    assert rm.exit_code == 0
    assert Ledger(tmp_path / "ledger.jsonl").entries() == []


def _full_manifest(sws: ShowWorkspace, pid: str, artist: str, show_date: str) -> None:
    """Overwrite the bare seeded manifest with a delivery-ready v2 manifest."""
    (sws.package_dir / "audio").mkdir(parents=True, exist_ok=True)
    write_artifact(sws.package_dir / "manifest.json", {
        "schema_version": 2,
        "show": {"artist": artist, "date": show_date, "venue": "RFK",
                 "city": None, "context": ""},
        "source": {"performance_id": pid},
        "tracks": [], "set_breaks": [],
        "total_duration_sec": 0, "set_durations_sec": {},
    })


def test_deliver_copies_package_and_records(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _seed_show(tmp_path, "gratefuldead-1973-06-10", "GratefulDead/1973-06-10", "myrun")
    _full_manifest(sws, "GratefulDead/1973-06-10", "Grateful Dead", "1973-06-10")
    dest = tmp_path / "station-inbox"
    result = runner.invoke(cli.app, ["deliver", str(sws.dir), "--dest", str(dest),
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    assert (dest / "gratefuldead-1973-06-10" / "manifest.json").exists()
    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    assert entries[0].status == "delivered"
    assert entries[0].performance_id == "GratefulDead/1973-06-10"
    assert entries[0].run == "myrun"       # run now comes from provenance


def test_deliver_refuses_needs_review_without_force(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _seed_show(tmp_path, "gratefuldead-1973-06-10", "GratefulDead/1973-06-10",
                     "myrun", held=True)
    _full_manifest(sws, "GratefulDead/1973-06-10", "Grateful Dead", "1973-06-10")
    dest = tmp_path / "station-inbox"

    result = runner.invoke(cli.app, ["deliver", str(sws.dir), "--dest", str(dest), "--config", cfg])
    assert result.exit_code == 1
    assert "needs-review" in result.output
    assert not dest.exists()

    forced = runner.invoke(cli.app, ["deliver", str(sws.dir), "--dest", str(dest),
                                     "--force", "--config", cfg])
    assert forced.exit_code == 0, forced.output
    assert (dest / "gratefuldead-1973-06-10" / "manifest.json").exists()


def test_redo_batch_unvoiced_plans_and_confirms(tmp_path, monkeypatch):
    from test_pipeline import FakeIA, fake_providers
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    runner.invoke(cli.app, ["find", "GD 1973", "--auto", "--script",
                            "--run-name", "r", "--config", cfg])

    calls = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda *a, **k: calls.append(a[3].slug) or a[3].ws.package_dir)
    r = runner.invoke(cli.app, ["redo", "--unvoiced", "--from", "package",
                                "--voice", "--config", cfg], input="y\n")
    assert r.exit_code == 0, r.output
    assert calls == ["gratefuldead-1973-06-10"]


def test_redo_batch_requires_target(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["redo", "--from", "package", "--config", cfg])
    assert r.exit_code != 0
    assert "a show or a selector" in r.output.lower()


def test_redo_rejects_name_and_selector_together(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["redo", "someshow", "--unvoiced", "--from", "package",
                                "--config", cfg])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_deliver_batch_continues_past_oserror(tmp_path, monkeypatch):
    """A per-show OSError (e.g. shutil.copytree hitting disk-full/permissions)
    must be reported as FAILED and not abort the rest of the batch -- matching
    the batch redo loop's (LlamaError, TaskFailed, LLMError, IAError,
    SpeechError) broad catch."""
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\ndelivery_path = "{tmp_path}/out"\n')
    build(tmp_path, "aready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
    build(tmp_path, "bready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
    delivered = []

    def fake_deliver_one(cfg_, led_, e, dest, force):
        if e.slug == "aready":
            raise OSError("disk full")
        delivered.append(e.slug)

    monkeypatch.setattr(cli, "_deliver_one", fake_deliver_one)
    r = runner.invoke(cli.app, ["deliver", "--packaged", "--yes", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert "FAILED aready" in r.output
    assert delivered == ["bready"]


def test_deliver_rejects_name_and_selector_together(tmp_path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    r = runner.invoke(cli.app, ["deliver", "someshow", "--packaged", "--config", cfg])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_deliver_batch_excludes_held(tmp_path, monkeypatch):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\ndelivery_path = "{tmp_path}/out"\n')
    # one packaged, one held+packaged
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
    build(tmp_path, "heldpkg", stages={"select", "gather", "research", "vet", "synthesize", "package"},
          needs_review=True)
    delivered = []
    monkeypatch.setattr(cli, "_deliver_one", lambda cfg_, led_, e, dest, force: delivered.append(e.slug))
    r = runner.invoke(cli.app, ["deliver", "--packaged", "--yes", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert delivered == ["ready"]  # held excluded


def test_deliver_batch_excludes_held_via_nonstate_selector(tmp_path, monkeypatch):
    """Both shows share an artist (no --state/--packaged filter involved), so
    the held one can only be dropped by the `if not held` post-filter in
    _batch_select -- not by select_shows(states=...)."""
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\ndelivery_path = "{tmp_path}/out"\n')
    build(tmp_path, "ready", stages={"select", "gather", "research", "vet", "synthesize", "package"})
    build(tmp_path, "heldpkg", stages={"select", "gather", "research", "vet", "synthesize", "package"},
          needs_review=True)
    delivered = []
    monkeypatch.setattr(cli, "_deliver_one", lambda cfg_, led_, e, dest, force: delivered.append(e.slug))
    r = runner.invoke(cli.app, ["deliver", "--artist", "Grateful Dead", "--yes", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert delivered == ["ready"]  # held excluded even though --artist matched both


def test_run_unknown_stage_exits_with_message(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))

    result = runner.invoke(cli.app, ["run", str(ws.dir), "--stage", "bogus", "--config", cfg])
    assert result.exit_code == 1
    assert "unknown stage" in result.output


def test_review_resolves_run_by_substring(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "2026-07-16-countryish")
    write_artifact(ws.criteria, Criteria(query="q"))
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["review", "countryish", "--config", cfg],
                           input="1\nn\n")
    assert result.exit_code == 0, result.output
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert entries[0].approved is True


def test_run_unknown_name_fails_loud(tmp_path: Path):
    from llama.catalog import CatalogError

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["run", "nope", "--config", cfg])
    # _resolve_run no longer catches CatalogError; only main_cli() (not this direct
    # cli.app invocation) renders it as clean stderr text, so assert on the
    # propagated exception instead.
    assert result.exit_code == 1
    assert isinstance(result.exception, CatalogError)
    assert "no run matches" in str(result.exception)


FUZZY_CRITERIA = json.dumps({
    "query": "x", "collection": None, "artist": None,
    "date_from": "1960-01-01", "date_to": "1979-12-31",
    "setlist_constraints": [], "soft_preferences": "folk/acoustic, well known",
    "min_avg_rating": 3.5, "min_reviews": 3, "count": 1,
})

ARTIST_COLLECTIONS = [
    {"identifier": "JoanBaez", "title": "Joan Baez", "downloads": 900000},
    {"identifier": "DocWatson", "title": "Doc and Merle Watson", "downloads": 800000},
    {"identifier": "TownesVanZandt", "title": "Townes Van Zandt", "downloads": 700000},
]


class FuzzyFakeIA:
    def __init__(self, *args, **kwargs):
        self.etree_queries = []

    def scrape(self, query, fields, count=10000):
        if "mediatype:collection" in query:
            return ARTIST_COLLECTIONS  # artist-index build: collections pass
        if query.startswith("collection:etree"):
            return []  # artist-index build: per-item counts pass
        self.etree_queries.append(query)  # search stage
        return []  # no shows: pipeline ends at "No shows survived winnowing."


def fuzzy_matches():
    return json.dumps({"matches": [
        {"identifier": "JoanBaez", "reason": "folk icon"},
        {"identifier": "DocWatson", "reason": "flatpicking"},
        {"identifier": "TownesVanZandt", "reason": "songwriter"},
    ]})


def fuzzy_providers(config):
    from llama.llm.fake import FakeProvider
    return {
        "interpret": FakeProvider(completes=[FUZZY_CRITERIA]),
        "find_artists": FakeProvider(completes=[fuzzy_matches()]),
        "score_reviews": FakeProvider(),
        "light_research": FakeProvider(),
        "extract_setlist": FakeProvider(),
        "deep_research": FakeProvider(),
        "synthesize": FakeProvider(),
    }


def _fuzzy_setup(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ia = FuzzyFakeIA()
    monkeypatch.setattr(cli, "make_providers", fuzzy_providers)
    monkeypatch.setattr(cli, "IAClient", lambda *a, **k: ia)
    return ia


def test_fuzzy_query_interactive_prune(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--run-name", "fz",
        "--config", str(tmp_path / "config.toml"),
    ], input="2\n")
    assert result.exit_code == 0, result.output
    assert "Doc and Merle Watson" in result.output
    assert len(ia.etree_queries) == 1
    assert "collection:DocWatson" in ia.etree_queries[0]
    saved = json.loads((tmp_path / "runs" / "fz" / "artists.json").read_text())
    assert [a["identifier"] for a in saved] == ["DocWatson"]


def test_fuzzy_query_auto_uses_all(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--auto", "--run-name", "fz2",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert len(ia.etree_queries) == 3


def test_fuzzy_query_zero_matches_exits_cleanly(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: {
        **fuzzy_providers(config),
        "find_artists": __import__("llama.llm.fake", fromlist=["FakeProvider"]).FakeProvider(
            completes=[json.dumps({"matches": [{"identifier": "NickDrake", "reason": "x"}]})]),
    })
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--auto", "--run-name", "fz3",
        "--config", str(tmp_path / "config.toml"),
    ])
    assert result.exit_code == 0, result.output
    assert "no matching artists" in result.output
    assert ia.etree_queries == []


def test_fuzzy_query_invalid_prune_aborts(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, [
        "find", "folk 60s-70s", "--run-name", "fz4",
        "--config", str(tmp_path / "config.toml"),
    ], input="99\n")
    assert result.exit_code == 0, result.output
    assert "no valid selections" in result.output
    assert ia.etree_queries == []
    saved = json.loads((tmp_path / "runs" / "fz4" / "artists.json").read_text())
    assert len(saved) == 3  # artifact NOT overwritten with the empty prune


def test_profile_add_and_list(tmp_path: Path, monkeypatch):
    from llama.llm.fake import FakeProvider
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({
        "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
        "date_from": None, "date_to": None, "setlist_constraints": [],
        "soft_preferences": None, "min_avg_rating": 4.0, "min_reviews": 3, "count": 1,
    })
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    add = runner.invoke(cli.app, ["profile", "add", "sunday-dead", "GD classics",
                                  "--count", "2", "--human-gate", "--artist-cap", "0.5",
                                  "--year-cap", "0.25",
                                  "--min-score", "7.5", "--config", cfg])
    assert add.exit_code == 0, add.output
    assert (tmp_path / "profiles" / "sunday-dead.toml").exists()
    from llama.profiles import load_profile
    saved = load_profile(tmp_path, "sunday-dead")
    assert saved.criteria.artist_cap == 0.5
    assert saved.criteria.min_quality_score == 7.5
    assert saved.criteria.year_cap == 0.25
    listing = runner.invoke(cli.app, ["profile", "list", "--config", cfg])
    assert "sunday-dead" in listing.output


def test_find_stamps_year_cap_into_run_criteria(tmp_path: Path, monkeypatch):
    from llama.llm.fake import FakeProvider
    from llama.models import Criteria as C

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({"query": "x", "collection": "GratefulDead"})
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    result = runner.invoke(cli.app, ["find", "GD classics", "--year-cap", "0.5",
                                     "--run-name", "yc", "--config", cfg])
    assert result.exit_code == 0, result.output
    saved = read_model(RunWorkspace(tmp_path, "yc").criteria, C)
    assert saved.year_cap == 0.5


def test_profile_run_stamps_count_and_script_into_run_criteria(tmp_path: Path, monkeypatch):
    # Replaying a profile's run dir must behave like the profile: count and
    # script live in the run's criteria.json, not only in the profile.
    from llama.llm.fake import FakeProvider
    from llama.models import Criteria as C
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_profile(tmp_path, Profile(name="classic", criteria=C(query="GD classics"),
                                   count=13, script=True))
    captured = {}

    def fake_execute(config, ia, ledger, ws, criteria, count, auto, human_gate,
                     force=False, script=False, voice=None,
                     presenter=None, title=None, force_stage=None,
                     full_rationale=False):
        captured.update(count=count, script=script, criteria=criteria)

    monkeypatch.setattr(cli, "_execute", fake_execute)
    result = runner.invoke(cli.app, ["profile", "run", "classic", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert captured["count"] == 13 and captured["script"] is True
    saved = read_model(RunWorkspace(tmp_path, f"{date.today().isoformat()}-classic").criteria, C)
    assert saved.count == 13 and saved.script is True


def test_run_inherits_script_and_count_from_criteria(tmp_path: Path, monkeypatch):
    from llama.models import Criteria as C

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, C(query="q", count=13, script=True))
    captured = {}

    def fake_execute(config, ia, ledger, ws, criteria, count, auto, human_gate,
                     force=False, script=False, voice=None,
                     presenter=None, title=None, force_stage=None,
                     full_rationale=False):
        captured.update(count=count, script=script)

    monkeypatch.setattr(cli, "_execute", fake_execute)
    result = runner.invoke(cli.app, ["run", str(ws.dir), "--config", cfg])
    assert result.exit_code == 0, result.output
    assert captured == {"count": 13, "script": True}

    # explicit --no-script overrides the persisted flag
    result = runner.invoke(cli.app, ["run", str(ws.dir), "--no-script", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert captured["script"] is False


def test_stage_force_deletion_is_deferred_to_processing(tmp_path: Path, monkeypatch):
    # run() must NOT bulk-delete show artifacts up front: with count < shows
    # present, unchosen shows would lose their packages and never be rebuilt
    # (this vaporized 10 manifests in a real run). Deletion happens per chosen
    # show inside process_show.
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    cfg, ws = _approved_run(tmp_path)
    sws = ws.show_ws("GratefulDead/1973-06-10")
    for path in [sws.selection, sws.show, sws.dj_notes_json]:
        write_artifact(path, "{}")
    write_artifact(sws.package_dir / "manifest.json", "{}")
    result = runner.invoke(cli.app, ["run", str(ws.dir), "--stage", "synthesize",
                                     "--force", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert sws.dj_notes_json.exists()                      # untouched by run()
    assert (sws.package_dir / "manifest.json").exists()


def test_stage_vet_is_valid_and_maps_to_vetting_artifact(tmp_path: Path):
    from llama.workspace import show_stage_artifacts

    assert "vet" in cli.VALID_STAGES
    sws = ShowWorkspace(tmp_path / "s")
    assert show_stage_artifacts(sws, "vet") == [sws.vetting]


def test_stage_research_maps_to_research_and_vetting(tmp_path: Path):
    # re-researching with --force must also drop vetting.json so the fresh
    # document is re-vetted rather than shipping under the old extraction.
    from llama.workspace import show_stage_artifacts

    sws = ShowWorkspace(tmp_path / "s")
    assert show_stage_artifacts(sws, "research") == [sws.research, sws.vetting]


PIN_INDEX = [
    {"identifier": "Galactic", "title": "Galactic"},
    {"identifier": "Lettuce", "title": "Lettuce"},
    {"identifier": "Soulive", "title": "Soulive"},
]


def test_profile_add_pins_resolved_artists(tmp_path: Path, monkeypatch):
    from llama.llm.fake import FakeProvider
    from llama.profiles import load_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({"query": "funk"})
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    monkeypatch.setattr(cli, "load_or_build", lambda ia, cache: PIN_INDEX)
    result = runner.invoke(cli.app, ["profile", "add", "funky", "funk",
                                     "--artists", "galactic, lettuce", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "pinned: Galactic (Galactic), Lettuce (Lettuce)" in result.output
    assert load_profile(tmp_path, "funky").criteria.artists == ["Galactic", "Lettuce"]


def test_profile_add_rejects_unknown_pinned_artist(tmp_path: Path, monkeypatch):
    from llama.errors import ArtistResolutionError
    from llama.llm.fake import FakeProvider

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[json.dumps({"query": "funk"})])})
    monkeypatch.setattr(cli, "load_or_build", lambda ia, cache: PIN_INDEX)
    result = runner.invoke(cli.app, ["profile", "add", "funky", "funk",
                                     "--artists", "Zebra Ensemble", "--config", cfg])
    # resolve_artists now raises ArtistResolutionError, an uncaught LlamaError that
    # only main_cli() (not this direct cli.app invocation) renders as clean stderr text.
    assert result.exit_code == 1
    assert isinstance(result.exception, ArtistResolutionError)
    assert "cannot pin artist" in str(result.exception)
    assert not (tmp_path / "profiles" / "funky.toml").exists()


def test_pinned_artists_skip_discover_and_prune(tmp_path: Path, monkeypatch):
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_profile(tmp_path, Profile(
        name="funky",
        criteria=Criteria(query="funk", soft_preferences="funky",
                          artists=["Galactic", "Lettuce"]),
    ))

    def boom(*a, **k):
        raise AssertionError("discover must not run for a pinned roster")

    seen = {}
    monkeypatch.setattr(cli, "run_discover", boom)
    monkeypatch.setattr(cli, "run_search",
                        lambda ws, ia, criteria, artists=None, force=False, jerrybase_enabled=True:
                            seen.update(artists=artists) or [])
    monkeypatch.setattr(cli, "run_winnow", lambda *a, **k: [])
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"score_reviews": None, "light_research": None})
    # interactive mode (auto=False): a pinned roster must not prompt either
    result = runner.invoke(cli.app, ["profile", "run", "funky", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "pinned artists: Galactic, Lettuce" in result.output
    assert [a["identifier"] for a in seen["artists"]] == ["Galactic", "Lettuce"]
    run_dir = tmp_path / "runs"
    artists_files = list(run_dir.glob("*/artists.json"))
    assert len(artists_files) == 1  # roster recorded in the run dir


def _seed_show(root: Path, slug: str, pid: str, run: str, *, held=False,
               packaged=True, delivered=False,
               recorded_at="2026-07-17T00:00:00+00:00"):
    sws = ShowWorkspace(root / "shows" / slug)
    write_artifact(sws.provenance, Provenance(
        performance_id=pid, run=run, dossier="d",
        candidate=Candidate(performance_id=pid, collection=pid.split("/")[0],
                            date=pid.split("/")[1],
                            recordings=[RecordingSummary(identifier="x")]),
        processed_at="2026-07-17T00:00:00+00:00"))
    write_artifact(sws.show, Show(
        performance_id=pid, identifier="x", artist=pid.split("/")[0],
        date=pid.split("/")[1],
        tracks=[Track(index=1, set="1", title="T", filename="a.mp3",
                      title_source="tags")],
        needs_review=held, review_flags=["two sets missing"] if held else []))
    if packaged:
        write_artifact(sws.package_dir / "manifest.json", {"schema_version": 2})
    if delivered:
        Ledger(root / "ledger.jsonl").record(LedgerEntry(
            performance_id=pid, artist=pid.split("/")[0], date=pid.split("/")[1],
            status="delivered", run=run, recorded_at=recorded_at))
    return sws


def test_status_orders_held_first_and_filters(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1", delivered=True)
    _seed_show(tmp_path, "bbb-1971-01-01", "bbb/1971-01-01", "r1", held=True)
    _seed_show(tmp_path, "ccc-1972-01-01", "ccc/1972-01-01", "r2")

    result = runner.invoke(cli.app, ["status", "--config", cfg])
    assert result.exit_code == 0, result.output
    lines = [ln for ln in result.output.splitlines() if ln.strip()]
    rows = [ln for ln in lines if not ln.startswith("      ")]  # drop flag detail lines
    assert rows[0].startswith("bbb-1971-01-01")       # held first
    assert "two sets missing" in result.output
    assert "packaged" in rows[1]                       # ccc next
    assert "delivered" in rows[-1]                     # aaa last

    held_only = runner.invoke(cli.app, ["status", "--held", "--config", cfg])
    assert "bbb-1971-01-01" in held_only.output
    assert "ccc-1972-01-01" not in held_only.output

    by_run = runner.invoke(cli.app, ["status", "--run", "r2", "--config", cfg])
    assert "ccc-1972-01-01" in by_run.output
    assert "bbb-1971-01-01" not in by_run.output


def test_status_recent_delivered_keeps_most_recent_not_slug_order(tmp_path: Path):
    """The 5-show trim must keep the most recently delivered shows, not the
    alphabetically-last slugs. Seed 7 delivered shows where recency and slug
    order disagree: "a" and "b" sort first but were delivered most recently;
    "f" and "g" sort last but were delivered longest ago."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    letters = ["a", "b", "c", "d", "e", "f", "g"]
    # descending recency: a is newest, g is oldest.
    for i, letter in enumerate(letters):
        hour = 7 - i
        _seed_show(tmp_path, f"{letter}-1970-01-01", f"{letter}/1970-01-01", "r1",
                  delivered=True, recorded_at=f"2026-07-17T{hour:02d}:00:00+00:00")

    result = runner.invoke(cli.app, ["status", "--config", cfg])
    assert result.exit_code == 0, result.output

    # Most recently delivered 5 (a, b, c, d, e) must survive the trim.
    for letter in ["a", "b", "c", "d", "e"]:
        assert f"{letter}-1970-01-01" in result.output, result.output
    # Oldest deliveries (f, g) — alphabetically last but stalest — must be trimmed.
    for letter in ["f", "g"]:
        assert f"{letter}-1970-01-01" not in result.output, result.output


def test_status_json(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1")
    result = runner.invoke(cli.app, ["status", "--json", "--config", cfg])
    rows = json.loads(result.output)
    assert rows[0]["slug"] == "aaa-1970-01-01"
    assert rows[0]["state"] == "packaged"
    assert rows[0]["run"] == "r1"


def test_status_voiced_and_unvoiced_filters(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "silent-1970-01-01", "silent/1970-01-01", "r1", packaged=True)
    voiced_ws = _seed_show(tmp_path, "voiced-1971-01-01", "voiced/1971-01-01", "r1", packaged=True)
    write_artifact(voiced_ws.package_dir / "manifest.json",
                   {"schema_version": 2, "dj_audio": {"set_intros": {}, "outro": "o"}})

    unvoiced = runner.invoke(cli.app, ["status", "--unvoiced", "--config", cfg])
    assert unvoiced.exit_code == 0, unvoiced.output
    assert "silent-1970-01-01" in unvoiced.output
    assert "voiced-1971-01-01" not in unvoiced.output

    voiced = runner.invoke(cli.app, ["status", "--voiced", "--config", cfg])
    assert voiced.exit_code == 0, voiced.output
    assert "voiced-1971-01-01" in voiced.output
    assert "silent-1970-01-01" not in voiced.output
    assert "[voiced]" in voiced.output


def test_status_state_filter(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1", packaged=False)
    _seed_show(tmp_path, "bbb-1971-01-01", "bbb/1971-01-01", "r1", packaged=True)

    result = runner.invoke(cli.app, ["status", "--state", "gathered", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "aaa-1970-01-01" in result.output
    assert "bbb-1971-01-01" not in result.output


def test_status_json_has_voiced_and_overrides(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1", packaged=False)
    write_artifact(sws.overrides, Overrides(exclude=["a.mp3"], narration="vague"))

    result = runner.invoke(cli.app, ["status", "--json", "--config", cfg])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    row = next(r for r in rows if r["slug"] == "aaa-1970-01-01")
    assert row["voiced"] is None
    assert row["overrides"] == {"exclude": ["a.mp3"], "narration": "vague"}


def test_status_text_row_annotation(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1", packaged=True)
    write_artifact(sws.overrides, Overrides(exclude=["a.mp3", "b.mp3"], narration="vague"))

    result = runner.invoke(cli.app, ["status", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "[vague, 2x-excl]" in result.output


def test_runs_lists_runs_with_counts(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "2026-07-16-countryish")
    write_artifact(ws.criteria, Criteria(query="countryish bluegrass"))
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "2026-07-16-countryish")
    _seed_show(tmp_path, "bbb-1971-01-01", "bbb/1971-01-01", "2026-07-16-countryish",
               held=True)
    result = runner.invoke(cli.app, ["runs", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "2026-07-16-countryish" in result.output
    assert "countryish bluegrass" in result.output
    assert "held 1" in result.output and "packaged 1" in result.output


def test_show_resolves_by_name_and_lists_stages(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "mekons-1989-12-02", "mekons/1989-12-02", "r1", held=True)
    result = runner.invoke(cli.app, ["show", "mek", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "needs-review: yes" in result.output
    assert "show.json" in result.output          # stage table
    assert "research.md" in result.output
    assert "missing" in result.output            # research.md was never written


def test_show_tracks_lists_numbered_tracks(tmp_path: Path):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = runner.invoke(cli.app, ["show", "gratefuldead", "--tracks", "--config", cfg])
    assert r.exit_code == 0, r.output
    assert "tracks:" in r.output
    assert "1." in r.output and "Morning Dew" in r.output and "a.mp3" in r.output


def test_show_ambiguous_name_fails_loud(tmp_path: Path):
    from llama.catalog import CatalogError

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1")
    _seed_show(tmp_path, "aab-1970-01-01", "aab/1970-01-01", "r1")
    result = runner.invoke(cli.app, ["show", "aa", "--config", cfg])
    # _resolve_show no longer catches CatalogError; only main_cli() (not this direct
    # cli.app invocation) renders the candidate list as indented stderr lines, so
    # assert on the propagated exception's matches instead.
    assert result.exit_code == 1
    assert isinstance(result.exception, CatalogError)
    assert "aaa-1970-01-01" in result.exception.matches
    assert "aab-1970-01-01" in result.exception.matches


def test_show_clear_still_works_by_name(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _seed_show(tmp_path, "mekons-1989-12-02", "mekons/1989-12-02", "r1", held=True)
    result = runner.invoke(cli.app, ["show", "mekons", "--clear", "--config", cfg])
    assert result.exit_code == 0, result.output
    assert read_model(sws.show, Show).needs_review is False


def test_deliver_by_name_records_provenance_run(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "myrun")
    (sws.package_dir / "audio").mkdir(parents=True, exist_ok=True)
    write_artifact(sws.package_dir / "manifest.json", {
        "schema_version": 2,
        "show": {"artist": "aaa", "date": "1970-01-01", "venue": None,
                 "city": None, "context": ""},
        "source": {"performance_id": "aaa/1970-01-01"},
        "tracks": [], "set_breaks": [],
        "total_duration_sec": 0, "set_durations_sec": {},
    })
    dest = tmp_path / "inbox"
    result = runner.invoke(cli.app, ["deliver", "aaa", "--dest", str(dest),
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    assert (dest / "aaa-1970-01-01" / "manifest.json").exists()
    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    assert entries[0].status == "delivered" and entries[0].run == "myrun"


def test_redo_requires_from_and_reruns_tail(tmp_path: Path, monkeypatch):
    # tests/ has no __init__.py; pytest puts the tests dir on sys.path
    from test_pipeline import FakeIA, fake_providers

    cfg = str(tmp_path / "config.toml")
    # gd73-06-10 is a real in-dataset jerrybase performance; disable jerrybase so
    # this end-to-end find+redo test stays isolated from the dataset (the
    # synthesized candidate's "RFK Stadium" venue differs from jerrybase's
    # "Robert F. Kennedy Stadium", which would otherwise flag needs-review).
    (tmp_path / "config.toml").write_text(
        f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    # First, produce a real packaged show via find (writes provenance).
    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--script", "--run-name", "redorun",
        "--config", cfg,
    ])
    assert result.exit_code == 0, result.output
    sws = ShowWorkspace(tmp_path / "shows" / "gratefuldead-1973-06-10")
    research_before = sws.research.read_text()

    # --from is required
    missing = runner.invoke(cli.app, ["redo", "gratefuldead", "--config", cfg])
    assert missing.exit_code != 0

    result = runner.invoke(cli.app, ["redo", "gratefuldead", "--from", "gather",
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    assert sws.show.exists() and (sws.package_dir / "manifest.json").exists()
    assert sws.research.read_text() == research_before   # preserved by default


def test_redo_from_select_keeps_winnow_assessment(tmp_path: Path, monkeypatch):
    # redo --from select must feed run_select_recording the original winnow
    # assessment (quality_score + recording_complaints), not a zeroed stub.
    from test_pipeline import FakeIA, fake_providers
    from llama.models import Provenance

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    result = runner.invoke(cli.app, [
        "find", "GD 1973", "--auto", "--script", "--run-name", "redosel",
        "--config", cfg,
    ])
    assert result.exit_code == 0, result.output
    sws = ShowWorkspace(tmp_path / "shows" / "gratefuldead-1973-06-10")

    # Inject a recording complaint into the persisted winnow assessment so we
    # can prove redo preserves it (rather than rebuilding an empty stub).
    prov = read_model(sws.provenance, Provenance)
    assert prov.assessment is not None and prov.assessment.quality_score == 9.5
    prov.assessment.recording_complaints = ["hiss on side two (badtaper)"]
    write_artifact(sws.provenance, prov)

    result = runner.invoke(cli.app, ["redo", "gratefuldead", "--from", "select",
                                     "--config", cfg])
    assert result.exit_code == 0, result.output

    prov = read_model(sws.provenance, Provenance)
    assert prov.assessment is not None
    assert prov.assessment.quality_score == 9.5                    # preserved
    assert prov.assessment.recording_complaints == ["hiss on side two (badtaper)"]
    assert prov.assessment.rationale == prov.dossier               # dossier round-trip


def test_redo_without_provenance_errors(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = ShowWorkspace(tmp_path / "shows" / "orphan-1970-01-01")
    write_artifact(sws.show, Show(
        performance_id="orphan/1970-01-01", identifier="x", artist="orphan",
        date="1970-01-01", tracks=[Track(index=1, set="1", title="T",
                                         filename="a.mp3", title_source="tags")]))
    result = runner.invoke(cli.app, ["redo", "orphan", "--from", "vet",
                                     "--config", cfg])
    assert result.exit_code == 1
    assert "provenance.json" in result.output and "reprocess" in result.output


def test_config_init_writes_template(tmp_path: Path):
    target = tmp_path / "config.toml"
    result = runner.invoke(cli.app, ["config", "init", "--config", str(target)])
    assert result.exit_code == 0, result.output
    assert target.read_text() == DEFAULT_CONFIG_TOML
    tomllib.loads(target.read_text())        # parseable
    assert str(target) in result.output
    assert "replace" in result.output        # the no-merge reminder


def test_config_init_refuses_existing(tmp_path: Path):
    target = tmp_path / "config.toml"
    target.write_text('audio_format = "flac"\n')
    result = runner.invoke(cli.app, ["config", "init", "--config", str(target)])
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert target.read_text() == 'audio_format = "flac"\n'   # untouched


def test_config_init_defaults_to_root(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "DEFAULT_ROOT", tmp_path)
    result = runner.invoke(cli.app, ["config", "init"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "config.toml").read_text() == DEFAULT_CONFIG_TOML


def test_config_init_stdout_prints_and_writes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "DEFAULT_ROOT", tmp_path)
    result = runner.invoke(cli.app, ["config", "init", "--stdout"])
    assert result.exit_code == 0, result.output
    assert "[[selection.lineage_eras]]" in result.output
    assert not (tmp_path / "config.toml").exists()


def test_show_displays_corrected_date(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = ShowWorkspace(tmp_path / "shows" / "countryjoe-1976-01-01")
    write_artifact(sws.show, Show(
        performance_id="CountryJoe/1976-01-01", identifier="cjm76",
        artist="Country Joe McDonald", date="1976-02-08",
        item_date="1976-01-01", date_source="research", venue="WDR studio",
    ))
    result = runner.invoke(cli.app, ["show", str(sws.dir), "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "1976-02-08 (item date 1976-01-01, corrected via research)" in result.output


def test_show_displays_jerrybase_venue_provenance(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    sws = ShowWorkspace(tmp_path / "shows" / "gd-1977-05-08")
    write_artifact(sws.show, Show(
        performance_id="GratefulDead/1977-05-08", identifier="gd77",
        artist="Grateful Dead", date="1977-05-08",
        venue="Barton Hall, Cornell University", city="Ithaca",
        venue_source="jerrybase"))
    result = runner.invoke(cli.app, ["show", str(sws.dir), "--config", cfg])
    assert result.exit_code == 0, result.output
    assert "(venue from jerrybase)" in result.output


def test_show_interactive_vague_runs_resolution(tmp_path, monkeypatch):
    from test_pipeline import FakeIA, fake_providers
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    monkeypatch.setattr(cli, "_interactive_enabled", lambda: True)

    # real held show via find
    runner.invoke(cli.app, ["find", "GD 1973", "--auto", "--script",
                            "--run-name", "r", "--config", cfg])
    ws = ShowWorkspace(tmp_path / "shows" / "gratefuldead-1973-06-10")
    s = read_model(ws.show, Show); s.needs_review = True; s.review_flags = ["x"]
    write_artifact(ws.show, s)

    r = runner.invoke(cli.app, ["show", "gratefuldead", "--config", cfg], input="v\n")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).narration == "vague"
    assert read_model(ws.show, Show).needs_review is False


def test_show_single_interactive_prints_entry_once(tmp_path, monkeypatch):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "_interactive_enabled", lambda: True)
    build(tmp_path, "held-one", stages={"select", "gather"}, needs_review=True)

    r = runner.invoke(cli.app, ["show", "held-one", "--config", cfg], input="s\n")
    assert r.exit_code == 0, r.output
    assert r.output.count("state: held") == 1


def test_show_set_form_defaults_to_held(tmp_path, monkeypatch):
    from test_catalog import build
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "_interactive_enabled", lambda: False)  # inspect-only
    build(tmp_path, "held-one", stages={"select", "gather"}, needs_review=True)
    build(tmp_path, "clean-one", stages={"select", "gather"}, needs_review=False)
    r = runner.invoke(cli.app, ["show", "--config", cfg])
    assert "held-one" in r.output and "clean-one" not in r.output
