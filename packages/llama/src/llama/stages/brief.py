from herder import run_json_task
from llama.models import Briefing, Show, VettingResult
from llama.prompts import load_prompt
from llama.songs import normalize_song
from llama.stages.synthesize import (_COUNT_WORDS, _ORDINALS, _ORDINAL_SET,
                                     _SET_COUNT_CLAIM, _set_label, narration_note)
from llama.util import reviews_digest
from llama.workspace import (ShowWorkspace, read_model, read_overrides,
                             should_run, write_artifact)


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
    contract — must never ship; cross-check against show.json. Same hold
    semantics as synthesize's factual_guard, stricter vague enforcement."""
    problems: list[str] = []
    known = {normalize_song(t.title) for t in show.tracks}
    for song in briefing.mentioned_songs:
        if normalize_song(song) not in known:
            problems.append(f"briefing mentions unknown song: {song}")
    sets = {t.set for t in show.tracks}
    for s in briefing.per_set:
        if s not in sets:
            problems.append(f"briefing references nonexistent set: {s}")
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
        return read_model(show_ws.briefing_json, Briefing)

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
