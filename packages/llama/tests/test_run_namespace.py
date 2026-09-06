"""`llama run` -- the session namespace: list/approve/resume/rm. Absorbs the
old top-level `review` (-> `run approve`) and root `run` (-> `run resume`)
commands, which this task deletes outright (Plan B Task 12)."""
import json
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.models import (
    Candidate, Criteria, QualityAssessment, RecordingSummary, ShortlistEntry,
)
from llama.sessions import (STATE_AWAITING, STATE_COMPLETE, STATE_INCOMPLETE,
                            STATE_PAUSED, mark_awaiting, mark_complete,
                            mark_incomplete, mark_paused)
from llama.workspace import RunWorkspace, read_model_list, write_artifact

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


def _session(tmp_path, name, *, state=None, query="q", profile=None):
    ws = RunWorkspace(tmp_path, name)
    write_artifact(ws.criteria, Criteria(query=query, profile=profile))
    if state == STATE_AWAITING:
        mark_awaiting(ws)
    elif state == STATE_COMPLETE:
        mark_complete(ws, "done")
    return ws


# ---------------------------------------------------------------------------
# run list
# ---------------------------------------------------------------------------

def test_run_list_empty_says_no_sessions(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "no sessions need attention"


def test_run_list_header_is_verbatim(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _session(tmp_path, "s1")
    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "SESSION                              STATE               AGE   CRITERIA"


def test_run_list_shows_awaiting_and_incomplete_hides_complete(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _session(tmp_path, "s-awaiting", state=STATE_AWAITING, query="a query")
    _session(tmp_path, "s-incomplete", query="an incomplete query")   # no marker
    _session(tmp_path, "s-complete", state=STATE_COMPLETE, query="done query")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert result.exit_code == 0, result.output
    assert "s-awaiting" in result.output
    assert "s-incomplete" in result.output
    assert "s-complete" not in result.output
    assert "awaiting approval" in result.output
    assert "incomplete" in result.output
    assert '"a query"' in result.output
    assert '"an incomplete query"' in result.output


def test_run_list_criteria_shows_profile_when_set(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _session(tmp_path, "s-profile", query="ignored", profile="sunday-dead-hour")
    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert result.exit_code == 0, result.output
    assert "profile: sunday-dead-hour" in result.output
    assert "ignored" not in result.output


def test_run_list_query_is_truncated_to_40_chars(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    long_query = "x" * 80
    _session(tmp_path, "s-long", query=long_query)
    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert result.exit_code == 0, result.output
    assert f'"{"x" * 40}"' in result.output
    assert "x" * 41 not in result.output


def test_run_list_json_emits_session_info_dicts(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _session(tmp_path, "s1", query="q")
    result = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "s1"
    assert data[0]["state"] == "incomplete"
    assert data[0]["query"] == "q"
    assert data[0]["profile"] is None
    assert "updated_at" in data[0]


def test_run_list_shows_paused_label_and_resume_suffix(tmp_path: Path):
    # Task 6's cli.py rendering (STATE_PAUSED label + "resumes <iso>" suffix)
    # had zero coverage before this: reverting cli.py to its pre-Task-6
    # state left the suite green. Pin both the label and the suffix, and
    # confirm the suffix is paused-only (not printed for an incomplete run).
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    # Deliberately NOT named "*paused*" -- the id itself must not satisfy a
    # substring check on the word "paused", or the assertion below would
    # pass no matter what the label column actually says.
    ws = RunWorkspace(tmp_path, "s-onhold")
    write_artifact(ws.criteria, Criteria(query="q"))
    mark_paused(ws, None, [], "2026-09-04T15:10:00+00:00", "five_hour", "session limit")
    _session(tmp_path, "s-incomplete", query="an incomplete query")   # no marker

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert result.exit_code == 0, result.output
    lines_by_id = {ln.split()[0]: ln for ln in result.output.splitlines() if ln.strip()}

    paused_line = lines_by_id["s-onhold"]
    assert paused_line.split()[1] == "paused"   # the label column, exactly
    assert "resumes 2026-09-04T15:10:00+00:00" in paused_line

    incomplete_line = lines_by_id["s-incomplete"]
    assert "resumes" not in incomplete_line


def test_run_list_resume_suffix_requires_paused_state(tmp_path: Path):
    # The public mark_* API can never produce state=incomplete with
    # resume_after set (mark_incomplete always writes it None), so this
    # marker is written directly to exercise the `s.state == STATE_PAUSED`
    # guard itself, not just "this session happens to have no resume_after".
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "s-incomplete-carries-resume-after")
    write_artifact(ws.criteria, Criteria(query="q"))
    write_artifact(ws.session, json.dumps({
        "state": STATE_INCOMPLETE, "updated_at": "2026-09-04T00:00:00+00:00",
        "outcome": None, "failures": [],
        "resume_after": "2026-09-04T15:10:00+00:00",
        "pause_scope": None, "pause_reason": None,
    }))

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])
    assert result.exit_code == 0, result.output
    line = next(ln for ln in result.output.splitlines()
                if ln.startswith("s-incomplete-carries-resume-after"))
    assert "resumes" not in line


def test_attention_dicts_carry_a_paused_entry():
    # `.get(state, state)` / `.get(state, "llama run resume {id}")` both
    # happen to fall back to the exact text STATE_PAUSED's entry holds, so a
    # CLI-output assertion cannot distinguish "entry present" from "entry
    # deleted, default coincides". Index the dicts directly instead.
    assert cli._ATTENTION_LABELS[STATE_PAUSED] == "paused"
    assert cli._ATTENTION_HINTS[STATE_PAUSED] == "llama run resume {id}"


# ---------------------------------------------------------------------------
# run approve (today's `review`)
# ---------------------------------------------------------------------------

def test_run_approve_approves_selected_ranks(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
                                     "run", "approve", str(ws.dir)], input="1\nn\n")
    assert result.exit_code == 0, result.output
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert entries[0].approved is True
    assert entries[1].approved is None       # unnamed ranks are left undecided
    assert "next: llama run resume r1" in result.output


def test_run_approve_shortlist_shows_artist(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    entries = make_entries()
    entries[1].candidate.collection = "mekons"  # multi-artist profile
    write_artifact(ws.shortlist, entries)
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
                                     "run", "approve", str(ws.dir)], input="\n")
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert any("GratefulDead" in ln and "1973-06-10" in ln for ln in lines)
    assert any("mekons" in ln and "1973-06-11" in ln for ln in lines)


LONG_RATIONALE = " ".join(f"w{i:03d}" for i in range(120))  # ~600 chars, unique tokens


def _long_rationale_entries():
    entries = make_entries()
    entries[0].assessment.rationale = LONG_RATIONALE
    return entries


def test_run_approve_full_rationale_flag(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.shortlist, _long_rationale_entries())
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
                                     "run", "approve", str(ws.dir), "--full-rationale"],
                           input="\n")
    assert result.exit_code == 0, result.output
    assert "w119" in result.output


