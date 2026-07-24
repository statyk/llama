# tests/test_presenters.py
from pathlib import Path

import pytest
from pydantic import ValidationError

from llama.errors import LlamaError
from llama.presenters import Presenter, PresenterError, load_presenter, save_presenter


def make(**overrides):
    d = dict(id="casey", name="Casey", sex="male", voice="american-dj",
             character="Warm late-night FM veteran.\nDry humor, deep tape knowledge.")
    d.update(overrides)
    return Presenter(**d)


def test_roundtrip_and_id_from_filename(tmp_path: Path):
    path = save_presenter(tmp_path, make())
    assert path == tmp_path / "presenters" / "casey.toml"
    assert "id" not in path.read_text()          # id is the filename, not a field
    loaded = load_presenter(tmp_path, "casey")
    assert loaded == make()
    assert "\nDry humor" in loaded.character     # multi-line character survives


def test_voice_clone_roundtrip(tmp_path: Path):
    save_presenter(tmp_path, make(voice=None, voice_clone="/refs/casey.wav"))
    loaded = load_presenter(tmp_path, "casey")
    assert loaded.voice is None and loaded.voice_clone == "/refs/casey.wav"
    assert loaded.voice_id == "/refs/casey.wav"


def test_voice_id_prefers_preset():
    assert make().voice_id == "american-dj"


def test_exactly_one_of_voice_and_clone():
    with pytest.raises(ValidationError):
        make(voice=None, voice_clone=None)
    with pytest.raises(ValidationError):
        make(voice="a", voice_clone="/b.wav")


def test_missing_file_raises_presenter_error(tmp_path: Path):
    with pytest.raises(PresenterError) as exc:
        load_presenter(tmp_path, "ghost")
    assert "ghost" in str(exc.value)
    assert isinstance(exc.value, LlamaError)     # CLI boundary prints it cleanly


def test_invalid_toml_raises_presenter_error(tmp_path: Path):
    path = tmp_path / "presenters" / "bad.toml"
    path.parent.mkdir(parents=True)
    path.write_text("name = [unclosed")
    with pytest.raises(PresenterError):
        load_presenter(tmp_path, "bad")


def test_failed_validation_raises_presenter_error(tmp_path: Path):
    path = tmp_path / "presenters" / "half.toml"
    path.parent.mkdir(parents=True)
    path.write_text('name = "Casey"\n')          # no sex / voice / character
    with pytest.raises(PresenterError):
        load_presenter(tmp_path, "half")
