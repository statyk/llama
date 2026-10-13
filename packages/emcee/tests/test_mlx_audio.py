"""The mlx_audio provider against httpx.MockTransport (spec sections 2-3)."""
import hashlib
import json
import math

import httpx
import pytest

from emcee.tts.calibration import cap_seconds, guard_problem, max_tokens_for, text_units
from emcee.tts.mlx_audio import (CONNECT_RETRY_DELAY_S, PREFLIGHT_MAX_TOKENS, PREFLIGHT_TEXT,
                                 MlxAudioProvider)
from emcee.tts.provider import SpeechDefect, SpeechError, SpeechProvider

from tests.mlx_helpers import TEST_CAL, TEST_MODEL, MlxServer, plausible_seconds, wav_bytes

SENTENCE = "The tapes have always called the room the Rotterdam Civic Hall."
TRANSCRIPT = "It's the chemistry, basically."


@pytest.fixture
def clip(tmp_path):
    p = tmp_path / "phil_ex.wav"
    p.write_bytes(wav_bytes(1.0))
    return p


def make(handler, clip, *, text=TRANSCRIPT, sleeps=None, url="http://127.0.0.1:8000"):
    return MlxAudioProvider(url=url, model=TEST_MODEL, clone_ref=str(clip), clone_text=text,
                            calibration=TEST_CAL, transport=httpx.MockTransport(handler),
                            sleep=(sleeps if sleeps is not None else []).append)


def replying(data: bytes, status: int = 200):
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, content=data)
    return handler, calls


def raising(exc_type):
    calls: list[httpx.Request] = []

    def handler(request):
        calls.append(request)
        raise exc_type("boom", request=request)
    return handler, calls


# --- guard math ---------------------------------------------------------------


def test_text_units_collapse_whitespace():
    assert text_units("  Here  is\nMorning   Dew. ") == len("Here is Morning Dew.")


def test_max_tokens_is_proportional_to_text_length():
    short, long = "Hello there, friends.", SENTENCE * 3
    assert max_tokens_for(TEST_CAL, short) < max_tokens_for(TEST_CAL, long)
    n = text_units(long)
    assert max_tokens_for(TEST_CAL, long) == math.ceil((8.0 + 0.12 * n) * 12.5)
    assert max_tokens_for(TEST_CAL, SENTENCE) == 195


def test_cap_seconds_is_tokens_over_frame_rate():
    assert cap_seconds(TEST_CAL, 250) == 20.0


def test_guard_accepts_a_plausible_clip():
    mt = max_tokens_for(TEST_CAL, SENTENCE)
    assert guard_problem(TEST_CAL, SENTENCE, plausible_seconds(SENTENCE), mt) is None


def test_guard_rejects_long_short_and_cap_length():
    mt = max_tokens_for(TEST_CAL, SENTENCE)  # n = 63: max_tokens 195 (cap 15.6 s), longest 10.93 s
    assert "implausibly long" in guard_problem(TEST_CAL, SENTENCE, 13.0, mt)
    assert "implausibly short" in guard_problem(TEST_CAL, SENTENCE, 0.2, mt)
    assert "token cap" in guard_problem(TEST_CAL, SENTENCE, cap_seconds(TEST_CAL, mt), mt)
    assert "token cap" in guard_problem(TEST_CAL, SENTENCE, cap_seconds(TEST_CAL, mt) - 0.5, mt)


def test_guard_rejects_a_zero_length_clip_for_short_text():
    # A short sentence's lower bound floors at 0 s; an empty clip must still fail.
    short = "Here is Morning Dew."
    mt = max_tokens_for(TEST_CAL, short)
    assert "clip is empty" in guard_problem(TEST_CAL, short, 0.0, mt)
    assert "clip is empty" in guard_problem(TEST_CAL, short, -1.0, mt)
    assert guard_problem(TEST_CAL, short, 0.5, mt) is None


# --- request ------------------------------------------------------------------


def test_is_a_speech_provider(clip):
    assert isinstance(make(MlxServer(), clip), SpeechProvider)


def test_request_body_and_url(clip):
    handler, calls = replying(wav_bytes(plausible_seconds(SENTENCE)))
    make(handler, clip, url="http://127.0.0.1:8000/").synthesize(SENTENCE, fmt="wav")
    assert str(calls[0].url) == "http://127.0.0.1:8000/v1/audio/speech"
    assert json.loads(calls[0].content) == {
        "model": TEST_MODEL, "input": SENTENCE, "response_format": "wav",
        "max_tokens": max_tokens_for(TEST_CAL, SENTENCE),
        "ref_audio": str(clip.resolve()), "ref_text": TRANSCRIPT}


