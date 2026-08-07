import pytest
from pydantic import BaseModel

from herder import FakeProvider, HerderError, ResearchNotSupported, TaskFailed, tasks


class Answer(BaseModel):
    value: int


def test_render_replaces_all_and_catches_missing():
    out = tasks.render("Hello {{name}}, {{name}}! n={{n}}", name="dj", n=2)
    assert out == "Hello dj, dj! n=2"
    with pytest.raises(ValueError, match="unfilled"):
        tasks.render("Hello {{name}} and {{other}}", name="dj")


def test_extract_json_variants():
    assert tasks.extract_json('{"a": 1}') == '{"a": 1}'
    assert tasks.extract_json('Sure!\n```json\n{"a": 1}\n```\nDone.') == '{"a": 1}'
    assert tasks.extract_json('prefix [1, 2] suffix') == "[1, 2]"


def test_run_json_task_happy_path():
    fake = FakeProvider(completes=['{"value": 42}'])
    result = tasks.run_json_task(fake, "interpret", Answer, template="Q: {{q}}", q="six times seven")
    assert result.value == 42
    assert fake.calls == [("complete", "Q: six times seven")]


def test_run_json_task_retries_with_feedback():
    fake = FakeProvider(completes=["not json at all", '{"value": 7}'])
    result = tasks.run_json_task(fake, "interpret", Answer, template="Q: {{q}}", q="x")
    assert result.value == 7
    assert "previous response was invalid" in fake.calls[1][1]


def test_run_json_task_exhausts_and_preserves_raw():
    fake = FakeProvider(completes=["bad", "worse", "worst"])
    with pytest.raises(TaskFailed) as exc:
        tasks.run_json_task(fake, "interpret", Answer, template="Q: {{q}}", q="x", retries=2)
    assert exc.value.raw_output == "worst"


def test_run_research_task():
    fake = FakeProvider(researches=["# Findings"])
    assert tasks.run_research_task(fake, "deep_research", template="Research {{topic}}",
                                   topic="RFK 73") == "# Findings"
    assert fake.calls == [("research", "Research RFK 73")]


def test_run_json_task_escalates_on_final_attempt():
    base = FakeProvider(completes=["bad", "still bad"])
    escalated = FakeProvider(completes=['{"value": 9}'])
    result = tasks.run_json_task([base, base, escalated], "interpret", Answer,
                                 template="Q: {{q}}", q="x")
    assert result.value == 9
    assert len(base.calls) == 2
    assert len(escalated.calls) == 1
    assert "previous response was invalid" in escalated.calls[0][1]


def test_run_json_task_short_ladder_reuses_last_rung():
    only = FakeProvider(completes=["bad", "bad", '{"value": 3}'])
    assert tasks.run_json_task([only], "interpret", Answer, template="Q: {{q}}", q="x").value == 3


def test_run_research_task_uses_first_rung():
    base = FakeProvider(researches=["# Findings"])
    escalated = FakeProvider()
    assert tasks.run_research_task([base, escalated], "deep_research",
                                   template="Research {{topic}}", topic="x") == "# Findings"
    assert escalated.calls == []


NARRATION = ("The research workflow is running in the background — "
             "I'll have the results when it finishes.")
REPORT = "## Reputation\nx\n## Performance highlights\ny\n## Context\nz\n## Recording notes\nw"
SECTIONS = ["## Reputation", "## Performance highlights", "## Context", "## Recording notes"]


def test_run_research_task_rejects_narration_and_retries():
    fake = FakeProvider(researches=[NARRATION, REPORT])
    out = tasks.run_research_task(fake, "deep_research", template="Research {{topic}}",
                                  required_sections=SECTIONS, topic="x")
    assert out == REPORT
    assert len(fake.calls) == 2
    assert "missing sections" in fake.calls[1][1]
    assert "## Reputation" in fake.calls[1][1]


def test_run_research_task_exhausts_and_preserves_raw():
    fake = FakeProvider(researches=[NARRATION, NARRATION, NARRATION])
    with pytest.raises(TaskFailed) as exc:
        tasks.run_research_task(fake, "deep_research", template="Research {{topic}}",
                                required_sections=SECTIONS, retries=2, topic="x")
    assert exc.value.raw_output == NARRATION


