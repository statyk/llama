import json
from pathlib import Path

from llama.grouping import group_candidates
from llama.ledger import Ledger
from llama.llm.fake import FakeProvider
from llama.models import LedgerEntry
from llama.stages.gather import run_gather
from llama.util import slugify
from llama.workspace import ShowWorkspace

FIXTURES = Path(__file__).parent / "fixtures"
LATE_ID = "gd1970-02-14.141007.late.show.sbd.pcm.dalton.miller.clugston.flac1644"
SPANS_ID = "gd1970-02-14.sbd.miller.97644.flac16"


class FixtureIA:
    """Serves each 1970-02-14 fixture by identifier."""

    def __init__(self):
        self.md = {
            LATE_ID: json.loads((FIXTURES / "gd1970-02-14_late_metadata.json").read_text()),
            SPANS_ID: json.loads((FIXTURES / "gd1970-02-14_spans_metadata.json").read_text()),
        }

    def metadata(self, identifier):
        return self.md[identifier]


def _doc(identifier, md):
    m = md["metadata"]
    desc = m.get("description", "")
    desc = "\n".join(desc) if isinstance(desc, list) else str(desc)
    return {"identifier": identifier, "title": m.get("title", ""),
            "date": "1970-02-14T00:00:00Z", "venue": "Fillmore East",
            "coverage": m.get("coverage"), "description": desc}


def test_one_date_two_events_split_and_slug_independently():
    ia = FixtureIA()
    docs = [_doc(LATE_ID, ia.md[LATE_ID]), _doc(SPANS_ID, ia.md[SPANS_ID])]
    cands = {c.performance_id: c for c in group_candidates("GratefulDead", docs)}

    assert "GratefulDead/1970-02-14/e2" in cands       # clean late show
    assert "GratefulDead/1970-02-14/spans" in cands    # complete-evening tape held
    e2, spans = cands["GratefulDead/1970-02-14/e2"], cands["GratefulDead/1970-02-14/spans"]
    assert e2.recordings[0].identifier == LATE_ID
    assert spans.recordings[0].identifier == SPANS_ID
    # Distinct performance identity -> distinct workspace/library slug.
    assert slugify(e2.performance_id) != slugify(spans.performance_id)


def test_per_event_gather_stamps_event_identity(tmp_path):
    ia = FixtureIA()
    docs = [_doc(LATE_ID, ia.md[LATE_ID]), _doc(SPANS_ID, ia.md[SPANS_ID])]
    cands = {c.performance_id: c for c in group_candidates("GratefulDead", docs)}

    e2 = cands["GratefulDead/1970-02-14/e2"]
    late_show = run_gather(ShowWorkspace(tmp_path / "e2"), ia, FakeProvider(), e2, LATE_ID,
                           audio_format="flac", jerrybase_enabled=True)
    assert late_show.performance_id == "GratefulDead/1970-02-14/e2"
    assert late_show.venue == "Fillmore East"          # events[1] = event 802
    assert not any(f.startswith("multi-event date") for f in late_show.review_flags)

    spans = cands["GratefulDead/1970-02-14/spans"]
    held = run_gather(ShowWorkspace(tmp_path / "spans"), ia, FakeProvider(), spans, SPANS_ID,
                      audio_format="flac", jerrybase_enabled=True)
    assert held.needs_review is True
    assert "tape spans 2 events" in held.review_flags


def test_two_events_get_distinct_ledger_rows(tmp_path):
    led = Ledger(tmp_path / "ledger.jsonl")
    for pid in ("GratefulDead/1970-02-14/e2", "GratefulDead/1970-02-14/spans"):
        led.record(LedgerEntry(performance_id=pid, artist="Grateful Dead",
                               date="1970-02-14", status="selected", run="r",
                               recorded_at="2026-07-19T00:00:00Z"))
    assert led.played_ids() == {"GratefulDead/1970-02-14/e2", "GratefulDead/1970-02-14/spans"}
