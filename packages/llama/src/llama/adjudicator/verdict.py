"""The adjudicator's verdict schema and its one LLM call. The model's reply is parsed
permissively (unknown keys are ignored) but every enum is closed: an unknown op, evidence
kind, confidence or flag verdict fails validation and `run_json_task` retries it."""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from herder import resolve_model, run_json_task
from llama.adjudicator.bundle import Bundle
from llama.config import Config
from llama.prompts import load_prompt

EvidenceKind = Literal["taper-description", "original-tag", "derivative-tag", "sibling-tracks",
                       "setlistfm", "jerrybase", "review"]
Confidence = Literal["high", "medium", "low"]

PROPOSE_ONLY_OPS = frozenset({"set_date", "untitled", "narration", "rm", "redo_research"})


class _Lax(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Evidence(_Lax):
    kind: EvidenceKind
    quote: str

    @field_validator("quote")
    @classmethod
    def _stripped_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("quote is empty")
        return v


class _Edit(_Lax):
    confidence: Confidence
    evidence: list[Evidence] = Field(min_length=1)
    why: str


class Include(_Edit):
    op: Literal["include"]
    file: str


class Exclude(_Edit):
    op: Literal["exclude"]
    file: str


class SetTitle(_Edit):
    op: Literal["set_title"]
    file: str
    title: str


class Structure(_Edit):
    op: Literal["structure"]
    breaks_after: list[str]
    encore_after: str | None = None


class Venue(_Edit):
    op: Literal["venue"]
    venue: str


class City(_Edit):
    op: Literal["city"]
    city: str


class SwitchRecording(_Edit):
    op: Literal["switch_recording"]
    identifier: str


class OverruleFlag(_Edit):
    op: Literal["overrule"]
    flag: str


class ProposeOnly(_Lax):
    op: Literal["set_date", "untitled", "narration", "rm", "redo_research"]
    value: str | None = None
    confidence: Confidence
    evidence: list[Evidence] = Field(default_factory=list)
    why: str


Edit = Annotated[Union[Include, Exclude, SetTitle, Structure, Venue, City, SwitchRecording,
                       OverruleFlag, ProposeOnly], Field(discriminator="op")]


class FlagJudgement(_Lax):
    flag: str
    verdict: Literal["real-fixed-by-action", "spurious", "real-not-fixable", "undecidable"]
    confidence: Confidence
    why: str


class Verdict(_Lax):
    flags: list[FlagJudgement]
    edits: list[Edit]
    kind: Literal["fix", "overrule", "hold"]
    show_correct_after: Literal["yes", "no", "unsure"]
    partial_tape: bool = False
    better_sibling: str | None = None
    decide: str | None = None          # what Shawn must decide, for a hold
    rationale: str
    root_causes: list[str] = Field(default_factory=list)


def call_adjudicator(provider, bundle: Bundle) -> Verdict:
    """One `adjudicate` call. RateLimited, TaskFailed, HerderError and a render ValueError
    propagate; the runner classifies them."""
    return run_json_task(provider, "adjudicate", Verdict, template=load_prompt("adjudicate"),
                         bundle=bundle.text)


def model_label(config: Config) -> str:
    backend, model = resolve_model(config.llm_settings(), "adjudicate")
    return f"{backend}:{model}"
