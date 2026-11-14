"""Staleness against gather's post-drop list (spec
docs/superpowers/specs/2026-11-13-junk-tag-drop-design.md, "Placement in gather" last
bullet and "What a drop looks like"): `staleness.expected_track_files` is gather's final
kept list minus the files `show.json` records as dropped with reason `junk title` (and
not re-admitted by `overrides.include`); `stale_message` and the `--suggest-titles`
comparison both compare `show.tracks` with it. Driven through the CLI over the packaged
gd73 fixture, whose d1t02 (China Cat Sunflower, 452 s) is retagged `Tuning`."""
import json

import llama.cli as cli
import test_pipeline
from conftest import cli_invoke
from helpers import packaged_gd73
from llama.catalog import resolve_show
from llama.ledger import Ledger
from llama.models import Show
from llama import staleness
from llama.staleness import stale_message
from llama.workspace import read_model, read_overrides

SLUG = "gratefuldead-1973-06-10"
TUNED = "gd73-06-10d1t02.mp3"
SIX = ["gd73-06-10d1t01.mp3", TUNED, "gd73-06-10d1t03.mp3",
       "gd73-06-10d2t01.mp3", "gd73-06-10d2t02.mp3", "gd73-06-10d3t01.mp3"]
HOLD_PREFIX = "junk-title drop held for review: "


def _tuning_ia(length: str):
    """FakeIA whose d1t02 VBR MP3 is tagged `Tuning` with `length` ("3:00" drops
    unheld; "8:00" meets 2 of 3 breaker tests, > 360 s and > 5% of the show, so the
    drop holds)."""
    class TuningIA(test_pipeline.FakeIA):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            for f in self.fixture["files"]:
                if f["name"] == TUNED:
                    f["title"], f["length"] = "Tuning", length
    return TuningIA


def _dropped(tmp_path, monkeypatch, length: str = "3:00"):
    """The packaged gd73, re-gathered through `llama redo --from gather` after its
    d1t02 tag became `Tuning`. Returns (config path, ShowWorkspace, IA class)."""
    cfg, ws = packaged_gd73(tmp_path, monkeypatch)
    ia = _tuning_ia(length)
    monkeypatch.setattr(cli, "IAClient", ia)
    r = cli_invoke(cfg, "redo", "gratefuldead", "--from", "gather")
    assert r.exit_code == 0, r.output
    show = read_model(ws.show, Show)
    assert TUNED not in [t.filename for t in show.tracks]
    assert [e for e in show.excluded_files if e["filename"] == TUNED][0]["reasons"] == [
        "junk title"]
    return cfg, ws, ia


def _stale(cfg, ws, ia):
    return stale_message(ia(), cli.load_config(cfg), ws, SLUG)


def test_expected_track_files_unit():
    show = Show(performance_id="p", identifier="i", artist="a", date="1973-06-10",
                tracks=[], excluded_files=[
                    {"filename": "b.mp3", "reasons": ["junk title"]},
                    {"filename": "c.mp3", "reasons": ["implausibly short"]},
                    {"filename": "d.mp3", "reasons": ["junk title"]},
                    {"filename": "e.mp3"}])
    kept = ["a.mp3", "b.mp3", "c.mp3", "d.mp3", "e.mp3"]
    assert staleness.expected_track_files(kept, show, []) == ["a.mp3", "c.mp3", "e.mp3"]
    # A file re-admitted by overrides.include is expected back on the track list.
    assert staleness.expected_track_files(kept, show, ["d.mp3"]) == ["a.mp3", "c.mp3", "d.mp3", "e.mp3"]


def test_show_the_rule_changed_is_not_stale(tmp_path, monkeypatch):
    cfg, ws, ia = _dropped(tmp_path, monkeypatch)
    assert _stale(cfg, ws, ia) is None
    # And a positional edit goes through (the staleness check runs before it).
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-title", "1=Dew", "--no-run")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).titles == {SIX[0]: "Dew"}


def test_genuinely_stale_show_still_refused(tmp_path, monkeypatch):
    cfg, ws, ia = _dropped(tmp_path, monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "1", "--no-run")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).exclude == [SIX[0]]
    msg = _stale(cfg, ws, ia)
    assert msg == (f"{SLUG}: show.json's track list is not what gather keeps now; re-gather "
                   f"under the new rule first (llama redo {SLUG} --from gather)")
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-title", "2=X", "--no-run")
    assert r.exit_code == 1, r.output
    assert msg in r.output


def test_suggest_titles_not_declined_on_a_dropped_show(tmp_path, monkeypatch):
    cfg, ws, ia = _dropped(tmp_path, monkeypatch)
    entry = resolve_show(tmp_path, Ledger(tmp_path / "ledger.jsonl"), SLUG)
    prop, _ = cli._propose_titles_for_show(ia(), cli.load_config(cfg), entry,
                                           read_model(ws.show, Show))
    assert "stale" not in (prop.reason or ""), prop.reason
    r = cli_invoke(cfg, "fix", "gratefuldead", "--suggest-titles", input="n\n")
    assert "stale" not in r.output and "not what gather keeps now" not in r.output, r.output


def test_regather_is_idempotent_and_not_stale(tmp_path, monkeypatch):
    cfg, ws, ia = _dropped(tmp_path, monkeypatch)
    first = ws.show.read_bytes()
    r = cli_invoke(cfg, "redo", "gratefuldead", "--from", "gather")
    assert r.exit_code == 0, r.output
    assert ws.show.read_bytes() == first
    assert _stale(cfg, ws, ia) is None


def test_fix_include_restores_a_dropped_track_and_clears_its_hold(tmp_path, monkeypatch):
    cfg, ws, ia = _dropped(tmp_path, monkeypatch, length="8:00")
    held = read_model(ws.show, Show)
    assert held.needs_review
    assert [f for f in held.review_flags if f.startswith(HOLD_PREFIX)] == [
        f for f in held.review_flags if f.startswith(HOLD_PREFIX) and f.endswith(TUNED)]
    assert any(f.startswith(HOLD_PREFIX) for f in held.review_flags)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", TUNED)
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == [TUNED]
    show = read_model(ws.show, Show)
    assert [t.filename for t in show.tracks] == SIX
    assert show.tracks[1].title == "Tuning" and show.tracks[1].included
    assert not [e for e in show.excluded_files if "junk title" in e.get("reasons", [])]
    assert not any(f.startswith(HOLD_PREFIX) for f in show.review_flags)
    assert show.needs_review is False, show.review_flags
    assert _stale(cfg, ws, ia) is None


def test_fix_include_no_run_of_a_dropped_file_is_stale(tmp_path, monkeypatch):
    cfg, ws, ia = _dropped(tmp_path, monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", TUNED, "--no-run")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == [TUNED]
    assert _stale(cfg, ws, ia) is not None


def test_show_tracks_lists_junk_title_reason(tmp_path, monkeypatch):
    cfg, ws, _ = _dropped(tmp_path, monkeypatch)
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert r.exit_code == 0, r.output
    rows = [ln for ln in r.output.splitlines() if ln.lstrip().startswith("x")]
    junk = [ln for ln in rows if TUNED in ln]
    assert len(junk) == 1 and junk[0].rstrip().endswith(f"{TUNED}  junk title"), r.output
    assert "3:00" in junk[0]
    short = [ln for ln in rows if "implausibly short" in ln]
    assert short and all("junk title" not in ln for ln in short), r.output
    assert json.loads(ws.show.read_text())["excluded_files"][-1]["filename"] == TUNED