def test_run_approve_empty_input_changes_nothing(tmp_path: Path):
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
                                     "run", "approve", str(ws.dir)], input="\n")
    assert result.exit_code == 0, result.output
    assert "unchanged" in result.output
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert all(e.approved is None for e in entries)


def test_run_approve_can_continue_straight_into_processing(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: calls.append((a, k)))
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["--config", str(tmp_path / "config.toml"),
                                     "run", "approve", str(ws.dir)], input="1\ny\n")
    assert result.exit_code == 0, result.output
    assert len(calls) == 1


def test_run_approve_resolves_run_by_substring(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "2026-07-16-countryish")
    write_artifact(ws.criteria, Criteria(query="q"))
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["--config", cfg, "run", "approve", "countryish"],
                           input="1\nn\n")
    assert result.exit_code == 0, result.output
    entries = read_model_list(ws.shortlist, ShortlistEntry)
    assert entries[0].approved is True


def test_run_approve_no_script_voice_overrides(tmp_path: Path):
    """The old `review --script/--no-script`/`--voice/--no-voice` overrides
    are dropped entirely -- there is nothing left to set them with."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.shortlist, make_entries())
    result = runner.invoke(cli.app, ["--config", cfg, "run", "approve", str(ws.dir),
                                     "--no-script"], input="\n")
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()
    result = runner.invoke(cli.app, ["--config", cfg, "run", "approve", str(ws.dir),
                                     "--voice"], input="\n")
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


# ---------------------------------------------------------------------------
# run resume (today's root `run`)
# ---------------------------------------------------------------------------

def test_run_resume_passes_full_rationale_to_execute(tmp_path: Path, monkeypatch):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    captured = {}
    monkeypatch.setattr(cli, "_execute",
                        lambda *a, **k: captured.update(full_rationale=k.get("full_rationale")))
    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", str(ws.dir),
                                     "--full-rationale"])
    assert result.exit_code == 0, result.output
    assert captured["full_rationale"] is True


def test_run_resume_inherits_count_from_criteria(tmp_path: Path, monkeypatch):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q", count=13))
    captured = {}

    def fake_execute(config, ia, ledger, ws, criteria, count, auto, human_gate,
                     force=False, force_stage=None,
                     full_rationale=False, plan=False, pace=None):
        captured.update(count=count)

    monkeypatch.setattr(cli, "_execute", fake_execute)
    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", str(ws.dir)])
    assert result.exit_code == 0, result.output
    assert captured == {"count": 13}


def test_run_resume_rejects_stage_and_force(tmp_path: Path, monkeypatch):
    # Belt-and-suspenders mocking: on unmodified code these options would
    # still parse and fall through to a real _execute() (real network) --
    # keep this offline regardless of which side of the change it runs on.
    monkeypatch.setattr(cli, "_execute", lambda *a, **k: None)
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))

    r1 = runner.invoke(cli.app, ["--config", cfg, "run", "resume", str(ws.dir),
                                 "--stage", "search"])
    assert r1.exit_code != 0
    assert "no such option" in r1.output.lower()

    r2 = runner.invoke(cli.app, ["--config", cfg, "run", "resume", str(ws.dir), "--force"])
    assert r2.exit_code != 0
    assert "no such option" in r2.output.lower()

    r3 = runner.invoke(cli.app, ["--config", cfg, "run", "resume", str(ws.dir), "--no-script"])
    assert r3.exit_code != 0
    assert "no such option" in r3.output.lower()

    r4 = runner.invoke(cli.app, ["--config", cfg, "run", "resume", str(ws.dir), "--voice"])
    assert r4.exit_code != 0
    assert "no such option" in r4.output.lower()


def test_run_resume_unknown_name_fails_loud(tmp_path: Path):
    from llama.catalog import CatalogError

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["--config", cfg, "run", "resume", "nope"])
    # _resolve_run no longer catches CatalogError; only main_cli() (not this direct
    # cli.app invocation) renders it as clean stderr text, so assert on the
    # propagated exception instead.
    assert result.exit_code == 1
    assert isinstance(result.exception, CatalogError)
    assert "no run matches" in str(result.exception)


# `run resume` no longer resolves voice/presenter/script from the persisted
# criteria -- scripting and voice/presenter assignment are both entirely
# emcee's job now (station-side [assign] profile -> presenter/title). The old
# presenter-resolution/voice-note/script-inheritance tests (moved-to-emcee
# behavior) are gone; test_run_resume_inherits_count_from_criteria above
# still covers the one field (count) that survives.


# ---------------------------------------------------------------------------
# run rm
# ---------------------------------------------------------------------------

def test_run_rm_confirms_then_deletes(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = _session(tmp_path, "r1", state=STATE_AWAITING)
    result = runner.invoke(cli.app, ["--config", cfg, "run", "rm", "r1"], input="y\n")
    assert result.exit_code == 0, result.output
    assert "r1" in result.output and "awaiting" in result.output
    assert "removed session r1" in result.output
    assert not ws.dir.exists()


def test_run_rm_declining_leaves_session(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = _session(tmp_path, "r1")
    result = runner.invoke(cli.app, ["--config", cfg, "run", "rm", "r1"], input="n\n")
    assert result.exit_code == 0, result.output
    assert ws.dir.exists()


def test_run_rm_yes_skips_confirmation(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = _session(tmp_path, "r1")
    result = runner.invoke(cli.app, ["--config", cfg, "run", "rm", "r1", "--yes"])
    assert result.exit_code == 0, result.output
    assert "removed session r1" in result.output
    assert not ws.dir.exists()


def test_run_rm_leaves_shows_untouched(tmp_path: Path):
    from llama.models import Provenance, Show
    from llama.workspace import ShowWorkspace

    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = _session(tmp_path, "r1")
    sws = ShowWorkspace(tmp_path / "shows" / "gd-1973-06-10")
    write_artifact(sws.show, Show(performance_id="GratefulDead/1973-06-10",
                                  identifier="x", artist="Grateful Dead", date="1973-06-10"))
    write_artifact(sws.provenance, Provenance(
        performance_id="GratefulDead/1973-06-10", run="r1", dossier="d",
        candidate=Candidate(performance_id="GratefulDead/1973-06-10",
                            collection="GratefulDead", date="1973-06-10",
                            recordings=[RecordingSummary(identifier="x")]),
        processed_at="2026-07-17T00:00:00+00:00"))

    result = runner.invoke(cli.app, ["--config", cfg, "run", "rm", "r1", "--yes"])
    assert result.exit_code == 0, result.output
    assert not ws.dir.exists()
    assert sws.dir.exists()          # the show is untouched -- lives in shows/


def test_run_rm_resolves_by_substring(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = _session(tmp_path, "2026-07-16-countryish")
    result = runner.invoke(cli.app, ["--config", cfg, "run", "rm", "countryish", "--yes"])
    assert result.exit_code == 0, result.output
    assert not ws.dir.exists()


# ---------------------------------------------------------------------------
# `review` and the bare positional `run <x>` are gone; --run-name too.
# ---------------------------------------------------------------------------

def test_review_command_is_gone(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["--config", cfg, "review", "r1"])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_bare_run_positional_form_is_gone(tmp_path: Path):
    """`run` is now a sub-app group; the old `llama run <session>` positional
    form must fail (no `list`/`approve`/`resume`/`rm` subcommand named after
    a session id)."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "r1")
    write_artifact(ws.criteria, Criteria(query="q"))
    result = runner.invoke(cli.app, ["--config", cfg, "run", str(ws.dir)])
    assert result.exit_code != 0
    assert "No such command" in result.output


