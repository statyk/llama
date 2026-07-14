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


def should_run(path: Path, force: bool) -> bool:
    return force or not path.exists()


class ShowWorkspace:
    def __init__(self, dir: Path):
        self.dir = dir
        self.selection = dir / "selection.json"
        self.show = dir / "show.json"
        self.reviews = dir / "reviews.json"
        self.research = dir / "research.md"
        self.dj_notes_md = dir / "dj-notes.md"
        self.dj_notes_json = dir / "dj-notes.json"
        self.package_dir = dir / "package"


class RunWorkspace:
    def __init__(self, root: Path, name: str):
        self.name = name
        self.dir = root / "runs" / name
        self.criteria = self.dir / "criteria.json"
        self.candidates = self.dir / "candidates.json"
        self.shortlist = self.dir / "shortlist.json"

    def show_ws(self, performance_id: str) -> ShowWorkspace:
        return ShowWorkspace(self.dir / "shows" / slugify(performance_id))
