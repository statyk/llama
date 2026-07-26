import re

from llama.llm.tasks import run_json_task
from llama.models import DJNotes, Show
from llama.presenters import Presenter
from llama.songs import normalize_song
from llama.util import reviews_digest
from llama.workspace import ShowWorkspace, read_model, read_overrides, should_run, write_artifact

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


# Set-count claims in script prose. "sets of ..." ("two sets of fiddle tunes")
# is a quantity of songs, not a set count, so it never counts as a claim.
_SET_COUNT_CLAIM = re.compile(
    r"\b(both|two|three|four|[234])\s+(?:\w+\s+)?sets\b(?!\s+of\b)", re.I
)
_ORDINAL_SET = re.compile(r"\b(second|third|fourth)\s+set\b", re.I)
_COUNT_WORDS = {"both": 2, "two": 2, "three": 3, "four": 4, "2": 2, "3": 3, "4": 4}
_ORDINALS = {"second": 2, "third": 3, "fourth": 4}

# The pre-presenter house narrator, verbatim: rendering the template with this
# fill must reproduce the original prompt byte-for-byte (a test locks it).
NEUTRAL_STYLE = (
    "Every fact must come from the\n"
    "inputs below — do not invent stories, dates, personnel, or song details. "
    "Voice: warm,\nknowledgeable, economical; written to be read aloud."
)


def persona_style(presenter: Presenter, title: str | None) -> str:
    """The {{style}} block for a presenter-hosted show: identity + character
    + the loosened-but-bounded grounding rules. Concert facts stay grounded;
    the final rule keeps adopted opinions inside factual_guard's contract."""
    lines = [
        f"You are {presenter.name}, the host, speaking in the first person; "
        f"written to be read aloud. You are {presenter.sex}; refer to "
        "yourself accordingly.",
        "Character:",
        presenter.character.strip(),
    ]
    if title:
        lines.append(f'Your show is called "{title}" — you know it well; drop '
                     "the name naturally now and then, not in every segment.")
    lines += [
        "Grounding rules:",
        "- Concert facts — dates, venue, songs, set structure, personnel, what "
        "happened on stage — must come from the inputs below; do not invent any.",
        "- You may voice opinions, perspective, and brief subjective color of "
        "your own.",
        "- You may adopt opinions found in the research or listener reviews as "
        "your own, paraphrased in your voice — never quote reviewers verbatim "
        "at length and never cite them as sources.",
        "- Never claim you attended this concert or took part in real events; "
        "no invented first-hand history presented as fact.",
        "- Every song you name — including in opinions — must be one of this "
        "show's tracks, spelled exactly as in the show data (map any loose "
        "review titles to those spellings), and listed in mentioned_songs.",
    ]
    return "\n".join(lines)


def factual_guard(notes: DJNotes, show: Show) -> list[str]:
    """DJ patter that misnames songs or sets must never ship — cross-check against show.json."""
    problems: list[str] = []
    known = {normalize_song(t.title) for t in show.tracks}
    for song in notes.mentioned_songs:
        if normalize_song(song) not in known:
            problems.append(f"dj notes mention unknown song: {song}")
    # The encore gets no lead-in (Option A): set_intros is keyed by the
    # non-encore sets only, and must cover every one of them.
    lead_in_sets = {t.set for t in show.tracks if t.set != "encore"}
    for s in notes.set_intros:
        if s not in lead_in_sets:
            problems.append(f"dj notes reference nonexistent or encore set: {s}")
    missing = lead_in_sets - set(notes.set_intros)
    if missing:
        problems.append(f"dj notes missing set intros: {sorted(missing)}")
    # Free-text set-count claims: structured fields above can be consistent
    # while the lead-in prose still tells listeners "they played two sets".
    prose = " ".join([notes.context, notes.outro, *notes.set_intros.values()])
    n_sets = len({t.set for t in show.tracks if t.set != "encore"})
    claimed = {_COUNT_WORDS[m.group(1).lower()] for m in _SET_COUNT_CLAIM.finditer(prose)}
    for n in sorted(claimed):
        if n != n_sets:
            problems.append(f"dj notes claim {n} sets but structure has {n_sets}")
    implied = {_ORDINALS[m.group(1).lower()]: m.group(1).lower()
               for m in _ORDINAL_SET.finditer(prose)}
    for n, word in sorted(implied.items()):
        if n > n_sets:
            problems.append(
                f"dj notes mention the {word} set but structure has {n_sets} sets"
            )
    return problems


def _set_label(s: str) -> str:
    return "Encore" if s == "encore" else f"Set {s}"


def render_notes_md(notes: DJNotes, show: Show) -> str:
    lines = [f"# {show.artist} — {show.date}, {show.venue or 'venue unknown'}", ""]
    if notes.context:
        lines += [f"*{notes.context}*", ""]
    # One lead-in per non-encore set, in show order, then the outro. The
    # encore has no lead-in (it folds into the final set's music).
    for s in sorted(notes.set_intros, key=lambda x: (x == "encore", x)):
        lines += [f"## {_set_label(s)} lead-in", notes.set_intros[s], ""]
    lines += ["## Outro", notes.outro, ""]
    return "\n".join(lines)


def run_synthesize(
    show_ws: ShowWorkspace,
    provider,
    show: Show,
    research_md: str,
    reviews: list[dict],
    force: bool = False,
    presenter: Presenter | None = None,
    title: str | None = None,
) -> DJNotes:
    if not should_run(show_ws.dj_notes_json, force):
        return read_model(show_ws.dj_notes_json, DJNotes)

    sets = sorted({t.set for t in show.tracks}, key=lambda x: (x == "encore", x))
    lead_in_sets = [s for s in sets if s != "encore"]
    encore_note = (
        "This show ends with an encore that plays unannounced right after the "
        "final set — write NO lead-in for it; instead have the outro recap it."
        if "encore" in sets else ""
    )
    note = narration_note(read_overrides(show_ws).narration)
    inputs = dict(
        show_json=show.model_dump_json(indent=2),
        research=research_md or "(no research available)",
        reviews_digest=reviews_digest(reviews),
        lead_in_sets=", ".join(f'"{s}"' for s in lead_in_sets),
        encore_note=encore_note,
        style=persona_style(presenter, title) if presenter else NEUTRAL_STYLE,
        narration_note=note,
    )
    feedback = ""
    for _attempt in range(2):
        notes = run_json_task(provider, "synthesize", DJNotes, feedback=feedback, **inputs)
        problems = factual_guard(notes, show)
        if not problems:
            break
        feedback = (
            "IMPORTANT: your previous script failed fact-checking: "
            + "; ".join(problems)
            + ". Fix every problem; write exactly one lead-in per set listed above."
        )
    if problems:
        current = read_model(show_ws.show, Show)
        current.review_flags = current.review_flags + problems
        current.needs_review = True
        write_artifact(show_ws.show, current)
    write_artifact(show_ws.dj_notes_json, notes)
    write_artifact(show_ws.dj_notes_md, render_notes_md(notes, show))
    return notes
