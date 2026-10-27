"""Transcript verification (spec section 3): the comparison, the STT
client, the layer's use of it, and preflight's end-to-end STT check."""
from pathlib import Path

import json

import httpx
import pytest
from herder import FakeProvider
from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.audio import _synthesize_dj_audio
from emcee.cli import _process_one, app
from emcee.config import EmceeConfig, load_config
from emcee.models import ScriptNotes
from emcee.package_io import Package
from emcee.presenters import Presenter, save_presenter
from emcee.process import ad_hoc_speech, process_package
from emcee.tts import speech_provider_for
from emcee.tts.fake import FakeSpeechProvider
from emcee.tts.mlx_audio import PREFLIGHT_TEXT
from emcee.tts.provider import SpeechDefect, SpeechError
from emcee.tts.quality import QualitySpeech
from emcee.tts.resolve import resolve_tts
from emcee.tts.verify import (SttClient, Verifier, comparable_words, match_words,
                              preflight_clip_wav, transcript_problem)

from tests.helpers import build_package, no_moves, voicing_for
from tests.mlx_helpers import (TEST_MODEL, MlxServer, calibrate_test_model, install_mlx,
                               plausible_seconds, wav_bytes)

runner = CliRunner()
STT = "stt/test-model"
WAV = wav_bytes(1.0)
LINE = "Tonight we open the vault to the Grateful Dead in Rotterdam."


# --- the comparison -------------------------------------------------------------


def test_comparable_words_normalize_and_drop_numbers():
    assert comparable_words("It's May Eleventh, 1972 -- the 15th show!") == ["its", "may", "the", "show"]
    assert comparable_words("Seventy-two, twenty-one hundred.") == []


def test_exact_and_case_punctuation_differences_pass():
    assert transcript_problem(LINE, "tonight, we open the vault to the grateful dead in rotterdam") is None


def test_a_wrong_word_or_two_passes():
    assert transcript_problem("Here is Morning Dew.", "Here is morning due.") is None
    assert transcript_problem(
        "It was really the great hall of De Doelen, in Rotterdam.",
        "It was really the great hall of Dedoulin in Rotterdam.") is None


def test_number_formatting_is_ignored():
    assert transcript_problem("On May eleventh, 1972, the band played.",
                              "On May 11th, nineteen seventy-two, the band played.") is None


def test_all_number_sentence_passes():
    assert transcript_problem("1972.", "Nineteen seventy-two.") is None
    assert transcript_problem("Seventy-two.", "72") is None


def test_too_few_script_words_heard_fails():
    problem = transcript_problem(LINE, "tonight we")
    assert problem is not None and "words were heard" in problem


def test_a_transcript_far_longer_than_the_script_fails():
    loop = " ".join(["here is morning dew"] * 6)
    problem = transcript_problem("Here is Morning Dew.", loop)
    assert problem is not None and "words for a" in problem


def test_an_empty_transcript_fails_a_real_sentence():
    assert transcript_problem(LINE, "") is not None


# Calibration (docs/superpowers/2026-10-12-mlx-audio-calibration.md): every
# clean miss that drove the thresholds up was a joined or split word -- "Here
# is" heard as "Here's", "L.A." as "LA", "Wharf Rat" as "Wharfrat".


def found(script: str, transcript: str) -> int:
    return match_words(comparable_words(script), comparable_words(transcript))[0]


def test_a_script_bigram_heard_joined_counts_as_found():
    assert found("Here is the second set, from Pittsburgh.",
                 "Here's the second set from Pittsburgh.") == 6
    assert found("Listen for West L.A.", "Listen for West LA.") == 5
    assert found("Jerry sang Wharf Rat.", "Jerry sang Wharfrat.") == 4


def test_a_heard_bigram_matching_a_script_token_counts_as_found():
    assert found("Throwin' Stones and Lovelight.", "Throw in stones and love light.") == 4
    assert found("Here's the set.", "Here is the set.") == 3


def test_folding_never_counts_a_heard_token_twice():
    assert found("Here is, here is.", "Here's.") == 2
    assert found("Love light.", "Lovelight lovelight.") == 2


