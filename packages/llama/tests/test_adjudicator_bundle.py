import json

import pytest

import fixture_library
import helpers
from llama.adjudicator.bundle import (BUNDLE_CAP, DESC_CAP, EVIDENCE_KINDS, Bundle, Row,
                                      build_bundle, escape_braces)
from llama.config import Config
from llama.show_unit import capture_view

FN = "gd73-06-10d1t01.mp3"
SIB = "gd73-06-10.sib.flac"
HEADERS = ["# gratefuldead-1973-06-10", "## review flags", "## track table", "## excluded files",
           "## overrides.json", "## vetting", "## notes", "## research", "## briefing",
           "## considered recordings", "## evidence: taper-description",
           "## evidence: original-tag", "## evidence: derivative-tag",
           "## evidence: sibling-tracks", "## evidence: setlistfm", "## evidence: jerrybase",
           "## evidence: review"]


class StubIA:
    def __init__(self, md, siblings=None):
        self.md, self.siblings, self.calls = md, siblings or {}, []

    def metadata(self, identifier):
        self.calls.append(identifier)
        if identifier == fixture_library.IDENT:
            return self.md
        return self.siblings[identifier]


def _sib_md(length="11:04", desc="sibling desc"):
    return {"metadata": {"description": desc},
            "files": [{"name": "s01.flac", "source": "original", "format": "Flac",
                       "title": "Morning Dew", "length": length}]}


def _setup(tmp_path, *, siblings=True, **kw):
    ws, show = fixture_library.library_show(tmp_path, held=True, **kw)
    md = json.loads((fixture_library.FIXTURES / "gd73_metadata.json").read_text())
    sibs = {SIB: _sib_md()} if siblings else {}
    ident = fixture_library.IDENT
    scores = {ident: {"score": 0.9, "lineage": "SBD", "kept_tracks": 6, "title_fraction": 1.0}}
    for s in sibs:
        scores[s] = {"score": 0.5, "lineage": "AUD", "kept_tracks": 5, "title_fraction": 0.4}
    ws.selection.write_text(json.dumps({"identifier": ident, "scores": scores}))
    cfg = Config(root=tmp_path, jerrybase={"enabled": False})
    return ws, show, StubIA(md, sibs), cfg


