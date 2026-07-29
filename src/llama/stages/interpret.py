from llama.llm.tasks import run_json_task
from llama.models import Criteria
from llama.prompts import load_prompt
from llama.workspace import RunWorkspace, read_model, should_run, write_artifact


def run_interpret(ws: RunWorkspace, provider, query: str, force: bool = False) -> Criteria:
    if not should_run(ws.criteria, force):
        return read_model(ws.criteria, Criteria)
    criteria = run_json_task(provider, "interpret", Criteria,
                             template=load_prompt("interpret"), query=query)
    criteria = criteria.model_copy(update={"query": query})
    write_artifact(ws.criteria, criteria)
    return criteria
