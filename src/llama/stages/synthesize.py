from llama.llm.tasks import run_json_task
from llama.models import DJNotes, Show
from llama.songs import normalize_song
from llama.util import reviews_digest
from llama.workspace import ShowWorkspace, read_model, should_run, write_artifact


def factual_guard(notes: DJNotes, show: Show) -> list[str]:
    """DJ patter that misnames songs or sets must never ship — cross-check against show.json."""
    problems: list[str] = []
    known = {normalize_song(t.title) for t in show.tracks}
    for song in notes.mentioned_songs:
        if normalize_song(song) not in known:
            problems.append(f"dj notes mention unknown song: {song}")
    actual_sets = {t.set for t in show.tracks}
    for s in notes.set_intros:
        if s not in actual_sets:
            problems.append(f"dj notes reference nonexistent set: {s}")
    missing = actual_sets - set(notes.set_intros)
    if missing:
        problems.append(f"dj notes missing set intros: {sorted(missing)}")
    if len(notes.set_break_notes) != len(show.set_breaks):
        problems.append(
            f"set-break note count mismatch: {len(notes.set_break_notes)} notes"
            f" for {len(show.set_breaks)} breaks"
        )
    return problems


def _set_label(s: str) -> str:
    return "Encore" if s == "encore" else f"Set {s}"


def render_notes_md(notes: DJNotes, show: Show) -> str:
    lines = [f"# {show.artist} — {show.date}, {show.venue or 'venue unknown'}", ""]
    if notes.context:
        lines += [f"*{notes.context}*", ""]
    lines += ["## Show intro", notes.intro, ""]
    for s in sorted(notes.set_intros, key=lambda x: (x == "encore", x)):
        lines += [f"## {_set_label(s)} intro", notes.set_intros[s], ""]
    for i, note in enumerate(notes.set_break_notes, 1):
        lines += [f"## Set break {i}", note, ""]
    lines += ["## Outro", notes.outro, ""]
    return "\n".join(lines)


def run_synthesize(
    show_ws: ShowWorkspace,
    provider,
    show: Show,
    research_md: str,
    reviews: list[dict],
    force: bool = False,
) -> DJNotes:
    if not should_run(show_ws.dj_notes_json, force):
        return read_model(show_ws.dj_notes_json, DJNotes)

    sets = sorted({t.set for t in show.tracks}, key=lambda x: (x == "encore", x))
    inputs = dict(
        show_json=show.model_dump_json(indent=2),
        research=research_md or "(no research available)",
        reviews_digest=reviews_digest(reviews),
        sets=", ".join(f'"{s}"' for s in sets),
        n_breaks=len(show.set_breaks),
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
            + ". Fix every problem; use exactly the sets and break count above."
        )
    if problems:
        current = read_model(show_ws.show, Show)
        current.review_flags = current.review_flags + problems
        current.needs_review = True
        write_artifact(show_ws.show, current)
    write_artifact(show_ws.dj_notes_json, notes)
    write_artifact(show_ws.dj_notes_md, render_notes_md(notes, show))
    return notes
