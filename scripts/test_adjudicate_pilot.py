"""scripts/adjudicate_pilot.py: select / run / compare (plan Task 11), offline.

A tmp library from `fixture_library.build_library` plus fake prototype-verdict files.
`scripts/` tests do not get the llama conftest, so every `run` injects its meter reader
and its process lister, and the live-meter test patches `herder.usage.read_usage` to
raise."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "llama" / "tests"))

import adjudicate_pilot as pilot
from fixture_library import FIXTURES, build_library, library_show
from herder import FakeProvider
from llama.adjudicator import runner
from llama.config import load_config
from llama.ledger import Ledger
from llama.models import Show, Track
from llama.workspace import read_model, write_artifact

HELD = "gratefuldead-1973-06-10"
HELD2 = "gratefuldead-1973-06-12"
NO_PROCS = ["1 0 /sbin/launchd"]


def verdict(**kw):
    """A venue-edit verdict the gate passes at the medium bar (quote from the description)."""
    v = {"flags": [{"flag": "unresolved track titles", "verdict": "real-fixed-by-action",
                    "confidence": "high", "why": "w"}],
         "edits": [{"op": "venue", "venue": "RFK Stadium, Washington", "confidence": "high",
                    "why": "w", "evidence": [{"kind": "taper-description",
                                              "quote": "Morning Dew"}]}],
         "kind": "fix", "show_correct_after": "yes", "rationale": "r"}
    v.update(kw)
    return json.dumps(v)


class Meter:
    """Five-hour reading = the read count (1.0, 2.0, ...); seven-day is fixed."""

    def __init__(self, seven=10.0):
        self.reads = 0
        self.seven = seven

    def __call__(self):
        self.reads += 1
        return pilot.Windows(float(self.reads), self.seven)


class IA:
    def __init__(self):
        md = json.loads((FIXTURES / "gd73_metadata.json").read_text())
        self.md = md

    def metadata(self, identifier):
        return self.md


def tree(root: Path, skip=()) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file() and not p.name.endswith(".lock")
            and not any(s in p.relative_to(root).parts for s in skip)}


class Env:
    def __init__(self, tmp_path, monkeypatch, *, second_held=False):
        self.root = tmp_path / "lib"
        self.libs = build_library(self.root)
        if second_held:
            library_show(self.root, held=True, date="1973-06-12")
        self.out = tmp_path / "pilot"
        self.config = load_config(self.root / "config.toml")
        self.ia = IA()
        self.meter = Meter()
        self.slugs = [HELD] + ([HELD2] if second_held else [])
        self.out.mkdir()
        (self.out / "shows.json").write_text(json.dumps(
            [{"slug": s, "cls": "other"} for s in self.slugs]))
        monkeypatch.setattr(runner, "stale_message", lambda *a, **k: None)

    def redo(self, entry, stage):
        s = read_model(entry.ws.show, Show)
        ov = json.loads(entry.ws.overrides.read_text()) if entry.ws.overrides.exists() else {}
        tracks = list(s.tracks)
        if ov.get("recording"):          # the re-gather of a switch: the sibling adds a song
            tracks.append(Track(index=7, set="2", title="Brand New Song", filename="new.mp3",
                                duration_sec=30.0, title_source="tags"))
        write_artifact(entry.ws.show, s.model_copy(update={
            "venue": ov.get("venue", s.venue), "review_flags": [], "needs_review": False,
            "tracks": tracks}))

    def add_sibling(self):
        """A considered recording, so a switch verdict validates."""
        from llama.workspace import ShowWorkspace
        ws = ShowWorkspace(self.root / "shows" / HELD)
        write_artifact(ws.selection, {"identifier": read_model(ws.show, Show).identifier,
                                      "scores": {"gd73-sib": {"lineage": "sbd",
                                                              "kept_tracks": 3, "score": 2.0}}})

    def run(self, arm="opus", provider=None, **kw):
        provider = provider or FakeProvider([verdict() for _ in self.slugs])
        self.provider = provider
        kw.setdefault("read_meter", self.meter)
        kw.setdefault("ps", lambda: NO_PROCS)
        return pilot.run(arm, config=self.config, out=self.out, ia=self.ia, provider=provider,
                         redo=self.redo, **kw)


def costs(env, arm="opus"):
    p = env.out / arm / "costs.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()]


# ------------------------------------------------------------------ select

def test_allocation_has_a_floor_and_is_deterministic():
    pop = {"a": 100, "b": 50, "c": 3, "d": 1, "e": 40}
    alloc = pilot.allocate(pop, 30)
    assert sum(alloc.values()) == 30
    assert alloc["d"] == 1 and alloc["c"] >= 2          # floor 2, capped at the class size
    assert all(alloc[k] >= 2 for k in ("a", "b", "e"))
    assert alloc["a"] > alloc["b"] > alloc["e"]         # otherwise proportional
    assert pilot.allocate(pop, 30) == alloc


def test_classify_uses_prototype_root_causes_then_flag_patterns():
    c = pilot.classify
    assert c(["x"], {"root_causes": ["partial-tape", "selection-should-prefer-sibling"],
                     "needed_beyond_bundle": "nothing"}) == pilot.PARTIAL_SIBLING
    assert c(["x"], {"root_causes": ["partial-tape"]}) == pilot.PARTIAL
    assert c(["x"], {"root_causes": ["selection-should-prefer-sibling"]}) == pilot.SIBLING
    assert c(["x"], {"root_causes": ["shifted-or-scrambled-tags"]}) == pilot.SCRAMBLED
    assert c(["x"], {"root_causes": ["flags-echo-untitled-tape"]}) == pilot.UNTITLED
    assert c(["x"], {"root_causes": ["partial-tape"],
                     "needed_beyond_bundle": "listen"}) == pilot.LISTEN
    assert c(["x"], {"root_causes": ["spurious-venue-variant"]}) == pilot.OTHER
    assert c(["unresolved track titles"], None) == pilot.UNTITLED     # no verdict: flags
    assert c(["venue mismatch: a vs b"], None) == pilot.OTHER


def test_select_stratifies_with_floor_and_is_deterministic(tmp_path, capsys, monkeypatch):
    env = Env(tmp_path, monkeypatch, second_held=True)
    library_show(env.root, held=True, date="1973-06-13")
    verdicts = tmp_path / "verdicts"
    verdicts.mkdir()
    for slug, causes in ((HELD, ["partial-tape"]), (HELD2, ["partial-tape"]),
                         ("gratefuldead-1973-06-13", ["shifted-or-scrambled-tags"])):
        (verdicts / f"{slug}.json").write_text(json.dumps(
            {"root_causes": causes, "needed_beyond_bundle": "nothing",
             "action": {"kind": "fix", "steps": []}}))
    out = tmp_path / "sel"
    rows = pilot.select(env.config, out, n=3, seed=7, verdicts_dir=verdicts)
    assert {r["slug"] for r in rows} == {HELD, HELD2, "gratefuldead-1973-06-13"}
    assert {r["cls"] for r in rows} == {pilot.PARTIAL, pilot.SCRAMBLED}
    assert json.loads((out / "shows.json").read_text()) == rows
    assert json.loads((out / "population.json").read_text()) == {pilot.PARTIAL: 2,
                                                                 pilot.SCRAMBLED: 1}
    printed = capsys.readouterr().out.splitlines()
    assert sorted(l for l in printed if l.startswith("/")) == sorted(
        str(env.root / "shows" / r["slug"]) for r in rows)      # absolute dirs, one per line
    again = pilot.select(env.config, tmp_path / "sel2", n=2, seed=7, verdicts_dir=verdicts)
    assert again == pilot.select(env.config, tmp_path / "sel3", n=2, seed=7,
                                 verdicts_dir=verdicts)
    assert len(again) == 3                      # the floor of 2 per class beats a small n


def test_select_is_read_only(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    before = tree(env.root)
    pilot.select(env.config, tmp_path / "sel", n=5, seed=1, verdicts_dir=tmp_path / "none")
    assert tree(env.root) == before


# ------------------------------------------------------------------ run

def test_run_writes_sink_records_not_adjudication_json(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    env.run()
    assert (env.out / "opus" / f"{HELD}.json").exists()
    assert not (env.libs[HELD].dir / "adjudication.json").exists()
    assert not list(env.root.rglob("adjudication.json"))


def test_run_trials_switch_verdicts_and_restores(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    before = tree(env.root, skip=("sink",))
    env.run(trial_applies=1)
    assert tree(env.root, skip=("sink",)) == before            # the trial apply was restored
    rec = json.loads((env.out / "opus" / f"{HELD}.json").read_text())
    assert rec["result"]["status"] == "applied"                # but it did run
    assert costs(env)[0]["trial"] is True


def test_trial_whose_redo_appends_a_ledger_row_leaves_the_ledger_identical(tmp_path, monkeypatch):
    """The fake redo records the row process_show records when a show clears (pid,
    `selected`, the provenance run); the trial's restore must take it back out."""
    from llama.models import LedgerEntry, Provenance
    env = Env(tmp_path, monkeypatch)
    path = env.root / "ledger.jsonl"
    path.write_text(json.dumps({"performance_id": "Other/1970-01-01", "artist": "x",
                                "date": "1970-01-01", "status": "selected", "run": "r0",
                                "recorded_at": "2026-01-01T00:00:00+00:00"}) + "\n")
    before, appended = path.read_bytes(), []
    fake = env.redo

    def redo(entry, stage):
        fake(entry, stage)
        prov = read_model(entry.ws.provenance, Provenance)
        Ledger(path).record(LedgerEntry(
            performance_id=prov.candidate.performance_id, artist="Grateful Dead",
            date="1973-06-10", status="selected", run=prov.run,
            recorded_at="2026-11-07T00:00:00+00:00"))
        appended.append(len(Ledger(path).entries()))
    env.redo = redo
    env.run(trial_applies=1)
    assert appended == [2]                                     # the row was appended
    rec = json.loads((env.out / "opus" / f"{HELD}.json").read_text())
    assert rec["result"]["status"] == "applied"
    assert path.read_bytes() == before                         # and taken back out


