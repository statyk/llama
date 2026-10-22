"""llama.replay: cache-only clients and the harness's input digests (spec slice 0)."""
import json

import pytest

from llama.config import Config
from llama.models import ResearchVetting, VettingResult
from llama.replay import (CacheMiss, CacheOnlyIA, CacheOnlySetlistFM, code_identity,
                          config_fingerprint, input_digests, setlistfm_client)
from llama.setlistfm import cache_key
from llama.workspace import ShowWorkspace, write_artifact
from llama.models import Briefing, Overrides, Show, StructureInfo, Track
from llama.replay import (Legs, ShowReplay, briefing_reusable, classify, compute_legs,
                          flag_family, shipped_diff)
from llama.stages.gather import GatherResult
from llama.stages.vet_research import apply_vet
from fixture_library import IDENT
from fixture_library import library_show as _library_show
from fixture_library import replay_config as _config
from llama.models import Provenance, RecordingSummary
from llama.replay import replay_show
from llama.workspace import read_model


def test_cache_only_ia_reads_the_cache_and_refuses_the_network(tmp_path):
    (tmp_path / "md_x.json").write_text(json.dumps({"metadata": {"title": "t"}, "files": []}))
    ia = CacheOnlyIA(tmp_path)
    assert ia.metadata("x")["metadata"]["title"] == "t"
    with pytest.raises(CacheMiss):
        ia.metadata("missing")
    assert ia.misses == ["missing"]
    for call in (lambda: ia.search("q", ["identifier"]),
                 lambda: ia.scrape("q", ["identifier"]),
                 lambda: ia.download_file("x", "a.mp3", tmp_path / "a.mp3")):
        with pytest.raises(CacheMiss):
            call()


def test_cache_only_setlistfm_uses_the_clients_key_and_counts_misses(tmp_path):
    raw = {"setlist": [{"venue": {"name": "RFK Stadium"}, "sets": {"set": []}}]}
    (tmp_path / (cache_key("Grateful Dead", "1973-06-10") + ".json")).write_text(json.dumps(raw))
    sl = CacheOnlySetlistFM(tmp_path)
    assert sl.setlist("Grateful Dead", "1973-06-10", venue="RFK Stadium") == raw["setlist"][0]
    assert sl.setlist("Grateful Dead", "1973-06-11") is None
    assert sl.misses == [("Grateful Dead", "1973-06-11")]


def test_input_digests_cover_the_five_inputs_and_ignore_vet_flags(tmp_path):
    ws = ShowWorkspace(tmp_path / "s")
    write_artifact(ws.show, {"a": 1})
    write_artifact(ws.provenance, {"b": 2})
    ws.research.write_text("r")
    v = VettingResult(vetting=ResearchVetting(asserted_songs=["X"]), flags=["research asserts unknown song: X"])
    write_artifact(ws.vetting, v)
    d = input_digests(ws)
    assert set(d) == {"show.json", "overrides.json", "provenance.json", "research.md", "vetting.extraction"}
    assert d["overrides.json"] is None
    write_artifact(ws.vetting, v.model_copy(update={"flags": []}))
    assert input_digests(ws)["vetting.extraction"] == d["vetting.extraction"]
    write_artifact(ws.vetting, v.model_copy(update={"vetting": ResearchVetting(asserted_songs=["Y"])}))
    assert input_digests(ws)["vetting.extraction"] != d["vetting.extraction"]


