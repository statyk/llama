"""Tests for `emcee status`: a table (or --json list) of every package in
the station -- slug, state, reasons -- with the same `[station] root`
resolution and the same broad per-package error handling as `run`.

Task 9.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from emcee.cli import app
from emcee.config import EmceeConfig
from emcee.errors import EmceeError

from tests.helpers import build_package, no_moves

runner = CliRunner()


def _write_config(root: Path, station_root: Path | None = None) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = ['[tts]', 'backend = "fake"', 'voice = "test-voice"', '']
    if station_root is not None:
        lines = ['[station]', f'root = "{station_root}"', ''] + lines
    (root / "config.toml").write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# [station] root resolution
# ---------------------------------------------------------------------------


def test_status_missing_station_root_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=None)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_status_nonexistent_station_root_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=tmp_path / "does-not-exist")

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_status_station_root_pointing_at_a_file_raises_emcee_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    a_file = tmp_path / "not-a-directory.txt"
    a_file.write_text("hi")
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=a_file)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1
    assert isinstance(result.exception, EmceeError)
    assert "[station] root" in str(result.exception)


def test_status_station_root_flag_overrides_config(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=None)  # no [station] root in config at all

    result = runner.invoke(app, ["status", "--station-root", str(station)])

    assert result.exit_code == 0, result.output
    assert "no packages" in result.output.lower()


# ---------------------------------------------------------------------------
# All three states, table + --json
# ---------------------------------------------------------------------------


def _setup_three_states(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    build_package(station, slug="ready-show", voiced=True)
    build_package(station, slug="pending-show", voiced=False)
    v2_dir = station / "unsupported-show"
    v2_dir.mkdir(parents=True)
    (v2_dir / "manifest.json").write_text(json.dumps({"schema_version": 2}))
    return station


def test_status_table_renders_all_three_states_with_reasons(tmp_path, monkeypatch):
    _setup_three_states(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status", "--list"])

    assert result.exit_code == 0, result.output
    out = result.output
    assert "ready-show" in out and "ready" in out
    assert "pending-show" in out and "pending" in out
    assert "unsupported-show" in out and "unsupported" in out
    # pending's reasons are surfaced (at least one leg named)
    assert "unvoiced" in out    # the compact form of the three missing legs
    assert "re-deliver from llama" in out


def test_status_json_shape(tmp_path, monkeypatch):
    _setup_three_states(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, list)
    by_slug = {row["slug"]: row for row in payload}
    assert set(by_slug) == {"ready-show", "pending-show", "unsupported-show"}
    assert by_slug["ready-show"]["state"] == "ready"
    assert by_slug["ready-show"]["reasons"] == []
    assert by_slug["pending-show"]["state"] == "pending"
    assert by_slug["pending-show"]["reasons"]
    assert by_slug["unsupported-show"]["state"] == "unsupported"
    assert "re-deliver from llama" in by_slug["unsupported-show"]["reasons"][0]


def test_status_empty_station_reports_no_packages(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "no packages" in result.output.lower()


# ---------------------------------------------------------------------------
# Broad per-package error handling: a malformed-but-valid-JSON manifest must
# render as an error row, not crash the table.
# ---------------------------------------------------------------------------


def test_status_malformed_manifest_renders_as_error_row_and_table_continues(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)

    build_package(station, slug="okshow", voiced=True)

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

    result = runner.invoke(app, ["status", "--list"])

    assert result.exit_code == 0, result.output
    assert result.exception is None
    assert "okshow" in result.output and "ready" in result.output
    assert "badshow" in result.output
    assert "error" in result.output.lower()

    # same, via --json
    result_json = runner.invoke(app, ["status", "--json"])
    assert result_json.exit_code == 0, result_json.output
    payload = json.loads(result_json.output)
    by_slug = {row["slug"]: row for row in payload}
    assert by_slug["badshow"]["state"] == "error"
    assert "filename" in by_slug["badshow"]["reasons"][0]


# ---------------------------------------------------------------------------
# Profile-aware views: summary (default), --list/--profile/--state, --json
# ---------------------------------------------------------------------------


def _write_assign_config(home: Path, station: Path, assign: str) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n[tts]\nbackend = "fake"\nvoice = "v"\n\n{assign}\n')


def _set_voiced_by(pkg_dir: Path, **kw) -> None:
    """Rewrite a voiced fixture's dj_audio block: `presenter=<x>` sets the
    key; `legacy=True` drops it."""
    path = pkg_dir / "manifest.json"
    m = json.loads(path.read_text())
    if kw.get("legacy"):
        m["dj_audio"].pop("presenter", None)
    else:
        m["dj_audio"]["presenter"] = kw["presenter"]
    path.write_text(json.dumps(m))


def _mixed_station(tmp_path, monkeypatch, assign=""):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_assign_config(home, station, assign)
    build_package(station, slug="b1", voiced=True, profile="beta")
    build_package(station, slug="b2", voiced=False, profile="beta")
    build_package(station, slug="a1", voiced=True, profile="alpha")
    build_package(station, slug="n1", voiced=False)
    v2 = station / "u1"
    v2.mkdir(parents=True)
    (v2 / "manifest.json").write_text("{\"schema_version\": 2}")
    return station


def test_status_summary_rows_counts_labels_and_order(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch, '[assign]\ndefault = "dflt"\n\n'
                   '[assign.profiles.beta]\npresenter = "bob"\ntitle = "T"\n')

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    lines = [ln.split() for ln in result.output.splitlines()]
    assert lines[0] == ["profile", "presenter", "ready", "pending", "other",
                        "awaiting", "fix", "voiced", "on"]
    assert lines[1] == ["alpha", "dflt", "(default)", "1", "0", "0", "0", "?", "1"]
    assert lines[2] == ["beta", "bob", "1", "1", "0", "0", "?", "1"]
    assert lines[3] == ["(none)", "dflt", "(default)", "0", "1", "0", "0"]
    assert lines[4] == ["(unknown)", "0", "0", "1", "0"]  # blank presenter
    assert lines[5] == ["total", "2", "2", "1", "0", "?", "2"]
    assert len(lines) == 6
    assert "slug" not in result.output


def test_status_summary_omits_empty_none_and_unknown_rows(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_assign_config(home, station, "")
    build_package(station, slug="a1", voiced=True, profile="alpha")

    out = runner.invoke(app, ["status"]).output

    assert "(none)" not in out and "(unknown)" not in out
    assert "house" in out  # no assignment configured


def test_status_summary_empty_station(tmp_path, monkeypatch):
    home = tmp_path / "home"
    station = tmp_path / "station"
    station.mkdir(parents=True)
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_assign_config(home, station, "")

    assert "no packages found" in runner.invoke(app, ["status"]).output


def test_status_list_flag_and_short_flag_show_per_show_table(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    for flag in ("--list", "-l"):
        out = runner.invoke(app, ["status", flag]).output
        rows = {ln.split()[0]: ln for ln in out.splitlines()[1:]}
        assert set(rows) == {"a1", "b1", "b2", "n1", "u1"}
        assert "alpha" in rows["a1"] and "ready" in rows["a1"]
        assert "(none)" in rows["n1"]
        assert "re-deliver from llama" in rows["u1"]


def test_status_profile_filter_implies_list_and_is_repeatable(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    out = runner.invoke(app, ["status", "--profile", "beta"]).output
    assert {ln.split()[0] for ln in out.splitlines()[1:]} == {"b1", "b2"}

    out = runner.invoke(app, ["status", "--profile", "beta", "--profile", "alpha"]).output
    assert {ln.split()[0] for ln in out.splitlines()[1:]} == {"a1", "b1", "b2"}


def test_status_state_filter_implies_list_and_combines_with_profile(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    out = runner.invoke(app, ["status", "--state", "pending"]).output
    assert {ln.split()[0] for ln in out.splitlines()[1:]} == {"b2", "n1"}

    out = runner.invoke(app, ["status", "--state", "pending", "--profile", "beta"]).output
    assert {ln.split()[0] for ln in out.splitlines()[1:]} == {"b2"}

    out = runner.invoke(app, ["status", "--state", "ready", "--state", "unsupported"]).output
    assert {ln.split()[0] for ln in out.splitlines()[1:]} == {"a1", "b1", "u1"}


def test_status_unknown_state_is_a_usage_error(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status", "--state", "bogus"])

    assert result.exit_code == 2


def test_status_filter_matching_nothing_reports_no_packages(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status", "--profile", "zzz"])

    assert "no packages match" in result.output
    assert "no packages found" not in result.output
    assert "note: no package has profile 'zzz'" in result.output


def test_status_state_filter_matching_nothing_says_no_match_without_note(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status", "--state", "error"])

    assert "no packages match" in result.output
    assert "note:" not in result.output


def test_status_wrong_case_profile_is_noted_alongside_matches(tmp_path, monkeypatch):
    _mixed_station(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status", "--profile", "Beta", "--profile", "beta"])

    assert "note: no package has profile 'Beta'" in result.output
    assert "b1" in result.output


def test_status_json_unreadable_rows_claim_no_assignment(tmp_path, monkeypatch):
    station = _mixed_station(tmp_path, monkeypatch, '[assign]\ndefault = "dflt"\n')
    bad = station / "bad1"
    bad.mkdir()
    (bad / "manifest.json").write_text("{not json")

    by = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).output)}

    for slug in ("u1", "bad1"):
        assert by[slug]["profile"] is None
        assert by[slug]["assigned_presenter"] is None
        assert by[slug]["assignment_source"] is None
    # ready/pending rows with no profile genuinely resolve to the default
    assert by["n1"]["assigned_presenter"] == "dflt"
    assert by["n1"]["assignment_source"] == "default"


def test_scan_broad_skips_dot_prefixed_dir_with_manifest(tmp_path):
    from emcee.cli import _scan_broad

    build_package(tmp_path, slug="real", voiced=False)
    build_package(tmp_path, slug=".real.deliver-abc", voiced=False)
    build_package(tmp_path, slug=".real.old-abc", voiced=True)

    assert [s.path.name for s in _scan_broad(tmp_path, EmceeConfig(), no_moves())] == ["real"]


def test_status_voiced_by_states_and_drift_annotation(tmp_path, monkeypatch):
    station = _mixed_station(tmp_path, monkeypatch,
                             '[assign.profiles.alpha]\npresenter = "BillyG"\n'
                             '[assign.profiles.beta]\npresenter = "bob"\n')
    # b1: voiced by someone else now -> drift; a1: same id, different case -> none
    _set_voiced_by(station / "b1", presenter="carol")
    _set_voiced_by(station / "a1", presenter="billyg")
    build_package(station, slug="legacy", voiced=True, profile="alpha")  # no presenter key
    build_package(station, slug="hse", voiced=True, profile="alpha")
    _set_voiced_by(station / "hse", presenter=None)
    build_package(station, slug="hse2", voiced=True, profile="gamma")  # gamma -> house now
    _set_voiced_by(station / "hse2", presenter=None)
    build_package(station, slug="gone", voiced=True, profile="gamma")
    _set_voiced_by(station / "gone", presenter="dave")

    out = runner.invoke(app, ["status", "--list"]).output
    rows = {ln.split()[0]: ln for ln in out.splitlines()[1:]}

    assert "(now: bob)" in rows["b1"] and "carol" in rows["b1"]
    assert "billyg" in rows["a1"] and "(now:" not in rows["a1"]
    assert "(now:" not in rows["legacy"] and rows["legacy"].split()[3] == "?"
    assert "(now: BillyG)" in rows["hse"] and "house" in rows["hse"]
    assert "house" in rows["hse2"] and "(now:" not in rows["hse2"]
    assert "dave (now: house)" in rows["gone"]
    assert "(now:" not in rows["b2"]  # unvoiced: "-"


def test_status_json_adds_profile_voiced_by_and_assignment(tmp_path, monkeypatch):
    station = _mixed_station(tmp_path, monkeypatch,
                             '[assign]\ndefault = "dflt"\n\n'
                             '[assign.profiles.beta]\npresenter = "bob"\n')
    _set_voiced_by(station / "b1", presenter="bob")

    payload = json.loads(runner.invoke(app, ["status", "--json"]).output)
    by = {r["slug"]: r for r in payload}

    assert by["b1"]["profile"] == "beta" and by["b1"]["voiced_by"] == "bob"
    assert by["b1"]["assigned_presenter"] == "bob"
    assert by["b1"]["assignment_source"] == "profile"
    assert by["b2"]["voiced_by"] is None
    assert by["a1"]["voiced_by"] == "?"  # legacy
    assert by["a1"]["assigned_presenter"] == "dflt"
    assert by["a1"]["assignment_source"] == "default"
    assert by["n1"]["profile"] is None
    assert by["u1"]["state"] == "unsupported"

    # filters apply to --json, which stays per-show
    only = json.loads(runner.invoke(app, ["status", "--json", "--profile", "beta"]).output)
    assert {r["slug"] for r in only} == {"b1", "b2"}


def test_status_json_house_voiced_and_house_assignment(tmp_path, monkeypatch):
    station = _mixed_station(tmp_path, monkeypatch)
    _set_voiced_by(station / "a1", presenter=None)

    by = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).output)}

    assert by["a1"]["voiced_by"] == "house"
    assert by["a1"]["assigned_presenter"] is None
    assert by["a1"]["assignment_source"] == "house"


def test_status_broad_scan_skips_dot_prefixed_dirs(tmp_path, monkeypatch):
    station = _setup_three_states(tmp_path, monkeypatch)
    build_package(station, slug=".ready-show.deliver-abc123", voiced=False)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0, result.output
    assert {r["slug"] for r in json.loads(result.output)} == {
        "ready-show", "pending-show", "unsupported-show"}


# ---------------------------------------------------------------------------
# Recorded TTS, drift against the current resolution, --tts / --drifted
# ---------------------------------------------------------------------------

from unittest.mock import patch  # noqa: E402

import emcee.cli as cli_mod  # noqa: E402
from emcee.presenters import Presenter, save_presenter  # noqa: E402
from emcee.tts.resolve import DEFAULT_MODELS  # noqa: E402

VOX = f"voxtral {DEFAULT_MODELS['voxtral']}"
ELEVEN = f"elevenlabs {DEFAULT_MODELS['elevenlabs']}"


def _set_tts(pkg_dir: Path, tts) -> None:
    """Rewrite a voiced fixture's recorded TTS: a dict, or None to drop it."""
    path = pkg_dir / "manifest.json"
    m = json.loads(path.read_text())
    if tts is None:
        m["dj_audio"].pop("tts", None)
    else:
        m["dj_audio"]["tts"] = tts
    path.write_text(json.dumps(m))