def test_match_words_returns_the_unmatched_words_on_each_side():
    n, missing, extra = match_words(comparable_words("Here is Kezar Stadium."),
                                    comparable_words("Here's Kizar Stadium."))
    assert (n, sorted(missing.elements()), sorted(extra.elements())) == (3, ["kezar"], ["kizar"])


def test_joined_words_do_not_fail_a_sentence():
    script = "Here is L.A., and you are in Wharf Rat country."
    assert transcript_problem(script, "Here's LA, and you're in Wharfrat country.") is None


def test_nothing_of_a_short_script_heard_fails():
    # Below the miss floor a total mishearing used to pass.
    problem = transcript_problem("Thanks, everyone.", "Goodbye.")
    assert problem is not None and "none of the script's 2 words" in problem
    assert transcript_problem("Thanks.", "") is not None


def test_one_word_heard_of_a_short_script_still_passes():
    assert transcript_problem("Thanks, everyone.", "Thanks, everybody.") is None


def test_a_repeated_word_pairs_only_with_two_unmatched_copies():
    # The exact match takes one "bye"; the lone remaining copy cannot pair
    # with itself, so found never exceeds the script's word count.
    assert found("Bye bye.", "Bye byebye.") == 1
    assert found("Bye byebye.", "Bye bye.") == 1


def test_only_adjacent_script_words_fold():
    assert found("L b a.", "La.") == 0


def test_an_unrelated_heard_word_is_not_credited():
    assert match_words(["show"], ["snow"])[0] == 0
    assert found("Here is the show.", "Here's the snow.") == 3


def test_a_long_script_heard_as_a_few_contractions_still_fails():
    script = "Here is what you are going to hear tonight from the band on the stage."
    assert transcript_problem(script, "Here's you're.") is not None


# The lexicon spells a dropped g with an apostrophe ("Goin' Down The Road
# Feelin' Bad"); the transcriber writes "going"/"feeling" (calibration unit 21).


def test_a_dropped_g_matches_the_ing_form_both_ways():
    assert comparable_words("Goin' Down The Road Feelin' Bad") == [
        "going", "down", "the", "road", "feeling", "bad"]
    assert found("Goin' Down The Road Feelin' Bad.", "Going down the road feeling bad.") == 6
    assert found("Going down the road feeling bad.", "Goin' down the road feelin’ bad.") == 6


def test_a_dropped_g_heard_as_two_words_still_matches():
    assert found("Throwin' Stones.", "Throw in stones.") == 2


def test_words_that_merely_end_in_in_are_not_g_dropped():
    assert comparable_words("Begin in within, then 'within' and in'.") == [
        "begin", "in", "within", "then", "within", "and", "in"]
    assert found("Begin within.", "Beginning withing.") == 0


# A single-quoted title ending in "in" closes its quote on that word; the
# closing quote is not a dropped g (final review: 'Fire on the Mountain').


def test_a_closing_quote_after_in_is_not_a_dropped_g():
    assert comparable_words("Then 'Fire on the Mountain' closed it.") == [
        "then", "fire", "on", "the", "mountain", "closed", "it"]
    assert found("Then 'Fire on the Mountain' closed it.",
                 "Then Fire on the Mountain closed it.") == 7
    assert transcript_problem("Then ‘Fire on the Mountain’ closed it.",
                              "Then Fire on the Mountain closed it.") is None


def test_dropped_gs_inside_a_quoted_title_fold_after_its_first_word():
    # A quoted word ending in in' reads as a one-word quoted title ('Win'):
    # folding it could only ever give false credit, so it stays.
    assert comparable_words("They opened with 'Goin' Down The Road Feelin' Bad'.") == [
        "they", "opened", "with", "goin", "down", "the", "road", "feeling", "bad"]


def test_a_one_word_quoted_title_is_never_folded():
    assert comparable_words("'Win' and the drummers' solo, 'Mountain' and James' guitar") == [
        "win", "and", "the", "drummers", "solo", "mountain", "and", "james", "guitar"]
    # ... whatever precedes its quote mark, recognised as an opening quote or not
    assert comparable_words("Then\u2014'Win' was next, `Win' and \u2019Win\u2019 too.") == [
        "then", "win", "was", "next", "win", "and", "win", "too"]


