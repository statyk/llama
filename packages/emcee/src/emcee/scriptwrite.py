"""The `scriptwrite` LLM task: persona/style, the deterministic fact guard,
markdown rendering, and the orchestration that turns a delivered package into
a `ScriptNotes` object.

This is a manifest-sourced port of llama's `stages/synthesize.py` (persona,
guard, render) and `songs.py` (`normalize_song`) -- emcee never imports
llama, so the shared logic is copied here as plain text, re-addressed to read
from a package manifest dict instead of a `Show` model.
"""

import json
import re

from herder import run_json_task

from emcee.errors import EmceeError
from emcee.models import ScriptNotes
from emcee.package_io import Package
from emcee.presenters import Presenter
from emcee.prompts import load_prompt

# --- normalize_song, ported verbatim from packages/llama/src/llama/songs.py
# (just the normalizer emcee needs -- not matches_sequence). GD-heavy curated
# alias table, per spec; extend as other artists come up.

# Keys and values are in normalized form (lowercase, no punctuation, apostrophes dropped).
DEFAULT_ALIASES: dict[str, str] = {
    "china cat": "china cat sunflower",
    "rider": "i know you rider",
    "u s blues": "us blues",
    "gdtrfb": "goin down the road feeling bad",
    "going down the road feeling bad": "goin down the road feeling bad",
    "going down the road feelin bad": "goin down the road feeling bad",
    "goin down the road feelin bad": "goin down the road feeling bad",
    "playin in the band": "playing in the band",
    "playin": "playing in the band",
    "nfa": "not fade away",
    "st stephen": "saint stephen",
    "uncle john": "uncle johns band",
    "jbg": "johnny b goode",
    "one more sat night": "one more saturday night",
    "wharf rat": "wharf rat",
}

_PUNCT = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize_song(name: str, aliases: dict[str, str] | None = None) -> str:
    s = name.lower().replace("'", "")
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    table = DEFAULT_ALIASES if aliases is None else {**DEFAULT_ALIASES, **aliases}
    return table.get(s, s)


# --- narration note, ported verbatim from synthesize.py:11-25.

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


# --- guard constants, ported verbatim from synthesize.py:29-35.

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
    the final rule keeps adopted opinions inside script_guard's contract."""
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


def script_guard(notes: ScriptNotes, manifest: dict, narration: str) -> list[str]:
    """DJ patter that misnames songs or sets must never ship -- cross-check
    against the package manifest's `tracks`/`set` fields. Ported from
    llama's `factual_guard` (synthesize.py:78-109), re-sourced to a manifest
    dict instead of a `Show` model, plus a narration="vague" check: when the
    show data can't support named songs or a set count, the script must not
    assert either (the per-gap segment structure -- one lead-in per set --
    still stands; only what the prose may *claim* is constrained)."""
    problems: list[str] = []
    known = {normalize_song(t["title"]) for t in manifest["tracks"]}
    for song in notes.mentioned_songs:
        if normalize_song(song) not in known:
            problems.append(f"dj notes mention unknown song: {song}")
    # The encore gets no lead-in (Option A): set_intros is keyed by the
    # non-encore sets only, and must cover every one of them.
    lead_in_sets = {t["set"] for t in manifest["tracks"] if t["set"] != "encore"}
    for s in notes.set_intros:
        if s not in lead_in_sets:
            problems.append(f"dj notes reference nonexistent or encore set: {s}")
    missing = lead_in_sets - set(notes.set_intros)
    if missing:
        problems.append(f"dj notes missing set intros: {sorted(missing)}")
    # Free-text set-count claims: structured fields above can be consistent
    # while the lead-in prose still tells listeners "they played two sets".
    prose = " ".join([notes.context, notes.outro, *notes.set_intros.values()])
    n_sets = len(lead_in_sets)
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
    if narration == "vague":
        # The show data can't support named songs or an asserted set count;
        # the per-gap lead-in/outro structure above stays untouched.
        for song in notes.mentioned_songs:
            problems.append(f"dj notes name a song but narration is vague: {song}")
        for n in sorted(claimed):
            problems.append(f"dj notes claim {n} sets but narration is vague")
        for n, word in sorted(implied.items()):
            problems.append(f"dj notes mention the {word} set but narration is vague")
    return problems


def _set_label(s: str) -> str:
    return "Encore" if s == "encore" else f"Set {s}"


def render_notes_md(notes: ScriptNotes, manifest: dict) -> str:
    show = manifest["show"]
    lines = [f"# {show['artist']} — {show['date']}, {show.get('venue') or 'venue unknown'}", ""]
    if notes.context:
        lines += [f"*{notes.context}*", ""]
    # One lead-in per non-encore set, in show order, then the outro. The
    # encore has no lead-in (it folds into the final set's music).
    for s in sorted(notes.set_intros, key=lambda x: (x == "encore", x)):
        lines += [f"## {_set_label(s)} lead-in", notes.set_intros[s], ""]
    lines += ["## Outro", notes.outro, ""]
    return "\n".join(lines)


def write_script(
    pkg: Package,
    provider,
    presenter: Presenter | None,
    title: str | None,
) -> ScriptNotes:
    """Build the scriptwrite prompt from the package's briefing + manifest
    slice, run it, guard the result, retry once with feedback on failure,
    and raise EmceeError on persistent failure.

    PURE: reads the package but never writes to it -- `process_package`
    (the orchestrator) owns writing the manifest's `dj_notes` block and
    `dj-notes.md`.
    """
    manifest = pkg.manifest()
    briefing_md = pkg.briefing_md()
    narration = manifest["briefing"]["narration"]

    manifest_show_json = json.dumps(
        {
            "show": manifest["show"],
            "tracks": manifest["tracks"],
            "set_breaks": manifest["set_breaks"],
        },
        indent=2,
    )

    sets = sorted({t["set"] for t in manifest["tracks"]}, key=lambda x: (x == "encore", x))
    lead_in_sets = [s for s in sets if s != "encore"]
    encore_note = (
        "This show ends with an encore that plays unannounced right after the "
        "final set — write NO lead-in for it; instead have the outro recap it."
        if "encore" in sets else ""
    )

    inputs = dict(
        manifest_show_json=manifest_show_json,
        briefing_md=briefing_md,
        lead_in_sets=", ".join(f'"{s}"' for s in lead_in_sets),
        encore_note=encore_note,
        style=persona_style(presenter, title) if presenter else NEUTRAL_STYLE,
        narration_note=narration_note(narration),
    )

    feedback = ""
    problems: list[str] = []
    notes: ScriptNotes | None = None
    for _attempt in range(2):
        notes = run_json_task(
            provider, "scriptwrite", ScriptNotes,
            template=load_prompt("scriptwrite"), feedback=feedback, **inputs,
        )
        problems = script_guard(notes, manifest, narration)
        if not problems:
            return notes
        feedback = (
            "IMPORTANT: your previous script failed fact-checking: "
            + "; ".join(problems)
            + ". Fix every problem; write exactly one lead-in per set listed above."
        )
    raise EmceeError("scriptwrite failed fact-checking after retry", details=problems)