def _tts_station(tmp_path, monkeypatch):
    """House voice = voxtral. alpha -> house; beta -> bob (pinned elevenlabs);
    gamma -> ghost (no presenter file: unresolved now)."""
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    home.mkdir(parents=True)
    (home / "config.toml").write_text(
        f'[station]\nroot = "{station}"\n\n[tts]\nbackend = "voxtral"\nvoice = "v"\n\n'
        '[assign.profiles.beta]\npresenter = "bob"\n'
        '[assign.profiles.gamma]\npresenter = "ghost"\n')
    save_presenter(home, Presenter(id="bob", name="Bob", sex="male", voice="x",
                                   character="c", tts="elevenlabs"))
    return station


def _vox(voice="h1", model=None):
    return {"backend": "voxtral", "model": model or DEFAULT_MODELS["voxtral"], "voice": voice}


def _rows(out: str) -> dict[str, str]:
    return {ln.split()[0]: ln for ln in out.splitlines()[1:] if ln.strip()}


def test_status_list_tts_cell_recorded_unrecorded_unvoiced_drifted_unresolved(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="ok", voiced=True, profile="alpha")
    _set_tts(station / "ok", _vox())
    build_package(station, slug="legacy", voiced=True, profile="alpha")  # no tts key
    build_package(station, slug="bad", voiced=True, profile="alpha")
    _set_tts(station / "bad", {"backend": "", "model": "m"})
    build_package(station, slug="unv", voiced=False, profile="alpha")
    build_package(station, slug="drift", voiced=True, profile="beta")
    _set_tts(station / "drift", _vox())
    build_package(station, slug="unres", voiced=True, profile="gamma")
    _set_tts(station / "unres", _vox())
    build_package(station, slug="mlx", voiced=True, profile="alpha")
    _set_tts(station / "mlx", {"backend": "mlx_audio",
                               "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"})
    build_package(station, slug="nomodel", voiced=True, profile="alpha")
    _set_tts(station / "nomodel", {"backend": "fake", "model": None})

    out = runner.invoke(app, ["status", "--list"]).output
    rows = _rows(out)

    assert "voxtral" in rows["ok"].split() and "(now:" not in rows["ok"]
    assert DEFAULT_MODELS["voxtral"] not in out          # the table names backends only
    assert "?" in rows["legacy"].split() and "(now:" not in rows["legacy"]
    assert "?" in rows["bad"].split()
    assert "(now:" not in rows["unv"] and VOX not in rows["unv"]
    assert "voxtral (now: elevenlabs)" in rows["drift"]
    assert "voxtral (now: unresolved)" in rows["unres"]
    assert "mlx_audio" in rows["mlx"].split() and "Qwen3" not in out
    assert rows["nomodel"].split()[-4:] == ["?", "fake", "(now:", "voxtral)"]
    # the TTS column sits right after the voiced-by column
    assert rows["ok"].index(" ? ") < rows["ok"].index("voxtral")


