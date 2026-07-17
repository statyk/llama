import json
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.ledger import Ledger
from llama.models import (
    Candidate, Criteria, LedgerEntry, QualityAssessment, RecordingSummary, ShortlistEntry,
)
from llama.workspace import RunWorkspace, ShowWorkspace, read_model, read_model_list, write_artifact

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


def test_review_full_rationale_flag(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.shortlist, _long_rationale_entries())
    result = runner.invoke(cli.app, ["review", str(ws.dir), "--full-rationale",
                                     "--config", str(tmp_path / "config.toml")], input="\n")
    assert result.exit_code == 0, result.output
    assert "w119" in result.output


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

    sws = ShowWorkspace(tmp_path / "runs" / "r1" / "shows" / "mekons-1989-12-02")
    write_artifact(sws.show, Show(
        performance_id="Mekons/1989-12-02", identifier="mek89", artist="Mekons",
        date="1989-12-02", venue="Metro", needs_review=True,
        review_flags=["single-set structure for a long show"],
    ))
    return sws


def test_show_prints_flags(tmp_path: Path):
    sws = _flagged_show(tmp_path)
    result = runner.invoke(cli.app, ["show", str(sws.dir)])
    assert result.exit_code == 0, result.output
    assert "needs-review: yes" in result.output
    assert "single-set structure for a long show" in result.output


def test_show_clear_overrules_the_hold(tmp_path: Path):
    sws = _flagged_show(tmp_path)
    result = runner.invoke(cli.app, ["show", str(sws.dir), "--clear"])
    assert result.exit_code == 0, result.output
    saved = json.loads(sws.show.read_text())
    assert saved["needs_review"] is False
    assert saved["review_flags"] == []
    assert "llama run" in result.output      # points at the resume command


def test_show_errors_without_show_json(tmp_path: Path):
    result = runner.invoke(cli.app, ["show", str(tmp_path)])
    assert result.exit_code == 1
    assert "no show.json" in result.output


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


def test_deliver_copies_package_and_records(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    show_dir = tmp_path / "runs" / "r1" / "shows" / "gratefuldead-1973-06-10"
    pkg = show_dir / "package"
    (pkg / "audio").mkdir(parents=True)
    (pkg / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "show": {"artist": "Grateful Dead", "date": "1973-06-10", "venue": "RFK",
                 "city": None, "context": ""},
        "source": {"performance_id": "GratefulDead/1973-06-10"},
        "tracks": [], "set_breaks": [],
        "dj_notes": {"intro": "i", "set_intros": {}, "outro": "o"},
        "total_duration_sec": 0, "set_durations_sec": {},
    }))
    dest = tmp_path / "station-inbox"
    result = runner.invoke(cli.app, ["deliver", str(show_dir), "--dest", str(dest),
                                     "--config", cfg])
    assert result.exit_code == 0, result.output
    assert (dest / "gratefuldead-1973-06-10" / "manifest.json").exists()
    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    assert entries[0].status == "delivered"
    assert entries[0].performance_id == "GratefulDead/1973-06-10"


def test_deliver_refuses_needs_review_without_force(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    show_dir = tmp_path / "runs" / "r1" / "shows" / "gratefuldead-1973-06-10"
    pkg = show_dir / "package"
    (pkg / "audio").mkdir(parents=True)
    (pkg / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "show": {"artist": "Grateful Dead", "date": "1973-06-10", "venue": "RFK",
                 "city": None, "context": ""},
        "source": {"performance_id": "GratefulDead/1973-06-10"},
        "tracks": [], "set_breaks": [],
        "dj_notes": {"intro": "i", "set_intros": {}, "outro": "o"},
        "total_duration_sec": 0, "set_durations_sec": {},
    }))
    (show_dir / "show.json").write_text(json.dumps({
        "performance_id": "GratefulDead/1973-06-10", "identifier": "gd73",
        "artist": "Grateful Dead", "date": "1973-06-10", "venue": "RFK",
        "needs_review": True, "review_flags": ["duration mismatch on 01.mp3"],
    }))
    dest = tmp_path / "station-inbox"

    result = runner.invoke(cli.app, ["deliver", str(show_dir), "--dest", str(dest), "--config", cfg])
    assert result.exit_code == 1
    assert "needs-review" in result.output
    assert not dest.exists()

    forced = runner.invoke(cli.app, ["deliver", str(show_dir), "--dest", str(dest),
                                     "--force", "--config", cfg])
    assert forced.exit_code == 0, forced.output
    assert (dest / "gratefuldead-1973-06-10" / "manifest.json").exists()


def test_run_unknown_stage_exits_with_message(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))

    result = runner.invoke(cli.app, ["run", str(ws.dir), "--stage", "bogus", "--config", cfg])
    assert result.exit_code == 1
    assert "unknown stage" in result.output


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
                                  "--min-score", "7.5", "--config", cfg])
    assert add.exit_code == 0, add.output
    assert (tmp_path / "profiles" / "sunday-dead.toml").exists()
    from llama.profiles import load_profile
    saved = load_profile(tmp_path, "sunday-dead")
    assert saved.criteria.artist_cap == 0.5
    assert saved.criteria.min_quality_score == 7.5
    listing = runner.invoke(cli.app, ["profile", "list", "--config", cfg])
    assert "sunday-dead" in listing.output


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
                     force=False, script=False, force_stage=None, full_rationale=False):
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
                     force=False, script=False, force_stage=None, full_rationale=False):
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
    from llama.llm.fake import FakeProvider

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[json.dumps({"query": "funk"})])})
    monkeypatch.setattr(cli, "load_or_build", lambda ia, cache: PIN_INDEX)
    result = runner.invoke(cli.app, ["profile", "add", "funky", "funk",
                                     "--artists", "Zebra Ensemble", "--config", cfg])
    assert result.exit_code == 1
    assert "cannot pin artists" in result.output
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
                        lambda ws, ia, criteria, artists=None, force=False: seen.update(artists=artists) or [])
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