def test_config_fingerprint_changes_with_structure_and_setlistfm(monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    a = config_fingerprint(Config())
    assert a == config_fingerprint(Config())
    assert a != config_fingerprint(Config(structure={"align_coverage_threshold": 0.7}))
    monkeypatch.setenv("SETLISTFM_API_KEY", "k")
    assert a != config_fingerprint(Config())


def test_code_identity_is_a_git_sha_or_a_version_string():
    import re
    ident = code_identity()
    assert re.fullmatch(r"[0-9a-f]{40}(?:-dirty)?", ident) or ident.startswith("version:")


def test_setlistfm_client_is_none_unless_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    assert setlistfm_client(Config(root=tmp_path)) is None
    monkeypatch.setenv("SETLISTFM_API_KEY", "k")
    client = setlistfm_client(Config(root=tmp_path))
    assert isinstance(client, CacheOnlySetlistFM)


# --- Task 4: compute_legs, the briefing reuse rule, outcome classification ---


def _legs(root, ws):
    return compute_legs(ws, config=_config(root), ia=CacheOnlyIA(root / "cache"),
                        slfm=None, scratch=root / "scratch" / ws.dir.name)


def test_compute_legs_reproduces_a_stored_show_and_writes_nothing_to_it(tmp_path):
    ws, stored = _library_show(tmp_path, held=False, with_briefing=True)
    before = {p.name: p.read_bytes() for p in ws.dir.iterdir()}
    legs = _legs(tmp_path, ws)
    assert isinstance(legs, Legs)
    assert legs.gather.show.review_flags == [] and legs.vet.result.flags == []
    assert legs.brief == "reuse" and legs.brief_flags == []
    assert legs.briefing is not None
    assert legs.needs_llm == []
    assert {p.name: p.read_bytes() for p in ws.dir.iterdir()} == before
    assert classify(legs, "briefed") == ("clean", None)


def test_compute_legs_copies_only_overrides_into_a_fresh_scratch(tmp_path):
    ws, _ = _library_show(tmp_path, held=False)
    write_artifact(ws.overrides, Overrides(narration="full"))
    scratch = tmp_path / "scratch" / ws.dir.name
    scratch.mkdir(parents=True)
    (scratch / "stale.json").write_text("{}")
    compute_legs(ws, config=_config(tmp_path), ia=CacheOnlyIA(tmp_path / "cache"),
                 slfm=None, scratch=scratch)
    assert sorted(p.name for p in scratch.iterdir()) == ["overrides.json"]
    assert (scratch / "overrides.json").read_bytes() == ws.overrides.read_bytes()


@pytest.mark.parametrize("where", ["show", "inside", "parent"])
def test_compute_legs_refuses_a_scratch_overlapping_the_show_dir(tmp_path, where):
    from llama.errors import LlamaError
    ws, _ = _library_show(tmp_path, held=False)
    scratch = {"show": ws.dir, "inside": ws.dir / "scratch", "parent": ws.dir.parent}[where]
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    with pytest.raises(LlamaError, match="overlaps the show directory"):
        compute_legs(ws, config=_config(tmp_path), ia=CacheOnlyIA(tmp_path / "cache"),
                     slfm=None, scratch=scratch)
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


def test_compute_legs_raises_on_missing_show_or_provenance(tmp_path):
    from llama.errors import LlamaError
    ws, _ = _library_show(tmp_path, held=False)
    ws.provenance.unlink()
    with pytest.raises(LlamaError, match="provenance.json"):
        _legs(tmp_path, ws)
    ws2, _ = _library_show(tmp_path, held=False, date="1973-06-11")
    ws2.show.unlink()
    with pytest.raises(LlamaError, match="show.json"):
        _legs(tmp_path, ws2)


def test_compute_legs_raises_cache_miss_through(tmp_path):
    ws, _ = _library_show(tmp_path, held=False)
    (tmp_path / "cache" / f"md_{IDENT}.json").unlink()
    with pytest.raises(CacheMiss):
        _legs(tmp_path, ws)


def test_stored_llm_alignment_is_needs_llm(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, alignment="llm")
    legs = _legs(tmp_path, ws)
    assert "stored alignment llm" in legs.needs_llm
    assert classify(legs, "held") == ("needs-llm", None)


_PLACING = ("Set 1:\nMorning Dew\nChina Cat Sunflower > I Know You Rider\n\n"
            "Set 2:\nDark Star > Eyes of the World\n")
_NO_MARKERS = "Morning Dew\nChina Cat Sunflower > I Know You Rider\nDark Star > Eyes of the World\n"
# paf2007-10-12.schoeps.taraszki.barfield.87850.flac24 (cache excerpt): `set 3, disc 2`
# is a label only `parse_setlist` reads, so the taper reader declines (cross-check).
_CROSS_CHECK = ("set 1 & 2, disc 1\n1 - good morning little schoolgirl\n2 - deal > jam >\n"
                "3 - mexican girl > jam >\n4 - scarlet begonias >\n5 - i'm so gone\n"
                "6 - turn on your lovelight\nset 2\n7 - lost highway\n8 - tell me mama\n"
                "9 - deep elem blues\n10- friend of the devil >\n11- big mon\n\n"
                "set 3, disc 2\n1 - playin' in the band >\n2 - cumberland blues >\n"
                "3 - uncle john's band > jam >\n4 - mountains of the moon >\n"
                "5 - terrapin station >\n6 - i know you rider\n7 - e: donor rap/intros\n"
                "8 - help on the way > slipknot! >\n9 - franklins tower")


def test_stored_llm_taper_owned_is_replayable(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, alignment="llm", description=_PLACING)
    legs = _legs(tmp_path, ws)
    assert legs.gather.taper_owned is True
    assert "stored alignment llm" not in legs.needs_llm
    assert legs.needs_llm == []


def test_stored_llm_deterministic_candidate_stays_needs_llm(tmp_path):
    # (pin) the candidate aligns deterministically with no LLM call, but the taper
    # does not own it: the relaxation keys on taper_owned, not on "no LLM needed".
    ws, _ = _library_show(tmp_path, held=True, alignment="llm", description=_NO_MARKERS)
    legs = _legs(tmp_path, ws)
    assert legs.gather.taper_owned is False and legs.gather.needs_llm == ()
    assert legs.gather.show.structure.alignment == "deterministic"
    assert "stored alignment llm" in legs.needs_llm


def test_stored_llm_anchored_candidate_stays_needs_llm(tmp_path, monkeypatch):
    from llama import jerrybase
    from llama.jerrybase import JerrybaseEvent, JerrybaseSet
    ev = JerrybaseEvent(event_id="1", venue="V", city="C", state="ST", sets=[
        JerrybaseSet(name="1", closer="I Know You Rider", break_length="long"),
        JerrybaseSet(name="2", closer="Eyes of the World", break_length="long")])
    monkeypatch.setattr(jerrybase, "lookup", lambda a, d: [ev])
    ws, _ = _library_show(tmp_path, held=True, alignment="llm", description=_NO_MARKERS)
    legs = compute_legs(ws, config=Config(root=tmp_path), ia=CacheOnlyIA(tmp_path / "cache"),
                        slfm=None, scratch=tmp_path / "scratch" / ws.dir.name)
    assert legs.gather.taper_owned is False
    assert legs.gather.show.structure.alignment == "jerrybase"
    assert "stored alignment llm" in legs.needs_llm


def test_cross_check_failure_keeps_stored_llm_needs_llm(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, alignment="llm", description=_CROSS_CHECK)
    legs = _legs(tmp_path, ws)
    assert legs.gather.taper.reason.startswith("cross-check:")
    assert legs.gather.taper_owned is False
    assert "stored alignment llm" in legs.needs_llm


def test_track_title_veto_keeps_stored_llm_needs_llm(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, alignment="llm", description=_PLACING)
    cache = tmp_path / "cache" / f"md_{IDENT}.json"
    md = json.loads(cache.read_text())
    for f in md["files"]:
        if f.get("title") == "Eyes of the World":
            f["title"] = "Encore: Eyes of the World"
    cache.write_text(json.dumps(md))
    legs = _legs(tmp_path, ws)
    assert legs.gather.taper.reason == "veto: track title"
    assert legs.gather.taper_owned is False
    assert "stored alignment llm" in legs.needs_llm


def test_missing_vetting_json_is_needs_llm(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, with_vetting=False)
    legs = _legs(tmp_path, ws)
    assert legs.vet is None
    assert legs.needs_llm == ["no vetting.json"]
    assert classify(legs, "held") == ("needs-llm", None)


def test_missing_vetting_json_is_needs_llm_even_when_gather_flags_remain(tmp_path):
    # Spec slice 0 / slice 6 step 2: "No stored vetting.json means needs-LLM",
    # with no exception for a show whose gather still flags it.
    ws, _ = _library_show(tmp_path, held=True, with_vetting=False)
    # Jerrybase ON for the replay only: the vendored dataset's three numbered
    # sets against the fixture's two raise a deterministic gather flag.
    legs = compute_legs(ws, config=Config(root=tmp_path), ia=CacheOnlyIA(tmp_path / "cache"),
                        slfm=None, scratch=tmp_path / "scratch" / ws.dir.name)
    assert legs.gather.needs_llm == ()
    assert legs.gather.show.review_flags == ["structure has 2 sets but jerrybase shows 3"]
    assert legs.needs_llm == ["no vetting.json"]
    assert classify(legs, "held") == ("needs-llm", None)
    assert classify(legs, "packaged") == ("needs-llm", None)


def test_held_show_whose_replay_clears_with_a_reusable_briefing_is_clears(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, with_briefing=True)
    legs = _legs(tmp_path, ws)
    assert legs.flags == [] and legs.brief == "reuse"
    assert classify(legs, "held") == ("clears", None)


def test_held_show_whose_replay_clears_without_a_briefing_is_needs_brief(tmp_path):
    ws, _ = _library_show(tmp_path, held=True)
    legs = _legs(tmp_path, ws)
    assert legs.brief == "fresh" and legs.briefing is None
    assert classify(legs, "held") == ("needs-brief", None)


def test_held_show_still_flagged_is_still_held(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, asserted_dates=["1973-06-10", "1974-01-01"],
                          held_flags=("research asserts wrong date: 1974-01-01",))
    legs = _legs(tmp_path, ws)
    assert legs.flags == ["research asserts wrong date: 1974-01-01"] and legs.brief == "none"
    assert classify(legs, "held") == ("still-held", None)
    assert classify(legs, "packaged") == ("newly-held", None)


def test_carried_package_flag_is_still_held_package(tmp_path):
    ws, show = _library_show(tmp_path, held=True, with_briefing=True)
    show.review_flags = ["duration mismatch on 01 - Morning Dew.mp3: file 10s vs metadata 20s"]
    write_artifact(ws.show, show)
    legs = _legs(tmp_path, ws)
    # The brief leg runs only when no flag remains, carried package flags included.
    assert legs.carried_flags == show.review_flags and legs.brief == "none"
    assert legs.flags == show.review_flags and legs.brief_reason is None
    assert classify(legs, "held") == ("still-held-package", None)


def test_structure_change_on_a_would_clear_show_is_listed_apart(tmp_path):
    ws, show = _library_show(tmp_path, held=True, with_briefing=True)
    show.tracks = [t.model_copy(update={"set": "1"}) for t in show.tracks]   # stored labels differ
    show.set_breaks = []
    write_artifact(ws.show, show)
    legs = _legs(tmp_path, ws)
    assert classify(legs, "held") == ("structure-changed", "needs-brief")   # fields changed, so no reuse
    assert legs.brief_reason.startswith("broadcast fields changed: sets, set_breaks")
    d = shipped_diff(show, legs.vet.show)
    assert d["set_changes"] and d["set_breaks"] == {"old": [], "new": [3, 5]}


def test_alignment_change_on_a_would_clear_show_is_structure_changed(tmp_path):
    # Broadcast fields equal (the briefing is reused), only structure.alignment differs.
    ws, show = _library_show(tmp_path, held=True, with_briefing=True, alignment="override")
    legs = _legs(tmp_path, ws)
    assert legs.brief == "reuse"
    assert classify(legs, "held") == ("structure-changed", "clears")


def test_non_held_shipped_field_change_is_clean_changed(tmp_path):
    ws, show = _library_show(tmp_path, held=False)
    show.venue = "Somewhere Else"
    write_artifact(ws.show, show)
    legs = _legs(tmp_path, ws)
    assert legs.flags == []
    assert classify(legs, "packaged") == ("clean-changed", None)


def test_shipped_diff_compares_against_the_vetted_show(tmp_path):
    # M7: vet's placeholder-date adoption changes `date`; the stored show
    # carries the adopted date, the replayed gather does not, the vetted one does.
    ws, stored = _library_show(tmp_path, held=False, date="1973-01-01",
                               asserted_dates=["1973-06-10"], vetted=True)
    assert stored.date == "1973-06-10" and stored.date_source == "research"
    legs = _legs(tmp_path, ws)
    assert legs.gather.show.date == "1973-01-01" and legs.vet.show.date == "1973-06-10"
    assert legs.replayed_show is legs.vet.show
    assert legs.flags == []
    assert classify(legs, "packaged") == ("clean", None)
    assert shipped_diff(stored, legs.gather.show)["date"] == {"old": "1973-06-10", "new": "1973-01-01"}


def test_briefing_reuse_compares_against_the_vetted_show(tmp_path):
    # The reuse rule sees the show that would ship: a held placeholder-date
    # show whose stored briefing went out with the adopted date reuses it.
    ws, stored = _library_show(tmp_path, held=True, date="1973-01-01", with_briefing=True,
                               asserted_dates=["1973-06-10"], vetted=True)
    legs = _legs(tmp_path, ws)
    assert legs.brief == "reuse" and legs.brief_reason is None
    assert classify(legs, "held") == ("clears", None)


def _show(**kw):
    tracks = kw.pop("tracks", None) or [
        Track(index=1, set="1", title="Dew", filename="a.mp3", title_source="tags"),
        Track(index=2, set="2", title="Star", filename="b.mp3", title_source="tags", segue=True),
        Track(index=3, set="2", title="Eyes", filename="c.mp3", title_source="tags")]
    base = dict(performance_id="A/1973-06-10", identifier="x", artist="A", date="1973-06-10",
                venue="V", city="C", tracks=tracks, set_breaks=[1],
                structure=StructureInfo(source="chosen", alignment="deterministic", coverage=1.0))
    base.update(kw)
    return Show(**base)


def test_shipped_diff_equal_shows_is_empty():
    s = _show()
    assert shipped_diff(s, s) == {"title_changes": [], "venue": None, "city": None,
                                  "set_changes": [], "segue_changes": [], "set_breaks": None,
                                  "alignment": None, "date": None}


def test_shipped_diff_reports_each_field():
    old = _show()
    tracks = [old.tracks[0].model_copy(update={"title_source": "setlist"}),
              old.tracks[1].model_copy(update={"title": "Dark Star", "segue": False}),
              old.tracks[2].model_copy(update={"set": "encore"})]
    new = _show(tracks=tracks, venue="W", city="D", date="1973-06-11", set_breaks=[1, 2],
                structure=StructureInfo(source="chosen", alignment="jerrybase", coverage=1.0))
    d = shipped_diff(old, new)
    assert d["title_changes"] == [
        {"index": 1, "old": "Dew", "new": "Dew", "old_source": "tags", "new_source": "setlist"},
        {"index": 2, "old": "Star", "new": "Dark Star", "old_source": "tags", "new_source": "tags"}]
    assert d["venue"] == {"old": "V", "new": "W"} and d["city"] == {"old": "C", "new": "D"}
    assert d["date"] == {"old": "1973-06-10", "new": "1973-06-11"}
    assert d["set_changes"] == [{"index": 3, "old": "2", "new": "encore"}]
    assert d["segue_changes"] == [{"index": 2, "old": True, "new": False}]
    assert d["set_breaks"] == {"old": [1], "new": [1, 2]}
    assert d["alignment"] == {"old": "deterministic", "new": "jerrybase"}
    assert shipped_diff(old, new.model_copy(update={"structure": None}))["alignment"] == \
        {"old": "deterministic", "new": None}


def test_shipped_diff_track_count_change_reports_every_index():
    old = _show()
    new = _show(tracks=old.tracks[:2])
    d = shipped_diff(old, new)
    assert [r["index"] for r in d["title_changes"]] == [1, 2, 3]
    # Each side carries its own track's value; None only past that show's end.
    assert [(r["new"], r["new_source"]) for r in d["title_changes"]] == \
        [("Dew", "tags"), ("Star", "tags"), (None, None)]
    assert d["set_changes"][2] == {"index": 3, "old": "2", "new": None}
    assert [r["index"] for r in d["set_changes"]] == [1, 2, 3]
    assert [r["index"] for r in d["segue_changes"]] == [1, 2, 3]
    # A stored show with no tracks still reports the change.
    empty = old.model_copy(update={"tracks": []})
    assert [r["index"] for r in shipped_diff(empty, old)["title_changes"]] == [1, 2, 3]


def test_briefing_reusable_reasons():
    show = Show(performance_id="A/1973-06-10", identifier="x", artist="A", date="1973-06-10",
                venue="V", tracks=[Track(index=1, set="1", title="Dew", filename="a.mp3", title_source="tags")])
    b = Briefing(context="c", significance="s", per_set={"1": ["x"]})
    assert briefing_reusable(show, show, b, "full") is None
    assert briefing_reusable(show, show.model_copy(update={"venue": "W"}), b, "full").startswith("broadcast fields changed: venue")
    assert briefing_reusable(show, show, b, "vague").startswith("narration differs")
    assert briefing_reusable(show, show, b, "vague") == "narration differs: briefing full, overrides vague"
    bad = b.model_copy(update={"mentioned_songs": ["Nope"]})
    assert briefing_reusable(show, show, bad, "full").startswith("briefing guard: briefing mentions unknown song: Nope")


def test_briefing_reusable_names_every_changed_broadcast_field():
    old = _show()
    retitled = [old.tracks[0].model_copy(update={"title": "Morning Dew"}), *old.tracks[1:]]
    b = Briefing(context="c", significance="s", per_set={"1": ["x"], "2": ["y"]})
    new = old.model_copy(update={"tracks": retitled, "date": "1973-06-11", "city": "D"})
    assert briefing_reusable(old, new, b, "full") == "broadcast fields changed: titles, date, city"
    # title_source alone is not a broadcast field.
    resourced = [old.tracks[0].model_copy(update={"title_source": "setlist"}), *old.tracks[1:]]
    assert briefing_reusable(old, old.model_copy(update={"tracks": resourced}), b, "full") is None
    segue = [old.tracks[0], old.tracks[1].model_copy(update={"segue": False}), old.tracks[2]]
    assert briefing_reusable(old, old.model_copy(update={"tracks": segue}), b, "full") == \
        "broadcast fields changed: segues"


def test_reuse_refused_when_recorded_narration_differs():
    # Review Focus 3: a briefing.json written before `narration` existed reads as "full".
    show = Show(performance_id="A/1973-06-10", identifier="x", artist="A", date="1973-06-10",
                tracks=[Track(index=1, set="1", title="Dew", filename="a.mp3", title_source="tags")])
    legacy = Briefing.model_validate({"context": "c", "significance": "s", "per_set": {"1": ["x"]}})
    assert legacy.narration == "full"
    assert briefing_reusable(show, show, legacy, "vague") is not None


def test_legacy_briefing_on_a_vague_show_is_needs_brief(tmp_path):
    # Review Focus 3, end to end: the stored briefing.json predates `narration`.
    ws, _ = _library_show(tmp_path, held=True)
    ws.briefing_json.write_text(json.dumps(
        {"context": "c", "significance": "s", "per_set": {"1": ["a"], "2": ["b"], "encore": ["c"]}}))
    write_artifact(ws.overrides, Overrides(narration="vague"))
    legs = _legs(tmp_path, ws)
    assert legs.brief == "fresh"
    assert legs.brief_reason == "narration differs: briefing full, overrides vague"
    assert classify(legs, "held") == ("needs-brief", None)


def _synthetic_legs(*, gather_flags=(), needs_llm=(), vet=True, carried=(), brief="none"):
    show = _show(review_flags=list(gather_flags), needs_review=bool(gather_flags))
    vet_outcome = apply_vet(ResearchVetting(), show) if vet else None
    flags = list(gather_flags) + list(carried)
    return Legs(gather=GatherResult(show=show, reviews=[], notes=[], needs_llm=()),
                stored=show, vet=vet_outcome, needs_llm=list(needs_llm), brief=brief,
                brief_reason=None, brief_flags=[], briefing=None, carried_flags=list(carried),
                flags=flags)


def test_classify_needs_llm_wins_over_every_flag():
    legs = _synthetic_legs(gather_flags=["low-confidence structure alignment"],
                           needs_llm=["align_structure"], carried=["duration mismatch on x"])
    assert classify(legs, "held") == ("needs-llm", None)
    assert classify(legs, "packaged") == ("needs-llm", None)
    legs = _synthetic_legs(gather_flags=["unresolved track titles"], needs_llm=["no vetting.json"],
                           vet=False)
    assert classify(legs, "held") == ("needs-llm", None)


def test_show_replay_to_dict_has_the_contract_keys_plus_date():
    r = ShowReplay(slug="s", state="held")
    assert list(r.to_dict()) == [
        "slug", "state", "stored_flags", "stored_core_flags", "gather_flags", "vet_flags",
        "brief_flags", "stored_brief_guard", "needs_llm", "outcome", "would_be", "briefing",
        "reproduces", "title_changes", "venue", "city", "date", "selected_venue", "selected_city",
        "set_changes", "segue_changes", "set_breaks", "alignment", "notes", "digests",
        "slfm_miss", "unreplayable", "taper_owned", "sets", "filler", "taper_source",
        "taper_reason", "step1_alignment"]
    assert r.to_dict()["date"] is None


@pytest.mark.parametrize("flag, family", [
    ("venue mismatch: archive 'A' vs jerrybase 'B'", "venue"),
    ("recordings of this date disagree on city: 'A' (selected) vs 'B'", "city"),
    ("unresolved track titles", "titles"),
    ("research asserts unknown song: X", "research-song"),
    ("research asserts 2 sets but structure has 1", "research-sets"),
    ("research asserts wrong date: 1 Jan", "research-date"),
    ("research asserts 1973-06-10; item date 1973-01-01 looks like a year-only placeholder", "research-date"),
    ("briefing mentions unknown song: X", "briefing"),
    ("low-confidence structure alignment", "structure"),
    ("single-set structure for a 120-minute show", "structure"),
    ("setlist evidence shows multiple sets but tape has one", "structure"),
    ("low-confidence setlist", "structure"),
    ("merged track(s): 3", "structure"),
    ("structure has 1 sets but jerrybase shows 2", "structure"),
    ("jerrybase set closer 'X' is not at a set break", "structure"),
    ("duration mismatch on 01 - X.mp3: file 1s vs metadata 2s", "package"),
    ("tape spans 2 events", "events"),
    ("unassigned multi-event tape", "events"),
    ("multi-event date: 2 shows", "events"),
    ("no playable tracks", "tracks"),
    ("research asserts something new", "other"),
    ("something else", "other"),
])
def test_flag_family(flag, family):
    assert flag_family(flag) == family


# --- Task 5: carried fixes from the Task 2 and Task 4 reviews ---

@pytest.mark.parametrize("body", ["{not json", "[1, 2]", '"text"', '{"setlist": 7}',
                                  '{"setlist": [3]}'])
def test_cache_only_setlistfm_never_raises_on_a_malformed_cache_file(tmp_path, body):
    # Mirrors SetlistFMClient.setlist: a corrupted cache degrades to None, and
    # is not a miss (the real client would not fetch: the file exists).
    (tmp_path / (cache_key("Grateful Dead", "1973-06-10") + ".json")).write_text(body)
    sl = CacheOnlySetlistFM(tmp_path)
    assert sl.setlist("Grateful Dead", "1973-06-10", venue="RFK Stadium") is None
    assert sl.misses == []


def _fake_git(sha: str, status: str):
    import subprocess

    def run(cmd, **kw):
        out = sha if "rev-parse" in cmd else status
        return subprocess.CompletedProcess(cmd, 0, stdout=out + "\n", stderr="")
    return run


def test_code_identity_marks_an_uncommitted_tree_dirty(monkeypatch):
    import llama.replay as rp
    sha = "a" * 40
    monkeypatch.setattr(rp.subprocess, "run", _fake_git(sha, " M x.py"))
    assert code_identity() == sha + "-dirty"
    monkeypatch.setattr(rp.subprocess, "run", _fake_git(sha, ""))
    assert code_identity() == sha


@pytest.mark.parametrize("failure", ["oserror", "called", "empty"])
def test_code_identity_falls_back_to_the_version(monkeypatch, failure):
    import subprocess

    import llama
    import llama.replay as rp

    def run(cmd, **kw):
        if failure == "oserror":
            raise FileNotFoundError("git")
        if failure == "called":
            raise subprocess.CalledProcessError(128, cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="\n", stderr="")
    monkeypatch.setattr(rp.subprocess, "run", run)
    assert code_identity() == f"version:{llama.__version__}"


def test_shipped_diff_track_count_change_carries_the_new_values():
    old = _show()
    longer = _show(tracks=[*old.tracks, Track(index=4, set="encore", title="Casey Jones",
                                              filename="d.mp3", title_source="setlist",
                                              segue=False)])
    d = shipped_diff(old, longer)
    assert d["title_changes"][3] == {"index": 4, "old": None, "new": "Casey Jones",
                                     "old_source": None, "new_source": "setlist"}
    assert d["title_changes"][0] == {"index": 1, "old": "Dew", "new": "Dew",
                                     "old_source": "tags", "new_source": "tags"}
    assert d["set_changes"][3] == {"index": 4, "old": None, "new": "encore"}
    assert d["segue_changes"][1] == {"index": 2, "old": True, "new": True}
    assert d["segue_changes"][3] == {"index": 4, "old": None, "new": False}


def test_compute_legs_refuses_a_scratch_inside_the_library_shows_dir(tmp_path):
    # A scratch at shows/<other-slug> would rmtree another show.
    from llama.errors import LlamaError
    ws, _ = _library_show(tmp_path, held=False)
    other, _ = _library_show(tmp_path, held=False, date="1973-06-11")
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))
    for scratch in (other.dir, ws.dir.parent / "new-dir", ws.dir.parent / "a" / "b"):
        with pytest.raises(LlamaError, match="inside the library's shows directory"):
            compute_legs(ws, config=_config(tmp_path), ia=CacheOnlyIA(tmp_path / "cache"),
                         slfm=None, scratch=scratch)
    assert sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*")) == before