def test_bundle_has_every_section_header_in_order(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    b = build_bundle(ws, ia, cfg)
    pos = [b.text.index("\n" + h if i else h) for i, h in enumerate(HEADERS)]
    assert pos == sorted(pos)
    assert set(b.sections) == set(EVIDENCE_KINDS) and len(EVIDENCE_KINDS) == 7
    assert "gd73-06-10.sib.flac" in b.text and f"{SIB} | AUD | 5 | 0.4 | 0.5" in b.text
    assert f"* {fixture_library.IDENT} | SBD | 6 | 1.0 | 0.9" in b.text
    assert "unresolved track titles" in b.text


def test_track_table_row_format(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    b = build_bundle(ws, ia, cfg)
    t = b.show.tracks[0]
    assert (f"1 | {t.set} | {t.title} | {t.title_source} | {t.matched} | {round(t.duration_sec)} | "
            f"{t.filename}") in b.text


def test_original_and_derivative_rows_carry_filename_and_length(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    b = build_bundle(ws, ia, cfg)
    row = b.own_row("derivative-tag", FN)
    assert row.filename == FN and row.length_s == pytest.approx(664.0, abs=1)
    assert row.text == f"{FN} | VBR MP3 | Morning Dew | 664"
    assert b.own_row("original-tag", FN).filename.endswith(".shn")
    assert b.own_row("original-tag", "gd73-06-10d1t01.shn").filename == "gd73-06-10d1t01.shn"
    assert b.own_row("derivative-tag", "gd73-06-10d1t01.shn") is None
    assert b.own_row("derivative-tag", "nope.mp3") is None
    assert b.files[FN].original == "gd73-06-10d1t01.shn" and b.files[FN].title == "Morning Dew"


def test_length_of_takes_the_larger_and_unknown_is_none(tmp_path):
    ws, show, ia, cfg = _setup(tmp_path)
    ws_show = show.model_copy(deep=True)
    ws_show.tracks[0].duration_sec = 900.0           # larger than metadata 664
    ws_show.tracks[1].duration_sec = 10.0            # smaller than metadata 452
    ws_show.excluded_files = [{"filename": "ex.mp3", "reasons": ["junk"], "duration_sec": 33.0}]
    from llama.workspace import write_artifact
    write_artifact(ws.show, ws_show)
    b = build_bundle(ws, ia, cfg)
    assert b.length_of(ws_show.tracks[0].filename) == 900.0
    assert b.length_of(ws_show.tracks[1].filename) == pytest.approx(452.0, abs=1)
    assert b.length_of("ex.mp3") == 33.0
    assert b.length_of("gd73-06-10d3t01.shn") is None
    assert b.length_of("never-heard-of.mp3") is None


def test_sibling_rows_carry_identifier_and_length(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    b = build_bundle(ws, ia, cfg)
    rows = b.sections["sibling-tracks"]
    assert rows[0].text == "sibling desc" and rows[0].filename is None and rows[0].identifier == SIB
    r = rows[1]
    assert (r.identifier, r.filename, r.title) == (SIB, "s01.flac", "Morning Dew")
    assert r.length_s == pytest.approx(664.0, abs=1)
    assert r.text == f"{SIB} | s01.flac | Morning Dew | 664"


def test_setlistfm_is_read_from_cache_only(tmp_path):
    from llama.setlistfm import cache_key
    ws, show, ia, cfg = _setup(tmp_path)
    assert build_bundle(ws, ia, cfg).sections["setlistfm"] == []
    cdir = tmp_path / "cache"
    (cdir / f"{cache_key(show.artist, show.date)}.json").write_text(
        json.dumps({"setlist": [{"sets": {"set": [{"song": [{"name": "Dark Star"}]}]}}]}))
    rows = build_bundle(ws, ia, cfg).sections["setlistfm"]
    assert len(rows) == 1 and "Dark Star" in rows[0].text


def test_jerrybase_section_obeys_config(tmp_path):
    ws, show, ia, _ = _setup(tmp_path)
    off = build_bundle(ws, ia, Config(root=tmp_path, jerrybase={"enabled": False}))
    on = build_bundle(ws, ia, Config(root=tmp_path, jerrybase={"enabled": True}))
    assert off.sections["jerrybase"] == []
    assert on.sections["jerrybase"], "the vendored dataset has GD 1973-06-10"
    assert all(r.text.startswith("JerrybaseEvent") for r in on.sections["jerrybase"])


def test_notes_section_is_the_notes_json_capped(tmp_path):
    from llama.models import ShowNotes
    from llama.workspace import write_artifact
    ws, _, ia, cfg = _setup(tmp_path)
    write_artifact(ws.notes, ShowNotes(gather=["note-" + "z" * 5000]))
    b = build_bundle(ws, ia, cfg)
    seg = b.text.split("## notes")[1].split("## research")[0]
    assert "note-zzz" in seg and len(seg) < 3200


def test_reviews_and_description_rows(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    b = build_bundle(ws, ia, cfg)
    assert b.sections["review"][0].text.startswith("[2004-08-01 5*] I WAS THERE: Best day")
    assert b.sections["taper-description"], "the fixture item has a description"


def test_bundle_escapes_braces_and_caps_size(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    ia.md["metadata"]["description"] = "{{slug}} " + "x" * 200_000 + "\x00"
    (ws.dir / "research.md").write_text("{{r}} " + "y" * 300_000)
    b = build_bundle(ws, ia, cfg)
    assert "{{" not in b.text and "}}" not in b.text and "{ {slug} }" in b.text
    assert len(b.text) <= BUNDLE_CAP
    assert len(b.sections["taper-description"][0].text) <= DESC_CAP + len("{ {slug} } ")


def _order(b):
    seen = []
    for r in b.sections["sibling-tracks"]:
        if r.identifier not in seen:
            seen.append(r.identifier)
    return seen


def test_oversize_drops_siblings_last_first_then_research(tmp_path, monkeypatch):
    import llama.adjudicator.bundle as bm
    ws, _, ia, cfg = _setup(tmp_path, siblings=False)
    sel = json.loads(ws.selection.read_text())
    for i in range(8):
        ia.siblings[f"sib{i}"] = _sib_md(desc="d" * 3000)
        sel["scores"][f"sib{i}"] = {"score": 0.1 * (8 - i), "lineage": "AUD", "kept_tracks": 1,
                                    "title_fraction": 0.0}
    ws.selection.write_text(json.dumps(sel))
    (ws.dir / "research.md").write_text("R" * 12000)
    full = build_bundle(ws, ia, cfg)
    order = _order(full)
    assert order == [f"sib{i}" for i in range(8)]
    # a cap that fits only part of the siblings: the tail goes first, research intact
    monkeypatch.setattr(bm, "BUNDLE_CAP", len(full.text) - 5000)
    b = build_bundle(ws, ia, cfg)
    assert len(b.text) <= bm.BUNDLE_CAP
    assert _order(b) == order[:len(_order(b))] and 0 < len(_order(b)) < 8
    assert "R" * 12000 in b.text
    assert _all_rows_in_text(b)
    kept = set(_order(b))
    for gone in set(order) - kept:
        assert f"{gone} | s01.flac" not in b.text
        assert all(r.identifier != gone for r in b.sections["sibling-tracks"])
    # a cap below the no-sibling size: all siblings gone, research is cut, the rest stays
    nosib = len(full.text) - sum(len(r.text) + 1 for r in full.sections["sibling-tracks"])
    monkeypatch.setattr(bm, "BUNDLE_CAP", nosib - 3000)
    c = build_bundle(ws, ia, cfg)
    assert len(c.text) <= bm.BUNDLE_CAP and _order(c) == []
    assert 0 < c.text.count("R") < 12000
    for keep in ("## review flags", "## track table", "## excluded files", "## overrides.json"):
        assert keep in c.text
    assert _all_rows_in_text(c)
    assert "s01.flac" not in c.text and c.sections["sibling-tracks"] == []
    assert c.sections["taper-description"] == full.sections["taper-description"]


def test_escape_braces_breaks_every_adjacent_pair():
    assert escape_braces("{{{x}}}") == "{ { {x} } }" and "{{" not in escape_braces("{{{{")


def test_build_bundle_writes_nothing(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    before = helpers.tree_bytes(ws.dir)
    mtimes = {p: p.stat().st_mtime_ns for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    build_bundle(ws, ia, cfg)
    assert helpers.tree_bytes(ws.dir) == before
    assert {p: p.stat().st_mtime_ns for p in sorted(tmp_path.rglob("*")) if p.is_file()} == mtimes
    assert set(p for p in tmp_path.rglob("*") if p.is_file()) == set(mtimes)


def test_bundle_view_is_captured_before_reading(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    b = build_bundle(ws, ia, cfg)
    assert b.view == capture_view(ws)
    assert isinstance(b, Bundle) and isinstance(b.sections["review"][0], Row)
    assert b.provenance is not None and b.selection["identifier"] == fixture_library.IDENT


def _all_rows_in_text(b):
    return all(r.text in b.text for k in EVIDENCE_KINDS for r in b.sections[k])


def test_rows_are_substrings_of_text_including_braced_rows(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    ia.md["metadata"]["description"] = "{{a}} {{{b}}}"
    ia.md["reviews"][0]["reviewbody"] = "{{x}}"
    ia.md["files"][6]["title"] = "T{{q}}\x00"
    b = build_bundle(ws, ia, cfg)
    assert any("{ {a} }" in r.text for r in b.sections["taper-description"])
    assert _all_rows_in_text(b)
    assert b.files[FN].title == "T{ {q} }" and b.own_row("derivative-tag", FN).title == "T{ {q} }"


def test_list_valued_description_notes_and_sibling_keep_text_verbatim(tmp_path):
    ws, _, ia, cfg = _setup(tmp_path)
    ia.md["metadata"]["description"] = ["Jerry's guitar", "line two"]
    ia.md["metadata"]["notes"] = ["n1", "it's n2"]
    ia.siblings[SIB]["metadata"]["description"] = ["sib's a", "sib b"]
    b = build_bundle(ws, ia, cfg)
    assert b.sections["taper-description"][0].text == "Jerry's guitar\nline two"
    assert b.sections["taper-description"][1].text == "n1\nit's n2"
    assert b.sections["sibling-tracks"][0].text == "sib's a\nsib b"
    assert _all_rows_in_text(b)


def test_lookups_use_the_item_date_when_a_date_override_corrected_it(tmp_path):
    from llama.setlistfm import cache_key
    from llama.workspace import write_artifact
    ws, show, ia, cfg = _setup(tmp_path)
    corrected = show.model_copy(update={"date": "1973-06-11", "item_date": show.date,
                                        "date_source": "override"})
    write_artifact(ws.show, corrected)
    (tmp_path / "cache" / f"{cache_key(show.artist, show.date)}.json").write_text(
        json.dumps({"setlist": [{"id": "ITEM-DATE"}]}))
    (tmp_path / "cache" / f"{cache_key(show.artist, '1973-06-11')}.json").write_text(
        json.dumps({"setlist": [{"id": "OVERRIDE-DATE"}]}))
    rows = build_bundle(ws, ia, cfg).sections["setlistfm"]
    assert len(rows) == 1 and "ITEM-DATE" in rows[0].text
    on = build_bundle(ws, ia, Config(root=tmp_path, jerrybase={"enabled": True}))
    assert on.sections["jerrybase"], "looked up by the item date 1973-06-10"


def test_unknown_durations_render_as_question_mark(tmp_path):
    from llama.workspace import write_artifact
    ws, show, ia, cfg = _setup(tmp_path)
    s = show.model_copy(deep=True)
    s.tracks[0].duration_sec = None
    s.excluded_files = [{"filename": "ex.mp3", "reasons": ["junk"], "duration_sec": None}]
    write_artifact(ws.show, s)
    b = build_bundle(ws, ia, cfg)
    assert f"| ? | {s.tracks[0].filename}" in b.text
    assert "ex.mp3 | ['junk'] | ?" in b.text


def test_unreachable_sibling_gets_a_metadata_unavailable_row(tmp_path):
    from llama.ia_client import IAError
    ws, _, ia, cfg = _setup(tmp_path)

    class Down(StubIA):
        def metadata(self, identifier):
            if identifier == SIB:
                raise IAError("boom")
            return super().metadata(identifier)
    b = build_bundle(ws, Down(ia.md, ia.siblings), cfg)
    assert b.sections["sibling-tracks"] == [Row(text=f"{SIB}: (metadata unavailable)",
                                                identifier=SIB)]
