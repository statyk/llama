"""Junk-title drop wired into `compute_gather` (spec
docs/superpowers/specs/2026-11-13-junk-tag-drop-design.md, "What a drop looks like" and
"Placement in gather"). Built on the canonical gd73-06-10 fixture with its tags edited.

The fixture's six kept tracks, in order (0-based position, file, seconds):
0 d1t01 Morning Dew 664 | 1 d1t02 China Cat Sunflower 452 (segue) | 2 d1t03 I Know You
Rider 371 || 3 d2t01 Dark Star 1908 (segue) | 4 d2t02 Eyes of the World 1040 || 5 d3t01
(untagged; Johnny B. Goode from the setlist) 299. Set breaks [3, 5]."""
import json
from pathlib import Path

import pytest

import llama.stages.gather as gather_mod
from llama import junk_titles
from llama.models import Overrides
from llama.stages.gather import compute_gather
from llama.workspace import ShowWorkspace, write_artifact

FIXTURE = Path(__file__).parent / "fixtures" / "gd73_metadata.json"
IDENT = "gd73-06-10.sbd.hollister.174.sbeok.shnf"
F = {k: f"gd73-06-10{k}.mp3" for k in ("d1t01", "d1t02", "d1t03", "d2t01", "d2t02", "d3t01")}
SPAM_ROW = {"filename": "FOLLOW-ME @BYPIKENO.mp3",
            "reasons": ["filename convention mismatch", "implausibly short"],
            "duration_sec": 29.0}


class StubIA:
    def __init__(self, md):
        self.md = md

    def metadata(self, identifier):
        return self.md


def _candidate():
    from llama.models import Candidate, RecordingSummary
    return Candidate(performance_id="GratefulDead/1973-06-10", collection="GratefulDead",
                     date="1973-06-10", venue="RFK Stadium", city="Washington, DC",
                     recordings=[RecordingSummary(identifier=IDENT)])


def _md(changes: dict[str, tuple[str | None, str | None]] | None = None) -> dict:
    """The fixture with `{file key: (tag title or None, length or None)}` applied to its
    VBR MP3 derivatives (None leaves the field as captured)."""
    base = json.loads(FIXTURE.read_text())
    md = {"metadata": dict(base["metadata"]), "files": [dict(f) for f in base["files"]]}
    by_name = {F[k]: v for k, v in (changes or {}).items()}
    for f in md["files"]:
        if f["name"] in by_name:
            title, length = by_name[f["name"]]
            if title is not None:
                f["title"] = title
            if length is not None:
                f["length"] = length
    return md


def _gather(tmp_path, md, overrides: Overrides | None = None):
    sws = ShowWorkspace(tmp_path / "show")
    if overrides is not None:
        write_artifact(sws.overrides, overrides)
    return compute_gather(sws, StubIA(md), None, _candidate(), IDENT)


def test_tuning_track_drops_and_is_recorded(tmp_path):
    res = _gather(tmp_path, _md({"d1t02": ("Tuning", "3:00")}))
    show = res.show
    assert F["d1t02"] not in [t.filename for t in show.tracks]
    assert [t.index for t in show.tracks] == [1, 2, 3, 4, 5]
    assert [t.filename for t in show.tracks] == [F[k] for k in ("d1t01", "d1t03", "d2t01",
                                                                "d2t02", "d3t01")]
    assert show.excluded_files == [SPAM_ROW, {
        "filename": F["d1t02"], "reasons": ["junk title"], "duration_sec": 180.0,
        "title": "Tuning", "set": "1", "after_track": 1}]
    assert len(res.junk_drops) == 1
    drop = res.junk_drops[0]
    assert (drop.rule, drop.position, drop.after_track, drop.held) == ("A", 1, 1, False)
    assert res.kept_positions == (0, 2, 3, 4, 5)
    assert len(res.title_paths) == 5
    assert show.needs_review is False