# --- Task 5: replay_show, one show's arm row ---


def _replay(root, ws, *, slfm=None, delivered=frozenset()):
    return replay_show(ws, config=_config(root), ia=CacheOnlyIA(root / "cache"), slfm=slfm,
                       scratch=root / "scratch" / ws.dir.name, delivered=set(delivered))


def test_stored_briefing_flags_are_not_core_flags_and_are_reported_apart(tmp_path):
    # P2: a show held by the briefing guard reproduces on gather+vet; its briefing
    # flag is compared on its own line through stored_brief_guard.
    ws, show = _library_show(tmp_path, held=True,
                             held_flags=("briefing mentions unknown song: Nope",))
    write_artifact(ws.briefing_json, Briefing(context="c", significance="s",
                                              per_set={"1": ["a"], "2": ["b"], "encore": ["c"]},
                                              mentioned_songs=["Nope"]))
    r = replay_show(ws, config=_config(tmp_path), ia=CacheOnlyIA(tmp_path / "cache"), slfm=None,
                    scratch=tmp_path / "scratch" / ws.dir.name, delivered=set())
    assert r.stored_core_flags == [] and r.reproduces is True
    assert r.stored_brief_guard == ["briefing mentions unknown song: Nope"]
    assert (r.selected_venue, r.selected_city) == (None, None)   # the fixture's recording names neither


