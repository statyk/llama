"""`--profile NAME`: the shared selector, exact-match on `provenance.profile`,
wired into every selector-capable command (`deliver`'s own tests live in
test_deliver_cmd.py) plus `run list`, which filters sessions instead."""
import json
from pathlib import Path

import pytest
import typer.testing as typer_testing
from typer.testing import CliRunner

import llama.cli as cli
from llama.models import Criteria, Provenance
from llama.workspace import RunWorkspace, read_model, write_artifact

from test_cli_commands import _seed_show

runner = CliRunner()


def _cfg(tmp_path: Path) -> str:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return str(tmp_path / "config.toml")


def _seed(tmp_path: Path, slug: str, profile: str | None, **kw):
    """A packaged show stamped with `profile` (None = a one-off query show)."""
    sws = _seed_show(tmp_path, slug, f"{slug.split('-')[0]}/{slug.split('-', 1)[1]}",
                     "r1", **kw)
    prov = read_model(sws.provenance, Provenance)
    write_artifact(sws.provenance, prov.model_copy(update={"profile": profile}))
    return sws


@pytest.fixture
def three_shows(tmp_path: Path):
    """`funky` is the near-miss an accidental substring match would admit."""
    return {
        "funk": _seed(tmp_path, "funk-1973-06-10", "funk"),
        "funky": _seed(tmp_path, "funky-1973-06-11", "funky"),
        "oneoff": _seed(tmp_path, "oneoff-1973-06-12", None),
    }


def test_status_profile_filters_exactly(tmp_path: Path, three_shows):
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "status",
                                "--packaged", "--profile", "funk"])
    assert r.exit_code == 0, r.output
    assert [ln.split()[0] for ln in r.stdout.splitlines()] == ["funk-1973-06-10"]


def test_status_profile_json(tmp_path: Path, three_shows):
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "status",
                                "--profile", "funk", "--json"])
    assert r.exit_code == 0, r.output
    assert [s["slug"] for s in json.loads(r.stdout)["shows"]] == ["funk-1973-06-10"]


def test_status_by_run_rejects_profile(tmp_path: Path):
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "status",
                                "--by-run", "--profile", "funk"])
    assert r.exit_code != 0
    assert "--by-run" in r.output


def test_triage_profile_walks_only_that_profile(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(typer_testing._NamedTextIOWrapper, "isatty", lambda self: True)
    _seed(tmp_path, "funk-1973-06-10", "funk", held=True)
    _seed(tmp_path, "funky-1973-06-11", "funky", held=True)
    _seed(tmp_path, "oneoff-1973-06-12", None, held=True)
    walked = []
    monkeypatch.setattr(cli, "_interactive_resolve",
                        lambda config, ia, ledger, e: walked.append(e.slug))
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "triage",
                                "--held", "--profile", "funk"])
    assert r.exit_code == 0, r.output
    assert walked == ["funk-1973-06-10"]


def test_triage_rejects_name_and_profile_together(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(typer_testing._NamedTextIOWrapper, "isatty", lambda self: True)
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "triage", "someshow",
                                "--profile", "funk"])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_redo_profile_batch(tmp_path: Path, three_shows, monkeypatch):
    redone = []
    monkeypatch.setattr(cli, "_redo_show",
                        lambda config, ia, ledger, e, from_stage, **kw: redone.append(e.slug))
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "redo", "--from", "package",
                                "--profile", "funk", "--yes"])
    assert r.exit_code == 0, r.output
    assert redone == ["funk-1973-06-10"]


def test_redo_rejects_run_and_profile_together(tmp_path: Path):
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "redo", "--from", "package",
                                "--run", "r1", "--profile", "funk"])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_rm_profile_batch_removes_only_that_profile(tmp_path: Path, three_shows):
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "rm", "--profile", "funk", "--yes"])
    assert r.exit_code == 0, r.output
    assert not three_shows["funk"].dir.exists()
    assert three_shows["funky"].dir.exists()
    assert three_shows["oneoff"].dir.exists()


def _session(tmp_path, name, *, query="q", profile=None):
    ws = RunWorkspace(tmp_path, name)
    write_artifact(ws.criteria, Criteria(query=query, profile=profile))
    return ws   # no marker -> incomplete, so it is on the attention list


