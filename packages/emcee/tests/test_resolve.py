"""resolve_tts: which backend, model and key voice a presenter or the house
voice (spec section 1 "Resolution"). Pure: no files, no network."""
import pytest

from emcee.config import EmceeConfig
from emcee.presenters import Presenter
from emcee.tts import calibration
from emcee.tts.elevenlabs import DEFAULT_MODEL as EL_DEFAULT
from emcee.tts.resolve import DEFAULT_MODELS, TTSResolution, TTSResolutionError, resolve_tts
from emcee.tts.voxtral import DEFAULT_MODEL as VOX_DEFAULT

from tests.mlx_helpers import TEST_CAL, TEST_MODEL, TEST_MODEL_B, calibrate_test_model


def cfg(**tts) -> EmceeConfig:
    return EmceeConfig.model_validate({"tts": tts})


def host(**overrides) -> Presenter:
    d = dict(id="phil", name="Phil", sex="male", voice=None, voice_clone="/refs/phil.wav",
             character="Professorial.")
    d.update(overrides)
    return Presenter(**d)


def mlx_host(**overrides) -> Presenter:
    return host(tts="mlx_audio", voice_clone_text="It's the chemistry.", **overrides)


def test_test_models_are_never_production_entries():
    # Production entries are measured (plan Task 12); test entries exist only
    # inside a test, via calibrate_test_model.
    assert TEST_MODEL not in calibration.CALIBRATED_MODELS
    assert TEST_MODEL_B not in calibration.CALIBRATED_MODELS


def test_calibration_invariants():
    with pytest.raises(ValueError, match="cap_s_per_char"):
        calibration.ModelCalibration(12.5, 8.0, 0.10, 4.0, 0.11, 0.03, 1.0, 1.0)
    with pytest.raises(ValueError, match="must exceed max_floor_s"):
        calibration.ModelCalibration(12.5, 5.0, 0.12, 4.0, 0.11, 0.03, 1.0, 1.0)
    with pytest.raises(ValueError, match="positive"):
        calibration.ModelCalibration(0, 8.0, 0.12, 4.0, 0.11, 0.03, 1.0, 1.0)
    with pytest.raises(ValueError, match="negative"):
        calibration.ModelCalibration(12.5, 8.0, 0.12, 4.0, 0.11, -0.1, 1.0, 1.0)


def test_default_models_are_the_providers_defaults():
    assert DEFAULT_MODELS == {"voxtral": VOX_DEFAULT, "elevenlabs": EL_DEFAULT}


# --- house voice -----------------------------------------------------------


def test_house_hosted_uses_legacy_key_and_model_and_names_both_key_locations():
    r = resolve_tts(cfg(api_key="k-legacy", model="m-legacy"), None)
    assert r == TTSResolution(backend="voxtral", model="m-legacy", api_key="k-legacy",
                              key_sources=("[tts.voxtral] api_key", "[tts] api_key"),
                              presenter=None, pinned=False)


def test_house_hosted_subtable_key_and_model():
    r = resolve_tts(cfg(voxtral={"api_key": "k-sub", "model": "m-sub"}), None)
    assert (r.api_key, r.model) == ("k-sub", "m-sub")


def test_house_hosted_model_defaults_and_key_may_be_absent():
    r = resolve_tts(cfg(backend="elevenlabs"), None)
    assert (r.backend, r.model, r.api_key) == ("elevenlabs", EL_DEFAULT, None)


def test_house_fake_resolves_to_fake():
    r = resolve_tts(cfg(backend="fake"), None)
    assert (r.backend, r.model, r.api_key, r.key_sources) == ("fake", None, None, ())


def test_house_unknown_backend_passes_through_for_the_factory_to_reject():
    assert resolve_tts(cfg(backend="kokoro"), None).backend == "kokoro"


def test_house_mlx_uses_the_mlx_table_model(monkeypatch):
    calibrate_test_model(monkeypatch)
    r = resolve_tts(cfg(backend="mlx_audio", mlx_audio={"model": TEST_MODEL}), None)
    assert r == TTSResolution(backend="mlx_audio", model=TEST_MODEL, api_key=None,
                              key_sources=(), presenter=None, pinned=False)


def test_house_mlx_without_a_model_is_an_error():
    with pytest.raises(TTSResolutionError, match=r"no mlx_audio model.*\[tts.mlx_audio\] model"):
        resolve_tts(cfg(backend="mlx_audio"), None)


def test_house_mlx_uncalibrated_model_is_an_error():
    with pytest.raises(TTSResolutionError,
                       match="mlx_audio model not calibrated for the runaway guard"):
        resolve_tts(cfg(backend="mlx_audio", mlx_audio={"model": "other/model"}), None)


