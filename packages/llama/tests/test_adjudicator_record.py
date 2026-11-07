"""The adjudication record and its digest (spec "Adjudication record and loop guard"):
the digest is the one staleness test, over flags, track table, excluded rows, overrides
without overrule timestamps and the identifier; never research or briefing text."""
from __future__ import annotations

import pytest

from llama.adjudicator.record import (RECORD_FILE_VERSION, AdjudicationRecord, is_current,
                                      read_record, show_digest, view_digest, write_outside_unit,
                                      write_record)
from llama.locks import file_lock
from llama.models import Overrides, Overrule, Show, Track
from llama.show_unit import capture_view
from llama.workspace import ShowWorkspace, write_artifact

PID = "GratefulDead/1973-06-10"


def _show(**kw) -> Show:
    base = dict(performance_id=PID, identifier="gd73", artist="Grateful Dead", date="1973-06-10",
                venue="RFK Stadium", needs_review=True, review_flags=["flag one"],
                tracks=[Track(index=1, set="1", title="Bertha", filename="a.mp3",
                              duration_sec=300.0, title_source="tags"),
                        Track(index=2, set="1", title="Jam", filename="b.mp3",
                              duration_sec=30.0, title_source="unresolved", segue=True)],
                excluded_files=[{"filename": "x.mp3", "reasons": ["implausibly short"],
                                 "duration_sec": 4.0}])
    base.update(kw)
    return Show(**base)


def _rule(at: str) -> Overrule:
    return Overrule(identifier="gd73", kind="venue", subject=None, flag="venue mismatch: x",
                    source="adjudicate", at=at)


def _ws(tmp_path, show: Show | None = None, ov: Overrides | None = None) -> ShowWorkspace:
    ws = ShowWorkspace(tmp_path / "shows" / "s")
    ws.dir.mkdir(parents=True, exist_ok=True)
    if show is not None:
        write_artifact(ws.show, show)
    if ov is not None:
        write_artifact(ws.overrides, ov)
    return ws


def _rec(**kw) -> AdjudicationRecord:
    return AdjudicationRecord(**{"at": "t", "model": "fake:m", "outcome": "proposal", **kw})


def test_digest_ignores_overrule_timestamps_research_and_briefing(tmp_path):
    ws = _ws(tmp_path, _show(), Overrides(overrules=[_rule("2026-01-01T00:00:00Z")]))
    d0 = show_digest(ws)
    write_artifact(ws.overrides, Overrides(overrules=[_rule("2026-11-07T09:09:09Z")]))
    write_artifact(ws.research, "# research, rewritten")
    write_artifact(ws.briefing_md, "# a new briefing")
    write_artifact(ws.briefing_json, {"context": "c"})
    assert show_digest(ws) == d0
    # an indent-only rewrite of show.json is the same state
    ws.show.write_text(_show().model_dump_json())
    assert show_digest(ws) == d0


def _t(i, **kw):
    return _show().tracks[i].model_copy(update=kw)


CHANGES = {
    "review_flags": lambda: (_show(review_flags=["flag two"]), None),
    "track filename": lambda: (_show(tracks=[_t(0, filename="z.mp3"), _t(1)]), None),
    "track title": lambda: (_show(tracks=[_t(0, title="Dark Star"), _t(1)]), None),
    "track title_source": lambda: (_show(tracks=[_t(0, title_source="override"), _t(1)]), None),
    "track set": lambda: (_show(tracks=[_t(0, set="2"), _t(1)]), None),
    "track segue": lambda: (_show(tracks=[_t(0), _t(1, segue=False)]), None),
    "track duration": lambda: (_show(tracks=[_t(0, duration_sec=301.0), _t(1)]), None),
    "excluded filename": lambda: (_show(excluded_files=[
        {"filename": "y.mp3", "reasons": ["implausibly short"], "duration_sec": 4.0}]), None),
    "excluded reasons": lambda: (_show(excluded_files=[
        {"filename": "x.mp3", "reasons": ["operator-excluded"], "duration_sec": 4.0}]), None),
    "overrides venue": lambda: (_show(), Overrides(venue="Kezar")),
    "overrides overrule flag": lambda: (_show(), Overrides(overrules=[
        _rule("2026-01-01T00:00:00Z").model_copy(update={"flag": "venue mismatch: y"})])),
    "identifier": lambda: (_show(identifier="gd73-sib"), None),
}


