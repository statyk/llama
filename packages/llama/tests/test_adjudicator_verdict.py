import json
import re
import typing

import pytest
from pydantic import ValidationError

from herder import FakeProvider, TaskFailed
from herder.limits import RateLimited
from llama.adjudicator.bundle import EVIDENCE_KINDS, Bundle
from llama.adjudicator.verdict import (PROPOSE_ONLY_OPS, Evidence, EvidenceKind, Verdict,
                                       call_adjudicator, model_label)
from llama.config import Config
from llama.prompts import load_prompt

EV = [{"kind": "taper-description", "quote": "Set II"}]
_E = {"confidence": "high", "evidence": EV, "why": "w"}

EDITS = [
    {"op": "include", "file": "d1t05.mp3", **_E},
    {"op": "exclude", "file": "d1t06.mp3", **_E},
    {"op": "set_title", "file": "d1t07.mp3", "title": "Dark Star", **_E},
    {"op": "structure", "breaks_after": ["d1t09.mp3"], "encore_after": "d2t09.mp3", **_E},
    {"op": "venue", "venue": "RFK Stadium", **_E},
    {"op": "city", "city": "Washington, DC", **_E},
    {"op": "switch_recording", "identifier": "gd73-06-10.sib.flac", **_E},
    {"op": "overrule", "flag": "venue mismatch: x", **_E},
    {"op": "set_date", "value": "1973-06-11", "confidence": "low", "why": "w"},
    {"op": "untitled", "confidence": "low", "why": "w"},
    {"op": "narration", "value": "vague", "confidence": "low", "why": "w"},
    {"op": "rm", "confidence": "low", "why": "w"},
    {"op": "redo_research", "confidence": "low", "why": "w"},
]
OPS = [e["op"] for e in EDITS]

BASE = {"flags": [{"flag": "venue mismatch: x", "verdict": "spurious", "confidence": "high",
                   "why": "w"}],
        "edits": [], "kind": "fix", "show_correct_after": "yes", "rationale": "r"}
FULL_VERDICT = {**BASE, "edits": EDITS, "partial_tape": True,
                "better_sibling": "gd73-06-10.sib.flac", "decide": "d",
                "root_causes": ["set-source-precedence"]}


def _bundle(text: str) -> Bundle:
    return Bundle(slug="s", show=None, overrides=None, view=None, provenance=None,
                  selection={}, files={}, sections={}, text=text)


def test_prompt_has_only_the_bundle_placeholder_and_the_rulings():
    text = load_prompt("adjudicate")
    assert set(re.findall(r"\{\{(\w+)\}\}", text)) == {"bundle"}
    assert text.rstrip().endswith("{{bundle}}")
    for phrase in ("presumed correct", "Discs are not sets", "partial_tape", "better_sibling",
                   "never track numbers", "copy each flag verbatim from the review-flags section",
                   "rather repeat a taper's error than mis-correct it",
                   "whole token", "unknown length", "## evidence: <kind>",
                   *EVIDENCE_KINDS,
                   *("include", "exclude", "set_title", "structure", "venue", "city",
                     "switch_recording", "overrule", *PROPOSE_ONLY_OPS)):
        assert phrase in text, phrase


def test_prompt_shell_era_instructions_are_gone():
    text = load_prompt("adjudicate")
    for gone in ("llama fix", "expect", "--set-breaks", "~/.llama", "verdict files"):
        assert gone not in text, gone


def test_prompt_example_json_is_a_valid_verdict_using_every_field():
    text = load_prompt("adjudicate")
    block = re.search(r"```json\n(.*?)```", text, re.S).group(1)
    data = json.loads(block)
    v = Verdict.model_validate(data)
    assert set(data) == set(Verdict.model_fields)
    assert v.edits and v.flags


def test_evidence_kind_literal_matches_the_bundle_kinds():
    assert typing.get_args(EvidenceKind) == EVIDENCE_KINDS


