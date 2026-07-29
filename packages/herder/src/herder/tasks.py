import re
from collections.abc import Sequence

from pydantic import BaseModel, ValidationError

from herder.provider import LLMProvider, TaskFailed

ProviderOrLadder = LLMProvider | Sequence[LLMProvider]


def _as_ladder(provider: ProviderOrLadder) -> list[LLMProvider]:
    if isinstance(provider, (list, tuple)):
        if not provider:
            raise ValueError("empty provider ladder")
        return list(provider)
    return [provider]


def render(template: str, **values) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{{" + key + "}}", str(val))
    missing = re.findall(r"\{\{(\w+)\}\}", out)
    if missing:
        raise ValueError(f"unfilled placeholders: {missing}")
    return out


def extract_json(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return text.strip()
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start : end + 1] if end > start else text.strip()


def run_json_task(
    provider: ProviderOrLadder,
    task: str,
    schema: type[BaseModel],
    *,
    template: str,
    retries: int = 2,
    **inputs,
) -> BaseModel:
    ladder = _as_ladder(provider)
    prompt = render(template, **inputs)
    attempt_prompt = prompt
    raw = ""
    for attempt in range(retries + 1):
        raw = ladder[min(attempt, len(ladder) - 1)].complete(attempt_prompt)
        try:
            return schema.model_validate_json(extract_json(raw))
        except (ValidationError, ValueError) as err:
            attempt_prompt = (
                prompt
                + f"\n\nYour previous response was invalid: {err}\n"
                + "Respond with ONLY valid JSON matching the requested schema."
            )
    raise TaskFailed(f"LLM task {task!r} failed after {retries + 1} attempts", raw_output=raw)


def run_research_task(
    provider: ProviderOrLadder,
    task: str,
    *,
    template: str,
    required_sections: Sequence[str] = (),
    retries: int = 2,
    **inputs,
) -> str:
    """Run a research task; when required_sections is given, reject replies
    that lack them (status narration, refusals, partial reports) and retry
    with feedback, escalating the ladder like run_json_task."""
    ladder = _as_ladder(provider)
    prompt = render(template, **inputs)
    attempt_prompt = prompt
    raw = ""
    for attempt in range(retries + 1):
        raw = ladder[min(attempt, len(ladder) - 1)].research(attempt_prompt)
        missing = [s for s in required_sections if s.lower() not in raw.lower()]
        if not missing:
            return raw
        attempt_prompt = (
            prompt
            + "\n\nYour previous reply was not the report (missing sections: "
            + ", ".join(missing)
            + "). Do the research now, in this session, and reply with ONLY the"
            + " finished markdown report."
        )
    raise TaskFailed(f"LLM task {task!r} failed after {retries + 1} attempts", raw_output=raw)
