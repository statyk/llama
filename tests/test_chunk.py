"""Sentence-level chunked TTS synthesis, gated behind [tts] chunk.

Covers the sentence splitter, the chunked-synthesis encode path (bitrate
selection + the 16-bit PCM guard), the cache-key sensitivity to the chunk
flag, and end-to-end threading through run_package with the fake speech
backend.
"""
import io
import wave
from pathlib import Path

import pytest

from llama.models import DJNotes, Show, Track
from llama.stages.package import (
    _bitrate_for_rate,
    _split_sentences,
    _synthesize_chunked,
    run_package,
)
from llama.tts.fake import FakeSpeechProvider
from llama.tts.provider import SpeechError
from llama.workspace import ShowWorkspace, write_artifact

# --- _split_sentences ---------------------------------------------------


def test_split_multi_sentence():
    assert _split_sentences("Good evening, night owls. It's June 10th, 1973.") == [
        "Good evening, night owls.", "It's June 10th, 1973.",
    ]


def test_split_no_split_on_abbreviation():
    # Prefix before "Dr." is >= 20 chars, so the generic short-fragment
    # merge rule can't be what's suppressing the split - only is_abbrev can.
    text = "We are thrilled to welcome the one and only Dr. Fillmore to the stage."
    assert _split_sentences(text) == [text]


def test_split_no_split_on_vs():
    # Prefix before "vs." is >= 20 chars, isolating is_abbrev as the only
    # possible reason for the no-split.
    text = "Everyone always argued about the Dead vs. the Allmans, a classic old rivalry."
    assert _split_sentences(text) == [text]


def test_split_no_split_on_decimal():
    # Prefix before the decimal point is >= 20 chars, and the next fragment
    # starts with a digit ("6"), so only is_decimal can suppress the split.
    text = "The reading that evening was 98. 6 degrees, unusually warm for a June night."
    assert _split_sentences(text) == [text]


def test_split_no_split_on_single_letter_initial():
    # Prefix before "W." is >= 20 chars, isolating is_initial as the only
    # possible reason for the no-split.
    text = "It featured guitarist Bob W. Weir on rhythm guitar tonight."
    assert _split_sentences(text) == [text]


def test_split_merges_short_fragment():
    text = "Wow! It's 1973."
    assert _split_sentences(text) == [text]


def test_split_single_sentence():
    assert _split_sentences("Just one sentence here, folks.") == [
        "Just one sentence here, folks."]


def test_split_empty_input():
    assert _split_sentences("") == [""]


def test_split_whitespace_only_input():
    assert _split_sentences("   ") == [""]


# --- _bitrate_for_rate ---------------------------------------------------


def test_bitrate_low_for_24khz():
    assert _bitrate_for_rate(24000) == 64


def test_bitrate_mid_for_32khz():
    assert _bitrate_for_rate(32000) == 96


def test_bitrate_full_above_32khz():
    assert _bitrate_for_rate(44100) == 128


# --- _synthesize_chunked --------------------------------------------------


def test_synthesize_chunked_multi_sentence_produces_one_valid_mp3():
    speech = FakeSpeechProvider()
    text = ("Good evening, night owls. It's June 10th, 1973 at RFK Stadium. "
            "Let's dig in!")
    data = _synthesize_chunked(text, speech)
    assert len(data) > 0
    assert data[:3] == b"ID3" or data[0] == 0xFF  # valid MP3 framing
    # 3 sentences -> 3 separate fmt="wav" synthesize calls.
    assert len(speech.calls) == 3
    assert speech.calls == [
        "Good evening, night owls.",
        "It's June 10th, 1973 at RFK Stadium.",
        "Let's dig in!",
    ]


def test_synthesize_chunked_single_sentence_still_calls_wav_once():
    speech = FakeSpeechProvider()
    data = _synthesize_chunked("Just one line tonight.", speech)
    assert len(data) > 0
    assert len(speech.calls) == 1