def test_no_drop_show_is_unchanged(tmp_path, monkeypatch):
    res = _gather(tmp_path / "a", _md())
    assert res.junk_drops == ()
    assert res.kept_positions is None
    monkeypatch.setattr(junk_titles, "plan_drops", lambda *a, **k: [])
    patched = _gather(tmp_path / "b", _md())
    assert res.show.model_dump() == patched.show.model_dump()
    assert res.notes == patched.notes
    assert res.title_paths == patched.title_paths


def test_no_drop_returns_the_title_paths_and_excluded_rows_untouched(tmp_path, monkeypatch):
    """No drop, no change: with the rule returning nothing the drop block is skipped
    whole, even on a show it would otherwise change."""
    monkeypatch.setattr(junk_titles, "plan_drops", lambda *a, **k: [])
    res = _gather(tmp_path, _md({"d1t02": ("Tuning", "3:00")}))
    assert [t.title for t in res.show.tracks][1] == "Tuning"
    assert res.show.excluded_files == [SPAM_ROW]
    assert res.junk_drops == () and res.kept_positions is None
    assert len(res.title_paths) == 6


def test_segue_into_a_dropped_track_is_lost_unless_arrowed(tmp_path):
    plain = _gather(tmp_path / "a", _md({"d1t03": ("Tuning", "3:00")}))
    cc = next(t for t in plain.show.tracks if t.filename == F["d1t02"])
    assert cc.title == "China Cat Sunflower" and cc.segue is False
    # The other segue (Dark Star -> Eyes) is untouched.
    assert next(t for t in plain.show.tracks if t.filename == F["d2t01"]).segue is True

    arrowed = _gather(tmp_path / "b", _md({"d1t02": ("China Cat Sunflower >", None),
                                          "d1t03": ("Tuning", "3:00")}))
    cc = next(t for t in arrowed.show.tracks if t.filename == F["d1t02"])
    assert cc.title == "China Cat Sunflower >" and cc.segue is True


def test_set_breaks_recomputed_after_drop(tmp_path):
    res = _gather(tmp_path, _md({"d1t02": ("Tuning", "3:00")}))
    assert [t.set for t in res.show.tracks] == ["1", "1", "2", "2", "encore"]
    assert res.show.set_breaks == [2, 4]


def test_set_of_only_dropped_tracks_vanishes(tmp_path):
    """An encore that is one `Crowd` file (structure forced by override) disappears."""
    res = _gather(tmp_path, _md({"d3t01": ("Crowd", None)}),
                  Overrides(set_breaks=[F["d1t03"]], encore_after=F["d2t02"]))
    show = res.show
    assert [t.set for t in show.tracks] == ["1", "1", "1", "2", "2"]
    assert show.set_breaks == [3]
    assert show.excluded_files[-1] == {
        "filename": F["d3t01"], "reasons": ["junk title"], "duration_sec": 299.0,
        "title": "Crowd", "set": "encore", "after_track": 5}
    assert show.needs_review is False


def test_encore_after_on_a_dropped_crowd_lands_on_the_previous_kept_file(tmp_path):
    res = _gather(tmp_path, _md({"d2t02": ("Crowd", "3:00")}),
                  Overrides(set_breaks=[F["d1t03"]], encore_after=F["d2t02"]))
    show = res.show
    assert [(t.filename, t.set) for t in show.tracks] == [
        (F["d1t01"], "1"), (F["d1t02"], "1"), (F["d1t03"], "1"),
        (F["d2t01"], "2"), (F["d3t01"], "encore")]
    assert show.set_breaks == [3, 4]


def test_include_keeps_a_junk_title(tmp_path):
    res = _gather(tmp_path, _md({"d1t02": ("Tuning", "3:00")}),
                  Overrides(include=[F["d1t02"]]))
    assert [t.title for t in res.show.tracks][1] == "Tuning"
    assert res.junk_drops == () and res.kept_positions is None
    assert all("junk title" not in e["reasons"] for e in res.show.excluded_files)


