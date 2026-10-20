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
from llama.models import Briefing, LedgerEntry, Show, ShowNotes, VettingResult
from llama.reapply import ReapplyOutcome, reapply_show
from llama.replay import input_digests
from llama.stages.brief import normalize_briefing, render_briefing_md
from llama.workspace import read_model, write_artifact

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