def test_ref_audio_is_sent_as_an_absolute_path(tmp_path, monkeypatch):
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples" / "phil_ex.wav").write_bytes(wav_bytes(1.0))
    monkeypatch.chdir(tmp_path)
    server = MlxServer()
    p = MlxAudioProvider(url="http://127.0.0.1:8000", model=TEST_MODEL,
                         clone_ref="samples/phil_ex.wav", clone_text=TRANSCRIPT,
                         calibration=TEST_CAL, transport=server.transport())
    p.synthesize(SENTENCE, fmt="wav")
    assert server.speech_bodies[0]["ref_audio"] == str((tmp_path / "samples" / "phil_ex.wav").resolve())


def test_tilde_ref_audio_is_sent_expanded_and_absolute(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "samples").mkdir(parents=True)
    (home / "samples" / "phil_ex.wav").write_bytes(wav_bytes(1.0))
    monkeypatch.setenv("HOME", str(home))
    server = MlxServer()
    p = MlxAudioProvider(url="http://127.0.0.1:8000", model=TEST_MODEL,
                         clone_ref="~/samples/phil_ex.wav", clone_text=TRANSCRIPT,
                         calibration=TEST_CAL, transport=server.transport())
    p.synthesize(SENTENCE, fmt="wav")
    sent = server.speech_bodies[0]["ref_audio"]
    assert sent == str((home / "samples" / "phil_ex.wav").resolve())
    assert "~" not in sent


def test_context_arguments_are_accepted_and_not_sent(clip):
    server = MlxServer()
    make(server, clip).synthesize(SENTENCE, fmt="wav", previous_text="a", next_text="b")
    assert set(server.speech_bodies[0]) == {"model", "input", "response_format", "max_tokens",
                                            "ref_audio", "ref_text"}


# --- identity -----------------------------------------------------------------


def test_identity_hashes_clip_and_transcript(clip):
    p = make(MlxServer(), clip)
    expected = hashlib.sha256(clip.read_bytes() + b"\0" + TRANSCRIPT.encode()).hexdigest()[:16]
    assert p.voice == "clone:" + expected
    assert p.model == TEST_MODEL


def test_a_corrected_transcript_changes_the_identity(clip):
    assert make(MlxServer(), clip).voice != make(MlxServer(), clip, text="It is the chemistry.").voice


def test_voice_identity_ignores_surrounding_whitespace_in_transcript(clip):
    server = MlxServer()
    padded = make(server, clip, text=f"  {TRANSCRIPT}\n")
    assert padded.voice == make(MlxServer(), clip).voice
    padded.synthesize(SENTENCE, fmt="wav")
    assert server.speech_bodies[0]["ref_text"] == TRANSCRIPT


# --- construction-time rejection ----------------------------------------------


@pytest.mark.parametrize("text", [None, "", "  \n "])
def test_blank_transcript_rejected_before_synthesis(clip, text):
    with pytest.raises(SpeechError, match="needs the reference clip's transcript"):
        make(MlxServer(), clip, text=text)


def test_unreadable_or_empty_clip_rejected(tmp_path):
    with pytest.raises(SpeechError, match="unreadable"):
        make(MlxServer(), tmp_path / "missing.wav")
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(SpeechError, match="empty"):
        make(MlxServer(), empty)


# --- audio contract -----------------------------------------------------------


def test_wav_is_returned_as_is_for_fmt_wav(clip):
    data = wav_bytes(plausible_seconds(SENTENCE))
    handler, _ = replying(data)
    assert make(handler, clip).synthesize(SENTENCE, fmt="wav") == data


def test_mp3_is_encoded_locally_and_wav_still_requested(clip, monkeypatch):
    seen = {}

    def fake_encode(pcm, framerate, channels):
        seen.update(framerate=framerate, channels=channels, n=len(pcm))
        return b"MP3!"

    monkeypatch.setattr("emcee.audio._encode_mp3", fake_encode)
    server = MlxServer()
    assert make(server, clip).synthesize(SENTENCE) == b"MP3!"
    assert server.speech_bodies[0]["response_format"] == "wav"
    assert (seen["framerate"], seen["channels"]) == (24000, 1)


@pytest.mark.parametrize("data, match", [
    (b"", "empty body"),
    (b"<html>Bad Gateway</html>", "non-WAV body"),
    (wav_bytes(3.0, width=4), "emcee needs 16-bit PCM"),
    (wav_bytes(3.0, channels=2), "emcee needs mono"),
    (wav_bytes(3.0, rate=44100), "emcee supports only 24 kHz mlx models"),
])
def test_bad_audio_is_a_speech_error(clip, data, match):
    handler, _ = replying(data)
    with pytest.raises(SpeechError, match=match):
        make(handler, clip).synthesize(SENTENCE, fmt="wav")


