from pathlib import Path

from llama.llm.fake import FakeProvider
from llama.models import Criteria
from llama.stages.interpret import run_interpret
from llama.workspace import RunWorkspace

CRITERIA_JSON = """{"query": "wrong echo", "collection": "GratefulDead", "artist": "Grateful Dead",
"date_from": "1973-01-01", "date_to": "1974-12-31",
"setlist_constraints": [{"sequence": ["China Cat Sunflower", "I Know You Rider"]}],
"soft_preferences": null, "min_avg_rating": 3.5, "min_reviews": 3, "count": 1}"""


def test_interpret_writes_criteria_and_pins_query(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[CRITERIA_JSON])
    crit = run_interpret(ws, fake, "GD 73-74 with a china>rider")
    assert crit.query == "GD 73-74 with a china>rider"  # original query wins over LLM echo
    assert crit.collection == "GratefulDead"
    assert crit.setlist_constraints[0].sequence[0] == "China Cat Sunflower"
    assert ws.criteria.exists()


def test_interpret_skips_when_artifact_exists(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "r1")
    fake = FakeProvider(completes=[CRITERIA_JSON])
    run_interpret(ws, fake, "GD 73-74 with a china>rider")
    # no queued responses left: a second call must read the artifact, not the provider
    again = run_interpret(ws, FakeProvider(), "ignored")
    assert isinstance(again, Criteria)
    assert again.collection == "GratefulDead"