def test_breaker_holds_with_flag(tmp_path):
    res = _gather(tmp_path, _md({"d1t02": ("Crowd", "6:40")}))
    show = res.show
    assert F["d1t02"] not in [t.filename for t in show.tracks]
    (drop,) = res.junk_drops
    assert drop.held is True
    # total 664+400+371+1908+1040+299 = 4682; median (400+664)/2 = 532.
    expected = junk_titles.hold_flag(drop, total=4682.0, median=532.0)
    assert expected == ("junk-title drop held for review: 'Crowd' (6:40, 8.5% of show, "
                        "0.75x median) file gd73-06-10d1t02.mp3")
    assert show.review_flags == [expected]
    assert show.needs_review is True


def test_all_tracks_dropped_holds_no_playable_tracks(tmp_path):
    keys = ("d1t01", "d1t02", "d1t03", "d2t01", "d2t02", "d3t01")
    res = _gather(tmp_path, _md({k: ("Tuning" if i % 2 else "Crowd", None)
                                 for i, k in enumerate(keys)}))
    show = res.show
    assert show.tracks == []
    assert show.set_breaks == []
    assert show.review_flags.count("no playable tracks") == 1
    assert show.needs_review is True
    assert len(res.junk_drops) == 6 and res.kept_positions == ()
    assert [e["after_track"] for e in show.excluded_files[1:]] == [0] * 6
    assert res.title_paths == ()


def test_flags_and_notes_are_renumbered(tmp_path, monkeypatch):
    monkeypatch.setattr(gather_mod, "structure_guard",
                        lambda *a, **k: "merged track(s) 5 span a set break")
    res = _gather(tmp_path, _md({"d1t03": ("Tuning", "3:00"),
                                 "d2t01": ("03:12 - Dark Star", None)}))
    assert "merged track(s) 4 span a set break" in res.show.review_flags
    assert "merged track(s) 5 span a set break" not in res.show.review_flags
    assert "cosmetic title strip: track 3 '03:12 - Dark Star' -> 'Dark Star'" in res.notes
    assert not any(n.startswith("cosmetic title strip: track 4 ") for n in res.notes)


def test_structure_conflicts_are_renumbered(tmp_path, monkeypatch):
    """`structure.conflicts` (the briefing LLM's input) is renumbered like the flags. The
    fixture's own conflict is the dropped song's name, which holds no number, so one
    numbered conflict is injected at the one place conflicts are assembled."""
    real = gather_mod._dedupe_ordered

    def dedupe(items):
        out = real(items)
        return out + ["merged track 5 conflict"] if "China Cat Sunflower" in out else out

    monkeypatch.setattr(gather_mod, "_dedupe_ordered", dedupe)
    res = _gather(tmp_path, _md({"d1t02": ("Tuning", "3:00")}))
    assert res.show.structure.conflicts == ["China Cat Sunflower", "merged track 4 conflict"]


def _fake_2a(position: int, shipped: str):
    """Stands in for slice 2a accepting the tag at `position` and shipping `shipped`. A
    real 2a never accepts a vocabulary word (each has at least 3 letters, so
    `is_real_title` passes it and 2a never judges it), so the wiring is tested with a
    stand-in that replaces the track object the way `accept_short_tags` does."""
    real = gather_mod.accept_short_tags

    def fake(tracks, tag_titles, tag_source, **kw):
        out, notes = real(tracks, tag_titles, tag_source, **kw)
        out = list(out)
        out[position] = out[position].model_copy(update={"title": shipped,
                                                         "title_source": tag_source})
        return out, notes
    return fake


def test_raw_2a_arrow_keeps(tmp_path, monkeypatch):
    monkeypatch.setattr(gather_mod, "accept_short_tags", _fake_2a(1, "Crowd"))
    res = _gather(tmp_path, _md({"d1t02": ("Crowd >", "3:00")}))
    assert res.title_record.short2a_arrowed == (1,)
    assert [t.title for t in res.show.tracks][1] == "Crowd"
    assert res.junk_drops == ()


