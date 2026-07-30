import json
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.models import Criteria
from llama.workspace import RunWorkspace, read_model

runner = CliRunner()

CRITERIA = json.dumps({
    "query": "x", "collection": "GratefulDead", "artist": "Grateful Dead",
    "date_from": "1973-01-01", "date_to": "1973-12-31",
    "setlist_constraints": [], "soft_preferences": None,
    "min_avg_rating": 3.5, "min_reviews": 3, "count": 1,
})


# ---------------------------------------------------------------------------
# find / profile run are gone; get is the one acquisition verb.
# ---------------------------------------------------------------------------

def test_find_command_is_gone():
    result = runner.invoke(cli.app, ["find", "GD 1973"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_profile_run_subcommand_is_gone():
    result = runner.invoke(cli.app, ["profile", "run", "classic"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_get_appears_under_acquire_panel():
    out = runner.invoke(cli.app, ["--help"]).output
    assert "Acquire" in out
    assert "get" in out


def test_get_voice_flag_is_gone(tmp_path: Path):
    # Voice moved to emcee entirely -- `get` no longer resolves or stamps it.
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--voice"])
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()
    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--no-voice"])
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


# ---------------------------------------------------------------------------
# Exactly one of QUERY / --profile.
# ---------------------------------------------------------------------------

def test_get_requires_query_or_profile(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["--config", cfg, "get"])
    assert result.exit_code == 1
    assert "give exactly one of QUERY or --profile" in result.output


def test_get_rejects_query_and_profile_together(tmp_path: Path, monkeypatch):
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_profile(tmp_path, Profile(name="classic", criteria=Criteria(query="GD classics")))
    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973", "--profile", "classic"])
    assert result.exit_code == 1
    assert "give exactly one of QUERY or --profile" in result.output


# ---------------------------------------------------------------------------
# Profile mode: tuning flags error rather than silently fighting the
# profile's persisted settings.
# ---------------------------------------------------------------------------

def test_get_profile_mode_rejects_tuning_flags(tmp_path: Path):
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_profile(tmp_path, Profile(name="classic", criteria=Criteria(query="GD classics")))

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic", "--limit", "3"])
    assert result.exit_code == 1
    assert "set these on the profile" in result.output
    assert "--limit" in result.output

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic", "--name", "x"])
    assert result.exit_code == 1
    assert "--name" in result.output

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic", "--no-script"])
    assert result.exit_code == 1
    assert "--script/--no-script" in result.output

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic", "--artist-cap", "0.5"])
    assert result.exit_code == 1
    assert "--artist-cap" in result.output

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic", "--min-score", "7"])
    assert result.exit_code == 1
    assert "--min-score" in result.output

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic", "--year-cap", "0.5"])
    assert result.exit_code == 1
    assert "--year-cap" in result.output


def test_get_profile_mode_reports_every_offending_flag_together(tmp_path: Path):
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_profile(tmp_path, Profile(name="classic", criteria=Criteria(query="GD classics")))
    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic",
                                     "--limit", "3", "--min-score", "7"])
    assert result.exit_code == 1
    assert "--limit" in result.output and "--min-score" in result.output


def test_get_profile_mode_accepts_auto_plan_full_rationale(tmp_path: Path, monkeypatch):
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_profile(tmp_path, Profile(name="classic", criteria=Criteria(query="GD classics")))
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic",
                                     "--auto", "--plan", "--full-rationale"])
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# `get "query"` / `get --profile NAME` pass full_rationale to `_execute`
# (ported from the old find/profile-run tests).
# ---------------------------------------------------------------------------

def test_get_query_and_profile_pass_full_rationale_to_execute(tmp_path: Path, monkeypatch):
    from herder import FakeProvider
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    captured = {}
    monkeypatch.setattr(cli, "_execute",
                        lambda *a, **k: captured.update(full_rationale=k.get("full_rationale")))

    criteria_json = json.dumps({"query": "x", "collection": "GratefulDead", "count": 1})
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD classics", "--full-rationale",
                                     "--name", "fr"])
    assert result.exit_code == 0, result.output
    assert captured["full_rationale"] is True

    save_profile(tmp_path, Profile(name="classic", criteria=Criteria(query="GD classics")))
    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic", "--full-rationale"])
    assert result.exit_code == 0, result.output
    assert captured["full_rationale"] is True


