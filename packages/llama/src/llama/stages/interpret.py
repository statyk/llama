from herder import run_json_task
from llama.models import Criteria
from llama.prompts import load_prompt
from llama.taperssection import Allowlist
from llama.workspace import RunWorkspace, read_model, should_run, write_artifact


def run_interpret(ws: RunWorkspace, provider, query: str, force: bool = False,
                  *, allowlist: Allowlist | None = None) -> Criteria:
    if not should_run(ws.criteria, force):
        return read_model(ws.criteria, Criteria)
    criteria = run_json_task(provider, "interpret", Criteria,
                             template=load_prompt("interpret"), query=query)
    criteria = criteria.model_copy(update={"query": query})
    # Applied AFTER the LLM so the prompt is untouched. Exact normalized match only
    # (never a substring: "JazzIsPhish" stays an LMA guess). Decision: if a name is
    # both an LMA collection and allowlisted, the allowlist wins here, because
    # interpret has no index to consult; the allowlist is kept disjoint from LMA names.
    if allowlist and (e := (allowlist.resolve_name(criteria.artist)
                            or allowlist.resolve_name(criteria.collection))):
        criteria = criteria.model_copy(update={"collection": allowlist.key(e),
                                               "artist": e.name})
    write_artifact(ws.criteria, criteria)
    return criteria