def test_verdict_parses_every_op_and_rejects_unknown_op():
    v = Verdict.model_validate(FULL_VERDICT)
    assert [e.op for e in v.edits] == OPS
    assert v.partial_tape and v.better_sibling == "gd73-06-10.sib.flac" and v.decide == "d"
    assert v.edits[3].breaks_after == ["d1t09.mp3"] and v.edits[3].encore_after == "d2t09.mp3"
    with pytest.raises(ValidationError):
        Verdict.model_validate({**FULL_VERDICT, "edits": [{"op": "delete", "file": "a", **_E}]})


def test_propose_only_ops_constant():
    assert PROPOSE_ONLY_OPS == frozenset({"set_date", "untitled", "narration", "rm",
                                          "redo_research"})


def test_defaults_and_extra_keys_ignored():
    v = Verdict.model_validate({**BASE, "surprise": 1,
                                "edits": [{"op": "venue", "venue": "X", "extra": 2, **_E}]})
    assert v.partial_tape is False and v.better_sibling is None and v.decide is None
    assert v.root_causes == []
    s = Verdict.model_validate({**BASE, "edits": [{"op": "structure", "breaks_after": [], **_E}]})
    assert s.edits[0].encore_after is None


def test_typed_edit_needs_evidence_but_propose_only_does_not():
    for edit in EDITS[:8]:
        bad = {**edit, "evidence": []}
        with pytest.raises(ValidationError):
            Verdict.model_validate({**BASE, "edits": [bad]})
        missing = {k: v for k, v in edit.items() if k != "evidence"}
        with pytest.raises(ValidationError):
            Verdict.model_validate({**BASE, "edits": [missing]})
    v = Verdict.model_validate({**BASE, "edits": [{"op": "rm", "confidence": "low", "why": "w"}]})
    assert v.edits[0].evidence == [] and v.edits[0].value is None


def test_closed_enums():
    with pytest.raises(ValidationError):
        Evidence(kind="web", quote="q")
    for bad in ({"kind": "maybe"}, {"show_correct_after": "probably"},
                {"flags": [{**BASE["flags"][0], "verdict": "fine"}]},
                {"flags": [{**BASE["flags"][0], "confidence": "certain"}]},
                {"edits": [{**EDITS[4], "confidence": "certain"}]}):
        with pytest.raises(ValidationError):
            Verdict.model_validate({**BASE, **bad})


def test_quote_is_stripped_and_non_empty():
    assert Evidence(kind="review", quote="  Set II \n").quote == "Set II"
    for q in ("", "   \n"):
        with pytest.raises(ValidationError):
            Evidence(kind="review", quote=q)


def test_call_renders_a_bundle_with_placeholders():
    fake = FakeProvider(completes=[json.dumps(FULL_VERDICT)])
    v = call_adjudicator([fake], _bundle("desc { {slug} } {x}"))
    assert isinstance(v, Verdict) and [e.op for e in v.edits] == OPS
    prompt = fake.calls[0][1]
    assert "desc { {slug} } {x}" in prompt and "{{bundle}}" not in prompt
    assert prompt.rstrip().endswith("desc { {slug} } {x}")


def test_call_retries_then_raises_taskfailed():
    fake = FakeProvider(completes=["not json"] * 3)
    with pytest.raises(TaskFailed):
        call_adjudicator([fake], _bundle("b"))
    assert len(fake.calls) == 3


def test_call_lets_rate_limited_and_render_errors_propagate():
    fake = FakeProvider(completes=[RateLimited("window empty")])
    with pytest.raises(RateLimited):
        call_adjudicator([fake], _bundle("b"))
    assert len(fake.calls) == 1
    with pytest.raises(ValueError, match="unfilled placeholders"):
        call_adjudicator([FakeProvider()], _bundle("raw {{oops}}"))


def test_model_label():
    assert model_label(Config()) == "claude_cli:opus"
    assert model_label(Config.model_validate({"llm": {"adjudicate": {"model": "sonnet"}}})) \
        == "claude_cli:sonnet"