def test_a_title_closed_on_in_does_not_shield_later_dropped_gs():
    assert comparable_words("'Fire on the Mountain' > Goin' Down The Road Feelin' Bad.") == [
        "fire", "on", "the", "mountain", "going", "down", "the", "road", "feeling", "bad"]
    assert comparable_words(
        "He's playin' 'Jack Straw' and 'Fire on the Mountain' and singin' loud.") == [
        "hes", "playing", "jack", "straw", "and", "fire", "on", "the", "mountain",
        "and", "singing", "loud"]


def test_punctuation_inside_the_closing_quote_still_closes_it():
    assert comparable_words("'Scarlet Begonias,' then Truckin'.") == [
        "scarlet", "begonias", "then", "trucking"]
    assert comparable_words("'Fire on the Mountain.' Truckin'") == [
        "fire", "on", "the", "mountain", "trucking"]


def test_a_later_ambiguous_mark_does_not_prove_a_close():
    # Goin' after the title could be a dropped g OR a close; only an
    # unambiguous mark proves the quote closed, so Mountain' stays a close.
    assert comparable_words("'Fire on the Mountain', then Goin'.") == [
        "fire", "on", "the", "mountain", "then", "going"]


def test_a_quote_closed_earlier_does_not_shield_a_later_dropped_g():
    assert comparable_words("'Mountain Jam', then goin' home.") == [
        "mountain", "jam", "then", "going", "home"]


def test_a_leading_elision_is_not_an_opening_quote():
    assert comparable_words("'Cause we're goin' home, rock 'n' rollin' on.") == [
        "cause", "were", "going", "home", "rock", "n", "rolling", "on"]
    assert comparable_words("'Cuz 'nuff said, we're goin' home.") == [
        "cuz", "nuff", "said", "were", "going", "home"]


# --- the STT client ---------------------------------------------------------------


def stt(server, url="http://127.0.0.1:8000"):
    return SttClient(url=url, model=STT, transport=server.transport())


def test_transcription_request_shape():
    server = MlxServer(transcript=lambda last: "  Hello there.  ")
    assert stt(server).transcribe(WAV) == "Hello there."
    req = server.transcriptions[0]
    assert req.url.path == "/v1/audio/transcriptions"
    body = req.content
    assert b'filename="clip.wav"' in body
    assert b'name="model"\r\n\r\nstt/test-model\r\n' in body
    assert b'name="language"\r\n\r\nen\r\n' in body
    assert b'name="response_format"\r\n\r\njson\r\n' in body


def test_failed_transcription_requests_are_speech_errors():
    with pytest.raises(SpeechError, match="not reachable at http://127.0.0.1:8000 for transcription"):
        stt(MlxServer(stt_down=True)).transcribe(WAV)
    with pytest.raises(SpeechError, match="mlx-audio transcription returned 500"):
        stt(MlxServer(stt_status=500)).transcribe(WAV)

    def no_text(request):
        return httpx.Response(200, json={"segments": []})

    client = SttClient(url="http://x", model=STT, transport=httpx.MockTransport(no_text))
    with pytest.raises(SpeechError, match="no text"):
        client.transcribe(WAV)


def test_unload_deletes_the_model():
    server = MlxServer()
    stt(server).unload()
    assert server.deletes == [{"model_name": STT}]


def test_the_bundled_clip_loader_fails_closed_when_missing(monkeypatch):
    monkeypatch.setattr("emcee.tts.verify.PREFLIGHT_CLIP", "no-such-clip.wav")
    with pytest.raises(SpeechError, match="emcee/data/no-such-clip.wav"):
        preflight_clip_wav()


# --- the layer with a verifier ----------------------------------------------------


class Scripted:
    voice = "inner-voice"
    model = "inner-model"

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[tuple] = []
        self.preflights = 0

    def synthesize(self, text, fmt="mp3", *, previous_text=None, next_text=None):
        self.calls.append((text, fmt))
        return self.outcomes.pop(0)

    def preflight(self):
        self.preflights += 1

    def close(self):
        pass


def verified(inner, server, backend="voxtral"):
    return QualitySpeech(inner, backend=backend, verifier=Verifier(stt(server)))