def test_run_research_task_escalates_on_final_attempt():
    base = FakeProvider(researches=[NARRATION, NARRATION])
    escalated = FakeProvider(researches=[REPORT])
    out = tasks.run_research_task([base, base, escalated], "deep_research",
                                  template="Research {{topic}}",
                                  required_sections=SECTIONS, topic="x")
    assert out == REPORT
    assert len(base.calls) == 2 and len(escalated.calls) == 1


# --- transport-failure retries -------------------------------------------
# A dropped connection mid-response (observed: claude exits 1 with
# "API Error: Connection closed mid-response") used to escape run_json_task's
# loop entirely, because the provider call sat outside the try. One network
# blip killed a whole show that was otherwise minutes from packaging.


def _no_sleep(monkeypatch):
    monkeypatch.setattr(tasks, "_sleep", lambda _s: None)


def test_transport_failure_is_retried_on_the_same_prompt(monkeypatch):
    _no_sleep(monkeypatch)
    fake = FakeProvider(completes=[HerderError("connection closed"), '{"value": 5}'])
    assert tasks.run_json_task(fake, "brief", Answer, template="Q: {{q}}", q="x").value == 5
    # retried verbatim: a dropped connection says nothing about prompt quality,
    # so it must not carry the "your previous response was invalid" feedback
    assert [c[1] for c in fake.calls] == ["Q: x", "Q: x"]


def test_transport_failure_exhausts_and_raises_the_last_error(monkeypatch):
    _no_sleep(monkeypatch)
    fake = FakeProvider(completes=[HerderError("boom 1"), HerderError("boom 2"),
                                   HerderError("boom 3")])
    with pytest.raises(HerderError, match="boom 3"):
        tasks.run_json_task(fake, "brief", Answer, template="Q: {{q}}", q="x")
    assert len(fake.calls) == 3


def test_transport_retry_does_not_consume_validation_attempts(monkeypatch):
    _no_sleep(monkeypatch)
    # one blip, then two bad replies, then a good one: the blip must not eat a
    # validation attempt, so the third reply still gets served
    fake = FakeProvider(completes=[HerderError("blip"), "bad", "worse", '{"value": 1}'])
    assert tasks.run_json_task(fake, "brief", Answer, template="Q: {{q}}", q="x").value == 1


def test_transport_retry_stays_on_the_same_ladder_rung(monkeypatch):
    _no_sleep(monkeypatch)
    base = FakeProvider(completes=[HerderError("blip"), '{"value": 2}'])
    escalated = FakeProvider(completes=['{"value": 99}'])
    result = tasks.run_json_task([base, base, escalated], "brief", Answer,
                                 template="Q: {{q}}", q="x")
    # a network blip must not buy a tier upgrade
    assert result.value == 2
    assert escalated.calls == []


def test_task_failed_is_not_retried_as_transport(monkeypatch):
    _no_sleep(monkeypatch)
    fake = FakeProvider(completes=[TaskFailed("definitive"), '{"value": 1}'])
    with pytest.raises(TaskFailed, match="definitive"):
        tasks.run_json_task(fake, "brief", Answer, template="Q: {{q}}", q="x")
    assert len(fake.calls) == 1


def test_research_not_supported_is_not_retried(monkeypatch):
    _no_sleep(monkeypatch)
    fake = FakeProvider(researches=[ResearchNotSupported("no web"), "# Findings"])
    with pytest.raises(ResearchNotSupported):
        tasks.run_research_task(fake, "deep_research", template="R {{t}}", t="x")
    assert len(fake.calls) == 1


def test_research_transport_failure_is_retried(monkeypatch):
    _no_sleep(monkeypatch)
    fake = FakeProvider(researches=[HerderError("connection closed"), "# Findings"])
    assert tasks.run_research_task(fake, "deep_research", template="R {{t}}", t="x") == "# Findings"
    assert len(fake.calls) == 2


def test_transport_retry_backs_off_between_attempts(monkeypatch):
    slept = []
    monkeypatch.setattr(tasks, "_sleep", slept.append)
    fake = FakeProvider(completes=[HerderError("a"), HerderError("b"), '{"value": 1}'])
    tasks.run_json_task(fake, "brief", Answer, template="Q: {{q}}", q="x")
    # backs off before each retry, and waits longer the second time
    assert len(slept) == 2 and slept[1] > slept[0]