def test_run_list_profile_filters_sessions(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _session(tmp_path, "2026-10-09-funk", profile="funk")
    _session(tmp_path, "2026-10-09-funky", profile="funky")
    _session(tmp_path, "2026-10-09-query", query="GD 1977")
    r = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--profile", "funk"])
    assert r.exit_code == 0, r.output
    assert "2026-10-09-funk " in r.output
    assert "2026-10-09-funky" not in r.output
    assert "2026-10-09-query" not in r.output

    j = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--profile", "funk", "--json"])
    assert [s["id"] for s in json.loads(j.stdout)] == ["2026-10-09-funk"]


# --- repeatable --profile (ORs, like --state; matches emcee's --profile) ---

def test_status_profile_is_repeatable(tmp_path: Path, three_shows):
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "status",
                                "--profile", "funk", "--profile", "funky"])
    assert r.exit_code == 0, r.output
    assert sorted(ln.split()[0] for ln in r.stdout.splitlines()) == [
        "funk-1973-06-10", "funky-1973-06-11"]


def test_run_list_profile_is_repeatable(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _session(tmp_path, "2026-10-09-funk", profile="funk")
    _session(tmp_path, "2026-10-09-jam", profile="jam")
    _session(tmp_path, "2026-10-09-indie", profile="indie")
    j = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json",
                                "--profile", "funk", "--profile", "jam"])
    assert sorted(s["id"] for s in json.loads(j.stdout)) == ["2026-10-09-funk",
                                                             "2026-10-09-jam"]


# --- unknown-profile note (stderr, never fails, never touches stdout) ---

def _profiles(tmp_path: Path, *names):
    (tmp_path / "profiles").mkdir(exist_ok=True)
    for n in names:
        (tmp_path / "profiles" / f"{n}.toml").write_text("")


def test_unknown_profile_notes_on_stderr_with_the_known_names(tmp_path: Path, three_shows):
    _profiles(tmp_path, "funk", "jam")
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "status", "--profile", "fnuk"])
    assert r.exit_code == 0, r.output
    assert r.stdout == ""
    assert "note: no profile named 'fnuk' (profiles: funk, jam)" in r.stderr


def test_known_profile_prints_no_note(tmp_path: Path, three_shows):
    _profiles(tmp_path, "funk")
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "status", "--profile", "funk"])
    assert r.exit_code == 0, r.output
    assert "note:" not in r.stderr


def test_removed_profile_still_selects_its_shows(tmp_path: Path, three_shows):
    """A note, not an error: a profile removed after it ran still owns shows."""
    _profiles(tmp_path, "jam")
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "status", "--profile", "funk"])
    assert r.exit_code == 0, r.output
    assert [ln.split()[0] for ln in r.stdout.splitlines()] == ["funk-1973-06-10"]
    assert "note: no profile named 'funk'" in r.stderr


@pytest.mark.parametrize("argv", [
    ["deliver", "--profile", "fnuk", "--yes"],
    ["redo", "--from", "package", "--profile", "fnuk", "--yes"],
    ["rm", "--profile", "fnuk", "--yes"],
    ["run", "list", "--profile", "fnuk"],
])
def test_every_profile_option_notes_an_unknown_name(tmp_path: Path, argv):
    _profiles(tmp_path, "funk")
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), *argv])
    assert r.exit_code == 0, r.output
    assert "note: no profile named 'fnuk'" in r.stderr


def test_triage_notes_an_unknown_name(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(typer_testing._NamedTextIOWrapper, "isatty", lambda self: True)
    _profiles(tmp_path, "funk")
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "triage", "--profile", "fnuk"])
    assert r.exit_code == 0, r.output
    assert "note: no profile named 'fnuk'" in r.stderr


# --- run list --json carries the NEXT column ---

def test_run_list_json_carries_next(tmp_path: Path):
    from llama.sessions import mark_awaiting

    cfg = _cfg(tmp_path)
    mark_awaiting(_session(tmp_path, "s-awaiting"))
    _session(tmp_path, "s-incomplete")
    rows = json.loads(runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json"]).output)
    assert {r["id"]: r["next"] for r in rows} == {
        "s-awaiting": "llama run approve s-awaiting",
        "s-incomplete": "llama run resume s-incomplete"}


# --- shell completion of profile names ---

class _Ctx:
    def __init__(self, config):
        self.params = {"config": config}

    def find_root(self):
        return self


def test_profile_completion_lists_matching_profile_names(tmp_path: Path):
    _profiles(tmp_path, "funk", "folk", "jam")
    ctx = _Ctx(Path(_cfg(tmp_path)))
    assert cli._complete_profile(ctx, "f") == ["folk", "funk"]
    assert cli._complete_profile(ctx, "") == ["folk", "funk", "jam"]


def test_profile_completion_never_raises_on_a_broken_config(tmp_path: Path):
    bad = tmp_path / "config.toml"
    bad.write_text("not = [valid toml")
    assert cli._complete_profile(_Ctx(bad), "f") == []
