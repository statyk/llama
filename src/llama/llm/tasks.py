import re
from importlib import resources

from pydantic import BaseModel, ValidationError

from llama.llm.provider import LLMProvider, TaskFailed


def load_prompt(name: str) -> str:
    return resources.files("llama.prompts").joinpath(f"{name}.md").read_text()


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
    provider: LLMProvider,
    task: str,
    schema: type[BaseModel],
    *,
    retries: int = 2,
    **inputs,
) -> BaseModel:
    prompt = render(load_prompt(task), **inputs)
    attempt_prompt = prompt
    raw = ""
    for _ in range(retries + 1):
        raw = provider.complete(attempt_prompt)
        try:
            return schema.model_validate_json(extract_json(raw))
        except (ValidationError, ValueError) as err:
            attempt_prompt = (
                prompt
                + f"\n\nYour previous response was invalid: {err}\n"
                + "Respond with ONLY valid JSON matching the requested schema."
            )
    raise TaskFailed(f"LLM task {task!r} failed after {retries + 1} attempts", raw_output=raw)


def run_research_task(provider: LLMProvider, task: str, **inputs) -> str:
    return provider.research(render(load_prompt(task), **inputs))
