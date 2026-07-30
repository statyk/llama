import json
import tomllib
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


def test_profile_add_zero_caps_are_rejected_before_they_poison_criteria(tmp_path: Path, monkeypatch):
    from herder import FakeProvider

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({"query": "x", "collection": "GratefulDead"})
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json] * 2)})
    for flag in ("--year-cap", "--artist-cap"):
        result = runner.invoke(cli.app, ["--config", cfg, "profile", "add", "z", "GD", flag, "0.0"])
        assert result.exit_code == 1, f"profile add {flag} 0.0 must be rejected"
        assert "must be above 0" in result.output


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
    result = runner.invoke(cli.app, ["--config", cfg, "show", str(sws.dir)])
    assert result.exit_code == 0, result.output
    assert "needs-review: yes" in result.output
    assert "single-set structure for a long show" in result.output


def _approved_run(tmp_path: Path) -> tuple[str, RunWorkspace]:
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    entries = make_entries()
    entries[0].approved = True
    write_artifact(ws.shortlist, entries)
    return cfg, ws


def test_drop_stage_artifacts_cascades_for_one_show(tmp_path: Path):
    from llama.workspace import drop_stage_artifacts

    sws = ShowWorkspace(tmp_path / "s")
    for path in [sws.selection, sws.show, sws.reviews, sws.vetting]:
        write_artifact(path, "{}")
    write_artifact(sws.research, "research")
    write_artifact(sws.package_dir / "manifest.json", "{}")

    drop_stage_artifacts(sws, "gather")
    assert sws.selection.exists()            # upstream stage untouched
    for path in [sws.show, sws.reviews, sws.research, sws.vetting,
                 sws.package_dir / "manifest.json"]:
        assert not path.exists(), path


def test_profile_add_and_list(tmp_path: Path, monkeypatch):
    from herder import FakeProvider
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({
        "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
        "date_from": None, "date_to": None, "setlist_constraints": [],
        "soft_preferences": None, "min_avg_rating": 4.0, "min_reviews": 3, "count": 1,
    })
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    add = runner.invoke(cli.app, ["--config", cfg, "profile", "add", "sunday-dead", "GD classics",
                                  "--count", "2", "--human-gate", "--artist-cap", "0.5",
                                  "--year-cap", "0.25",
                                  "--min-score", "7.5"])
    assert add.exit_code == 0, add.output
    assert (tmp_path / "profiles" / "sunday-dead.toml").exists()
    from llama.profiles import load_profile
    saved = load_profile(tmp_path, "sunday-dead")
    assert saved.criteria.artist_cap == 0.5
    assert saved.criteria.min_quality_score == 7.5
    assert saved.criteria.year_cap == 0.25
    listing = runner.invoke(cli.app, ["--config", cfg, "profile", "list"])
    assert "sunday-dead" in listing.output
    runs = tmp_path / "runs"
    assert not runs.exists() or not any(runs.iterdir())


def test_profile_artists_set_show_and_clear(tmp_path, monkeypatch):
    from herder import FakeProvider
    from llama.profiles import load_profile
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({
        "query": "q", "collection": "GratefulDead", "artist": "Grateful Dead",
        "date_from": None, "date_to": None, "setlist_constraints": [],
        "soft_preferences": None, "min_avg_rating": 4.0, "min_reviews": 3, "count": 1,
    })
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    assert runner.invoke(cli.app, ["--config", cfg, "profile", "add", "myprof", "q"]).exit_code == 0

    # offline artist resolution: echo names as identifiers
    monkeypatch.setattr(cli, "load_or_build", lambda ia, cache: [])
    monkeypatch.setattr(cli, "resolve_artists",
                        lambda index, names: [{"identifier": n, "title": n} for n in names])

    r = runner.invoke(cli.app, ["--config", cfg, "profile", "artists", "myprof",
                                "--set", "Galactic, Lettuce"])
    assert r.exit_code == 0, r.output
    assert load_profile(tmp_path, "myprof").criteria.artists == ["Galactic", "Lettuce"]

    shown = runner.invoke(cli.app, ["--config", cfg, "profile", "artists", "myprof"])
    assert "Galactic" in shown.output

    runner.invoke(cli.app, ["--config", cfg, "profile", "artists", "myprof", "--set", ""])
    assert load_profile(tmp_path, "myprof").criteria.artists == []



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
    from herder import FakeProvider
    from llama.profiles import load_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({"query": "funk"})
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    monkeypatch.setattr(cli, "load_or_build", lambda ia, cache: PIN_INDEX)
    result = runner.invoke(cli.app, ["--config", cfg, "profile", "add", "funky", "funk",
                                     "--artists", "galactic, lettuce"])
    assert result.exit_code == 0, result.output
    assert "pinned: Galactic (Galactic), Lettuce (Lettuce)" in result.output
    assert load_profile(tmp_path, "funky").criteria.artists == ["Galactic", "Lettuce"]