def test_status_drift_ignores_the_voice_hash(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="v1", voiced=True, profile="alpha")
    _set_tts(station / "v1", _vox(voice="unknown"))
    build_package(station, slug="v2", voiced=True, profile="alpha")
    _set_tts(station / "v2", _vox(voice="some-other-hash"))

    rows = _rows(runner.invoke(app, ["status", "--list"]).output)
    by = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).output)}

    assert "(now:" not in rows["v1"] and "(now:" not in rows["v2"]
    assert by["v1"]["tts_drifted"] is False and by["v2"]["tts_drifted"] is False
    assert runner.invoke(app, ["status", "--drifted"]).output.strip() == "no packages match"


def test_status_no_record_never_drifts(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="legacy", voiced=True, profile="beta")  # beta would drift
    build_package(station, slug="legacy-g", voiced=True, profile="gamma")

    by = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).output)}

    assert by["legacy"]["tts_drifted"] is None and by["legacy-g"]["tts_drifted"] is None
    assert by["legacy"]["tts_now"] == {"backend": "elevenlabs", "model": DEFAULT_MODELS["elevenlabs"]}
    assert "(now:" not in _rows(runner.invoke(app, ["status", "--list"]).output)["legacy-g"]


def test_status_resolves_each_profile_once(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    for slug in ("b1", "b2", "b3"):
        build_package(station, slug=slug, voiced=True, profile="beta")
        _set_tts(station / slug, _vox())
    build_package(station, slug="a1", voiced=True, profile="alpha")
    _set_tts(station / "a1", _vox())

    real = cli_mod.resolve_assignment
    seen: list = []

    def spy(config, profile):
        seen.append(profile)
        return real(config, profile)

    with patch.object(cli_mod, "resolve_assignment", spy):
        result = runner.invoke(app, ["status", "--list"])
        assert result.exit_code == 0, result.output
        assert sorted(seen) == ["alpha", "beta"]
        seen.clear()
        json.loads(runner.invoke(app, ["status", "--json"]).output)
        assert sorted(seen) == ["alpha", "beta"]
        seen.clear()
        summary = runner.invoke(app, ["status"])
        assert summary.exit_code == 0, summary.output
        assert seen == []  # the summary path resolves nothing


def test_status_error_row_has_no_now(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="boom", voiced=True, profile="beta")  # beta would drift
    _set_tts(station / "boom", _vox())
    path = station / "boom" / "manifest.json"
    m = json.loads(path.read_text())
    del m["tracks"][0]["filename"]  # loads as v3, but assess raises
    path.write_text(json.dumps(m))

    by = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).output)}
    assert by["boom"]["state"] == "error"
    assert by["boom"]["tts_now"] is None and by["boom"]["tts_drifted"] is None
    rows = _rows(runner.invoke(app, ["status", "--list"]).output)
    assert "voxtral" in rows["boom"].split() and "(now:" not in rows["boom"]
    assert runner.invoke(app, ["status", "--drifted"]).output.strip() == "no packages match"