def _wav_bytes(sampwidth: int, framerate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        w.writeframes(bytes(1000 * sampwidth))
    return buf.getvalue()


class _NonSixteenBitSpeech:
    """Stands in for a backend that (incorrectly) returns 8-bit PCM."""
    voice = "x"
    model = "y"

    def synthesize(self, text: str, fmt: str = "mp3") -> bytes:
        return _wav_bytes(sampwidth=1)


def test_synthesize_chunked_raises_on_non_16bit_pcm():
    with pytest.raises(SpeechError, match="16-bit"):
        _synthesize_chunked("One sentence.", _NonSixteenBitSpeech())


class _StubEncoder:
    """Records the bit rate lameenc.Encoder was configured with."""
    last_bit_rate = None

    def set_bit_rate(self, br):
        _StubEncoder.last_bit_rate = br

    def set_in_sample_rate(self, sr):
        pass

    def set_channels(self, c):
        pass

    def set_quality(self, q):
        pass

    def encode(self, pcm):
        return b""

    def flush(self):
        return b""


def test_synthesize_chunked_picks_low_bitrate_for_24khz(monkeypatch):
    import lameenc

    monkeypatch.setattr(lameenc, "Encoder", _StubEncoder)
    _synthesize_chunked("One sentence only, spoken at 24kHz.", FakeSpeechProvider())
    assert _StubEncoder.last_bit_rate == 64


# --- cache key sensitivity + end-to-end threading -------------------------


def make_show():
    return Show(
        performance_id="GratefulDead/1973-06-10", identifier="gd73",
        artist="Grateful Dead", date="1973-06-10", venue="RFK Stadium",
        tracks=[Track(index=1, set="1", title="Morning Dew", filename="d1t01.mp3",
                      duration_sec=600.0, title_source="tags")],
        set_breaks=[],
    )


def make_notes():
    return DJNotes(
        context="ctx",
        set_intros={"1": "Good evening, night owls. It's June 10th, 1973 at RFK "
                         "Stadium. Let's dig in!"},
        outro="Thanks for listening, folks.",
    )


class StubIA:
    def metadata(self, identifier):
        return {"files": [{"name": "d1t01.mp3", "md5": "m1"}]}

    def download_file(self, identifier, filename, dest, md5=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"\x00" * 64)
        return dest


def setup(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "s")
    show = make_show()
    write_artifact(sws.show, show)
    return sws, show


def test_chunk_flag_is_part_of_the_cache_key(tmp_path: Path):
    sws, show = setup(tmp_path)
    run_package(sws, StubIA(), show, make_notes(), speech=FakeSpeechProvider(), chunk=False)
    (sws.package_dir / "manifest.json").unlink()  # what redo --from package does

    second = FakeSpeechProvider()
    run_package(sws, StubIA(), show, make_notes(), speech=second, chunk=True)
    # Toggling chunk changed the cache key -> re-rendered, not skipped.
    assert len(second.calls) > 0


def test_chunk_true_synthesizes_via_chunked_path(tmp_path: Path):
    sws, show = setup(tmp_path)
    speech = FakeSpeechProvider()
    notes = make_notes()

    pkg = run_package(sws, StubIA(), show, notes, speech=speech, chunk=True)

    mp3_path = pkg / "dj-audio" / "set1-intro.mp3"
    data = mp3_path.read_bytes()
    assert len(data) > 0
    assert data[:3] == b"ID3" or data[0] == 0xFF  # valid MP3 framing

    # The set 1 lead-in splits into 3 sentences; the outro is 1. Chunked mode makes
    # one fmt="wav" synthesize call per sentence, so total calls (4) exceed
    # the 2 segments actually rendered.
    assert len(speech.calls) == 4


def test_chunk_false_uses_single_call_per_segment(tmp_path: Path):
    sws, show = setup(tmp_path)
    speech = FakeSpeechProvider()
    notes = make_notes()

    run_package(sws, StubIA(), show, notes, speech=speech, chunk=False)

    # One call per segment (set 1 lead-in, outro), not per sentence.
    assert speech.calls == [notes.set_intros["1"], notes.outro]