def test_run_name_flag_is_gone(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    result = runner.invoke(cli.app, ["--config", cfg, "get", "q", "--run-name", "x"])
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


def test_run_help_text_is_verbatim(tmp_path: Path):
    result = runner.invoke(cli.app, ["run", "--help"])
    assert result.exit_code == 0, result.output
    assert ("Acquisition sessions — approve, resume, list, or discard."
            in result.output.replace("\n", " "))


# ---------------------------------------------------------------------------
# run list: what a run lost
# ---------------------------------------------------------------------------
# The outcome string has been recorded on every session since the marker
# existed and was displayed nowhere; a run that lost shows now reports both
# it and the per-show reasons, which used to survive only in the terminal.


def _lost(tmp_path, name, failures, outcome="1 packaged, 1 failed", query="q"):
    ws = RunWorkspace(tmp_path, name)
    write_artifact(ws.criteria, Criteria(query=query, profile=None))
    mark_incomplete(ws, outcome, failures)
    return ws


def test_run_list_shows_the_outcome_of_a_run_that_lost_shows(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _lost(tmp_path, "s-lost", [{"show": "GratefulDead/1968-02-14",
                                "error": "usage limit reached"}])

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])

    assert result.exit_code == 0, result.output
    assert "1 packaged, 1 failed" in result.output


