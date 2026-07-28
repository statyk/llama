import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, ValidationError, model_validator

from llama.errors import LlamaError
from llama.workspace import atomic_write_text


class PresenterError(LlamaError):
    """A presenter file is missing, unparseable, or fails validation."""


class Presenter(BaseModel):
    """A reusable radio-show host: a TTS voice + an authored persona + an
    on-air identity. Referenced by profiles; never influences curation."""
    id: str              # filename stem; injected by load_presenter, not stored in TOML
    name: str            # on-air identity, spoken ("Casey")
    sex: str             # informs character + self-reference ("male" / "female")
    voice: str | None = None        # voxtral preset name (or elevenlabs voice_id)
    voice_clone: str | None = None  # path to a 3-25s reference WAV (voxtral-only)
    character: str       # free-text persona description shaping tone
    bed: str | None = None  # optional per-host bed WAV (overrides [tts] bed)

    @model_validator(mode="after")
    def _exactly_one_voice(self):
        if bool(self.voice) == bool(self.voice_clone):
            raise ValueError("a presenter needs exactly one of voice / voice_clone")
        return self

    @property
    def voice_id(self) -> str:
        """The resolved voice string this presenter stamps into a run."""
        return self.voice or self.voice_clone


def save_presenter(root: Path, presenter: Presenter) -> Path:
    path = root / "presenters" / f"{presenter.id}.toml"
    # TOML has no null: drop None fields; id is the filename, not file content.
    atomic_write_text(path, tomli_w.dumps(
        presenter.model_dump(mode="json", exclude_none=True, exclude={"id"})))
    return path


def load_presenter(root: Path, presenter_id: str) -> Presenter:
    path = root / "presenters" / f"{presenter_id}.toml"
    if not path.exists():
        raise PresenterError(f"no presenter {presenter_id!r}: {path} does not exist")
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise PresenterError(f"invalid presenter at {path}: {exc}") from exc
    try:
        return Presenter.model_validate({**data, "id": presenter_id})
    except ValidationError as exc:
        raise PresenterError(f"invalid presenter at {path}: {exc}") from exc


def delete_presenter(root: Path, presenter_id: str) -> Path:
    path = root / "presenters" / f"{presenter_id}.toml"
    if not path.exists():
        raise PresenterError(f"no presenter {presenter_id!r}: {path} does not exist")
    path.unlink()
    return path


def list_presenters(root: Path) -> list[tuple[str, Presenter | str]]:
    """(id, Presenter | error-string) for each presenters/*.toml, sorted by id."""
    d = root / "presenters"
    out = []
    for p in sorted(d.glob("*.toml")) if d.is_dir() else []:
        try:
            out.append((p.stem, load_presenter(root, p.stem)))
        except PresenterError as exc:
            out.append((p.stem, str(exc)))
    return out
