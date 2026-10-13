# tests/test_presenters.py
from pathlib import Path

import pytest
from pydantic import ValidationError

from emcee.errors import EmceeError
from emcee.presenters import (
    Presenter, PresenterError, delete_presenter, load_presenter, save_presenter,
)


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


def test_presenter_bed_roundtrips_and_omits_when_unset(tmp_path: Path):
    p = make(bed="/beds/soul.wav")
    path = save_presenter(tmp_path, p)
    assert 'bed = "/beds/soul.wav"' in path.read_text()
    assert load_presenter(tmp_path, "casey").bed == "/beds/soul.wav"

    p2 = make(id="dj2", bed=None)
    path2 = save_presenter(tmp_path, p2)
    assert "bed" not in path2.read_text()
    assert load_presenter(tmp_path, "dj2").bed is None


def test_missing_file_raises_presenter_error(tmp_path: Path):
    with pytest.raises(PresenterError) as exc:
        load_presenter(tmp_path, "ghost")
    assert "ghost" in str(exc.value)
    assert isinstance(exc.value, EmceeError)     # CLI boundary prints it cleanly


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


def test_delete_presenter_removes_file_and_errors_on_unknown(tmp_path: Path):
    path = save_presenter(tmp_path, make())
    assert path.exists()
    removed = delete_presenter(tmp_path, "casey")
    assert removed == path
    assert not path.exists()
    with pytest.raises(PresenterError):
        delete_presenter(tmp_path, "casey")


# --- pins: tts / tts_model / voice_clone_text (spec section 1) ----------------

from emcee.presenters import TTS_PINS


def clone(**overrides):
    return make(voice=None, voice_clone="/refs/phil.wav", **overrides)


def test_pin_values_are_exactly_the_three_backends():
    assert TTS_PINS == ("voxtral", "elevenlabs", "mlx_audio")


def test_valid_pins():
    assert make(tts="voxtral").tts == "voxtral"
    assert make(tts="elevenlabs").tts == "elevenlabs"
    assert clone(tts="voxtral").tts == "voxtral"
    p = clone(tts="mlx_audio", voice_clone_text="It's the chemistry, basically.")
    assert p.tts == "mlx_audio" and p.tts_model is None
    p = clone(tts="mlx_audio", tts_model="mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
              voice_clone_text="Hello there.")
    assert p.tts_model == "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"


@pytest.mark.parametrize("bad", ["", "fake", "kokoro", "Voxtral", " voxtral"])
def test_tts_rejects_anything_but_the_three_pins(bad):
    with pytest.raises(ValidationError, match="tts must be one of"):
        make(tts=bad)


@pytest.mark.parametrize("bad", ["", "   "])
def test_tts_model_rejects_empty_strings(bad):
    with pytest.raises(ValidationError, match="tts_model must not be empty"):
        clone(tts="mlx_audio", tts_model=bad, voice_clone_text="Hello there.")


@pytest.mark.parametrize("tts", [None, "voxtral", "elevenlabs"])
def test_tts_model_only_with_mlx_audio(tts):
    with pytest.raises(ValidationError, match='tts_model is allowed only with tts = "mlx_audio"'):
        make(tts=tts, tts_model="some/model")


def test_voice_clone_with_elevenlabs_pin_rejected():
    with pytest.raises(ValidationError, match="elevenlabs"):
        clone(tts="elevenlabs")


def test_mlx_audio_pin_rejects_a_preset_voice():
    with pytest.raises(ValidationError, match="clone-only"):
        make(tts="mlx_audio", voice_clone_text="Hello there.")


@pytest.mark.parametrize("text", [None, "", "  \n\t "])
def test_mlx_audio_pin_requires_a_non_blank_transcript(text):
    with pytest.raises(ValidationError, match="needs voice_clone_text"):
        clone(tts="mlx_audio", voice_clone_text=text)


def test_voice_clone_text_is_allowed_ahead_of_a_pin_and_with_voxtral():
    assert clone(voice_clone_text="Hello.").voice_clone_text == "Hello."
    assert clone(tts="voxtral", voice_clone_text="Hello.").tts == "voxtral"


def test_pin_fields_roundtrip(tmp_path: Path):
    p = clone(tts="mlx_audio", tts_model="m/x", voice_clone_text="It's the chemistry.\n")
    save_presenter(tmp_path, p)
    loaded = load_presenter(tmp_path, "casey")
    assert loaded == p
    text = (tmp_path / "presenters" / "casey.toml").read_text()
    assert 'tts = "mlx_audio"' in text and 'tts_model = "m/x"' in text


def test_unpinned_presenter_file_has_no_pin_keys(tmp_path: Path):
    text = save_presenter(tmp_path, make()).read_text()
    assert "tts" not in text and "voice_clone_text" not in text


def test_unknown_key_is_a_load_error(tmp_path: Path):
    path = tmp_path / "presenters" / "phil.toml"
    path.parent.mkdir(parents=True)
    path.write_text('name = "Phil"\nsex = "male"\nvoice_clone = "/r.wav"\n'
                    'character = "x"\ntts = "mlx_audio"\ntts_modle = "typo"\n'
                    'voice_clone_text = "Hi."\n')
    with pytest.raises(PresenterError, match="tts_modle"):
        load_presenter(tmp_path, "phil")


def test_unknown_constructor_key_rejected():
    with pytest.raises(ValidationError):
        make(tts_modle="typo")


# The five live presenter files (2026-10-12) use only these key sets; each
# must still load under the strict base.
@pytest.mark.parametrize("body", [
    'name = "Billy G"\nsex = "male"\nvoice_clone = "/s/billgraham2.wav"\n'
    'bed = "/s/dead_bed3.wav"\ncharacter = """\nBrooklyn-bred.\n"""\n',
    'name = "K.C."\nsex = "male"\nvoice_clone = "/s/kurt1.wav"\n'
    'bed = "/s/aurora_bed.wav"\ncharacter = "Grunge kid."\n',
    'name = "Uncle Pen"\nsex = "male"\nvoice_clone = "/s/monroe1.wav"\n'
    'bed = "/s/bluegrass-bed.wav"\ncharacter = """\nAn old bluegrass musician.\n"""\n',
    'name = "Professor Chapman"\nsex = "male"\nvoice_clone = "/s/phil.wav"\n'
    'bed = "/s/dead_bed3.wav"\ncharacter = """\nProfessorial.\n"""\n',
    'name = "Roy Demure"\nsex = "male"\nvoice_clone = "/s/troymcclure2.wav"\n'
    'bed = "/s/dead_bed3.wav"\ncharacter = """\nModeled on Troy McClure.\n"""\n',
])
def test_live_presenter_shapes_still_load(tmp_path: Path, body):
    path = tmp_path / "presenters" / "p.toml"
    path.parent.mkdir(parents=True)
    path.write_text(body)
    assert load_presenter(tmp_path, "p").tts is None


def test_save_revalidates_a_model_copy_built_presenter(tmp_path: Path):
    # model_copy(update=...) skips validators; save must not let it through.
    bad = make().model_copy(update={"tts": "fake"})
    with pytest.raises(PresenterError, match="tts must be one of"):
        save_presenter(tmp_path, bad)
    assert not (tmp_path / "presenters" / "casey.toml").exists()
