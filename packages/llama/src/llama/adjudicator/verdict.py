"""The adjudicator's verdict schema and its one LLM call. The model's reply is parsed
permissively (unknown keys are ignored) but every enum is closed: an unknown op, evidence
kind, confidence or flag verdict fails validation and `run_json_task` retries it."""
from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import (AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field,
                      field_validator, model_validator)

from herder import resolve_model, run_json_task
from llama.adjudicator.bundle import Bundle
from llama.config import Config
from llama.prompts import load_prompt



def _norm_token(v):
    """A Literal value as the model may spell it (`"High"`, `" venue "`): strip, lower-case."""
    return v.strip().lower() if isinstance(v, str) else v


def _null_to(default):
    return BeforeValidator(lambda v: default() if v is None else v)


def _flag_text(v):
    """A flag as copied from the review-flags section, with the bullet's `- ` dropped."""
    return re.sub(r"^\s*-\s+", "", v) if isinstance(v, str) else v


def _blank_to_none(v):
    """An optional identifier as the model may spell it: stripped, and blank means None."""
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def _non_empty(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("must not be empty")
    return v


_Tok = BeforeValidator(_norm_token)
Text = Annotated[str, AfterValidator(_non_empty)]
FlagText = Annotated[str, BeforeValidator(_flag_text), AfterValidator(_non_empty)]

EvidenceKind = Literal["taper-description", "original-tag", "derivative-tag", "sibling-tracks",
                       "setlistfm", "jerrybase", "review"]
Confidence = Literal["high", "medium", "low"]
_Conf = Annotated[Confidence, _Tok]

PROPOSE_ONLY_OPS = frozenset({"set_date", "untitled", "narration", "rm", "redo_research"})


class _Lax(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Evidence(_Lax):
    kind: Annotated[EvidenceKind, _Tok]
    quote: Text


class _Edit(_Lax):
    confidence: _Conf
    evidence: list[Evidence] = Field(min_length=1)
    why: str


class Include(_Edit):
    op: Literal["include"]
    file: Text


class Exclude(_Edit):
    op: Literal["exclude"]
    file: Text


class SetTitle(_Edit):
    op: Literal["set_title"]
    file: Text
    title: Text


class Structure(_Edit):
    op: Literal["structure"]
    breaks_after: list[Text]
    encore_after: Text | None = None

    @model_validator(mode="after")
    def _encore_not_a_break(self):
        if self.encore_after is not None and self.encore_after in self.breaks_after:
            raise ValueError(f"encore_after {self.encore_after!r} is also in breaks_after")
        return self


class Venue(_Edit):
    op: Literal["venue"]
    venue: Text


class City(_Edit):
    op: Literal["city"]
    city: Text


class SwitchRecording(_Edit):
    op: Literal["switch_recording"]
    identifier: Text


class OverruleFlag(_Edit):
    op: Literal["overrule"]
    flag: FlagText


class ProposeOnly(_Lax):
    op: Literal["set_date", "untitled", "narration", "rm", "redo_research"]
    value: str | None = None
    confidence: _Conf
    evidence: Annotated[list[Evidence], _null_to(list)] = Field(default_factory=list)
    why: str


Edit = Annotated[Union[Include, Exclude, SetTitle, Structure, Venue, City, SwitchRecording,
                       OverruleFlag, ProposeOnly], Field(discriminator="op")]


class FlagJudgement(_Lax):
    flag: FlagText
    verdict: Annotated[Literal["real-fixed-by-action", "spurious", "real-not-fixable",
                               "undecidable"], _Tok]
    confidence: _Conf
    why: str


class Verdict(_Lax):
    flags: Annotated[list[FlagJudgement], _null_to(list)]
    edits: Annotated[list[Edit], _null_to(list)]
    kind: Annotated[Literal["fix", "overrule", "hold"], _Tok]
    show_correct_after: Annotated[Literal["yes", "no", "unsure"], _Tok]
    partial_tape: Annotated[bool, _null_to(lambda: False)] = False
    better_sibling: Annotated[str | None, BeforeValidator(_blank_to_none)] = None
    decide: str | None = None          # what Shawn must decide, for a hold
    rationale: str
    root_causes: Annotated[list[str], _null_to(list)] = Field(default_factory=list)

    @field_validator("edits", mode="before")
    @classmethod
    def _normalise_ops(cls, v):
        """The union dispatches on the raw `op` before any field validator runs, so a
        `" Venue "` op is normalised here first."""
        if isinstance(v, list):
            v = [{**e, "op": _norm_token(e["op"])} if isinstance(e, dict) and "op" in e else e
                 for e in v]
        return v


def call_adjudicator(provider, bundle: Bundle) -> Verdict:
    """One `adjudicate` call. RateLimited, TaskFailed, HerderError and a render ValueError
    propagate; the runner classifies them."""
    return run_json_task(provider, "adjudicate", Verdict, template=load_prompt("adjudicate"),
                         bundle=bundle.text)


def model_label(config: Config) -> str:
    backend, model = resolve_model(config.llm_settings(), "adjudicate")
    return f"{backend}:{model}"
