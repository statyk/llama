import re

from herder import run_json_task
from llama.models import Briefing, Show, VettingResult
from llama.prompts import load_prompt
from llama.songs import normalize_song
from llama.util import reviews_digest
from llama.workspace import (ShowWorkspace, read_model, read_overrides,
                             should_run, write_artifact)

_VAGUE_NOTE = (
    "IMPORTANT — uncertain setlist: this show's song list is incomplete and the "
    "available sources conflict. Do NOT name specific songs, do NOT assert a set "
    "count or set structure, and state nothing as fact that the show data does "
    "not confirm. Speak to the band, the era, the venue, the performance, and its "
    "reputation instead. Leave mentioned_songs empty."
)


def narration_note(narration: str) -> str:
    # Trailing blank line so the prompt's `{{narration_note}}Show data` slot
    # reads cleanly when set; empty string leaves the full-path prompt
    # byte-identical to the pre-narration template (one blank line before
    # "Show data"), rather than injecting an extra blank line.
    return _VAGUE_NOTE + "\n\n" if narration == "vague" else ""


# Set-count claims in briefing prose. "sets of ..." ("two sets of fiddle tunes")
# is a quantity of songs, not a set count, so it never counts as a claim.
_SET_COUNT_CLAIM = re.compile(
    r"\b(both|two|three|four|[234])\s+(?:\w+\s+)?sets\b(?!\s+of\b)", re.I
)
_ORDINAL_SET = re.compile(r"\b(second|third|fourth)\s+set\b", re.I)
_COUNT_WORDS = {"both": 2, "two": 2, "three": 3, "four": 4, "2": 2, "3": 3, "4": 4}
_ORDINALS = {"second": 2, "third": 3, "fourth": 4}


def _set_label(s: str) -> str:
    return "Encore" if s == "encore" else f"Set {s}"


def render_briefing_md(briefing: Briefing, show: Show) -> str:
    """Deterministic markdown render of the briefing model: briefing.md is a
    pure function of briefing.json, so the two artifacts can never disagree."""
    lines = [f"# Briefing: {show.artist} — {show.date}, {show.venue or 'venue unknown'}", ""]
    lines += ["## Context", briefing.context, ""]
    lines += ["## Why this show", briefing.significance, ""]
    for s in sorted(briefing.per_set, key=lambda x: (x == "encore", x)):
        lines += [f"## {_set_label(s)}", *[f"- {p}" for p in briefing.per_set[s]], ""]
    if briefing.notable_moments:
        lines += ["## Notable moments", *[f"- {m}" for m in briefing.notable_moments], ""]
    lines += ["## Reception", briefing.review_sentiment, ""]
    if briefing.cautions:
        lines += ["## Cautions for the scriptwriter", *[f"- {c}" for c in briefing.cautions], ""]
    return "\n".join(lines)


def briefing_guard(briefing: Briefing, show: Show) -> list[str]:
    """A briefing that misnames songs or sets — or breaks the vague-narration
    contract — must never ship; cross-check against show.json."""
    problems: list[str] = []
    known = {normalize_song(t.title) for t in show.tracks}
    for song in briefing.mentioned_songs:
        if normalize_song(song) not in known:
            problems.append(f"briefing mentions unknown song: {song}")
    sets = {t.set for t in show.tracks}
    for s in briefing.per_set:
        if s not in sets:
            problems.append(f"briefing references nonexistent set: {s}")
    # briefing.cautions is deliberately excluded from prose: cautions exist to
    # flag exactly the kind of uncertain/conflicting-source phrasing (e.g.
    # "sources disagree on whether there were three sets") that the set-count
    # checks below would misread as an assertion and false-positive on.
    prose = " ".join([briefing.context, briefing.significance,
                      briefing.review_sentiment, *briefing.notable_moments,
                      *(p for pts in briefing.per_set.values() for p in pts)])
    n_sets = len({t.set for t in show.tracks if t.set != "encore"})
    claimed = {_COUNT_WORDS[m.group(1).lower()] for m in _SET_COUNT_CLAIM.finditer(prose)}
    implied = {_ORDINALS[m.group(1).lower()]: m.group(1).lower()
               for m in _ORDINAL_SET.finditer(prose)}
    if briefing.narration == "vague":
        # Vague means: assert nothing about set structure, name no songs.
        if briefing.per_set:
            problems.append("briefing has per-set talking points under vague narration")
        if briefing.mentioned_songs:
            problems.append("briefing names songs under vague narration")
        if claimed or implied:
            problems.append("briefing asserts set structure under vague narration")
    else:
        if not briefing.per_set:
            problems.append("briefing has no per-set talking points")
        for n in sorted(claimed):
            if n != n_sets:
                problems.append(f"briefing claims {n} sets but structure has {n_sets}")
        for n, word in sorted(implied.items()):
            if n > n_sets:
                problems.append(
                    f"briefing mentions the {word} set but structure has {n_sets} sets")
    return problems


def vetting_summary(show_ws: ShowWorkspace) -> str:
    """Compact rendering of vetting.json for the prompt's {{vetting}} slot, so
    `cautions` are grounded in the vet stage's findings rather than invented."""
    if not show_ws.vetting.exists():
        return "(no vetting data)"
    vr = read_model(show_ws.vetting, VettingResult)
    lines = ["Vetting flags: " + "; ".join(vr.flags) if vr.flags
             else "Research passed vetting with no flags."]
    if vr.adopted_date:
        lines.append(f"The show date was corrected to {vr.adopted_date} "
                     "based on research (archive metadata had a placeholder).")
    if vr.vetting.context:
        lines.append("Context: " + vr.vetting.context)
    return "\n".join(lines)


def run_brief(
    show_ws: ShowWorkspace,
    provider,
    show: Show,
    research_md: str,
    reviews: list[dict],
    force: bool = False,
) -> Briefing:
    if not should_run(show_ws.briefing_json, force):
        briefing = read_model(show_ws.briefing_json, Briefing)
        if not show_ws.briefing_md.exists():
            # briefing.md is a pure function of briefing.json (see
            # render_briefing_md); if only the .md is missing, self-heal by
            # re-rendering it instead of leaving package's hard requirement
            # for both artifacts unresolvable short of a full re-brief.
            write_artifact(show_ws.briefing_md, render_briefing_md(briefing, show))
        return briefing

    narration = read_overrides(show_ws).narration
    inputs = dict(
        show_json=show.model_dump_json(indent=2),
        research=research_md or "(no research available)",
        vetting=vetting_summary(show_ws),
        reviews_digest=reviews_digest(reviews),
        narration_note=narration_note(narration),
    )
    feedback = ""
    for _attempt in range(2):
        briefing = run_json_task(provider, "brief", Briefing,
                                 template=load_prompt("brief"), feedback=feedback, **inputs)
        briefing.narration = narration  # stamped; the LLM's value is never trusted
        problems = briefing_guard(briefing, show)
        if not problems:
            break
        feedback = (
            "IMPORTANT: your previous briefing failed fact-checking: "
            + "; ".join(problems)
            + ". Fix every problem; stay strictly grounded in the inputs."
        )
    if problems:
        current = read_model(show_ws.show, Show)
        current.review_flags = current.review_flags + problems
        current.needs_review = True
        write_artifact(show_ws.show, current)
    write_artifact(show_ws.briefing_json, briefing)
    write_artifact(show_ws.briefing_md, render_briefing_md(briefing, show))
    return briefing