def test_replay_show_fills_the_row_of_a_clearing_held_show(tmp_path):
    ws, show = _library_show(tmp_path, held=True, with_briefing=True)
    r = _replay(tmp_path, ws)
    assert (r.slug, r.state, r.outcome, r.would_be, r.briefing) == \
        (ws.dir.name, "held", "clears", None, "reuse")
    assert r.stored_flags == show.review_flags and "unresolved track titles" in r.stored_flags
    assert r.stored_core_flags == show.review_flags
    assert r.gather_flags == [] and r.vet_flags == [] and r.brief_flags == []
    assert r.reproduces is False and r.needs_llm == [] and r.unreplayable is None
    assert r.stored_brief_guard == []
    assert r.digests == input_digests(ws)
    assert r.title_changes == [] and r.venue is None and r.date is None
    assert r.slfm_miss is False


def test_replay_show_core_flags_drop_package_and_briefing_families(tmp_path):
    ws, show = _library_show(tmp_path, held=True, asserted_dates=["1973-06-10", "1974-01-01"],
                             held_flags=("research asserts wrong date: 1974-01-01",
                                         "duration mismatch on a.mp3: file 1s vs metadata 2s",
                                         "briefing claims 3 sets but structure has 2"))
    r = _replay(tmp_path, ws)
    assert r.stored_core_flags == ["research asserts wrong date: 1974-01-01"]
    assert r.vet_flags == ["research asserts wrong date: 1974-01-01"]
    assert r.reproduces is True and r.outcome == "still-held-package"
    assert r.stored_brief_guard is None          # no briefing.json