@pytest.mark.parametrize("case", list(CHANGES))
def test_digest_changes_on_flags_tracks_excluded_overrides_identifier(tmp_path, case):
    ws = _ws(tmp_path, _show(), Overrides(overrules=[_rule("2026-01-01T00:00:00Z")]))
    d0 = show_digest(ws)
    show, ov = CHANGES[case]()
    write_artifact(ws.show, show)
    if ov is not None:
        write_artifact(ws.overrides, ov)
    assert show_digest(ws) != d0, case


def test_digest_of_a_missing_show_json_is_absent(tmp_path):
    ws = _ws(tmp_path)
    assert show_digest(ws) == "absent"
    write_artifact(ws.show, _show())
    assert show_digest(ws) != "absent"


def test_show_digest_equals_view_digest_of_captured_view(tmp_path):
    ws = _ws(tmp_path, _show(), Overrides(venue="RFK"))
    assert show_digest(ws) == view_digest(capture_view(ws))
    assert len(show_digest(ws)) == 64


def test_record_round_trip_and_unreadable_reads_none(tmp_path):
    ws = _ws(tmp_path, _show())
    assert read_record(ws) is None
    rec = _rec(digest="d", malformed=["m"], held_proposal={"flags": [], "edits": []})
    write_record(ws, rec)
    assert read_record(ws) == rec and rec.version == RECORD_FILE_VERSION == 1
    ws.adjudication.write_text("{not json")
    assert read_record(ws) is None
    ws.adjudication.write_text('{"outcome": "nonsense"}')
    assert read_record(ws) is None
    ws.adjudication.write_text('{"outcome": "proposal", "future_key": 1}')   # permissive
    assert read_record(ws).outcome == "proposal"


def test_is_current_false_for_dry_run_unreadable_and_changed(tmp_path):
    ws = _ws(tmp_path, _show())
    assert not is_current(ws)                                       # no record
    write_record(ws, _rec(digest=show_digest(ws)))
    assert is_current(ws)
    write_record(ws, _rec(digest=show_digest(ws), dry_run=True, outcome="dry-run"))
    assert not is_current(ws)                                       # a dry run never is
    ws.adjudication.write_text("garbage")
    assert not is_current(ws)                                       # unreadable
    write_record(ws, _rec(digest=show_digest(ws)))
    write_artifact(ws.overrides, Overrides(venue="Kezar"))
    assert not is_current(ws)                                       # changed since


def test_records_go_to_an_explicit_path_when_given(tmp_path):
    ws = _ws(tmp_path, _show())
    sink = tmp_path / "pilot" / "s.json"
    write_record(ws, _rec(digest=show_digest(ws)), path=sink)
    assert sink.exists() and not ws.adjudication.exists()
    assert read_record(ws, path=sink).digest == show_digest(ws)
    assert is_current(ws, path=sink) and not is_current(ws)


def test_write_outside_unit_refuses_when_view_changed(tmp_path):
    ws = _ws(tmp_path, _show())
    expect = capture_view(ws)
    write_artifact(ws.overrides, Overrides(venue="Kezar"))
    assert write_outside_unit(ws, _rec(), expect=expect) is False
    assert not ws.adjudication.exists()
    expect = capture_view(ws)
    assert write_outside_unit(ws, _rec(), expect=expect) is True
    rec = read_record(ws)
    assert rec.digest == view_digest(expect) == show_digest(ws)     # stamped
    assert is_current(ws)


def test_write_outside_unit_takes_the_show_lock(tmp_path, monkeypatch):
    import llama.adjudicator.record as record
    from llama.locks import Locked
    ws = _ws(tmp_path, _show())
    expect = capture_view(ws)
    seen = []
    real = record.atomic_write_bytes

    def probe(path, data):
        try:
            with file_lock(ws.lock, blocking=False):
                seen.append("free")
        except Locked:
            seen.append("held")
        return real(path, data)
    monkeypatch.setattr(record, "atomic_write_bytes", probe)
    assert write_outside_unit(ws, _rec(), expect=expect)
    assert seen == ["held"]
