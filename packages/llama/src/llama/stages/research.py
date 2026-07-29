from llama.llm.tasks import run_research_task
from llama.models import Show
from llama.prompts import load_prompt
from llama.workspace import ShowWorkspace, should_run, write_artifact

# The deep_research prompt demands exactly these sections; a reply without
# them is not a report (narration, refusal, hand-off) and must not ship.
REQUIRED_SECTIONS = ["## Reputation", "## Performance highlights",
                     "## Context", "## Recording notes"]


def run_research(show_ws: ShowWorkspace, provider, show: Show, dossier: str, force: bool = False) -> str:
    if not should_run(show_ws.research, force):
        return show_ws.research.read_text()
    setlist = "\n".join(f"{t.set}: {t.title}" for t in show.tracks)
    text = run_research_task(
        provider, "deep_research", template=load_prompt("deep_research"),
        required_sections=REQUIRED_SECTIONS,
        artist=show.artist, date=show.date, venue=show.venue or "unknown venue",
        dossier=dossier, setlist=setlist,
    )
    write_artifact(show_ws.research, text)
    return text