def test_replay_show_selected_venue_and_city_come_from_the_selected_recording(tmp_path):
    ws, show = _library_show(tmp_path, held=False)
    prov = read_model(ws.provenance, Provenance)
    prov.candidate.recordings = [
        RecordingSummary(identifier="other", venue="Elsewhere", coverage="Nowhere"),
        RecordingSummary(identifier=IDENT, venue="  RFK Stadium ", coverage=" Washington, DC")]
    write_artifact(ws.provenance, prov)
    r = _replay(tmp_path, ws)
    assert (r.selected_venue, r.selected_city) == ("RFK Stadium", "Washington, DC")
    prov.candidate.recordings[1] = RecordingSummary(identifier=IDENT, venue="  ", coverage="")
    write_artifact(ws.provenance, prov)
    assert (_replay(tmp_path, ws).selected_venue, _replay(tmp_path, ws).selected_city) == (None, None)


def test_replay_show_computes_stored_fields_for_a_needs_llm_show(tmp_path):
    ws, show = _library_show(tmp_path, held=True, with_vetting=False, with_briefing=True)
    r = _replay(tmp_path, ws)
    assert r.outcome == "needs-llm" and r.needs_llm == ["no vetting.json"]
    assert r.stored_core_flags == ["unresolved track titles"] and r.reproduces is False
    assert r.stored_brief_guard == []