def test_verification_requests_wav_and_encodes_mp3_locally(monkeypatch):
    monkeypatch.setattr("emcee.audio._encode_mp3", lambda pcm, rate, ch: b"MP3!")
    inner = Scripted(WAV)
    server = MlxServer(transcript=lambda last: LINE)
    assert verified(inner, server).synthesize(LINE, "mp3") == b"MP3!"
    assert inner.calls == [(LINE, "wav")]
    assert len(server.transcriptions) == 1


def test_verification_pass_returns_the_wav():
    assert verified(Scripted(WAV), MlxServer(transcript=lambda last: LINE)).synthesize(LINE, "wav") == WAV


def test_verification_fail_then_pass():
    heard = iter(["completely unrelated words about the weather today", LINE])
    inner = Scripted(WAV, WAV)
    assert verified(inner, MlxServer(transcript=lambda last: next(heard))).synthesize(LINE, "wav") == WAV
    assert len(inner.calls) == 2


def test_verification_double_fail_names_both_texts():
    garbage = "completely unrelated words about the weather today"
    with pytest.raises(SpeechDefect) as exc:
        verified(Scripted(WAV, WAV), MlxServer(transcript=lambda last: garbage)).synthesize(LINE, "wav")
    assert exc.value.details == [f'text: "{LINE}"', f'transcript: "{garbage}"']
    assert "transcript mismatch" in exc.value.reason and "(failed twice)" in exc.value.reason


def test_a_failed_transcription_request_is_an_error_never_a_pass():
    inner = Scripted(WAV, WAV)
    with pytest.raises(SpeechError) as exc:
        verified(inner, MlxServer(stt_status=500)).synthesize(LINE, "wav")
    assert not isinstance(exc.value, SpeechDefect)
    assert len(inner.calls) == 1


def test_cache_hits_are_not_re_verified(tmp_path):
    checks: list[str] = []

    class CountingVerifier:
        def check(self, wav, text, *, backend):
            checks.append(text)

        def close(self):
            pass

    pkg = build_package(tmp_path / "station", voiced=False)
    notes = ScriptNotes(set_intros={"1": "Set one opens.", "2": "Set two follows."}, outro="Thanks.")
    speech = QualitySpeech(FakeSpeechProvider(), backend="voxtral", verifier=CountingVerifier())
    _synthesize_dj_audio(pkg, notes, speech, False, chunking=None)
    first = len(checks)
    _synthesize_dj_audio(pkg, notes, speech, False, chunking=None)
    assert first == 3 and len(checks) == first  # every clip came from the cache


# --- which providers are verified ---------------------------------------------------


def _verify_cfg(backends, **tts):
    return EmceeConfig.model_validate({"tts": {
        "mlx_audio": {"model": TEST_MODEL, "stt_model": STT},
        "verify": {"backends": backends}, **tts}})


def test_voxtral_is_verified_only_when_listed(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    off = _verify_cfg(["mlx_audio"])
    on = _verify_cfg(["voxtral"])
    plain = speech_provider_for(off, resolve_tts(off, None), voice="v", clone_ref=None, clone_text=None)
    wrapped = speech_provider_for(on, resolve_tts(on, None), voice="v", clone_ref=None, clone_text=None)
    assert not isinstance(plain, QualitySpeech)
    assert isinstance(wrapped, QualitySpeech) and wrapped.verifier is not None
    assert wrapped.voice == wrapped.inner.voice  # enabling verification keeps the cache key


@pytest.mark.parametrize("backends, verified_", [([], False), (["mlx_audio"], True)])
def test_mlx_gets_a_verifier_only_when_listed(tmp_path, monkeypatch, backends, verified_):
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = _verify_cfg(backends)
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text="Hi there.", tts="mlx_audio", character="x")
    p = speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None, clone_ref=str(clip),
                            clone_text="Hi there.")
    assert isinstance(p, QualitySpeech) and (p.verifier is not None) is verified_