def test_trial_whose_redo_packages_leaves_no_package_dir(tmp_path, monkeypatch):
    """Pilot defect (R1): a trial redo created package/ and package/audio/ in a show
    without them, and the restore left both behind, empty."""
    env = Env(tmp_path, monkeypatch)
    show_dir = env.root / "shows" / HELD
    assert not (show_dir / "package").exists()
    fake = env.redo

    def redo(entry, stage):
        fake(entry, stage)
        write_artifact(entry.ws.package_dir / "manifest.json", {"v": 3})
        (entry.ws.package_dir / "audio").mkdir(parents=True, exist_ok=True)
        (entry.ws.package_dir / "audio" / "01 - x.mp3").write_bytes(b"X")
    env.redo = redo
    env.run(trial_applies=1)
    assert json.loads((env.out / "opus" / f"{HELD}.json").read_text())[
        "result"]["status"] == "applied"
    assert not (show_dir / "package").exists()


def test_trial_policy_switches_always_others_up_to_the_limit():
    from llama.adjudicator.gate import GateResult
    from llama.adjudicator.verdict import Verdict
    sw = Verdict.model_validate_json(verdict(edits=[
        {"op": "switch_recording", "identifier": "gd73-sib", "confidence": "high", "why": "w",
         "evidence": [{"kind": "sibling-tracks", "quote": "q"}]}]))
    plain = Verdict.model_validate_json(verdict())
    auto, no = GateResult([], [], True), GateResult([], [], False)
    policy = pilot.make_trial_policy(1)
    assert policy(plain, no) is False
    assert policy(sw, no) is False                  # never without gate.auto
    assert policy(sw, auto) is True
    assert policy(sw, auto) is True                 # switches are not counted against the limit
    assert policy(plain, auto) is True              # the first other
    assert policy(plain, auto) is False             # the limit is 1