def test_replay_show_cache_miss_is_unreplayable(tmp_path):
    ws, _ = _library_show(tmp_path, held=True)
    (tmp_path / "cache" / f"md_{IDENT}.json").unlink()
    r = _replay(tmp_path, ws)
    assert r.outcome == "unreplayable" and r.unreplayable == f"cache miss: md_{IDENT}.json"
    assert r.state == "held" and r.stored_core_flags == ["unresolved track titles"]


@pytest.mark.parametrize("body", ["[1, 2", "[1, 2]", '"vague"', '{"exclude": 3}', b"\xff\xfe"])
def test_replay_show_unreadable_overrides_is_unreplayable(tmp_path, body):
    ws, _ = _library_show(tmp_path, held=True)
    if isinstance(body, bytes):
        ws.overrides.write_bytes(body)    # not UTF-8
    else:
        ws.overrides.write_text(body)
    r = _replay(tmp_path, ws)
    assert r.outcome == "unreplayable" and r.unreplayable == "overrides.json unreadable"


def test_replay_show_any_other_error_is_unreplayable_with_its_type(tmp_path):
    ws, _ = _library_show(tmp_path, held=True)
    ws.vetting.write_text("{broken")
    r = _replay(tmp_path, ws)
    assert r.outcome == "unreplayable" and r.unreplayable.startswith("ValidationError: ")
    assert len(r.unreplayable) <= 200
    ws2, _ = _library_show(tmp_path, held=False, date="1973-06-11")
    ws2.show.write_text("{broken")
    r2 = _replay(tmp_path, ws2)
    assert r2.outcome == "unreplayable" and r2.unreplayable.startswith("ValidationError: ")
    assert r2.state == "unknown"