def test_say_paths_are_wrapped_when_the_backend_is_listed(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = _verify_cfg(["voxtral"], voice="house-preset")
    host = Presenter(id="roy", name="R", sex="male", voice="roy-preset", character="x")
    for speech in (ad_hoc_speech(cfg), ad_hoc_speech(cfg, clone_ref=str(clip)),
                   ad_hoc_speech(cfg, presenter=host)):
        assert isinstance(speech, QualitySpeech) and speech.verifier is not None


# --- never silently skipped: preflight checks the STT path ---------------------------


def _station(tmp_path, monkeypatch, tts_toml: str, assign_toml: str = "") -> tuple[Path, Path]:
    home, station = tmp_path / "home", tmp_path / "station"
    home.mkdir()
    station.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(f'[station]\nroot = "{station}"\n\n{tts_toml}\n{assign_toml}\n')
    return home, station


def _forbid_scriptwrite(monkeypatch) -> list[str]:
    tasks: list[str] = []

    def no_llm(settings, task):
        tasks.append(task)
        raise AssertionError("LLM called before preflight passed")

    monkeypatch.setattr(process_mod, "provider_for", no_llm)
    return tasks


_MLX_VERIFIED = (f'[tts]\nbackend = "fake"\nvoice = "house"\n\n'
                 f'[tts.mlx_audio]\nmodel = "{TEST_MODEL}"\nstt_model = "{STT}"\n\n'
                 '[tts.verify]\nbackends = ["mlx_audio"]\n')
_VOXTRAL_VERIFIED = (f'[tts]\nvoice = "house-preset"\n\n'
                     f'[tts.mlx_audio]\nstt_model = "{STT}"\n\n'
                     '[tts.verify]\nbackends = ["voxtral"]\n')


def _mlx_presenter(home: Path) -> None:
    clip = home / "phil_ex.wav"
    clip.write_bytes(WAV)
    save_presenter(home, Presenter(id="phil", name="Phil", sex="male", voice_clone=str(clip),
                                   voice_clone_text="It's the chemistry.", tts="mlx_audio",
                                   character="x"))


@pytest.mark.parametrize("server_kwargs, error", [
    ({"stt_down": True}, "for transcription"),
    ({"transcript": lambda last: "nothing at all like the words that were sent"}, "transcript mismatch"),
])
def test_mlx_preflight_fails_the_package_on_a_broken_stt_path(tmp_path, monkeypatch,
                                                              server_kwargs, error):
    calibrate_test_model(monkeypatch)
    home, station = _station(tmp_path, monkeypatch, _MLX_VERIFIED,
                             '[assign.profiles.dead]\npresenter = "phil"\n')
    _mlx_presenter(home)
    pkg_dir = build_package(station, slug="showA", profile="dead", voiced=True)
    before = (pkg_dir / "manifest.json").read_bytes()
    install_mlx(monkeypatch, MlxServer(**server_kwargs))
    tasks = _forbid_scriptwrite(monkeypatch)

    with pytest.raises(SpeechError, match=error):
        _process_one(load_config(), no_moves(), Package(pkg_dir), False)

    assert tasks == []
    assert (pkg_dir / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("server_kwargs, error", [
    ({"stt_down": True}, "for transcription"),
    ({"transcript": lambda last: "nothing at all like the check sentence"}, "verification preflight failed"),
])
def test_hosted_preflight_checks_the_bundled_clip(tmp_path, monkeypatch, server_kwargs, error):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    home, station = _station(tmp_path, monkeypatch, _VOXTRAL_VERIFIED)
    pkg_dir = build_package(station, slug="showA", voiced=True)  # no profile: the house voice
    before = (pkg_dir / "manifest.json").read_bytes()
    install_mlx(monkeypatch, MlxServer(**server_kwargs))
    monkeypatch.setattr("emcee.tts.verify.preflight_clip_wav", lambda: wav_bytes(2.0))
    tasks = _forbid_scriptwrite(monkeypatch)

    with pytest.raises(SpeechError, match=error):
        _process_one(load_config(), no_moves(), Package(pkg_dir), False)

    assert tasks == []
    assert (pkg_dir / "manifest.json").read_bytes() == before


def test_hosted_preflight_passes_on_a_good_transcription(tmp_path, monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    _station(tmp_path, monkeypatch, _VOXTRAL_VERIFIED)
    server = MlxServer(transcript=lambda last: PREFLIGHT_TEXT)
    install_mlx(monkeypatch, server)
    monkeypatch.setattr("emcee.tts.verify.preflight_clip_wav", lambda: wav_bytes(2.0))
    cfg = load_config()
    speech = speech_provider_for(cfg, resolve_tts(cfg, None), voice="house-preset",
                                 clone_ref=None, clone_text=None)
    speech.preflight()
    assert len(server.transcriptions) == 1 and server.speech_bodies == []  # no hosted spend


def _verified_mlx_speech(tmp_path, monkeypatch, server):
    """A verified, unchunked mlx provider routed through `server`, and its config."""
    calibrate_test_model(monkeypatch)
    clip = tmp_path / "c.wav"
    clip.write_bytes(WAV)
    cfg = _verify_cfg(["mlx_audio"], chunk=False).model_copy(update={"root": tmp_path / "home"})
    phil = Presenter(id="phil", name="P", sex="male", voice_clone=str(clip),
                     voice_clone_text="Hi there.", tts="mlx_audio", character="x")
    install_mlx(monkeypatch, server)
    return cfg, speech_provider_for(cfg, resolve_tts(cfg, phil), voice=None,
                                    clone_ref=str(clip), clone_text="Hi there.")


def test_verified_mlx_preflight_transcribes_its_one_take(tmp_path, monkeypatch):
    server = MlxServer(transcript=lambda last: PREFLIGHT_TEXT)
    _, speech = _verified_mlx_speech(tmp_path, monkeypatch, server)
    speech.preflight()
    assert [(b["input"], b["max_tokens"]) for b in server.speech_bodies] == [(PREFLIGHT_TEXT, 200)]
    assert len(server.transcriptions) == 1
    assert wav_bytes(plausible_seconds(PREFLIGHT_TEXT)) in server.transcriptions[0].content


def test_verified_mlx_preflight_retries_once_on_a_mismatch(tmp_path, monkeypatch):
    heard = iter(["nothing like it, the weather today", PREFLIGHT_TEXT])
    server = MlxServer(transcript=lambda last: next(heard))
    _, speech = _verified_mlx_speech(tmp_path, monkeypatch, server)
    speech.preflight()
    assert [(b["input"], b["max_tokens"]) for b in server.speech_bodies] == [(PREFLIGHT_TEXT, 200)] * 2
    assert len(server.transcriptions) == 2


def test_a_verified_package_whose_segment_fails_twice_is_not_voiced(tmp_path, monkeypatch):
    garbage = "completely unrelated words about the weather today"
    cfg, speech = _verified_mlx_speech(tmp_path, monkeypatch,
                                       MlxServer(transcript=lambda last: garbage))
    notes = {"context": "Spring '73 tour",
             "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                            "2": "China Cat Sunflower leads set two."},
             "outro": "I Know You Rider sends us off. Thanks for listening.",
             "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"]}
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[json.dumps(notes)]))
    pkg = Package(build_package(tmp_path / "station", voiced=False))
    before = pkg.manifest_path.read_bytes()

    with pytest.raises(SpeechDefect) as exc:
        process_package(cfg, pkg, speech, voicing=voicing_for(cfg, pkg))

    assert exc.value.segment == "set1-intro"
    assert "in set1-intro" in str(exc.value) and "(failed twice)" in str(exc.value)
    assert pkg.manifest_path.read_bytes() == before
    assert not (pkg.dir / "dj-audio" / "set1-intro.mp3").exists()


def test_say_verifies_without_preflight(tmp_path, monkeypatch):
    calibrate_test_model(monkeypatch)
    home, _ = _station(tmp_path, monkeypatch, _MLX_VERIFIED)
    _mlx_presenter(home)
    server = MlxServer(stt_down=True)
    install_mlx(monkeypatch, server)
    text = tmp_path / "say.txt"
    text.write_text("Good evening, everybody, and welcome back to the archive.")

    result = runner.invoke(app, ["say", str(text), "--presenter", "phil"])

    assert result.exit_code == 1
    assert "for transcription" in str(result.exception)
    assert server.speech_bodies and server.speech_bodies[0]["input"] != PREFLIGHT_TEXT