def test_status_tts_filter_exact_none_repeatable_and_ands_with_profile(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="vox-a", voiced=True, profile="alpha")
    _set_tts(station / "vox-a", _vox())
    build_package(station, slug="vox-b", voiced=True, profile="beta")
    _set_tts(station / "vox-b", _vox())
    build_package(station, slug="el", voiced=True, profile="beta")
    _set_tts(station / "el", {"backend": "elevenlabs", "model": "m", "voice": "v"})
    build_package(station, slug="legacy", voiced=True, profile="alpha")
    build_package(station, slug="unv", voiced=False, profile="alpha")

    def slugs(*args):
        out = runner.invoke(app, ["status", *args]).output
        return {ln.split()[0] for ln in out.splitlines()[1:] if ln.strip()}

    assert slugs("--tts", "voxtral") == {"vox-a", "vox-b"}
    assert "no packages match" in runner.invoke(app, ["status", "--tts", "vox"]).output  # exact
    assert slugs("--tts", "none") == {"legacy"}  # voiced without a usable record only
    assert slugs("--tts", "voxtral", "--tts", "elevenlabs") == {"vox-a", "vox-b", "el"}
    assert slugs("--tts", "voxtral", "--tts", "none") == {"vox-a", "vox-b", "legacy"}
    assert slugs("--tts", "voxtral", "--profile", "beta") == {"vox-b"}
    only = json.loads(runner.invoke(app, ["status", "--json", "--tts", "elevenlabs"]).output)
    assert [r["slug"] for r in only] == ["el"]