def test_replay_show_records_a_setlistfm_miss(tmp_path):
    ws, _ = _library_show(tmp_path, held=False)
    slfm = CacheOnlySetlistFM(tmp_path / "cache")
    r = _replay(tmp_path, ws, slfm=slfm)
    assert slfm.misses and r.slfm_miss is True
    assert _replay(tmp_path, ws, slfm=slfm).slfm_miss is True     # grew again on this show
    (tmp_path / "cache" / (cache_key(*slfm.misses[0]) + ".json")).write_text('{"setlist": []}')
    assert _replay(tmp_path, ws, slfm=slfm).slfm_miss is False


def test_replay_show_state_counts_the_delivered_set(tmp_path):
    ws, show = _library_show(tmp_path, held=False)
    assert _replay(tmp_path, ws, delivered={show.performance_id}).state == "delivered"
    assert _replay(tmp_path, ws).state == "vetted"


# --- Task 14: stored briefings are normalised (3a) wherever replay guards or reuses them ---

def test_briefing_reusable_normalises_empty_sets_before_the_guard():
    show = Show(performance_id="A/1973-06-10", identifier="x", artist="A", date="1973-06-10",
                tracks=[Track(index=1, set="1", title="Dew", filename="a.mp3", title_source="tags")])
    b = Briefing(context="c", significance="s", per_set={"1": ["x"], "encore": []})
    assert briefing_reusable(show, show, b, "full") is None