def test_profile_add_rejects_unknown_pinned_artist(tmp_path: Path, monkeypatch):
    from llama.errors import ArtistResolutionError
    from herder import FakeProvider

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[json.dumps({"query": "funk"})])})
    monkeypatch.setattr(cli, "load_or_build", lambda ia, cache: PIN_INDEX)
    result = runner.invoke(cli.app, ["--config", cfg, "profile", "add", "funky", "funk",
                                     "--artists", "Zebra Ensemble"])
    # resolve_artists now raises ArtistResolutionError, an uncaught LlamaError that
    # only main_cli() (not this direct cli.app invocation) renders as clean stderr text.
    assert result.exit_code == 1
    assert isinstance(result.exception, ArtistResolutionError)
    assert "cannot pin artist" in str(result.exception)
    assert not (tmp_path / "profiles" / "funky.toml").exists()


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


def test_show_resolves_by_name_and_lists_stages(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "mekons-1989-12-02", "mekons/1989-12-02", "r1", held=True)
    result = runner.invoke(cli.app, ["--config", cfg, "show", "mek"])
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
    r = runner.invoke(cli.app, ["--config", cfg, "show", "gratefuldead", "--tracks"])
    assert r.exit_code == 0, r.output
    assert "tracks:" in r.output
    assert "1." in r.output and "Morning Dew" in r.output and "a.mp3" in r.output


def test_show_ambiguous_name_fails_loud(tmp_path: Path):
    from llama.catalog import CatalogError

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _seed_show(tmp_path, "aaa-1970-01-01", "aaa/1970-01-01", "r1")
    _seed_show(tmp_path, "aab-1970-01-01", "aab/1970-01-01", "r1")
    result = runner.invoke(cli.app, ["--config", cfg, "show", "aa"])
    # _resolve_show no longer catches CatalogError; only main_cli() (not this direct
    # cli.app invocation) renders the candidate list as indented stderr lines, so
    # assert on the propagated exception's matches instead.
    assert result.exit_code == 1
    assert isinstance(result.exception, CatalogError)
    assert "aaa-1970-01-01" in result.exception.matches
    assert "aab-1970-01-01" in result.exception.matches


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
    result = runner.invoke(cli.app, ["--config", cfg, "show", str(sws.dir)])
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
    result = runner.invoke(cli.app, ["--config", cfg, "show", str(sws.dir)])
    assert result.exit_code == 0, result.output
    assert "(venue from jerrybase)" in result.output


# --- Plan B Task 13: profile show/remove + enriched list ---

def test_profile_show_prints_all_fields_including_roster(tmp_path: Path):
    from llama.profiles import Profile, save_profile
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    crit = Criteria(query="sunday dead hour", collection="GratefulDead", artist="Grateful Dead",
                    date_from="1972-01-01", date_to="1974-12-31",
                    artist_cap=0.5, year_cap=0.25, min_quality_score=7.0,
                    artists=["Galactic", "Lettuce"])
    save_profile(tmp_path, Profile(name="sunday-dead", criteria=crit, count=3,
                                   human_gate=True))
    result = runner.invoke(cli.app, ["--config", cfg, "profile", "show", "sunday-dead"])
    assert result.exit_code == 0, result.output
    out = result.output
    assert "sunday-dead  count=3  human_gate=True" in out
    assert "query: sunday dead hour" in out
    assert "pinned roster: Galactic, Lettuce" in out
    assert "collection/artist: GratefulDead / Grateful Dead" in out
    assert "date range: 1972-01-01 .. 1974-12-31" in out
    assert "artist_cap/year_cap/min_quality_score: 0.5 / 0.25 / 7.0" in out