# --- presenters --------------------------------------------------------------


def test_unpinned_presenter_inherits_a_hosted_house():
    r = resolve_tts(cfg(api_key="k"), host())
    assert (r.backend, r.api_key, r.presenter, r.pinned) == ("voxtral", "k", "phil", False)


def test_unpinned_presenter_inherits_fake():
    assert resolve_tts(cfg(backend="fake"), host()).backend == "fake"


def test_unpinned_presenter_under_an_mlx_house_is_an_error(monkeypatch):
    calibrate_test_model(monkeypatch)
    with pytest.raises(TTSResolutionError,
                       match="pin tts explicitly: the house backend is mlx_audio"):
        resolve_tts(cfg(backend="mlx_audio", mlx_audio={"model": TEST_MODEL}), host())


def test_pinned_presenter_under_an_mlx_house_resolves_to_its_pin(monkeypatch):
    calibrate_test_model(monkeypatch)
    r = resolve_tts(cfg(backend="mlx_audio", mlx_audio={"model": TEST_MODEL}),
                    host(tts="voxtral"))
    assert (r.backend, r.model, r.presenter, r.pinned) == ("voxtral", VOX_DEFAULT, "phil", True)
    assert r.key_sources == ("[tts.voxtral] api_key",)


def test_presenter_pin_beats_the_house_backend():
    r = resolve_tts(cfg(backend="voxtral"), host(voice="v", voice_clone=None, tts="elevenlabs"))
    assert (r.backend, r.pinned) == ("elevenlabs", True)


def test_pinned_hosted_ignores_legacy_tts_key_and_model_of_another_house():
    # [tts] api_key/model mean the HOUSE backend's (elevenlabs here), never voxtral's.
    r = resolve_tts(cfg(backend="elevenlabs", api_key="el-key", model="el-model"),
                    host(tts="voxtral"))
    assert (r.backend, r.model, r.api_key) == ("voxtral", VOX_DEFAULT, None)
    assert r.key_sources == ("[tts.voxtral] api_key",)


def test_pinned_hosted_same_as_house_still_gets_legacy_key():
    r = resolve_tts(cfg(api_key="k", model="m"), host(tts="voxtral"))
    assert (r.model, r.api_key) == ("m", "k")
    assert r.key_sources == ("[tts.voxtral] api_key", "[tts] api_key")


def test_pinned_hosted_uses_its_subtable():
    r = resolve_tts(cfg(backend="elevenlabs", voxtral={"api_key": "vk", "model": "vm"}),
                    host(tts="voxtral"))
    assert (r.model, r.api_key) == ("vm", "vk")


def test_mlx_pin_model_beats_the_mlx_table_model(monkeypatch):
    calibrate_test_model(monkeypatch, TEST_MODEL, TEST_MODEL_B)
    config = cfg(mlx_audio={"model": TEST_MODEL})
    assert resolve_tts(config, mlx_host()).model == TEST_MODEL
    assert resolve_tts(config, mlx_host(tts_model=TEST_MODEL_B)).model == TEST_MODEL_B


def test_mlx_pin_without_any_model_is_an_error():
    with pytest.raises(TTSResolutionError, match="no mlx_audio model"):
        resolve_tts(cfg(), mlx_host())


def test_mlx_pin_uncalibrated_model_is_an_error(monkeypatch):
    calibrate_test_model(monkeypatch)
    with pytest.raises(TTSResolutionError,
                       match="mlx_audio model not calibrated for the runaway guard"):
        resolve_tts(cfg(mlx_audio={"model": TEST_MODEL}), mlx_host(tts_model="other/model"))


def test_mlx_pin_resolution_fields(monkeypatch):
    calibrate_test_model(monkeypatch)
    r = resolve_tts(cfg(mlx_audio={"model": TEST_MODEL}), mlx_host())
    assert r == TTSResolution(backend="mlx_audio", model=TEST_MODEL, api_key=None,
                              key_sources=(), presenter="phil", pinned=True)


def test_test_calibration_is_registered_only_inside_a_test(monkeypatch):
    assert TEST_MODEL not in calibration.CALIBRATED_MODELS
    calibrate_test_model(monkeypatch)
    assert calibration.CALIBRATED_MODELS[TEST_MODEL] is TEST_CAL
    monkeypatch.undo()
    # The registration is undone with the monkeypatch: nothing leaks into
    # the production table.
    assert TEST_MODEL not in calibration.CALIBRATED_MODELS
