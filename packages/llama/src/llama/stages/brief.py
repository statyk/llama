from llama.models import Briefing, Show
from llama.songs import normalize_song
from llama.stages.synthesize import (_COUNT_WORDS, _ORDINALS, _ORDINAL_SET,
                                     _SET_COUNT_CLAIM, _set_label)


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