def _with_empty_set_briefing(ws):
    write_artifact(ws.briefing_json, Briefing(context="c", significance="s",
                                              per_set={"1": ["a"], "2": ["b"], "encore": ["c"],
                                                       "3": []}))


def test_compute_legs_reuses_and_stores_the_normalised_briefing(tmp_path):
    ws, _ = _library_show(tmp_path, held=False)
    _with_empty_set_briefing(ws)
    legs = _legs(tmp_path, ws)
    assert legs.brief == "reuse" and legs.brief_flags == []
    assert legs.briefing.per_set == {"1": ["a"], "2": ["b"], "encore": ["c"]}


def test_stored_brief_guard_runs_on_the_normalised_briefing(tmp_path):
    ws, _ = _library_show(tmp_path, held=False)
    _with_empty_set_briefing(ws)
    assert _replay(tmp_path, ws).stored_brief_guard == []


def test_record_carries_taper_fields(tmp_path):
    ws, _ = _library_show(tmp_path, held=True, description=_PLACING)
    owned = _replay(tmp_path, ws)
    assert owned.taper_owned is True
    assert owned.taper_source == "description" and owned.taper_reason is None
    assert owned.sets and set(owned.sets) <= {"1", "2", "encore"} and "2" in owned.sets
    assert len(owned.filler) == len(owned.sets) and all(isinstance(f, bool) for f in owned.filler)
    assert owned.step1_alignment in ("deterministic", "jerrybase")
    d = owned.to_dict()
    assert d["sets"] == owned.sets and d["taper_owned"] is True

    ws2, _ = _library_show(tmp_path / "b", held=True, description=_NO_MARKERS)
    plain = _replay(tmp_path / "b", ws2)
    assert plain.taper_owned is False
    assert plain.taper_source == "none" and plain.taper_reason
    assert plain.sets and len(plain.filler) == len(plain.sets)
    assert plain.step1_alignment == "deterministic"