# --- errors -------------------------------------------------------------------


def test_non_200_fails_at_once_with_the_servers_text(clip):
    handler, calls = replying(b"Model not found: 'x' is not a known HuggingFace repo", 404)
    sleeps: list = []
    with pytest.raises(SpeechError, match="mlx-audio returned 404: Model not found"):
        make(handler, clip, sleeps=sleeps).synthesize(SENTENCE)
    assert len(calls) == 1 and sleeps == []


@pytest.mark.parametrize("exc", [httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout])
def test_generation_failures_are_not_retried(clip, exc):
    handler, calls = raising(exc)
    sleeps: list = []
    with pytest.raises(SpeechError, match="see the mlx-audio server log"):
        make(handler, clip, sleeps=sleeps).synthesize(SENTENCE)
    assert len(calls) == 1 and sleeps == []


def test_connect_error_is_retried_once_then_names_the_server(clip):
    handler, calls = raising(httpx.ConnectError)
    sleeps: list = []
    with pytest.raises(SpeechError) as exc:
        make(handler, clip, sleeps=sleeps).synthesize(SENTENCE)
    assert str(exc.value) == ("mlx-audio server not reachable at http://127.0.0.1:8000 "
                              "(is the launchd service running?)")
    assert len(calls) == 2 and sleeps == [CONNECT_RETRY_DELAY_S]


def test_connect_error_then_success(clip):
    data = wav_bytes(plausible_seconds(SENTENCE))
    calls: list = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, content=data)

    assert make(handler, clip).synthesize(SENTENCE, fmt="wav") == data
    assert len(calls) == 2


# --- runaway guard (inside the provider; never retried there) -------------------


@pytest.mark.parametrize("seconds, reason", [
    (13.0, "implausibly long"),
    (0.2, "implausibly short"),
    (cap_seconds(TEST_CAL, max_tokens_for(TEST_CAL, SENTENCE)), "token cap"),
])
def test_guard_failures_raise_speech_defect_unretried(clip, seconds, reason):
    handler, calls = replying(wav_bytes(seconds))
    with pytest.raises(SpeechDefect) as exc:
        make(handler, clip).synthesize(SENTENCE, fmt="wav")
    assert reason in exc.value.reason
    assert exc.value.text == SENTENCE and exc.value.backend == "mlx_audio"
    assert isinstance(exc.value, SpeechError)
    assert exc.value.details == [f'text: "{SENTENCE}"']
    assert len(calls) == 1


def test_speech_defect_message_names_its_segment():
    d = SpeechDefect("mlx_audio", text="x", reason="clip is 9.0s, implausibly long",
                     transcript="y y y")
    d.segment = "set2-intro"
    assert str(d) == "mlx_audio audio failed a quality check in set2-intro: clip is 9.0s, implausibly long"
    assert d.details == ['text: "x"', 'transcript: "y y y"']


# --- preflight ------------------------------------------------------------------


def test_preflight_sentence_is_fixed_and_long_enough():
    assert PREFLIGHT_TEXT == "Good evening, and welcome to the show."
    assert len(PREFLIGHT_TEXT) >= 20 and PREFLIGHT_MAX_TOKENS == 200


def test_preflight_synthesizes_the_fixed_sentence(clip):
    server = MlxServer()
    make(server, clip).preflight()
    body = server.speech_bodies[0]
    assert (body["input"], body["max_tokens"], body["response_format"]) == (
        PREFLIGHT_TEXT, 200, "wav")


def test_preflight_wav_is_the_one_checked_take(clip):
    data = wav_bytes(2.0)
    handler, calls = replying(data)
    assert make(handler, clip).preflight_wav() == data
    assert len(calls) == 1


def test_preflight_on_a_dead_server_fails(clip):
    handler, _ = raising(httpx.ConnectError)
    with pytest.raises(SpeechError, match="not reachable"):
        make(handler, clip).preflight()


def test_preflight_rejects_a_non_24k_model(clip):
    handler, _ = replying(wav_bytes(2.0, rate=22050))
    with pytest.raises(SpeechError, match="24 kHz"):
        make(handler, clip).preflight()


def test_preflight_rejects_an_empty_wav(clip):
    handler, _ = replying(wav_bytes(0.0))
    with pytest.raises(SpeechError, match="no audio"):
        make(handler, clip).preflight()


def test_close_closes_the_client(clip):
    p = make(MlxServer(), clip)
    p.close()
    assert p._client.is_closed