def test_run_pins_model_per_arm(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    env.run("opus")
    env.out.joinpath("opus").rename(tmp_path / "opus-done")
    env.run("sonnet", provider=FakeProvider([verdict()]))
    assert json.loads((tmp_path / "opus-done" / f"{HELD}.json").read_text())[
        "model"] == "claude_cli:opus"
    assert json.loads((env.out / "sonnet" / f"{HELD}.json").read_text())[
        "model"] == "claude_cli:sonnet"
    # never a tier: an explicit pin does not escalate
    from herder import provider_ladder
    cfg = pilot.arm_config(env.config, "sonnet")
    assert {p.model for p in provider_ladder(cfg.llm_settings(), "adjudicate")} == {"sonnet"}


def test_run_makes_one_llm_call_per_show_trial_or_not(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch, second_held=True)
    env.run(trial_applies=1)
    assert len(env.provider.calls) == 2
    assert [c["trial"] for c in costs(env)] == [True, False]


def test_run_never_calls_the_live_meter(tmp_path, monkeypatch):
    import herder.usage

    def boom(*a, **k):
        raise AssertionError("live meter read")
    monkeypatch.setattr(herder.usage, "read_usage", boom)
    env = Env(tmp_path, monkeypatch, second_held=True)
    env.run()
    assert env.meter.reads == 4                                 # before and after, per show
    row = costs(env)[0]
    assert set(row) == {"slug", "cls", "outcome", "five_hour_before", "five_hour_after",
                        "wall_s", "trial", "trial_kind"}
    assert (row["five_hour_before"], row["five_hour_after"]) == (1.0, 2.0)
    assert row["cls"] == "other" and row["outcome"] == runner.DRY_RUN


def test_run_skips_shows_already_in_costs(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch, second_held=True)
    env.run(provider=FakeProvider([verdict(), verdict()]))
    first = env.provider
    assert len(first.calls) == 2
    env.run(provider=FakeProvider([]))                          # a re-run spends nothing
    assert len(env.provider.calls) == 0 and len(costs(env)) == 2


def test_run_resume_is_per_arm(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch, second_held=True)
    env.run("opus")
    env.run("sonnet", provider=FakeProvider([verdict(), verdict()]))
    assert len(env.provider.calls) == 2                # not skipped on opus's rows
    assert [r["slug"] for r in costs(env, "sonnet")] == env.slugs


def test_run_trials_an_auto_switch_end_to_end_and_restores(tmp_path, monkeypatch):
    from llama.adjudicator.gate import EditGate, GateResult
    env = Env(tmp_path, monkeypatch)
    env.add_sibling()
    sw = verdict(edits=[{"op": "switch_recording", "identifier": "gd73-sib", "confidence": "high",
                         "why": "w", "evidence": [{"kind": "sibling-tracks", "quote": "Morning Dew"}]}])
    monkeypatch.setattr(runner, "evaluate", lambda v, f: GateResult(
        [EditGate(0, "switch_recording", "switch", True, "")], [], True))
    before = tree(env.root, skip=("sink",))
    env.run(provider=FakeProvider([sw]), trial_applies=0)      # a switch is trialled regardless
    assert tree(env.root, skip=("sink",)) == before
    row = costs(env)[0]
    assert row["trial"] is True and row["trial_kind"] == "switch"
    rec = json.loads((env.out / "opus" / f"{HELD}.json").read_text())
    assert rec["result"]["status"] == "applied", rec["result"]


def test_run_records_a_vanished_show_and_moves_on(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    (env.out / "shows.json").write_text(json.dumps(
        [{"slug": "gone-show", "cls": "other"}, {"slug": HELD, "cls": "other"}]))
    env.run()
    rows = costs(env)
    assert rows[0]["slug"] == "gone-show" and rows[0]["outcome"].startswith("failed: ")
    assert rows[1]["slug"] == HELD and rows[1]["outcome"] == runner.DRY_RUN
    env.run(provider=FakeProvider([]))                         # a resume does not retry it
    assert len(costs(env)) == 2


def test_trial_limit_survives_a_resume(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch, second_held=True)
    (env.out / "opus").mkdir()
    (env.out / "opus" / "costs.jsonl").write_text(json.dumps(
        {"slug": HELD, "cls": "other", "outcome": runner.DRY_RUN, "five_hour_before": 1.0,
         "five_hour_after": 2.0, "wall_s": 1.0, "trial": True, "trial_kind": "other"}) + "\n")
    env.run(provider=FakeProvider([verdict()]), trial_applies=1)   # the one trial is spent
    assert [r["trial"] for r in costs(env)] == [True, False]


# ---- the pacing ceiling (fail closed)

W = pilot.Windows


def stopper(env, reading, **kw):
    with pytest.raises(pilot.PilotStopped) as e:
        env.run(read_meter=lambda: reading, **kw)
    assert "\n" not in str(e.value)
    assert len(env.provider.calls) == 0 and not (env.out / "opus" / "costs.jsonl").exists()
    return str(e.value)


@pytest.mark.parametrize("reading,limit_kw,needle", [
    (W(85.0, 10.0), {}, "5-hour"),
    (W(10.0, 80.0), {}, "7-day"),
    (W(50.0, 10.0), {"stop_at_5h": 50.0}, "5-hour"),
    (W(10.0, 61.0), {"stop_at_7d": 60.0}, "7-day"),
    (None, {}, "unreadable"),
    (W(10.0, None), {}, "missing"),
    (W(None, 10.0), {}, "missing"),
])
def test_run_stops_before_a_show_when_a_window_is_at_its_limit_or_untrusted(
        tmp_path, monkeypatch, reading, limit_kw, needle):
    assert needle in stopper(Env(tmp_path, monkeypatch), reading, **limit_kw)


@pytest.mark.parametrize("reading", [W(84.99, 10.0), W(10.0, 79.99), W(84.99, 79.99)])
def test_run_proceeds_just_below_the_default_limits(tmp_path, monkeypatch, reading):
    env = Env(tmp_path, monkeypatch)
    env.run(read_meter=lambda: reading)
    assert [r["slug"] for r in costs(env)] == [HELD]


def test_run_stops_on_a_stale_live_reading(tmp_path, monkeypatch):
    import herder.usage as hu
    real = hu.read_usage
    stale = json.dumps({"result": "Showing last-known usage\nCurrent session: 5% used\n"
                                  "Current week (all models): 5% used"})
    monkeypatch.setattr(hu, "read_usage", lambda *a, **k: real(runner=lambda: stale))
    assert pilot.live_meter() is None
    env = Env(tmp_path, monkeypatch)
    with pytest.raises(pilot.PilotStopped):
        env.run(read_meter=pilot.live_meter)


def test_run_proceeds_below_both_limits_and_stops_resumably(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch, second_held=True)
    readings = iter([W(10.0, 10.0), W(11.0, 10.0), W(90.0, 10.0)])   # 2nd show's gate read is high
    with pytest.raises(pilot.PilotStopped):
        env.run(read_meter=lambda: next(readings))
    assert [r["slug"] for r in costs(env)] == [HELD]
    env.run(provider=FakeProvider([verdict()]))                      # resumes with the next show
    assert [r["slug"] for r in costs(env)] == env.slugs


def test_run_stops_when_rate_limited(tmp_path, monkeypatch):
    from herder.limits import RateLimited
    env = Env(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "adjudicate_show", lambda *a, **k: (_ for _ in ()).throw(
        RateLimited("window")))
    with pytest.raises(pilot.PilotStopped):
        env.run()


def test_main_exits_3_when_stopped(monkeypatch, tmp_path):
    monkeypatch.setattr(pilot, "load_config", lambda p: object())

    def stop(*a, **k):
        raise pilot.PilotStopped("stopped")
    monkeypatch.setattr(pilot, "run", stop)
    assert pilot.main(["run", "--arm", "opus", "--out", str(tmp_path)]) == 3
    monkeypatch.setattr(pilot, "run", lambda *a, **k: (_ for _ in ()).throw(
        pilot.PilotRefused("busy")))
    assert pilot.main(["run", "--arm", "opus", "--out", str(tmp_path)]) == 2


def test_proto_ops_match_whole_flags_and_read_proto_is_defensive(tmp_path):
    ops = pilot._proto_ops({"action": {"steps": [
        {"cmd": "llama fix s --clear-include a.mp3 --clear-recording"},
        {"cmd": "llama fix s --include b.mp3 --recording x"}]}})
    assert ops == {"include", "switch_recording"}
    assert pilot._proto_ops({"action": {"steps": [
        {"cmd": "llama fix s --clear-include a.mp3 --clear-recording"}]}}) == set()
    # a flag-looking string inside a value is not a flag
    assert pilot._proto_ops({"action": {"steps": [
        {"cmd": 'llama fix s --set-title 1="x--overrule"'}]}}) == {"set_title"}
    (tmp_path / "a.json").write_text("[1]")
    (tmp_path / "b.json").write_text(json.dumps({"root_causes": "partial-tape"}))
    assert pilot._read_proto(tmp_path, "a") is None
    assert pilot.classify(["x"], pilot._read_proto(tmp_path, "b")) == pilot.OTHER


def test_arm_config_keeps_the_rest_of_an_existing_adjudicate_task(tmp_path):
    from llama.config import Config
    cfg = Config.model_validate({"llm": {"adjudicate": {"backend": "openrouter",
                                                        "tier": "low"}}})
    pinned = pilot.arm_config(cfg, "opus").llm["adjudicate"]
    assert (pinned.backend, pinned.model, pinned.tier) == ("claude_cli", "opus", "low")


def test_select_uses_the_catalog_entry_state_and_flags(tmp_path, monkeypatch):
    from types import SimpleNamespace as NS
    entries = [NS(slug="a", state="held", flags=["unresolved track titles"], ws=NS(dir=tmp_path / "a")),
               NS(slug="b", state="packaged", flags=[], ws=NS(dir=tmp_path / "b"))]
    monkeypatch.setattr(pilot, "iter_shows", lambda root, ledger: entries)   # no show.json anywhere
    from llama.config import Config
    rows = pilot.select(Config(root=tmp_path), tmp_path / "sel", n=5, seed=1,
                        verdicts_dir=tmp_path / "x")
    assert rows == [{"slug": "a", "cls": pilot.UNTITLED}]


# ---- the process refusal (by name, via campaign_gate's parser)

def test_run_does_not_refuse_for_its_own_process_or_shells_mentioning_llama(tmp_path, monkeypatch):
    env = Env(tmp_path, monkeypatch)
    me = "/Users/shawn/projects/llama/.venv/bin/python scripts/adjudicate_pilot.py run --arm opus"
    lines = [f"500 400 {me}",
             "400 1 /bin/zsh -c cd /Users/shawn/projects/llama/ && "
             "./.venv/bin/python scripts/adjudicate_pilot.py run --arm opus",
             "300 1 /bin/bash /Users/shawn/projects/llama/.claude/worktrees/x/wrapper.sh",
             "301 1 claude --add-dir /Users/shawn/projects/llama"]
    env.run(ps=lambda: lines)
    assert (env.out / "opus" / "costs.jsonl").exists()


@pytest.mark.parametrize("line,tool", [("777 1 /usr/local/bin/llama get x", "llama"),
                                       ("778 1 /opt/bin/emcee run --dry-run", "emcee")])
def test_run_refuses_while_llama_or_emcee_runs(tmp_path, monkeypatch, line, tool):
    env = Env(tmp_path, monkeypatch)
    with pytest.raises(pilot.PilotRefused) as e:
        env.run(ps=lambda: [line])
    assert tool in str(e.value) and "\n" not in str(e.value)
    assert env.meter.reads == 0 and not (env.out / "opus").exists()


# ------------------------------------------------------------------ compare

def edit_rec(ops, *, auto=True, vetoes=(), cls_edits=None):
    """A dry-run record. `ops`: (op, bar, passed) per edit."""
    edits, gate = [], []
    for i, (op, bar, passed) in enumerate(ops):
        e = {"op": op, "confidence": "high", "why": "w",
             "evidence": [{"kind": "taper-description", "quote": f"quote-{i}"}]}
        e.update({"include": {"file": f"f{i}.mp3"}, "exclude": {"file": f"f{i}.mp3"},
                  "set_title": {"file": f"f{i}.mp3", "title": "T"},
                  "structure": {"breaks_after": ["f1.mp3"], "encore_after": None},
                  "switch_recording": {"identifier": "sib"}, "venue": {"venue": "V"}}[op])
        edits.append(e)
        gate.append({"index": i, "op": op, "bar": bar, "passed": passed,
                     "reason": "" if passed else f"{op} failed"})
    return {"version": 1, "at": "t", "model": "claude_cli:opus", "dry_run": True,
            "outcome": "dry-run", "digest": "", "malformed": [], "gate": gate,
            "vetoes": list(vetoes), "applied": [], "result": {}, "partial_tape": False,
            "held_proposal": None,
            "verdict": {"flags": [], "edits": edits, "kind": "fix", "show_correct_after": "yes",
                        "rationale": "r"}}


APPLIED_RESULT = {"status": "applied", "held": True, "diff": [], "changes": ["track 3 title"],
                  "error": None, "reheld": []}


def seed_pilot(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    shows = [{"slug": "s-long", "cls": pilot.UNTITLED}, {"slug": "s-short", "cls": pilot.OTHER},
             {"slug": "s-part1", "cls": pilot.PARTIAL},
             {"slug": "s-part2", "cls": pilot.PARTIAL_SIBLING},
             {"slug": "s-switch", "cls": pilot.SIBLING}, {"slug": "s-solo", "cls": pilot.OTHER}]
    (out / "shows.json").write_text(json.dumps(shows))
    (out / "population.json").write_text(json.dumps(
        {pilot.UNTITLED: 40, pilot.OTHER: 20, pilot.PARTIAL: 10, pilot.PARTIAL_SIBLING: 5,
         pilot.SIBLING: 8}))
    recs = {
        "s-long": edit_rec([("include", "long", True), ("set_title", "title", True),
                            ("structure", "structure", True)]),
        "s-short": edit_rec([("exclude", "short", True), ("venue", "medium", True)]),
        "s-part1": edit_rec([("exclude", "long", False)], vetoes=["show not judged correct"]),
        "s-part2": edit_rec([("switch_recording", "switch", False)]),
        "s-switch": edit_rec([("switch_recording", "switch", True)]),
        "s-solo": edit_rec([("venue", "medium", True)]),
    }
    trials = {"s-long": "other", "s-switch": "switch"}
    for arm in ("opus", "sonnet"):
        d = out / arm
        d.mkdir()
        rows = []
        for i, s in enumerate(shows):
            if arm == "sonnet" and s["slug"] == "s-solo":
                continue                                       # judged by opus only
            rec = json.loads(json.dumps(recs[s["slug"]]))
            if arm == "sonnet" and s["slug"] == "s-short":
                rec = edit_rec([("exclude", "long", False)])               # a disagreement
            trial = s["slug"] in trials
            if trial:
                rec["result"] = dict(APPLIED_RESULT)
            (d / f"{s['slug']}.json").write_text(json.dumps(rec))
            delta = 5.0 if trial else 1.0
            after = 10.0 + i + delta
            if arm == "sonnet" and s["slug"] == "s-part2":
                after = 0.0                                    # the window reset mid-show
            rows.append({"slug": s["slug"], "cls": s["cls"], "outcome": "dry-run",
                         "five_hour_before": 10.0 + i, "five_hour_after": after,
                         "wall_s": (200.0 if trial else 30.0) + (10 if arm == "sonnet" else 0),
                         "trial": trial, "trial_kind": trials.get(s["slug"])})
        (d / "costs.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def section(text, heading):
    return text.split(heading)[1].split("\n## ")[0]


def test_compare_lists_strict_surface_and_projection(tmp_path):
    out = tmp_path / "pilot"
    seed_pilot(out)
    verdicts = tmp_path / "verdicts"
    verdicts.mkdir()
    (verdicts / "s-short.json").write_text(json.dumps({"action": {
        "kind": "fix", "steps": [{"cmd": "llama fix s-short --exclude f0.mp3"}]}}))
    path = pilot.compare(out, verdicts_dir=verdicts)
    assert path == out / "compare.md"
    assert not path.name.upper().startswith(("REPORT", "SUMMARY", "FINDINGS", "ANALYSIS"))
    text = path.read_text()
    strict = section(text, "## Strict surface")
    for needle in ("s-long", "include", "set_title", "structure", "quote-0", "quote-1", "quote-2"):
        assert needle in strict
    assert "s-switch" in strict and "switch_recording" in strict   # an auto switch is strict
    assert "s-short" not in strict                    # short/medium edits are not strict
    assert "s-part2" not in strict                    # not auto-applied
    auto = section(text, "## Auto-apply list")
    assert "s-short" in auto and "s-long" in auto and "s-part1" not in auto
    proj = section(text, "## Projected held-with-proposal")
    assert "| other | opus | 0 of 2 | 20 | 0.0 |" in proj          # s-short and s-solo auto
    assert "| other | sonnet | 1 of 1 | 20 | 20.0 |" in proj        # s-short held with proposal
    dis = section(text, "## Disagreements")
    assert ("- s-short (other): opus would auto-apply [('exclude', 'f0.mp3'), ('venue', 'V')] / "
            "sonnet held with proposal [('exclude', 'f0.mp3')]") in dis
    assert "- s-solo: missing in sonnet" in dis
    agree = section(text, "## Agreement with the prototype")
    assert "| fix | fix | 1 |" in agree and "| exclude | 1 | 0 | 0 |" in agree


def test_compare_reports_trial_applies_and_separates_their_cost(tmp_path):
    out = tmp_path / "pilot"
    seed_pilot(out)
    text = pilot.compare(out, verdicts_dir=tmp_path / "none").read_text()
    trials = section(text, "## Trial applies")
    assert "### opus" in trials and "### sonnet" in trials
    assert "s-long" in trials and "s-switch" in trials
    assert "switch" in trials.split("s-switch")[1].splitlines()[0]
    assert "applied, still held" in trials and "track 3 title" in trials
    cost = section(text, "## Cost and wall time")
    assert ("| arm | kind | rows | mean 5h-meter points/show | mean wall s | dropped from points |"
            in cost.splitlines())
    assert "| opus | judge-only | 4 | 1.00 | 30.0 |" in cost
    assert "| opus | trial | 2 | 5.00 | 200.0 |" in cost
    assert "| sonnet | judge-only | 3 | 1.00 | 40.0 | 1 |" in cost      # a window reset dropped
    assert "judge-only" in cost.split("full sweep")[1]
    assert "83 points" in cost                                        # 1.00 x 83 held
    per_show = section(text, "## Per-show cost")
    assert "| s-switch | sibling" not in per_show                      # class column is the name
    assert "| s-switch | better sibling | dry-run | switch | 5.0 | 200.0 |" in per_show
    assert "| s-short | other | dry-run | - | 1.0 | 30.0 |" in per_show


def test_compare_reports_partial_tape_gate_blockers(tmp_path):
    out = tmp_path / "pilot"
    seed_pilot(out)
    text = pilot.compare(out, verdicts_dir=tmp_path / "none").read_text()
    sec = section(text, "## Partial-tape classes")
    assert "partial tape" in sec and "partial tape with a better sibling" in sec
    assert "0 of 1" in sec or "0/1" in sec               # none could be auto-applied
    assert "show not judged correct" in sec              # the veto, tallied
    assert "exclude failed" in sec and "switch_recording failed" in sec