def test_profile_show_no_pinned_roster_and_unknown_name_errors(tmp_path: Path):
    from llama.profiles import Profile, ProfileError, save_profile
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_profile(tmp_path, Profile(name="plain", criteria=Criteria(query="q")))
    result = runner.invoke(cli.app, ["--config", cfg, "profile", "show", "plain"])
    assert result.exit_code == 0, result.output
    assert "no pinned roster" in result.output

    missing = runner.invoke(cli.app, ["--config", cfg, "profile", "show", "ghost"])
    assert missing.exit_code == 1
    assert isinstance(missing.exception, ProfileError)
    assert "ghost" in str(missing.exception)


def test_profile_remove_confirms_deletes_and_errors_on_unknown(tmp_path: Path):
    from llama.profiles import Profile, ProfileError, save_profile
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    path = save_profile(tmp_path, Profile(name="temp", criteria=Criteria(query="q")))

    declined = runner.invoke(cli.app, ["--config", cfg, "profile", "remove", "temp"], input="n\n")
    assert declined.exit_code == 0, declined.output
    assert path.exists()

    confirmed = runner.invoke(cli.app, ["--config", cfg, "profile", "remove", "temp"], input="y\n")
    assert confirmed.exit_code == 0, confirmed.output
    assert not path.exists()
    assert f"removed: {path}" in confirmed.output

    missing = runner.invoke(cli.app, ["--config", cfg, "profile", "remove", "ghost"])
    assert missing.exit_code == 1
    assert isinstance(missing.exception, ProfileError)


def test_profile_remove_yes_skips_confirm(tmp_path: Path):
    from llama.profiles import Profile, save_profile
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    path = save_profile(tmp_path, Profile(name="temp2", criteria=Criteria(query="q")))
    result = runner.invoke(cli.app, ["--config", cfg, "profile", "remove", "temp2", "--yes"])
    assert result.exit_code == 0, result.output
    assert not path.exists()


def test_profile_list_shows_query_and_count_columns(tmp_path: Path):
    from llama.profiles import Profile, save_profile
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_profile(tmp_path, Profile(name="sunday-dead", criteria=Criteria(query="sunday dead hour"),
                                   count=3))
    save_profile(tmp_path, Profile(name="plain", criteria=Criteria(query="q")))
    result = runner.invoke(cli.app, ["--config", cfg, "profile", "list"])
    assert result.exit_code == 0, result.output
    name, count, query = "sunday-dead", 3, "sunday dead hour"
    assert f"{name:<20} {count:>3} {query:40.40s}" in result.output
    name2, count2, query2 = "plain", 1, "q"
    assert f"{name2:<20} {count2:>3} {query2:40.40s}" in result.output


# --- cosmetic-followups: clean errors for bad operator input + comma-form ---

def test_resolve_exclude_tokens_comma_form(tmp_path):
    sws = ShowWorkspace(tmp_path / "s")
    write_artifact(sws.show, Show(
        performance_id="X/1970-01-01", identifier="x", artist="X", date="1970-01-01",
        tracks=[Track(index=1, set="1", title="A", filename="a.mp3", title_source="tags"),
                Track(index=2, set="1", title="B", filename="b.mp3", title_source="tags")]))
    assert cli._resolve_exclude_tokens(sws, ["1,2"]) == ["a.mp3", "b.mp3"]
    # filename passthrough needs no show.json read
    assert cli._resolve_exclude_tokens(ShowWorkspace(tmp_path / "none"), ["z.mp3"]) == ["z.mp3"]
