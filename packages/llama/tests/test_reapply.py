"""llama reapply: exactly the harness's computation, applied under the show lock
with show.json written last (spec slice 6)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_library import build_library

import llama.reapply as reapply_mod
from herder import FakeProvider
from llama.config import load_config
from llama.errors import LlamaError
from llama.ia_client import IAError
from llama.ledger import Ledger
from llama.locks import Locked, file_lock
from llama.models import Overrides, Briefing, LedgerEntry, Show, ShowNotes, VettingResult
from llama.reapply import ReapplyOutcome, reapply_show
from llama.replay import input_digests
from llama.stages.brief import normalize_briefing, render_briefing_md
from llama.workspace import read_model, write_artifact
from llama.reapply import STOP_AFTER_LLM_FAILURES, batch_dir, load_list, read_progress
from llama.replay import config_fingerprint

HELD = "gratefuldead-1973-06-10"


def _env(tmp_path, *, held_for_real=False):
    root = tmp_path / "lib"
    shows = build_library(root, held_for_real=held_for_real)
    # the fixture library's own config.toml: `[jerrybase] enabled = false`, as the arms were built.
    # A bare Config(root=root) enables jerrybase, whose 3-set GD 1973-06-10 row would hold the show.
    config = load_config(root / "config.toml")
    ledger = Ledger(root / "ledger.jsonl")
    from llama.catalog import resolve_show
    entry = resolve_show(root, ledger, HELD)
    return root, config, ledger, entry, shows


def _snapshot(ws) -> dict:
    # file_lock leaves a `.lock` behind: create it first so it is in both snapshots
    ws.lock.touch()
    return {p.name: (p.read_bytes() if p.is_file() else None) for p in ws.dir.iterdir()}


def _stale(ws) -> None:
    """Make vetting.json and notes.json differ from what reapply would write
    (the replay re-grounds the flags and never reads either), so a write that
    must not happen shows up in a snapshot comparison."""
    vr = read_model(ws.vetting, VettingResult)
    write_artifact(ws.vetting, vr.model_copy(update={"flags": ["stale vet flag"]}))
    write_artifact(ws.notes, ShowNotes(gather=["stale note"], vet=[]))


def _stub_package(monkeypatch, fail_first=False, flags=()):
    calls = []
    def fake(show_ws, ia, show, force=False, profile=None):
        if (show_ws.package_dir / "manifest.json").exists() and not force:
            return show_ws.package_dir, []          # the real early return on an existing manifest
        calls.append(show.performance_id)
        if fail_first and len(calls) == 1:
            raise IAError("download failed")
        write_artifact(show_ws.package_dir / "manifest.json", {"schema_version": 3, "tracks": []})
        return show_ws.package_dir, list(flags)
    monkeypatch.setattr(reapply_mod, "build_package", fake)
    return calls


def _providers(*responses):
    return {"brief": FakeProvider(list(responses))}


def _run(config, ledger, entry, providers=None, *, ia=None, row=None, dry_run=False):
    return reapply_show(config, ia if ia is not None else object(), ledger, entry,
                        providers=providers if providers is not None else _providers(),
                        row=row, dry_run=dry_run, echo=lambda s: None)


def test_reapply_clears_a_held_show_with_a_reusable_briefing_and_writes_show_json_last(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    calls = _stub_package(monkeypatch)
    kept = {p: p.read_bytes() for p in (entry.ws.provenance, entry.ws.reviews)}
    out = _run(config, ledger, entry)
    assert isinstance(out, ReapplyOutcome)
    assert out.outcome == "cleared" and out.briefing == "reuse" and out.flags == []
    assert out.written == ["vetting.json", "notes.json", "briefing.json", "briefing.md", "package", "show.json"]
    show = read_model(entry.ws.show, Show)
    assert show.needs_review is False and show.review_flags == []
    assert calls == [show.performance_id]
    assert read_model(entry.ws.notes, ShowNotes) == ShowNotes(gather=[], vet=[])
    # reviews.json and provenance.json are never written; nor research.md or the ledger
    assert {p: p.read_bytes() for p in kept} == kept
    assert not entry.ws.research.exists() and ledger.entries() == []


def test_reapply_makes_no_llm_call_on_a_reusable_briefing_and_no_network_call_outside_package(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    class NetIA:
        def __getattr__(self, name): raise AssertionError(f"network client used for {name}")
    providers = _providers()
    out = _run(config, ledger, entry, providers, ia=NetIA())
    assert out.outcome == "cleared"
    assert providers["brief"].calls == []


def test_a_reused_briefing_is_rewritten_normalised_never_copied(tmp_path, monkeypatch):
    # spec 3a: "on every reuse of a stored briefing" the empty per_set entries
    # are dropped and briefing.md is re-rendered; a stored briefing.md with an
    # empty `## Encore` heading must not survive a reuse.
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    raw = read_model(entry.ws.briefing_json, Briefing)
    raw = raw.model_copy(update={"per_set": {**raw.per_set, "encore": []}})
    write_artifact(entry.ws.briefing_json, raw)
    stored = read_model(entry.ws.show, Show)
    write_artifact(entry.ws.briefing_md, render_briefing_md(raw, stored))
    assert "## Encore\n\n" in entry.ws.briefing_md.read_text()
    out = _run(config, ledger, entry)
    assert out.outcome == "cleared" and out.briefing == "reuse"
    shipped = read_model(entry.ws.briefing_json, Briefing)
    assert shipped == normalize_briefing(raw) and "encore" not in shipped.per_set
    final = read_model(entry.ws.show, Show)
    assert entry.ws.briefing_md.read_text() == render_briefing_md(shipped, final)
    assert "## Encore" not in entry.ws.briefing_md.read_text()


def test_reapply_generates_one_fresh_brief_when_none_is_stored(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    entry.ws.briefing_json.unlink()
    _stub_package(monkeypatch)
    ok = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"], "2": ["b"], "encore": ["c"]}))
    providers = _providers(ok)
    out = _run(config, ledger, entry, providers)
    assert out.outcome == "cleared" and out.briefing == "fresh" and len(providers["brief"].calls) == 1
    assert entry.ws.briefing_json.exists() and entry.ws.briefing_md.exists()
    assert out.written == ["vetting.json", "notes.json", "briefing.json", "briefing.md", "package", "show.json"]


def test_reapply_leaves_a_show_held_when_the_fresh_brief_fails_its_guard(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    entry.ws.briefing_json.unlink()
    calls = _stub_package(monkeypatch)
    bad = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"]}, mentioned_songs=["Nope"]))
    out = _run(config, ledger, entry, _providers(bad, bad))
    assert out.outcome == "held" and out.flags == ["briefing mentions unknown song: Nope"]
    show = read_model(entry.ws.show, Show)
    assert show.needs_review is True and show.review_flags == ["briefing mentions unknown song: Nope"]
    assert out.written == ["vetting.json", "notes.json", "briefing.json", "briefing.md", "show.json"]
    assert calls == []


def test_a_show_still_flagged_after_vet_is_written_held_with_no_briefing_or_package(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path, held_for_real=True)
    calls = _stub_package(monkeypatch)
    providers = _providers()
    out = _run(config, ledger, entry, providers)
    assert out.outcome == "held" and out.briefing == "none"
    assert out.flags == ["research asserts wrong date: 1974-01-01"]
    assert out.written == ["vetting.json", "notes.json", "show.json"]
    show = read_model(entry.ws.show, Show)
    assert show.needs_review is True and show.review_flags == out.flags
    assert calls == [] and providers["brief"].calls == []


def test_a_carried_package_flag_is_never_cleared(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    flag = "duration mismatch on 01 - Morning Dew.mp3: file 10s vs metadata 664s"
    show = read_model(entry.ws.show, Show)
    show.review_flags = show.review_flags + [flag]
    write_artifact(entry.ws.show, show)
    calls = _stub_package(monkeypatch)
    out = _run(config, ledger, entry)
    assert out.outcome == "held" and out.flags == [flag] and calls == []
    assert read_model(entry.ws.show, Show).review_flags == [flag]


def test_reapply_writes_nothing_on_a_needs_llm_show(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    show = read_model(entry.ws.show, Show)
    show.structure = show.structure.model_copy(update={"alignment": "llm"})
    write_artifact(entry.ws.show, show)
    _stale(entry.ws)
    before = _snapshot(entry.ws)
    out = _run(config, ledger, entry)
    assert out.outcome == "needs-llm" and out.written == []
    assert _snapshot(entry.ws) == before


def test_reapply_writes_nothing_on_a_refusal_mid_show(tmp_path, monkeypatch):
    from herder.limits import RateLimited
    root, config, ledger, entry, _ = _env(tmp_path)
    entry.ws.briefing_json.unlink()
    _stale(entry.ws)
    before = _snapshot(entry.ws)
    with pytest.raises(RateLimited):
        _run(config, ledger, entry, _providers(RateLimited("limit")))
    assert _snapshot(entry.ws) == before


def test_a_package_failure_leaves_the_show_held_and_a_rerun_completes_it(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch, fail_first=True)
    with pytest.raises(IAError):
        _run(config, ledger, entry)
    assert read_model(entry.ws.show, Show).needs_review is True          # show.json not yet rewritten
    assert entry.ws.vetting.exists() and entry.ws.briefing_json.exists()  # earlier writes stay
    out = _run(config, ledger, entry)
    assert out.outcome == "cleared"


def test_reapply_passes_no_setlistfm_client_when_no_key_is_configured(tmp_path, monkeypatch):
    # prediction/apply parity: the reapply half (Task 5 pins the harness half)
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    seen = []
    real = reapply_mod.compute_legs
    def spy(ws, **kw):
        seen.append(kw["slfm"])
        return real(ws, **kw)
    monkeypatch.setattr(reapply_mod, "compute_legs", spy)
    _run(config, ledger, entry)
    assert seen == [None]


def test_a_stale_manifest_never_short_circuits_the_package(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    write_artifact(entry.ws.package_dir / "manifest.json", {"schema_version": 3, "tracks": ["stale"]})
    calls = _stub_package(monkeypatch)
    out = _run(config, ledger, entry)
    assert out.outcome == "cleared" and len(calls) == 1
    assert json.loads((entry.ws.package_dir / "manifest.json").read_text())["tracks"] == []


def test_package_flags_land_in_the_one_final_show_json_write(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    flag = "duration mismatch on 01 - Morning Dew.mp3: file 10s vs metadata 664s"
    _stub_package(monkeypatch, flags=[flag])
    out = _run(config, ledger, entry)
    assert out.outcome == "held" and out.written[-1] == "show.json" and out.flags == [flag]
    show = read_model(entry.ws.show, Show)
    assert show.review_flags == [flag] and show.needs_review is True


def test_show_json_is_not_rewritten_before_the_package_is_built(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    seen = []
    def fake(show_ws, ia, show, force=False, profile=None):
        seen.append(read_model(show_ws.show, Show).needs_review)
        write_artifact(show_ws.package_dir / "manifest.json", {"schema_version": 3, "tracks": []})
        return show_ws.package_dir, []
    monkeypatch.setattr(reapply_mod, "build_package", fake)
    _run(config, ledger, entry)
    assert seen == [True]                     # still held while the package is built
    assert read_model(entry.ws.show, Show).needs_review is False


def test_reapply_holds_the_show_lock_throughout(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    def assert_locked(ws_dir):
        with pytest.raises(Locked):
            with file_lock(ws_dir / ".lock", blocking=False):
                pass
    held_during_package = []
    def fake(show_ws, ia, show, force=False, profile=None):
        assert_locked(show_ws.dir)
        held_during_package.append(True)
        write_artifact(show_ws.package_dir / "manifest.json", {"schema_version": 3, "tracks": []})
        return show_ws.package_dir, []
    monkeypatch.setattr(reapply_mod, "build_package", fake)
    real_compute, real_write = reapply_mod.compute_legs, reapply_mod.write_artifact
    def spy(ws, **kw):
        assert_locked(ws.dir)
        return real_compute(ws, **kw)
    writes = []
    def spy_write(path, data):
        if path.name == "show.json":
            assert_locked(path.parent)
            writes.append(path.name)
        return real_write(path, data)
    monkeypatch.setattr(reapply_mod, "compute_legs", spy)
    monkeypatch.setattr(reapply_mod, "write_artifact", spy_write)
    out = _run(config, ledger, entry)
    assert out.outcome == "cleared" and held_during_package == [True] and writes == ["show.json"]
    with file_lock(entry.ws.lock, blocking=False):   # released afterwards
        pass


def test_a_show_edited_after_its_row_was_written_is_skipped(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    row = {"slug": HELD, "digests": input_digests(entry.ws)}
    write_artifact(entry.ws.overrides, {"narration": "vague"})
    _stale(entry.ws)
    before = _snapshot(entry.ws)
    out = _run(config, ledger, entry, row=row)
    assert out.outcome == "skipped: inputs changed" and out.written == []
    assert _snapshot(entry.ws) == before


def test_a_row_whose_digests_match_is_applied(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    row = {"slug": HELD, "digests": input_digests(entry.ws)}
    assert _run(config, ledger, entry, row=row).outcome == "cleared"


def test_a_show_no_longer_held_is_skipped(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    show = read_model(entry.ws.show, Show); show.needs_review = False; show.review_flags = []
    write_artifact(entry.ws.show, show)
    _stale(entry.ws)
    before = _snapshot(entry.ws)
    out = _run(config, ledger, entry)
    assert out.outcome == "skipped: not held" and out.written == []
    assert _snapshot(entry.ws) == before


def test_dry_run_predicts_and_writes_nothing(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stale(entry.ws)
    before = _snapshot(entry.ws)
    out = _run(config, ledger, entry, dry_run=True)
    assert out.outcome == "dry-run: cleared" and out.briefing == "reuse" and out.written == []
    assert _snapshot(entry.ws) == before


def test_dry_run_predicts_needs_brief_and_held(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    entry.ws.briefing_json.unlink()
    providers = _providers()
    out = _run(config, ledger, entry, providers, dry_run=True)
    assert out.outcome == "dry-run: needs-brief" and out.briefing == "fresh"
    assert providers["brief"].calls == []
    root2, config2, ledger2, entry2, _ = _env(tmp_path / "b", held_for_real=True)
    assert _run(config2, ledger2, entry2, dry_run=True).outcome == "dry-run: held"


def test_reapply_flags_a_delivered_show_for_redelivery_and_writes_no_ledger_row(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    ledger.record(LedgerEntry(performance_id="GratefulDead/1973-06-10", artist="Grateful Dead", date="1973-06-10",
                              status="delivered", run="r1", recorded_at="2026-10-01T00:00:00+00:00"))
    n = len(ledger.entries())
    out = _run(config, ledger, entry)
    assert out.delivered is True and len(ledger.entries()) == n


def test_an_undelivered_show_is_not_flagged_for_redelivery(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    ledger.record(LedgerEntry(performance_id="GratefulDead/1973-06-10", artist="Grateful Dead", date="1973-06-10",
                              status="selected", run="r1", recorded_at="2026-10-01T00:00:00+00:00"))
    assert _run(config, ledger, entry).delivered is False


def test_cli_reapply_names_form(tmp_path, monkeypatch):
    from conftest import cli_invoke
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    import llama.cli as cli
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    ledger.record(LedgerEntry(performance_id="GratefulDead/1973-06-10", artist="Grateful Dead", date="1973-06-10",
                              status="delivered", run="r1", recorded_at="2026-10-01T00:00:00+00:00"))
    r = cli_invoke(root / "config.toml", "reapply", "gratefuldead-1973-06-10")   # the library's own config
    assert r.exit_code == 0, r.output
    assert "reapplied: gratefuldead-1973-06-10 -> cleared" in r.output
    assert "  re-deliver with: llama deliver gratefuldead-1973-06-10" in r.output


def test_cli_reapply_reports_a_failure_continues_and_exits_1(tmp_path, monkeypatch):
    from conftest import cli_invoke
    root, config, ledger, entry, _ = _env(tmp_path)
    import llama.cli as cli
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    seen = []
    def fake(config, ia, ledger, entry, **kw):
        seen.append(entry.slug)
        if entry.slug == HELD:
            raise LlamaError("boom")
        return ReapplyOutcome(slug=entry.slug, outcome="skipped: not held", briefing="none",
                              flags=[], delivered=False, written=[])
    monkeypatch.setattr(reapply_mod, "reapply_show", fake)
    r = cli_invoke(root / "config.toml", "reapply", HELD, "gratefuldead-1973-06-11")
    assert r.exit_code == 1
    assert f"FAILED {HELD}: boom" in r.output
    assert "reapplied: gratefuldead-1973-06-11 -> skipped: not held" in r.output
    assert seen == [HELD, "gratefuldead-1973-06-11"]


def test_cli_reapply_dry_run_writes_nothing(tmp_path, monkeypatch):
    from conftest import cli_invoke
    root, config, ledger, entry, _ = _env(tmp_path)
    import llama.cli as cli
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    before = _snapshot(entry.ws)
    r = cli_invoke(root / "config.toml", "reapply", "--dry-run", HELD)
    assert r.exit_code == 0, r.output
    assert f"reapplied: {HELD} -> dry-run: cleared" in r.output
    assert _snapshot(entry.ws) == before


# --- Task 20: --from-list batches, the pacing gate, stop rules, list checks ---


CLEAN_SHA = "c" * 40


@pytest.fixture(autouse=True)
def _no_global_capture_dir(monkeypatch):
    # The reapply command switches herder's module-level failure capture on;
    # restore it after every test so no later test captures into a dead tmp_path.
    monkeypatch.setattr("herder.failures._capture_dir", None)
    # The suite must not depend on whether the checkout is committed: a dirty
    # tree's `<sha>-dirty` identity is refused by load_list.
    monkeypatch.setattr("llama.replay.code_identity", lambda: CLEAN_SHA)


def _list_file(tmp_path, root, config, entries, sha=None, fp=None):
    rows = [{"slug": e.slug, "outcome": "clears", "briefing": "reuse", "digests": input_digests(e.ws)} for e in entries]
    data = {"sha": sha or CLEAN_SHA, "config_fingerprint": fp or config_fingerprint(config),
            "written_at": "2026-10-19T00:00:00+00:00", "rows": rows}
    p = tmp_path / "predicted_list.json"
    p.write_text(json.dumps(data))
    return p


def _cli(root):
    return root / "config.toml"     # the fixture library's own config ([jerrybase] enabled = false)


def _clones(root, entry, n):
    """`n` copies of the held show under slugs held-2.., returned as entries."""
    import shutil
    from llama.catalog import CatalogEntry
    out = []
    for i in range(2, 2 + n):
        d = root / "shows" / f"held-{i}"
        shutil.copytree(entry.ws.dir, d)
        out.append(CatalogEntry(slug=d.name, ws=type(entry.ws)(d), state="held"))
    return out


def test_list_from_another_sha_or_config_is_refused(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    bad = _list_file(tmp_path, root, config, [entry], sha="0" * 40)
    with pytest.raises(LlamaError) as exc:
        load_list(bad, sha=CLEAN_SHA, fingerprint=config_fingerprint(config))
    assert "was written for code" in str(exc.value)
    bad = _list_file(tmp_path, root, config, [entry], fp="deadbeef")
    with pytest.raises(LlamaError):
        load_list(bad, sha=CLEAN_SHA, fingerprint=config_fingerprint(config))


def test_rerun_of_the_same_list_skips_finished_shows_but_not_failed_ones(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    cfg = _cli(root)
    lst = _list_file(tmp_path, root, config, [entry])
    calls = _stub_package(monkeypatch, fail_first=True)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r1 = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert "FAILED gratefuldead-1973-06-10" in r1.output
    progress = read_progress(batch_dir(root, lst))
    assert progress[HELD]["retryable"] is True
    r2 = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert "reapplied: gratefuldead-1973-06-10 -> cleared" in r2.output
    r3 = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert "gratefuldead-1973-06-10" not in r3.output.replace(str(root), "")   # finished: skipped silently
    assert len(calls) == 2


def test_batch_stops_after_three_consecutive_llm_failures(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    from herder import HerderError
    monkeypatch.setattr("herder.tasks._sleep", lambda s: None)    # _with_transport_retry's backoff
    root, config, ledger, entry, shows = _env(tmp_path)
    # three held rows: clone the held show under three slugs
    import shutil
    for i in (2, 3, 4):
        shutil.copytree(entry.ws.dir, root / "shows" / f"held-{i}")
    for d in (root / "shows").glob("held-*"):
        (d / "briefing.json").unlink()
    entry.ws.briefing_json.unlink()
    from llama.catalog import iter_shows
    held = [e for e in iter_shows(root, ledger) if e.state == "held"]
    assert len(held) == 4
    lst = _list_file(tmp_path, root, config, held)
    cfg = _cli(root)
    monkeypatch.setattr(cli, "make_providers",
                        lambda config: {"brief": FakeProvider([HerderError("boom")] * 12)})   # run_json_task retries
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert r.output.count("FAILED") == STOP_AFTER_LLM_FAILURES
    assert "stopping after 3 consecutive LLM failures" in r.output
    assert r.exit_code == 1


def test_a_success_resets_the_consecutive_llm_failure_count(tmp_path, monkeypatch):
    # Mutant (a): `consecutive` not reset on success would stop at the 4th row.
    from conftest import cli_invoke
    import llama.cli as cli
    from herder import HerderError
    root, config, ledger, entry, _ = _env(tmp_path)
    rows = _clones(root, entry, 5)
    lst = _list_file(tmp_path, root, config, rows)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    script = {"held-2": "fail", "held-3": "fail", "held-4": "ok", "held-5": "fail", "held-6": "fail"}
    def fake(config, ia, ledger, entry, **kw):
        if script[entry.slug] == "fail":
            raise HerderError("boom")
        return ReapplyOutcome(slug=entry.slug, outcome="cleared", briefing="fresh",
                              flags=[], delivered=False, written=[])
    monkeypatch.setattr(reapply_mod, "reapply_show", fake)
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert r.output.count("FAILED") == 4 and "stopping after" not in r.output
    assert "reapplied: held-4 -> cleared" in r.output
    progress = read_progress(batch_dir(root, lst))
    assert {s: p["retryable"] for s, p in progress.items()} == {
        "held-2": True, "held-3": True, "held-4": False, "held-5": True, "held-6": True}


def test_missing_show_is_skipped_and_not_finished(tmp_path, monkeypatch):
    # Review Focus 4.
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    data = json.loads(lst.read_text()); data["rows"][0]["slug"] = "gone-1999-01-01"; lst.write_text(json.dumps(data))
    cfg = _cli(root)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert r.exit_code == 0 and "missing: gone-1999-01-01" in r.output
    assert read_progress(batch_dir(root, lst))["gone-1999-01-01"]["retryable"] is True


def test_a_pause_verdict_stops_the_batch_at_the_show_boundary(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    from llama.pacing import PauseUntil
    from datetime import datetime, timezone
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    cfg = _cli(root)
    calls = _stub_package(monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    monkeypatch.setattr(cli, "decide", lambda *a, **k: PauseUntil(datetime.now(timezone.utc), "five_hour", "5h window at 95%"))
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert r.exit_code == 0 and "paused: 5h window at 95%" in r.output
    assert f"resume with: llama reapply --from-list {lst}" in r.output
    assert calls == [] and read_progress(batch_dir(root, lst)) == {}


def test_a_refusal_mid_show_leaves_it_uncommitted_and_the_list_resumable(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    from herder.limits import RateLimited
    root, config, ledger, entry, _ = _env(tmp_path)
    entry.ws.briefing_json.unlink()
    lst = _list_file(tmp_path, root, config, [entry])
    cfg = _cli(root)
    monkeypatch.setattr(cli, "make_providers", lambda config: {"brief": FakeProvider([RateLimited("limit")])})
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst))
    assert r.exit_code == 0 and "paused: limit" in r.output and "resume with: llama reapply --from-list" in r.output
    assert read_model(entry.ws.show, Show).needs_review is True
    assert read_progress(batch_dir(root, lst)) == {}


def test_dry_run_prints_the_cost_summary_and_creates_no_batch(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    cfg = _cli(root)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r = cli_invoke(cfg, "reapply", "--from-list", str(lst), "--dry-run")
    assert r.exit_code == 0
    assert "would: gratefuldead-1973-06-10 -> cleared" in r.output
    assert "summary: 1 rows, 0 already finished, 0 fresh briefs, 1 downloads (~175 MB each, ~0.2 GB)" in r.output
    assert not (root / "reapply").exists()


def test_names_and_from_list_are_exclusive(tmp_path):
    from conftest import cli_invoke
    root, config, ledger, entry, _ = _env(tmp_path)
    r = cli_invoke(_cli(root), "reapply", HELD, "--from-list", str(tmp_path / "x.json"))
    assert r.exit_code != 0


def test_one_malformed_overrides_fails_its_row_and_the_batch_continues(tmp_path, monkeypatch):
    # M3: entries are built per row, never via catalog.iter_shows, which reads
    # every show's overrides.json and would abort the whole batch on this one.
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    (bad,) = _clones(root, entry, 1)
    bad.ws.overrides.write_text("[1, 2")
    lst = _list_file(tmp_path, root, config, [bad, entry])     # digests taken after the damage
    calls = _stub_package(monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert "FAILED held-2:" in r.output
    assert f"reapplied: {HELD} -> cleared" in r.output and len(calls) == 1
    assert r.exit_code == 1 and "Traceback" not in r.output
    progress = read_progress(batch_dir(root, lst))
    assert progress["held-2"]["retryable"] is True and progress[HELD]["retryable"] is False


def test_a_corrupt_show_json_fails_its_row_and_does_not_count_as_an_llm_failure(tmp_path, monkeypatch):
    # Task 19 review minor 4: a pydantic ValidationError on one row is a
    # per-row FAILED recorded retryable, never a traceback that aborts the batch.
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    bad = _clones(root, entry, 3)
    for c in bad:
        c.ws.show.write_text('{"artist": 1}')
    lst = _list_file(tmp_path, root, config, [*bad, entry])
    calls = _stub_package(monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert r.output.count("FAILED held-") == 3 and "stopping after" not in r.output
    assert f"reapplied: {HELD} -> cleared" in r.output and len(calls) == 1
    progress = read_progress(batch_dir(root, lst))
    assert all(progress[c.slug]["retryable"] is True for c in bad)


def test_the_reapply_command_switches_on_llm_failure_capture(tmp_path, monkeypatch):
    # Task 19 review C2: a failed `claude -p` during the apply is captured whole, as in `_execute`.
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    seen = []
    monkeypatch.setattr(cli, "set_capture_dir", lambda p: seen.append(p))
    lst = _list_file(tmp_path, root, config, [entry])
    assert cli_invoke(_cli(root), "reapply", "--from-list", str(lst), "--dry-run").exit_code == 0
    assert cli_invoke(_cli(root), "reapply", "--dry-run", HELD).exit_code == 0
    assert seen == []                                     # a dry run makes no LLM call
    assert cli_invoke(_cli(root), "reapply", "--from-list", str(lst)).exit_code == 0
    assert seen == [root / "llm-failures"]
    assert cli_invoke(_cli(root), "reapply", HELD).exit_code == 0
    assert seen == [root / "llm-failures"] * 2


def test_the_show_lock_is_held_when_the_row_digests_are_checked(tmp_path, monkeypatch):
    # Task 19 review mutant (h): the show.json re-read and the digest skip
    # must run under the per-show lock, or a concurrent `fix` slips between.
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    row = {"slug": HELD, "digests": input_digests(entry.ws)}
    real = reapply_mod.input_digests
    seen = []
    def spy(ws):
        with pytest.raises(Locked):
            with file_lock(ws.lock, blocking=False):
                pass
        seen.append(True)
        return real(ws)
    monkeypatch.setattr(reapply_mod, "input_digests", spy)
    assert _run(config, ledger, entry, row=row).outcome == "cleared"
    assert seen == [True]


def test_record_progress_survives_a_cut_short_line(tmp_path):
    from llama.reapply import record_progress
    batch = tmp_path / "b"
    batch.mkdir()
    record_progress(batch, "a", "cleared", retryable=False)
    with open(batch / "progress.jsonl", "a") as f:
        f.write('{"slug": "b", "outc')                 # a crash mid-append
    record_progress(batch, "c", "held", retryable=False)
    progress = read_progress(batch)
    assert set(progress) == {"a", "c"} and progress["c"]["outcome"] == "held"


def test_the_gate_reads_the_meter_around_each_show_and_never_records_pacing_state(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    from datetime import datetime, timezone
    from herder.usage import Meter, UsageReading
    from llama.pacing import Proceed
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    _stub_package(monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    seq = [40, 42]
    reset = datetime(2030, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(cli, "read_usage", lambda *a, **k: UsageReading(
        five_hour=Meter(seq.pop(0), reset), seven_day=Meter(7, reset)))
    gated = []
    monkeypatch.setattr(cli, "decide", lambda now, reading, progress, pace:
                        gated.append(reading.five_hour.percent) or Proceed())
    def no_record(*a, **k):
        raise AssertionError("reapply must not fold a show into the learned per-show cost")
    monkeypatch.setattr(cli.pacing_state, "record", no_record)
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert r.exit_code == 0, r.output
    assert gated == [40] and seq == []
    assert f"reapplied: {HELD} -> cleared\n  meter: 5h 40% -> 42%" in r.output


def test_a_dirty_code_identity_is_refused_on_either_side(tmp_path):
    # Review Important 1: `<sha>-dirty` is shared by every uncommitted tree at
    # one HEAD, so string equality would accept another tree's predictions.
    root, config, ledger, entry, _ = _env(tmp_path)
    fp = config_fingerprint(config)
    dirty = CLEAN_SHA + "-dirty"
    lst = _list_file(tmp_path, root, config, [entry], sha=dirty)
    for running in (dirty, CLEAN_SHA):          # list dirty: refused even by the "same" dirty identity
        with pytest.raises(LlamaError) as exc:
            load_list(lst, sha=running, fingerprint=fp)
        assert "commit first" in str(exc.value)
    clean = _list_file(tmp_path, root, config, [entry])
    with pytest.raises(LlamaError) as exc:      # running dirty: refused
        load_list(clean, sha=dirty, fingerprint=fp)
    assert "commit first" in str(exc.value)
    assert load_list(clean, sha=CLEAN_SHA, fingerprint=fp)["rows"][0]["slug"] == HELD


def test_the_cli_refuses_a_list_when_the_running_tree_is_dirty(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    monkeypatch.setattr("llama.replay.code_identity", lambda: CLEAN_SHA + "-dirty")
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert r.exit_code == 1 and "commit first" in r.output
    assert not (root / "reapply").exists()


def _scripted(monkeypatch, script):
    """reapply_show replaced by a per-slug script: an exception instance is
    raised, a (outcome, briefing) pair is returned."""
    def fake(config, ia, ledger, entry, **kw):
        step = script[entry.slug]
        if isinstance(step, BaseException):
            raise step
        outcome, briefing = step
        return ReapplyOutcome(slug=entry.slug, outcome=outcome, briefing=briefing,
                              flags=[], delivered=False, written=[])
    monkeypatch.setattr(reapply_mod, "reapply_show", fake)


def test_any_other_exception_fails_only_its_row(tmp_path, monkeypatch):
    # Review minor 1: a last-resort arm; it is not an LLM failure either.
    from conftest import cli_invoke
    import llama.cli as cli
    from herder import HerderError
    root, config, ledger, entry, _ = _env(tmp_path)
    rows = _clones(root, entry, 4)
    lst = _list_file(tmp_path, root, config, rows)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    _scripted(monkeypatch, {"held-2": HerderError("boom"), "held-3": RuntimeError("mutagen says no"),
                            "held-4": HerderError("boom"), "held-5": ("cleared", "reuse")})
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert "FAILED held-3: RuntimeError: mutagen says no" in r.output and "Traceback" not in r.output
    assert "stopping after" not in r.output and "reapplied: held-5 -> cleared" in r.output
    assert r.exit_code == 1
    progress = read_progress(batch_dir(root, lst))
    assert progress["held-3"]["retryable"] is True and progress["held-5"]["retryable"] is False


def test_rows_that_made_no_llm_call_do_not_reset_the_failure_count(tmp_path, monkeypatch):
    # Orchestrator ruling: only an applied fresh brief resets the counter.
    from conftest import cli_invoke
    import llama.cli as cli
    from herder import HerderError
    root, config, ledger, entry, _ = _env(tmp_path)
    rows = _clones(root, entry, 6)
    lst = _list_file(tmp_path, root, config, rows)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    _scripted(monkeypatch, {"held-2": HerderError("boom"), "held-3": ("cleared", "reuse"),
                            "held-4": HerderError("boom"), "held-5": ("needs-llm", "fresh"),
                            "held-6": HerderError("boom"), "held-7": ("cleared", "fresh")})
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert r.output.count("FAILED") == 3 and "stopping after 3 consecutive LLM failures" in r.output
    assert "held-7" not in r.output.replace(str(root), "") and r.exit_code == 1


def test_a_pause_after_a_failed_row_exits_1(tmp_path, monkeypatch):
    # Review minor 3: a script checking $? must see the earlier failure.
    from conftest import cli_invoke
    import llama.cli as cli
    from herder.limits import RateLimited
    from llama.pacing import PauseUntil, Proceed
    from datetime import datetime, timezone
    root, config, ledger, entry, _ = _env(tmp_path)
    rows = _clones(root, entry, 2)
    lst = _list_file(tmp_path, root, config, rows)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    _scripted(monkeypatch, {"held-2": LlamaError("bad"), "held-3": RateLimited("limit")})
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert "paused: limit" in r.output and r.exit_code == 1
    # the pacing pause too: held-2 fails again, then the gate pauses before held-3
    verdicts = iter([Proceed(), PauseUntil(datetime.now(timezone.utc), "five_hour", "5h at 95%")])
    monkeypatch.setattr(cli, "decide", lambda *a, **k: next(verdicts))
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert "FAILED held-2: bad" in r.output and "paused: 5h at 95%" in r.output and r.exit_code == 1


def test_dry_run_over_an_existing_batch_counts_and_skips_finished_rows(tmp_path, monkeypatch):
    # D2.
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    _stub_package(monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    assert cli_invoke(_cli(root), "reapply", "--from-list", str(lst)).exit_code == 0
    before = (batch_dir(root, lst) / "progress.jsonl").read_text()
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst), "--dry-run")
    assert r.exit_code == 0 and "would:" not in r.output
    assert ("summary: 1 rows, 1 already finished, 0 fresh briefs, 0 downloads "
            "(~175 MB each, ~0.0 GB)") in r.output
    assert (batch_dir(root, lst) / "progress.jsonl").read_text() == before


def test_dry_run_counts_fresh_briefs_and_downloads_only_for_rows_it_would_apply(tmp_path, monkeypatch):
    # D1: a held or needs-llm prediction packages nothing and briefs nothing.
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    rows = _clones(root, entry, 4)
    lst = _list_file(tmp_path, root, config, rows)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    _scripted(monkeypatch, {"held-2": ("dry-run: cleared", "fresh"), "held-3": ("dry-run: held", "fresh"),
                            "held-4": ("needs-llm", "fresh"), "held-5": ("dry-run: needs-brief", "fresh")})
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst), "--dry-run")
    assert r.exit_code == 0, r.output
    for line in ("would: held-2 -> cleared", "would: held-3 -> held", "would: held-4 -> needs-llm",
                 "would: held-5 -> needs-brief"):
        assert line in r.output
    assert ("summary: 4 rows, 0 already finished, 2 fresh briefs, 2 downloads "
            "(~175 MB each, ~0.3 GB)") in r.output


# --- fw2: structure-changed needs a deliberate allow; failure type names; purged-audio downloads ---

def _force_classify(monkeypatch, outcome, would_be="clears"):
    real = reapply_mod.classify
    def fake(legs, state):
        out, wb = real(legs, state)
        return (outcome, would_be) if out in ("clears", "needs-brief") else (out, wb)
    monkeypatch.setattr(reapply_mod, "classify", fake)


def test_structure_changed_is_skipped_unless_allowed_and_writes_nothing(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path)
    calls = _stub_package(monkeypatch)
    _stale(entry.ws)
    before = _snapshot(entry.ws)
    _force_classify(monkeypatch, "structure-changed")
    out = _run(config, ledger, entry)
    assert out.outcome == "skipped: structure changed" and out.written == []
    assert _snapshot(entry.ws) == before and calls == []
    ok = reapply_show(config, object(), ledger, entry, providers=_providers(), row=None,
                      dry_run=False, echo=lambda s: None, allow_structure_change=True)
    assert ok.outcome == "cleared" and calls


def test_cli_names_form_structure_changed_needs_the_flag(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    _force_classify(monkeypatch, "structure-changed")
    before = _snapshot(entry.ws)
    r = cli_invoke(_cli(root), "reapply", HELD)
    assert r.exit_code == 0, r.output
    assert (f"reapplied: {HELD} -> skipped: structure changed "
            "(re-run with --allow-structure-change after checking)") in r.output
    assert _snapshot(entry.ws) == before
    r = cli_invoke(_cli(root), "reapply", HELD, "--allow-structure-change")
    assert r.exit_code == 0 and f"reapplied: {HELD} -> cleared" in r.output


def test_list_form_skips_structure_changed_rows_unless_the_flag_is_given(tmp_path, monkeypatch):
    # Rows are in the harness's real shape (scripts/replay_holds.py `_list_row`:
    # slug/outcome/briefing/digests; a structure_changed_list row's outcome is the
    # would-be `clears`/`needs-brief`, never `structure-changed`), as `_list_file` writes them.
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    rows = _clones(root, entry, 1)
    lst = _list_file(tmp_path, root, config, rows)
    _stub_package(monkeypatch)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    _force_classify(monkeypatch, "structure-changed")
    before = _snapshot(rows[0].ws)
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert r.exit_code == 0, r.output
    assert ("reapplied: held-2 -> skipped: structure changed "
            "(re-run with --allow-structure-change after checking)") in r.output
    assert _snapshot(rows[0].ws) == before
    assert read_progress(batch_dir(root, lst))["held-2"]["retryable"] is True
    r2 = cli_invoke(_cli(root), "reapply", "--from-list", str(lst), "--allow-structure-change")
    assert r2.exit_code == 0 and "reapplied: held-2 -> cleared" in r2.output
    assert read_progress(batch_dir(root, lst))["held-2"]["retryable"] is False


def test_catch_all_failure_line_names_the_exception_type(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(reapply_mod, "compute_legs", boom)
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst))
    assert f"FAILED {HELD}: RuntimeError: boom" in r.output and r.exit_code == 1
    assert read_progress(batch_dir(root, lst))[HELD]["outcome"] == "failed: RuntimeError: boom"


def test_dry_run_counts_a_purged_delivered_show_as_a_download(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    write_artifact(entry.ws.package_dir / "manifest.json",
                   {"schema_version": 3, "tracks": [{"filename": "a.mp3"}, {"filename": "b.mp3"}]})
    audio = entry.ws.package_dir / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    (audio / "a.mp3").write_bytes(b"x")                    # one present, one missing
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst), "--dry-run")
    assert "1 downloads" in r.output, r.output
    (audio / "b.mp3").write_bytes(b"x")
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst), "--dry-run")
    assert "0 downloads" in r.output, r.output


def test_dry_run_of_a_structure_changed_row_is_skipped_unless_allowed(tmp_path, monkeypatch):
    # Without the flag the dry run predicts the skip and counts no brief/download;
    # with it the show is predicted, and counted, as `structure-changed`.
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    lst = _list_file(tmp_path, root, config, [entry])
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    _force_classify(monkeypatch, "structure-changed")
    write_artifact(entry.ws.package_dir / "manifest.json",
                   {"schema_version": 3, "tracks": [{"filename": "a.mp3"}]})   # audio missing
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst), "--dry-run")
    assert f"would: {HELD} -> skipped: structure changed" in r.output
    assert "0 downloads" in r.output, r.output
    r = cli_invoke(_cli(root), "reapply", "--from-list", str(lst), "--dry-run",
                   "--allow-structure-change")
    assert f"would: {HELD} -> structure-changed" in r.output
    assert "1 downloads" in r.output, r.output


def test_names_form_dry_run_of_a_structure_changed_show_prints_the_skip(tmp_path, monkeypatch):
    from conftest import cli_invoke
    import llama.cli as cli
    root, config, ledger, entry, _ = _env(tmp_path)
    monkeypatch.setattr(cli, "make_providers", lambda config: _providers())
    _force_classify(monkeypatch, "structure-changed")
    r = cli_invoke(_cli(root), "reapply", "--dry-run", HELD)
    assert r.exit_code == 0, r.output
    assert f"reapplied: {HELD} -> dry-run: skipped: structure changed" in r.output
    r = cli_invoke(_cli(root), "reapply", "--dry-run", HELD, "--allow-structure-change")
    assert f"reapplied: {HELD} -> dry-run: structure-changed" in r.output


def test_needs_audio_download_counts_an_unreadable_or_malformed_manifest_as_a_download(tmp_path):
    from llama.catalog import needs_audio_download
    from llama.workspace import ShowWorkspace
    ws = ShowWorkspace(tmp_path / "s")
    ws.package_dir.mkdir(parents=True)
    m = ws.package_dir / "manifest.json"
    m.write_text("{not json")
    assert needs_audio_download(ws) is True
    m.write_text('{"tracks": [{"title": "no filename"}]}')
    assert needs_audio_download(ws) is True
    m.write_text('{"tracks": "nope"}')
    assert needs_audio_download(ws) is True
    m.write_text('{"tracks": []}')
    assert needs_audio_download(ws) is False


# --- fw3: a held outcome drops a briefing written against older titles ---

def _retitle_stored(ws):
    """Make the stored show differ from the replay in a shipped field (a title)."""
    show = read_model(ws.show, Show)
    tracks = list(show.tracks)
    tracks[0] = tracks[0].model_copy(update={"title": "Stale Old Title"})
    write_artifact(ws.show, show.model_copy(update={"tracks": tracks}))


def test_a_held_outcome_with_changed_titles_drops_the_stale_briefing(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path, held_for_real=True)
    _stub_package(monkeypatch)
    write_artifact(entry.ws.package_dir / "manifest.json", {"schema_version": 3, "tracks": []})
    _retitle_stored(entry.ws)
    write_artifact(entry.ws.briefing_md, "# stale briefing\n")
    assert entry.ws.briefing_json.exists() and entry.ws.briefing_md.exists()
    out = _run(config, ledger, entry)
    assert out.outcome == "held" and out.briefing == "none"
    assert not entry.ws.briefing_json.exists() and not entry.ws.briefing_md.exists()
    assert not (entry.ws.package_dir / "manifest.json").exists()   # drop_stage_artifacts("brief") also drops it
    assert out.written == ["vetting.json", "notes.json", "drop:brief", "show.json"]
    assert read_model(entry.ws.show, Show).tracks[0].title != "Stale Old Title"


def test_a_held_outcome_with_only_a_stale_briefing_md_drops_it(tmp_path, monkeypatch):
    # fw3 review M6: no briefing.json, only briefing.md -- the `.md` clause alone
    # triggers the drop.
    root, config, ledger, entry, _ = _env(tmp_path, held_for_real=True)
    _stub_package(monkeypatch)
    _retitle_stored(entry.ws)
    entry.ws.briefing_json.unlink(missing_ok=True)
    write_artifact(entry.ws.briefing_md, "# stale briefing\n")
    out = _run(config, ledger, entry)
    assert out.outcome == "held" and out.briefing == "none"
    assert not entry.ws.briefing_md.exists() and "drop:brief" in out.written


def test_a_held_outcome_with_no_shipped_change_keeps_the_briefing(tmp_path, monkeypatch):
    # case (c): held, nothing shipped moved (a carried package flag)
    root, config, ledger, entry, _ = _env(tmp_path)
    flag = "duration mismatch on 01 - Morning Dew.mp3: file 10s vs metadata 664s"
    show = read_model(entry.ws.show, Show)
    write_artifact(entry.ws.show, show.model_copy(update={"review_flags": show.review_flags + [flag]}))
    write_artifact(entry.ws.briefing_md, "# stored briefing\n")
    _stub_package(monkeypatch)
    out = _run(config, ledger, entry)
    assert out.outcome == "held" and entry.ws.briefing_json.exists() and entry.ws.briefing_md.exists()
    assert "drop:brief" not in out.written


def test_a_held_outcome_with_no_shipped_change_and_no_carried_flag_keeps_the_briefing(tmp_path, monkeypatch):
    root, config, ledger, entry, _ = _env(tmp_path, held_for_real=True)
    write_artifact(entry.ws.briefing_md, "# stored briefing\n")
    _stub_package(monkeypatch)
    out = _run(config, ledger, entry)
    assert out.outcome == "held" and out.briefing == "none"
    assert entry.ws.briefing_json.exists() and entry.ws.briefing_md.exists() and "drop:brief" not in out.written


def test_a_failed_fresh_brief_is_not_dropped_even_when_titles_changed(tmp_path, monkeypatch):
    # case (a): the written briefing IS the new one
    root, config, ledger, entry, _ = _env(tmp_path)
    _retitle_stored(entry.ws)
    entry.ws.briefing_json.unlink()
    _stub_package(monkeypatch)
    bad = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"]}, mentioned_songs=["Nope"]))
    out = _run(config, ledger, entry, _providers(bad, bad))
    assert out.outcome == "held" and out.briefing == "fresh"
    assert entry.ws.briefing_json.exists() and "drop:brief" not in out.written


def test_a_reused_briefing_is_not_dropped(tmp_path, monkeypatch):
    # case (b): `compute_legs` never yields reuse + flags ("[] by construction"),
    # so force the combination on a retitled show: the briefing written is the
    # reused one and must survive the held outcome.
    import dataclasses
    root, config, ledger, entry, _ = _env(tmp_path)
    _retitle_stored(entry.ws)
    stored_briefing = read_model(entry.ws.briefing_json, Briefing)
    real = reapply_mod.compute_legs
    def forced(*a, **k):
        legs = real(*a, **k)
        return dataclasses.replace(legs, brief="reuse", briefing=stored_briefing,
                                   flags=legs.flags + ["forced flag"])
    monkeypatch.setattr(reapply_mod, "compute_legs", forced)
    _stub_package(monkeypatch)
    out = _run(config, ledger, entry)
    assert out.outcome == "held" and out.briefing == "reuse"
    assert entry.ws.briefing_json.exists() and entry.ws.briefing_md.exists()
    assert "drop:brief" not in out.written


def test_a_cleared_outcome_is_not_dropped(tmp_path, monkeypatch):
    # case (d)
    root, config, ledger, entry, _ = _env(tmp_path)
    _stub_package(monkeypatch)
    out = _run(config, ledger, entry)
    assert out.outcome == "cleared" and "drop:brief" not in out.written
    assert entry.ws.briefing_json.exists()


def test_reapply_on_refused_overrides_raises_and_writes_nothing(tmp_path, monkeypatch):   # (pin)
    root, config, ledger, entry, _ = _env(tmp_path)
    write_artifact(entry.ws.overrides, Overrides(set_breaks=[2, 4], encore_after=4))
    before = _snapshot(entry.ws)
    with pytest.raises(LlamaError, match="overrides\\.(encore_after|set_breaks)"):
        _run(config, ledger, entry)
    assert _snapshot(entry.ws) == before


def test_reapply_processes_a_taper_owned_stored_llm_show(tmp_path, monkeypatch):
    # Piece 2 spec section 7: a stored `llm` alignment is no longer needs-LLM when
    # the candidate is taper-owned. Its structure changes (the taper's markers
    # relabel the tape), so it is refused without --allow-structure-change.
    from fixture_library import IDENT
    root, config, ledger, entry, _ = _env(tmp_path)
    cache = root / "cache" / f"md_{IDENT}.json"
    md = json.loads(cache.read_text())
    md["metadata"]["description"] = ("Set 1:\nMorning Dew\nChina Cat Sunflower > I Know You Rider\n\n"
                                     "Set 2:\nDark Star > Eyes of the World\nJohnny B. Goode\n")
    cache.write_text(json.dumps(md))
    show = read_model(entry.ws.show, Show)
    show.structure = show.structure.model_copy(update={"alignment": "llm"})
    write_artifact(entry.ws.show, show)
    calls = _stub_package(monkeypatch)
    _stale(entry.ws)
    before = _snapshot(entry.ws)
    out = _run(config, ledger, entry)
    assert out.outcome == "skipped: structure changed" and out.written == []
    assert _snapshot(entry.ws) == before and calls == []
    ok = json.dumps(dict(context="c", significance="s", per_set={"1": ["a"], "2": ["b"]}))
    done = reapply_show(config, object(), ledger, entry, providers=_providers(ok), row=None,
                        dry_run=False, echo=lambda s: None, allow_structure_change=True)
    assert done.outcome == "cleared" and calls
    final = read_model(entry.ws.show, Show)
    assert final.structure.taper_owned is True and final.structure.alignment != "llm"
