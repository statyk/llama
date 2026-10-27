import json
from pathlib import Path

from llama.models import Overrides, Overrule, Show, Track
from llama.overrules import (FlagKey, flag_key, merge_rules, records_for,
                             rule_matches, split_overruled)
from llama.workspace import write_artifact

FIXTURE = Path(__file__).parent / "fixtures" / "arm_flags.json"


def _track(i, fn, source="tags"):
    return Track(index=i, set="1", title="t", filename=fn, title_source=source)


def _show(identifier="id1", unresolved=()):
    tracks = [_track(1, "ok.mp3")] + [
        _track(i + 2, fn, "unresolved") for i, fn in enumerate(unresolved)]
    return Show(performance_id="a/1", identifier=identifier, artist="A",
                date="1973-01-01", tracks=tracks)


def _rule(identifier="id1", kind="research-song", subject=("x",), flag="f"):
    return Overrule(identifier=identifier, kind=kind,
                    subject=None if subject is None else list(subject),
                    flag=flag, source="fix", at="2026-10-26T00:00:00Z")


def test_every_arm_flag_has_a_kind():
    flags = json.loads(FIXTURE.read_text())
    assert len(flags) == 2016
    show = _show()
    for f in flags:
        key = flag_key(f, show)
        if f.startswith("duration mismatch on "):
            assert key is None, f
        else:
            assert key is not None and key.kind != "other", f


def test_subjects():
    show = _show()
    assert flag_key("research asserts unknown song: Fixin’ to  Die", show) == \
        FlagKey("research-song", ("fixin' to die",))
    assert flag_key("jerrybase set closer 'Knockin' on Heaven's Door' is not at a set break",
                    show) == FlagKey("jerrybase-closer", ("knockin' on heaven's door",))
    assert flag_key("venue mismatch: archive 'The  Fillmore' vs jerrybase 'Fillmore West'",
                    show) == FlagKey("venue", ("the fillmore", "fillmore west"))
    assert flag_key("recordings of this date disagree on city: 'A, CA' (selected) vs 'B, CO'",
                    show) == FlagKey("city", ("a, ca", "b, co"))
    assert flag_key("research asserts 1973-09-17; item date 1973-01-01 looks like a "
                    "year-only placeholder", show) == FlagKey("research-date", ("1973-09-17",))
    assert flag_key("research asserts wrong date: June 10, 2005", show) == \
        FlagKey("research-date", ("June 10, 2005",))
    assert flag_key("single-set structure for a long show (155 min)", show) == \
        flag_key("single-set structure for a long show (199 min)", show)
    assert flag_key("research asserts 2 sets but structure has 1", show) == \
        FlagKey("research-sets", None)
    assert flag_key("structure has 2 sets but jerrybase shows 3", show).kind == \
        "jerrybase-set-count"
    assert flag_key("briefing claims 2 sets but structure has 1", show) == \
        FlagKey("briefing-other", ("briefing claims N sets but structure has N",))
    assert flag_key("merged track(s) 3, 4 span a set break", show) == FlagKey("merged-tracks", None)
    assert flag_key("duration mismatch on x.mp3: file 1s vs metadata 2s", show) is None
    assert flag_key("something novel", show) == FlagKey("other", ("something novel",))


def test_titles_subject_is_a_subset_match():
    rule = records_for(["unresolved track titles"], _show(unresolved=("a.mp3", "b.mp3")),
                       source="fix", at="t")[0]
    assert rule.subject == ["a.mp3", "b.mp3"]
    def m(show):
        return rule_matches(rule, flag_key("unresolved track titles", show), show.identifier)
    assert m(_show(unresolved=("a.mp3",)))
    assert not m(_show(unresolved=("a.mp3", "c.mp3")))


def test_another_identifier_never_matches():
    flag = "research asserts unknown song: X"
    show = _show("id1")
    rule = records_for([flag], show, source="fix", at="t")[0]
    assert rule_matches(rule, flag_key(flag, show), "id1")
    assert not rule_matches(rule, flag_key(flag, show), "id2")


def test_split_overruled():
    show = _show()
    rule = records_for(["research asserts unknown song: A"], show, source="fix", at="t")
    held, notes = split_overruled(
        ["research asserts unknown song: B", "research asserts unknown song: a"], rule, show)
    assert (held, notes) == (["research asserts unknown song: B"],
                             ["overruled: research asserts unknown song: a"])
    flags = ["z", "y", "x"]
    assert split_overruled(flags, [], show) == (flags, [])


def test_records_for_skips_package_flags_and_merge_dedupes():
    show = _show()
    recs = records_for(["duration mismatch on a.mp3: file 1s vs metadata 2s",
                        "research asserts unknown song: A", "low-confidence setlist"],
                       show, source="triage", at="2026-10-26T00:00:00Z")
    assert [r.kind for r in recs] == ["research-song", "low-confidence-setlist"]
    assert recs[1].subject is None and recs[0].identifier == "id1"
    again = records_for(["research asserts unknown song: a", "alignment?"], show,
                        source="fix", at="later")
    merged = merge_rules(recs, again)
    assert [r.kind for r in merged] == ["research-song", "low-confidence-setlist", "other"]
    assert merged[0].at == "2026-10-26T00:00:00Z"


def test_old_overrides_json_reads_no_overrules():
    ov = Overrides.model_validate_json('{"exclude": ["a.mp3"], "narration": "vague"}')
    assert ov.overrules == []


def test_overrules_round_trip_through_write_artifact(tmp_path):
    ov = Overrides(overrules=[_rule(), _rule(kind="alignment", subject=None)])
    p = tmp_path / "overrides.json"
    write_artifact(p, ov)
    assert Overrides.model_validate_json(p.read_text()) == ov
    assert json.loads(p.read_text())["overrules"][1]["subject"] is None
