import pytest
from pydantic import BaseModel

from llama.llm import tasks
from llama.llm.fake import FakeProvider
from llama.llm.provider import TaskFailed


class Answer(BaseModel):
    value: int


def use_template(monkeypatch, template: str):
    monkeypatch.setattr(tasks, "load_prompt", lambda name: template)


def test_render_replaces_all_and_catches_missing():
    out = tasks.render("Hello {{name}}, {{name}}! n={{n}}", name="dj", n=2)
    assert out == "Hello dj, dj! n=2"
    with pytest.raises(ValueError, match="unfilled"):
        tasks.render("Hello {{name}} and {{other}}", name="dj")


def test_extract_json_variants():
    assert tasks.extract_json('{"a": 1}') == '{"a": 1}'
    assert tasks.extract_json('Sure!\n```json\n{"a": 1}\n```\nDone.') == '{"a": 1}'
    assert tasks.extract_json('prefix [1, 2] suffix') == "[1, 2]"


def test_run_json_task_happy_path(monkeypatch):
    use_template(monkeypatch, "Q: {{q}}")
    fake = FakeProvider(completes=['{"value": 42}'])
    result = tasks.run_json_task(fake, "interpret", Answer, q="six times seven")
    assert result.value == 42
    assert fake.calls == [("complete", "Q: six times seven")]


def test_run_json_task_retries_with_feedback(monkeypatch):
    use_template(monkeypatch, "Q: {{q}}")
    fake = FakeProvider(completes=["not json at all", '{"value": 7}'])
    result = tasks.run_json_task(fake, "interpret", Answer, q="x")
    assert result.value == 7
    assert "previous response was invalid" in fake.calls[1][1]


def test_run_json_task_exhausts_and_preserves_raw(monkeypatch):
    use_template(monkeypatch, "Q: {{q}}")
    fake = FakeProvider(completes=["bad", "worse", "worst"])
    with pytest.raises(TaskFailed) as exc:
        tasks.run_json_task(fake, "interpret", Answer, q="x", retries=2)
    assert exc.value.raw_output == "worst"


def test_run_research_task(monkeypatch):
    use_template(monkeypatch, "Research {{topic}}")
    fake = FakeProvider(researches=["# Findings"])
    assert tasks.run_research_task(fake, "deep_research", topic="RFK 73") == "# Findings"
    assert fake.calls == [("research", "Research RFK 73")]


def test_run_json_task_escalates_on_final_attempt(monkeypatch):
    use_template(monkeypatch, "Q: {{q}}")
    base = FakeProvider(completes=["bad", "still bad"])
    escalated = FakeProvider(completes=['{"value": 9}'])
    result = tasks.run_json_task([base, base, escalated], "interpret", Answer, q="x")
    assert result.value == 9
    assert len(base.calls) == 2
    assert len(escalated.calls) == 1
    assert "previous response was invalid" in escalated.calls[0][1]


def test_run_json_task_short_ladder_reuses_last_rung(monkeypatch):
    use_template(monkeypatch, "Q: {{q}}")
    only = FakeProvider(completes=["bad", "bad", '{"value": 3}'])
    assert tasks.run_json_task([only], "interpret", Answer, q="x").value == 3


def test_run_research_task_uses_first_rung(monkeypatch):
    use_template(monkeypatch, "Research {{topic}}")
    base = FakeProvider(researches=["# Findings"])
    escalated = FakeProvider()
    assert tasks.run_research_task([base, escalated], "deep_research", topic="x") == "# Findings"
    assert escalated.calls == []


NARRATION = ("The research workflow is running in the background — "
             "I'll have the results when it finishes.")
REPORT = "## Reputation\nx\n## Performance highlights\ny\n## Context\nz\n## Recording notes\nw"
SECTIONS = ["## Reputation", "## Performance highlights", "## Context", "## Recording notes"]


def test_run_research_task_rejects_narration_and_retries(monkeypatch):
    use_template(monkeypatch, "Research {{topic}}")
    fake = FakeProvider(researches=[NARRATION, REPORT])
    out = tasks.run_research_task(fake, "deep_research", required_sections=SECTIONS, topic="x")
    assert out == REPORT
    assert len(fake.calls) == 2
    assert "missing sections" in fake.calls[1][1]
    assert "## Reputation" in fake.calls[1][1]


def test_run_research_task_exhausts_and_preserves_raw(monkeypatch):
    use_template(monkeypatch, "Research {{topic}}")
    fake = FakeProvider(researches=[NARRATION, NARRATION, NARRATION])
    with pytest.raises(TaskFailed) as exc:
        tasks.run_research_task(fake, "deep_research", required_sections=SECTIONS,
                                retries=2, topic="x")
    assert exc.value.raw_output == NARRATION


def test_run_research_task_escalates_on_final_attempt(monkeypatch):
    use_template(monkeypatch, "Research {{topic}}")
    base = FakeProvider(researches=[NARRATION, NARRATION])
    escalated = FakeProvider(researches=[REPORT])
    out = tasks.run_research_task([base, base, escalated], "deep_research",
                                  required_sections=SECTIONS, topic="x")
    assert out == REPORT
    assert len(base.calls) == 2 and len(escalated.calls) == 1


def test_make_providers_builds_ladders():
    from llama.config import Config
    from llama.pipeline import make_providers
    providers = make_providers(Config())
    # interpret is a medium task: base, base, escalated-to-high
    assert [p.model for p in providers["interpret"]] == ["sonnet", "sonnet", "opus"]
    # synthesize is already high: no headroom
    assert [p.model for p in providers["synthesize"]] == ["opus", "opus", "opus"]