def test_status_tts_unmatched_value_is_noted_but_none_is_not(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="vox-a", voiced=True, profile="alpha")
    _set_tts(station / "vox-a", _vox())

    r = runner.invoke(app, ["status", "--tts", "mlx_audio"])
    assert "note: no package is voiced with tts 'mlx_audio'" in r.output  # CliRunner mixes stderr
    r = runner.invoke(app, ["status", "--tts", "none"])
    assert "note:" not in r.output
    r = runner.invoke(app, ["status", "--tts", "voxtral"])
    assert "note:" not in r.output


def test_status_drifted_filter_and_both_filters_imply_list(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="ok", voiced=True, profile="alpha")
    _set_tts(station / "ok", _vox())
    build_package(station, slug="drift", voiced=True, profile="beta")
    _set_tts(station / "drift", _vox())
    build_package(station, slug="unres", voiced=True, profile="gamma")
    _set_tts(station / "unres", _vox())

    out = runner.invoke(app, ["status", "--drifted"]).output
    assert [ln.split()[0] for ln in out.splitlines()[1:]] == ["drift"]  # list view, not summary
    out = runner.invoke(app, ["status", "--tts", "voxtral"]).output
    assert {ln.split()[0] for ln in out.splitlines()[1:]} == {"ok", "drift", "unres"}
    out = runner.invoke(app, ["status", "--drifted", "--profile", "alpha"]).output
    assert "no packages match" in out
    js = json.loads(runner.invoke(app, ["status", "--json", "--drifted"]).output)
    assert [r["slug"] for r in js] == ["drift"]


