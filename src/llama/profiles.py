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
    script: bool = True  # verbatim DJ script (high-tier call); --no-script opts out
    # This radio show's host: presenters/<id>.toml. Naming a presenter voices
    # this profile's runs even when the global [tts] enabled flag is false.
    presenter: str | None = None
    # The radio show's on-air name ("Bluegrass Valley"); the host knows it and
    # drops it occasionally. Named `title` (rename-safe), not `show_name`.
    title: str | None = None


def save_profile(root: Path, profile: Profile) -> Path:
    path = root / "profiles" / f"{profile.name}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    # TOML has no null: drop None fields; Criteria defaults restore them on load
    path.write_text(tomli_w.dumps(profile.model_dump(mode="json", exclude_none=True)))
    return path


def load_profile(root: Path, name: str) -> Profile:
    path = root / "profiles" / f"{name}.toml"
    return Profile.model_validate(tomllib.loads(path.read_text()))
