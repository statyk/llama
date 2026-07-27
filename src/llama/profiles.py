import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, ValidationError

from llama.errors import LlamaError
from llama.models import Criteria


class ProfileError(LlamaError):
    """A profile file is missing, unparseable, or fails validation."""


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
    if not path.exists():
        raise ProfileError(f"no profile {name!r}: {path} does not exist")
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"invalid profile at {path}: {exc}") from exc
    try:
        return Profile.model_validate(data)
    except ValidationError as exc:
        raise ProfileError(f"invalid profile at {path}: {exc}") from exc


def delete_profile(root: Path, name: str) -> Path:
    path = root / "profiles" / f"{name}.toml"
    if not path.exists():
        raise ProfileError(f"no profile {name!r}: {path} does not exist")
    path.unlink()
    return path


def list_profiles(root: Path) -> list[tuple[str, Profile | str]]:
    """(name, Profile | error-string) for each profiles/*.toml, sorted by name."""
    d = root / "profiles"
    out = []
    for p in sorted(d.glob("*.toml")) if d.is_dir() else []:
        try:
            out.append((p.stem, load_profile(root, p.stem)))
        except ProfileError as exc:
            out.append((p.stem, str(exc)))
    return out