# ---------------------------------------------------------------------------
# --name override + criteria stamping (ported from test_find_stamps_year_cap).
# ---------------------------------------------------------------------------

def test_get_name_override_and_stamps_year_cap_into_run_criteria(tmp_path: Path, monkeypatch):
    from herder import FakeProvider

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({"query": "x", "collection": "GratefulDead"})
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json])})
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD classics", "--year-cap", "0.5",
                                     "--name", "yc"])
    assert result.exit_code == 0, result.output
    saved = read_model(RunWorkspace(tmp_path, "yc").criteria, Criteria)
    assert saved.year_cap == 0.5


def test_get_zero_caps_are_rejected_before_they_poison_criteria(tmp_path: Path, monkeypatch):
    from herder import FakeProvider

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    criteria_json = json.dumps({"query": "x", "collection": "GratefulDead"})
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"interpret": FakeProvider(completes=[criteria_json] * 2)})
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    for flag in ("--year-cap", "--artist-cap"):
        result = runner.invoke(cli.app, ["--config", cfg, "get", "GD", flag, "0.0", "--name", "z"])
        assert result.exit_code == 1, f"get {flag} 0.0 must be rejected"
        assert "must be above 0" in result.output


def test_get_profile_stamps_count_and_script_into_run_criteria(tmp_path: Path, monkeypatch):
    # Replaying a profile's run dir must behave like the profile: count and
    # script live in the run's criteria.json, not only in the profile.
    from llama.profiles import Profile, save_profile

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    save_profile(tmp_path, Profile(name="classic", criteria=Criteria(query="GD classics"),
                                   count=13, script=True))
    captured = {}

    def fake_execute(config, ia, ledger, ws, criteria, count, auto, human_gate,
                     force=False, script=False, force_stage=None,
                     full_rationale=False, plan=False):
        captured.update(count=count, script=script, criteria=criteria)

    monkeypatch.setattr(cli, "_execute", fake_execute)
    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "classic"])
    assert result.exit_code == 0, result.output
    assert captured["count"] == 13 and captured["script"] is True
    saved = read_model(RunWorkspace(tmp_path, f"{date.today().isoformat()}-classic").criteria, Criteria)
    assert saved.count == 13 and saved.script is True


def test_get_profile_pinned_artists_skip_discover_and_prune(tmp_path: Path, monkeypatch):
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
    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "funky"])
    assert result.exit_code == 0, result.output
    assert "pinned artists: Galactic, Lettuce" in result.output
    assert [a["identifier"] for a in seen["artists"]] == ["Galactic", "Lettuce"]
    run_dir = tmp_path / "runs"
    artists_files = list(run_dir.glob("*/artists.json"))
    assert len(artists_files) == 1  # roster recorded in the run dir


# ---------------------------------------------------------------------------
# Fuzzy-query artist-prune flow (ported from find's tests).
# ---------------------------------------------------------------------------

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
    from herder import FakeProvider
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


def test_get_fuzzy_query_interactive_prune(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "folk 60s-70s", "--name", "fz"], input="2\n")
    assert result.exit_code == 0, result.output
    assert "Doc and Merle Watson" in result.output
    assert len(ia.etree_queries) == 1
    assert "collection:DocWatson" in ia.etree_queries[0]
    saved = json.loads((tmp_path / "runs" / "fz" / "artists.json").read_text())
    assert [a["identifier"] for a in saved] == ["DocWatson"]


def test_get_fuzzy_query_auto_uses_all(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "folk 60s-70s", "--auto", "--name", "fz2"])
    assert result.exit_code == 0, result.output
    assert len(ia.etree_queries) == 3