def test_run_list_names_each_lost_show_and_its_reason(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _lost(tmp_path, "s-lost", [
        {"show": "GratefulDead/1968-02-14", "error": "usage limit reached"},
        {"show": "GratefulDead/1973-02-09", "error": "connection reset"},
    ])

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])

    assert "      - GratefulDead/1968-02-14: usage limit reached" in result.output
    assert "      - GratefulDead/1973-02-09: connection reset" in result.output


def test_run_list_json_carries_outcome_and_failures(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    failures = [{"show": "GratefulDead/1968-02-14", "error": "usage limit reached"}]
    _lost(tmp_path, "s-lost", failures)

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json"])

    payload = json.loads(result.output)
    assert payload[0]["outcome"] == "1 packaged, 1 failed"
    assert payload[0]["failures"] == failures


def test_run_list_json_carries_the_resume_time_of_a_paused_run(tmp_path: Path):
    """The JSON view is the table's machine-readable equivalent, and the
    table prints `resumes <instant>`. Without these keys a consumer reading
    state="paused" has nothing to answer "when may this be retried?" with."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    ws = RunWorkspace(tmp_path, "s-onhold")
    write_artifact(ws.criteria, Criteria(query="q"))
    mark_paused(ws, "2 packaged", [], "2026-09-04T15:10:00+00:00", "five_hour",
                "You've hit your session limit")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json"])

    payload = json.loads(result.output)
    assert payload[0]["resume_after"] == "2026-09-04T15:10:00+00:00"
    assert payload[0]["pause_reason"] == "You've hit your session limit"


def test_run_list_json_keys_are_present_and_null_off_a_pause(tmp_path: Path):
    """Always-present keys, like `outcome`: an unpaused row keeps its shape
    rather than gaining and losing fields."""
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _session(tmp_path, "s1", query="q")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list", "--json"])

    row = json.loads(result.output)[0]
    assert row["resume_after"] is None
    assert row["pause_reason"] is None


def test_run_list_adds_no_failure_lines_for_a_session_that_lost_nothing(tmp_path: Path):
    cfg = str(tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    _session(tmp_path, "s-awaiting", state=STATE_AWAITING, query="a query")

    result = runner.invoke(cli.app, ["--config", cfg, "run", "list"])

    assert "      - " not in result.output
