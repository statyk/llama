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