def test_get_fuzzy_query_zero_matches_exits_cleanly(tmp_path, monkeypatch):
    ia = _fuzzy_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: {
        **fuzzy_providers(config),
        "find_artists": __import__("herder.fake", fromlist=["FakeProvider"]).FakeProvider(
            completes=[json.dumps({"matches": [{"identifier": "NickDrake", "reason": "x"}]})]),
    })
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "folk 60s-70s", "--auto", "--name", "fz3"])
    assert result.exit_code == 0, result.output
    assert "no matching artists" in result.output
    assert ia.etree_queries == []


def test_get_fuzzy_query_invalid_prune_aborts(tmp_path, monkeypatch):
    from llama.sessions import STATE_COMPLETE, session_state

    ia = _fuzzy_setup(tmp_path, monkeypatch)
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
        "get", "folk 60s-70s", "--name", "fz4"], input="99\n")
    assert result.exit_code == 0, result.output
    assert "no valid selections" in result.output
    assert ia.etree_queries == []
    saved = json.loads((tmp_path / "runs" / "fz4" / "artists.json").read_text())
    assert len(saved) == 3  # artifact NOT overwritten with the empty prune
    # a deliberately-aborted run is done, not left dangling in the attention-list
    assert session_state(tmp_path / "runs" / "fz4") == STATE_COMPLETE


# ---------------------------------------------------------------------------
# --plan: stop after the shortlist, park awaiting-approval, print the hint --
# no approval prompt, no choose_entries, no process_show.
# ---------------------------------------------------------------------------

def test_get_plan_stops_after_shortlist_and_parks_awaiting_approval(tmp_path: Path, monkeypatch):
    from llama.sessions import STATE_AWAITING, session_state
    from test_pipeline import FakeIA, fake_providers

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)

    def boom(*a, **k):
        raise AssertionError("must not be called under --plan")

    monkeypatch.setattr(cli, "choose_entries", boom)
    monkeypatch.setattr(cli, "process_show", boom)

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973 best soundboard",
                                     "--auto", "--plan", "--name", "planrun"])
    assert result.exit_code == 0, result.output
    assert "GratefulDead" in result.output           # shortlist did print
    assert "shortlist ready — nothing processed." in result.output
    assert "to approve & process:  llama run approve planrun" in result.output
    assert "to discard:            llama run rm planrun" in result.output

    ws = RunWorkspace(tmp_path, "planrun")
    assert session_state(ws.dir) == STATE_AWAITING
    assert not (tmp_path / "shows").exists()          # nothing was processed


def test_get_plan_beats_auto_and_composes_with_it(tmp_path: Path, monkeypatch):
    # --auto --plan: spend on winnow, never prompt, park it -- exercised via
    # --auto above; here confirm --plan alone (auto defaults False) also
    # never prompts (no stdin given -> a real prompt would hang/error).
    from test_pipeline import FakeIA, fake_providers

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    monkeypatch.setattr(cli, "process_show",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not process")))

    result = runner.invoke(cli.app, ["--config", cfg, "get", "GD 1973 best soundboard",
                                     "--plan", "--name", "planrun2"])
    assert result.exit_code == 0, result.output
    assert "shortlist ready — nothing processed." in result.output


def test_get_profile_plan_stops_after_shortlist(tmp_path: Path, monkeypatch):
    from llama.sessions import STATE_AWAITING, session_state
    from llama.profiles import Profile, save_profile
    from test_pipeline import FakeIA, fake_providers

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    save_profile(tmp_path, Profile(
        name="sunday",
        criteria=Criteria(query="x", collection="GratefulDead", artist="Grateful Dead",
                          date_from="1973-01-01", date_to="1973-12-31"),
        count=1,
    ))
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    monkeypatch.setattr(cli, "IAClient", FakeIA)
    monkeypatch.setattr(cli, "process_show",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not process")))

    result = runner.invoke(cli.app, ["--config", cfg, "get", "--profile", "sunday",
                                     "--auto", "--plan"])
    assert result.exit_code == 0, result.output
    assert "shortlist ready — nothing processed." in result.output
    run_dir = next((tmp_path / "runs").glob("*-sunday"))
    assert session_state(run_dir) == STATE_AWAITING
    assert "to approve & process:  llama run approve " in result.output
    assert "to discard:            llama run rm " in result.output