def test_status_move_problem_makes_now_unresolved(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="mv", voiced=True, profile="alpha")
    _set_tts(station / "mv", _vox())
    from tests.helpers import write_moves_file
    perf = json.loads((station / "mv" / "manifest.json").read_text())["source"]["performance_id"]
    write_moves_file(tmp_path / "home", {perf: "nosuchprofile"})

    by = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).output)}

    assert by["mv"]["move_problem"] is not None
    assert by["mv"]["tts_now"] == {"unresolved": by["mv"]["move_problem"]}
    assert by["mv"]["tts_drifted"] is None
    assert "(now: unresolved)" in _rows(runner.invoke(app, ["status", "--list"]).output)["mv"]


def test_status_json_tts_now_and_drifted_values_and_existing_keys(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="ok", voiced=True, profile="alpha")
    _set_tts(station / "ok", _vox())
    build_package(station, slug="drift", voiced=True, profile="beta")
    _set_tts(station / "drift", _vox())
    build_package(station, slug="unres", voiced=True, profile="gamma")
    _set_tts(station / "unres", _vox())
    build_package(station, slug="unv", voiced=False, profile="alpha")
    v2 = station / "v2"
    v2.mkdir()
    (v2 / "manifest.json").write_text('{"schema_version": 2}')

    by = {r["slug"]: r for r in json.loads(runner.invoke(app, ["status", "--json"]).output)}

    now_vox = {"backend": "voxtral", "model": DEFAULT_MODELS["voxtral"]}
    assert by["ok"]["tts_now"] == now_vox and by["ok"]["tts_drifted"] is False
    assert by["drift"]["tts_now"] == {"backend": "elevenlabs",
                                      "model": DEFAULT_MODELS["elevenlabs"]}
    assert by["drift"]["tts_drifted"] is True
    assert list(by["unres"]["tts_now"]) == ["unresolved"]
    assert "ghost" in by["unres"]["tts_now"]["unresolved"]
    assert by["unres"]["tts_drifted"] is None
    assert by["unv"]["tts_now"] == now_vox and by["unv"]["tts_drifted"] is None
    assert by["v2"]["tts_now"] is None and by["v2"]["tts_drifted"] is None
    for key in ("slug", "state", "reasons", "profile", "delivered_profile", "profile_source",
                "voiced_by", "assigned_presenter", "assignment_source", "tts", "move_problem"):
        assert key in by["ok"]
    assert by["ok"]["tts"] == _vox()


