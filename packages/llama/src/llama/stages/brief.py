from llama.models import Briefing, Show
from llama.stages.synthesize import _set_label


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
