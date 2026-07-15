import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel

from llama.models import Criteria


class Profile(BaseModel):
    name: str
    criteria: Criteria
    count: int = 1
    human_gate: bool = False
    script: bool = False  # also generate the verbatim DJ script (extra high-tier call)


def save_profile(root: Path, profile: Profile) -> Path:
    path = root / "profiles" / f"{profile.name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    # TOML has no null: drop None fields; Criteria defaults restore them on load
    path.write_text(tomli_w.dumps(profile.model_dump(mode="json", exclude_none=True)))
    return path


def load_profile(root: Path, name: str) -> Profile:
    path = root / "profiles" / f"{name}.toml"
    return Profile.model_validate(tomllib.loads(path.read_text()))
