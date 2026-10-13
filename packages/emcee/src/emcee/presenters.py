import tomllib
from pathlib import Path

import tomli_w
from pydantic import ValidationError, model_validator

from emcee.config import _StrictModel
from emcee.errors import EmceeError
from emcee.workspace import atomic_write_text

# Backends a presenter may pin with `tts = "..."`. "fake" is deliberately not
# one: tests select it through [tts] backend.
TTS_PINS = ("voxtral", "elevenlabs", "mlx_audio")


class PresenterError(EmceeError):
    """A presenter file is missing, unparseable, or fails validation."""


class Presenter(_StrictModel):
    """A reusable radio-show host: a TTS voice + an authored persona + an
    on-air identity. Referenced by profiles; never influences curation.

    Strict (`extra="forbid"`): a misspelled key such as `tts_modle` is a load
    error, never a pin silently ignored."""
    id: str              # filename stem; injected by load_presenter, not stored in TOML
    name: str            # on-air identity, spoken ("Casey")
    sex: str             # informs character + self-reference ("male" / "female")
    voice: str | None = None        # preset name (voxtral) or voice_id (elevenlabs)
    voice_clone: str | None = None  # absolute path to a 3-25s reference clip (voxtral / mlx_audio)
    character: str       # free-text persona description shaping tone
    bed: str | None = None  # optional per-host bed WAV (overrides [tts] bed)
    tts: str | None = None             # backend pin; None = [tts] backend (never mlx_audio)
    tts_model: str | None = None       # mlx_audio only; None = [tts.mlx_audio] model
    voice_clone_text: str | None = None  # transcript of voice_clone (mlx_audio requires it)

    @model_validator(mode="after")
    def _validate(self):
        if bool(self.voice) == bool(self.voice_clone):
            raise ValueError("a presenter needs exactly one of voice / voice_clone")
        if self.tts is not None and self.tts not in TTS_PINS:
            raise ValueError(f"tts must be one of {', '.join(TTS_PINS)} (got {self.tts!r}); "
                             "remove the key to use [tts] backend")
        if self.tts_model is not None:
            if not self.tts_model.strip():
                raise ValueError("tts_model must not be empty; remove the key to use "
                                 "[tts.mlx_audio] model")
            if self.tts != "mlx_audio":
                raise ValueError('tts_model is allowed only with tts = "mlx_audio"')
        if self.tts == "elevenlabs" and self.voice_clone:
            raise ValueError('voice_clone cannot be voiced with tts = "elevenlabs" '
                             "(cloning needs voxtral or mlx_audio)")
        if self.tts == "mlx_audio":
            if self.voice:
                raise ValueError('tts = "mlx_audio" is clone-only: use voice_clone, '
                                 "not a preset voice")
            if not (self.voice_clone_text or "").strip():
                raise ValueError('tts = "mlx_audio" needs voice_clone_text, the transcript '
                                 "of voice_clone")
        return self

    @property
    def voice_id(self) -> str:
        """The resolved voice string this presenter stamps into a run."""
        return self.voice or self.voice_clone


def save_presenter(root: Path, presenter: Presenter) -> Path:
    # Validate whole before writing: a caller that built `presenter` with
    # model_copy(update=...) skipped the validators.
    try:
        Presenter.model_validate(presenter.model_dump())
    except ValidationError as exc:
        raise PresenterError(f"invalid presenter {presenter.id!r}: {exc}") from exc
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