def test_status_summary_voiced_on_column(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    for i in range(3):
        build_package(station, slug=f"a-vox{i}", voiced=True, profile="alpha")
        _set_tts(station / f"a-vox{i}", _vox())
    for i in range(2):
        build_package(station, slug=f"a-mlx{i}", voiced=True, profile="alpha")
        _set_tts(station / f"a-mlx{i}", {"backend": "mlx_audio", "model": "m"})
    build_package(station, slug="a-old", voiced=True, profile="alpha")  # ?
    build_package(station, slug="a-el", voiced=True, profile="alpha")
    _set_tts(station / "a-el", {"backend": "elevenlabs", "model": "m"})
    build_package(station, slug="a-el2", voiced=True, profile="alpha")
    _set_tts(station / "a-el2", {"backend": "elevenlabs", "model": "m"})
    build_package(station, slug="b-unv", voiced=False, profile="beta")
    build_package(station, slug="c1", voiced=True, profile="gamma")
    _set_tts(station / "c1", _vox())

    out = runner.invoke(app, ["status"]).output
    lines = out.splitlines()

    assert lines[0].split()[-2:] == ["voiced", "on"]
    rows = {ln.split()[0]: ln for ln in lines[1:]}
    # count descending, then name; backend only, no model
    assert rows["alpha"].endswith("voxtral 3, elevenlabs 2, mlx_audio 2, ? 1")
    assert rows["beta"].endswith("0")  # nothing voiced: empty cell (rstrip leaves pending/other)
    assert "voxtral" not in rows["beta"]
    assert rows["gamma"].endswith("voxtral 1")
    assert rows["total"].endswith("voxtral 4, elevenlabs 2, mlx_audio 2, ? 1")


def test_status_help_stays_short_and_has_no_eaten_markup(tmp_path, monkeypatch):
    monkeypatch.setenv("EMCEE_ROOT", str(tmp_path / "home"))
    out = runner.invoke(app, ["status", "--help"]).output
    before_options = out.split("Options")[0]

    assert len([ln for ln in before_options.splitlines() if ln.strip()]) <= 8
    assert "``" not in out
    assert "--tts" in out and "--drifted" in out


# --- awaiting_fix ---------------------------------------------------------


def _marked_station(tmp_path, monkeypatch):
    from tests.helpers import mark_awaiting_fix
    home = tmp_path / "home"
    station = tmp_path / "station"
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    _write_config(home, station_root=station)
    return station, mark_awaiting_fix


def test_marked_voiced_package_json_row_keeps_identity(tmp_path, monkeypatch):
    station, mark = _marked_station(tmp_path, monkeypatch)
    pkg = build_package(station, slug="m", voiced=True, profile="dead")
    from tests.helpers import set_dj_audio
    set_dj_audio(pkg, presenter=None, profile="dead", profile_source="llama",
                 tts={"backend": "fake", "model": None, "voice": "v"})
    mark(pkg)

    row = json.loads(runner.invoke(app, ["status", "--json"]).stdout)[0]

    assert row["state"] == "awaiting-fix"
    assert row["awaiting_fix"].startswith("awaiting fix from llama: ")
    assert row["voiced_by"] is not None
    assert row["tts"] is not None
    assert row["tts_now"] is not None


def test_unmarked_json_row_has_null_awaiting_fix(tmp_path, monkeypatch):
    station, _ = _marked_station(tmp_path, monkeypatch)
    build_package(station, slug="u", voiced=False)
    row = json.loads(runner.invoke(app, ["status", "--json"]).stdout)[0]
    assert row["awaiting_fix"] is None


def test_summary_counts_awaiting_fix_per_profile(tmp_path, monkeypatch):
    station, mark = _marked_station(tmp_path, monkeypatch)
    mark(build_package(station, slug="a1", voiced=True, profile="alpha"))
    build_package(station, slug="a2", voiced=True, profile="alpha")
    mark(build_package(station, slug="b1", voiced=False, profile="beta"))

    lines = [ln.split() for ln in runner.invoke(app, ["status"]).output.splitlines()]

    assert lines[0][:9] == ["profile", "presenter", "ready", "pending", "other",
                            "awaiting", "fix", "voiced", "on"]
    rows = {ln[0]: ln for ln in lines[1:]}
    # ready, pending, other, awaiting fix
    assert rows["alpha"][2:6] == ["1", "0", "0", "1"], rows["alpha"]
    assert rows["beta"][2:6] == ["0", "0", "0", "1"], rows["beta"]
    assert rows["total"][1:5] == ["1", "0", "0", "2"], rows["total"]


def test_status_state_filter_accepts_awaiting_fix(tmp_path, monkeypatch):
    station, mark = _marked_station(tmp_path, monkeypatch)
    mark(build_package(station, slug="m", voiced=True))
    build_package(station, slug="ok", voiced=True)

    result = runner.invoke(app, ["status", "--state", "awaiting-fix"])

    assert result.exit_code == 0, result.output
    assert "m " in result.output and "awaiting-fix" in result.output
    assert "awaiting fix from llama" not in result.output   # detail: --json
    assert "ok " not in result.output


def test_status_list_reasons_are_compact(tmp_path, monkeypatch):
    """The table's reasons column is a short summary; --json keeps the full text."""
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="unv", voiced=False, profile="alpha")
    out = runner.invoke(app, ["status", "--list"]).output
    row = _rows(out)["unv"]
    assert row.endswith("unvoiced") and "dj_notes block" not in row and "broadcast.m3u" not in row
    rows = json.loads(runner.invoke(app, ["status", "--json"]).output)
    full = next(r for r in rows if r["slug"] == "unv")["reasons"]
    assert "no DJ audio (unvoiced)" in full


def test_status_list_tts_same_backend_model_drift_reads_new_model():
    from emcee.cli import _compact_tts_cell
    assert _compact_tts_cell(("voxtral", "a"), ("voxtral", "b"), drifted=True,
                             has_now=True) == "voxtral (now: new model)"


def test_status_list_has_a_header_unless_no_header(tmp_path, monkeypatch):
    station = _tts_station(tmp_path, monkeypatch)
    build_package(station, slug="unv", voiced=False, profile="alpha")
    lines = runner.invoke(app, ["status", "--list"]).output.splitlines()
    assert lines[0].split() == ["show", "profile", "state", "voiced-by", "tts", "reasons"]
    assert lines[1].startswith("unv ")
    assert lines[0].index("profile") == lines[1].index("alpha")      # header aligned
    plain = runner.invoke(app, ["status", "--list", "--no-header"]).output.splitlines()
    assert [l.split() for l in plain] == [l.split() for l in lines[1:]]