def test_2a_accepted_without_a_raw_arrow_drops(tmp_path, monkeypatch):
    monkeypatch.setattr(gather_mod, "accept_short_tags", _fake_2a(1, "Crowd"))
    res = _gather(tmp_path, _md({"d1t02": ("Crowd", "3:00")}))
    assert res.title_record.short2a_arrowed == ()
    assert [d.filename for d in res.junk_drops] == [F["d1t02"]]


def test_short2a_arrowed_is_empty_without_2a(tmp_path):
    res = _gather(tmp_path, _md({"d1t02": ("Crowd >", "3:00")}))
    assert res.title_record.short2a_arrowed == ()
    assert [t.title for t in res.show.tracks][1] == "Crowd >"   # its own arrow keeps it
    assert res.junk_drops == ()


def _real_item(tmp_path, fixture: str, ident: str, date: str, overrides: Overrides):
    from llama.models import Candidate, RecordingSummary
    md = json.loads((Path(__file__).parent / "fixtures" / fixture).read_text())
    cand = Candidate(performance_id=f"x/{date}", collection="x", date=date, venue="v",
                     city="c", recordings=[RecordingSummary(identifier=ident)])
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, overrides)
    return compute_gather(sws, StubIA(md), None, cand, ident)


def test_1979_12_05_tuning_drops(tmp_path):
    ident = "gd1979-12-05.sbd.miller.112163.flac16"
    res = _real_item(tmp_path, f"{ident}.json", ident, "1979-12-05", Overrides())
    show = res.show
    assert "gd79-12-05d1t01.mp3" not in [t.filename for t in show.tracks]
    rows = [r for r in show.excluded_files if r["filename"] == "gd79-12-05d1t01.mp3"]
    assert len(rows) == 1
    assert rows[0]["reasons"] == ["junk title"]
    assert rows[0]["title"] == "Tuning"
    assert rows[0]["after_track"] == 0
    assert show.tracks[0].title.startswith("Alabama Getaway")


def test_railroadearth_2006_02_18_encore_on_dropped_crowd(tmp_path):
    ident = "rre2006-02-18.oktava.flac16"
    ov = Overrides(set_breaks=["rre2006-02-18d1t07.oktava.mp3"],
                   encore_after="rre2006-02-18d3t06.oktava.mp3")
    res = _real_item(tmp_path, f"{ident}.json", ident, "2006-02-18", ov)
    show = res.show
    assert len(show.tracks) == 19
    by_index = {t.index: t for t in show.tracks}  # 1-based, as the brief numbers them
    assert by_index[17] is show.tracks[16] and by_index[18] is show.tracks[17]
    assert show.set_breaks == [7, 17]
    assert (show.tracks[16].title, show.tracks[16].set) == ("Bird In A House", "2")
    assert (show.tracks[17].title, show.tracks[17].set) == ("Shockenaw Mountain Breakdown",
                                                            "encore")
    rows = [r for r in show.excluded_files if r["filename"] == "rre2006-02-18d3t06.oktava.mp3"]
    assert len(rows) == 1
    assert rows[0]["title"] == "Crowd"
    assert rows[0]["set"] == "2"
    assert rows[0]["after_track"] == 17
    assert not any(h for h in res.junk_drops if h.held)


def test_junk_drop_overrule_turns_hold_into_note(tmp_path):
    from llama.models import Overrule
    rule = Overrule(identifier=IDENT, kind="junk-drop", subject=[F["d1t02"]],
                    flag="f", source="fix", at="2026-11-14T00:00:00Z")
    res = _gather(tmp_path, _md({"d1t02": ("Crowd", "6:40")}), Overrides(overrules=[rule]))
    (drop,) = res.junk_drops
    flag = junk_titles.hold_flag(drop, total=4682.0, median=532.0)
    assert not any(f.startswith(junk_titles.HOLD_PREFIX) for f in res.show.review_flags)
    assert "overruled: " + flag in res.notes
    assert res.show.needs_review is False
    assert F["d1t02"] not in [t.filename for t in res.show.tracks]
