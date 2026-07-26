import json
from pathlib import Path

from pydantic import BaseModel

from llama.util import slugify


def _to_jsonable(data):
    if isinstance(data, BaseModel):
        return data.model_dump(mode="json")
    if isinstance(data, list):
        return [_to_jsonable(x) for x in data]
    return data


def write_artifact(path: Path, data) -> None:
    """Atomic write (temp + rename): a failed stage never leaves a partial artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(_to_jsonable(data), indent=2)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def read_model(path: Path, schema: type[BaseModel]) -> BaseModel:
    return schema.model_validate_json(path.read_text())


def read_model_list(path: Path, schema: type[BaseModel]) -> list[BaseModel]:
    return [schema.model_validate(x) for x in json.loads(path.read_text())]


def read_json(path: Path):
    return json.loads(path.read_text())


def read_overrides(show_ws: "ShowWorkspace"):
    from llama.models import Overrides
    if show_ws.overrides.exists():
        return read_model(show_ws.overrides, Overrides)
    return Overrides()


def should_run(path: Path, force: bool) -> bool:
    return force or not path.exists()


class ShowWorkspace:
    def __init__(self, dir: Path):
        self.dir = dir
        self.selection = dir / "selection.json"
        self.provenance = dir / "provenance.json"
        self.show = dir / "show.json"
        self.reviews = dir / "reviews.json"
        self.research = dir / "research.md"
        self.vetting = dir / "vetting.json"
        self.dj_notes_md = dir / "dj-notes.md"
        self.dj_notes_json = dir / "dj-notes.json"
        self.overrides = dir / "overrides.json"
        self.package_dir = dir / "package"


# Show-level stage order: forcing a stage drops its artifacts and everything
# downstream, so a replay can never package outputs derived from pre-force state.
SHOW_STAGE_ORDER = ["select", "gather", "research", "vet", "synthesize", "package"]


def show_stage_artifacts(show_ws: ShowWorkspace, stage: str) -> list[Path]:
    return {
        "select": [show_ws.selection],
        "gather": [show_ws.show, show_ws.reviews],
        "research": [show_ws.research, show_ws.vetting],
        "vet": [show_ws.vetting],
        "synthesize": [show_ws.dj_notes_json, show_ws.dj_notes_md],
        "package": [show_ws.package_dir / "manifest.json"],
    }[stage]


def drop_stage_artifacts(show_ws: ShowWorkspace, stage: str, keep_research: bool = False) -> None:
    """Delete one show's artifacts for `stage` and every stage after it.
    keep_research spares research.md (the expensive deep-research output)
    while still dropping everything derived from it."""
    for st in SHOW_STAGE_ORDER[SHOW_STAGE_ORDER.index(stage):]:
        for path in show_stage_artifacts(show_ws, st):
            if keep_research and path == show_ws.research:
                continue
            if path.exists():
                path.unlink()


class RunWorkspace:
    def __init__(self, root: Path, name: str):
        self.root = root
        self.name = name
        self.dir = root / "runs" / name
        self.criteria = self.dir / "criteria.json"
        self.candidates = self.dir / "candidates.json"
        self.shortlist = self.dir / "shortlist.json"
        self.artists = self.dir / "artists.json"

    def show_ws(self, performance_id: str) -> ShowWorkspace:
        return ShowWorkspace(self.root / "shows" / slugify(performance_id))
