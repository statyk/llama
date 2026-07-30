"""Tests for `emcee.audio`.

Two halves, both ported from llama:

- The pure sentence-splitter/bitrate/chunked-encode functions, ported
  verbatim (import-renamed) from `packages/llama/tests/test_chunk.py`
  against `emcee.audio` directly.
- The voice-specific `process_package` behaviors (dj-audio synthesis +
  manifest block, segment cache skip/re-key, orphan pruning, segue-symbol +
  pronunciation-lexicon normalization, the 5 bed tests, the chunk flag),
  ported from `packages/llama/tests/test_stage_package.py` /
  `test_chunk.py`'s end-to-end section, re-addressed to `process_package`
  with `FakeSpeechProvider` + `build_package` fixtures. `write_script` is
  stubbed to return a fixed `ScriptNotes` -- these tests exercise the audio
  pipeline, not scriptwriting (that's `test_scriptwrite.py`'s job).
"""

import io
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from emcee.audio import (
    _bitrate_for_rate,
    _split_sentences,
    _synthesize_chunked,
)
from emcee.config import EmceeConfig, TTSConfig
from emcee.models import ScriptNotes
from emcee.package_io import Package
from emcee.process import process_package
from emcee.tts.fake import SILENT_MP3, FakeSpeechProvider
from emcee.tts.provider import SpeechError

from tests.helpers import build_package

# ---------------------------------------------------------------------------
# _split_sentences
# ---------------------------------------------------------------------------


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


def test_split_merges_short_trailing_fragment_backward():
    # A short final sentence after a long one must fold into the previous
    # chunk rather than be synthesized as its own tiny, context-free clip -
    # short isolated inputs make the TTS backend hallucinate phoneme salad
    # (observed live: GD 1977-05-08 set-2 lead-in ending "Here's set two.").
    text = ("The second set is where the legend really lives and breathes. "
            "Here's set two.")
    assert _split_sentences(text) == [text]


def test_split_single_sentence():
    assert _split_sentences("Just one sentence here, folks.") == [
        "Just one sentence here, folks."]


def test_split_empty_input():
    assert _split_sentences("") == [""]


def test_split_whitespace_only_input():
    assert _split_sentences("   ") == [""]


# ---------------------------------------------------------------------------
# _bitrate_for_rate
# ---------------------------------------------------------------------------


def test_bitrate_low_for_24khz():
    assert _bitrate_for_rate(24000) == 64


def test_bitrate_mid_for_32khz():
    assert _bitrate_for_rate(32000) == 96


def test_bitrate_full_above_32khz():
    assert _bitrate_for_rate(44100) == 128


# ---------------------------------------------------------------------------
# _synthesize_chunked
# ---------------------------------------------------------------------------


def test_synthesize_chunked_multi_sentence_produces_one_valid_mp3():
    speech = FakeSpeechProvider()
    text = ("Good evening, night owls. It's June 10th, 1973 at RFK Stadium. "
            "Let's dig in!")
    data = _synthesize_chunked(text, speech)
    assert len(data) > 0
    assert data[:3] == b"ID3" or data[0] == 0xFF  # valid MP3 framing
    # Splits into 3 raw sentences, but the short trailing "Let's dig in!"
    # (< 20 chars) folds back into the prior sentence rather than becoming its
    # own tiny clip -> 2 fmt="wav" synthesize calls.
    assert len(speech.calls) == 2
    assert speech.calls == [
        "Good evening, night owls.",
        "It's June 10th, 1973 at RFK Stadium. Let's dig in!",
    ]


def test_synthesize_chunked_threads_neighbor_text_as_context():
    speech = FakeSpeechProvider()
    text = ("First sentence here, plenty long. Second sentence here, also long. "
            "Third one here, quite long too.")
    _synthesize_chunked(text, speech)
    c1, c2, c3 = speech.calls
    # Each chunk is synthesized with its actual neighbors as context so a
    # context-aware backend keeps prosody continuous across the boundaries;
    # the first/last chunk has None on its open side.
    assert speech.context == [(None, c2), (c1, c3), (c2, None)]


def test_synthesize_chunked_single_sentence_has_no_context():
    speech = FakeSpeechProvider()
    _synthesize_chunked("Just one line tonight, spoken alone.", speech)
    assert speech.context == [(None, None)]


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

    def synthesize(self, text: str, fmt: str = "mp3", *,
                   previous_text: str | None = None,
                   next_text: str | None = None) -> bytes:
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


# ---------------------------------------------------------------------------
# process_package: voice-specific behavior (dj-audio synthesis, segment
# cache, orphan pruning, normalization, bed, chunk flag)
# ---------------------------------------------------------------------------


def _pkg(tmp_path: Path, **kwargs) -> Package:
    return Package(build_package(tmp_path / "station", voiced=False, **kwargs))


def _config(tmp_path: Path, **tts_kwargs) -> EmceeConfig:
    return EmceeConfig(root=tmp_path / "home", tts=TTSConfig(**tts_kwargs))


def make_notes(**overrides) -> ScriptNotes:
    d = dict(context="from the notes", outro="o", set_intros={"1": "a", "2": "b"},
             mentioned_songs=[])
    d.update(overrides)
    return ScriptNotes(**d)


def _process(config: EmceeConfig, pkg: Package, speech, notes: ScriptNotes,
            force: bool = False) -> None:
    """process_package with write_script stubbed to return `notes` --
    these tests exercise the audio pipeline, not scriptwriting."""
    with patch("emcee.process.write_script", return_value=notes):
        process_package(config, pkg, speech, force=force)


def test_process_package_synthesizes_dj_audio_and_manifest_block(tmp_path):
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    speech = FakeSpeechProvider()
    notes = make_notes()

    _process(config, pkg, speech, notes)

    dj = pkg.dir / "dj-audio"
    for name in ["set1-intro.mp3", "set2-intro.mp3", "99-outro.mp3"]:
        assert (dj / name).read_bytes() == SILENT_MP3
    assert not (dj / "00-intro.mp3").exists() and not (dj / "break1.mp3").exists()
    assert speech.calls == [notes.set_intros["1"], notes.set_intros["2"], notes.outro]
    m = pkg.manifest()
    assert m["dj_audio"] == {
        "set_intros": {"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        "outro": "dj-audio/99-outro.mp3",
    }


def test_process_package_segment_cache_skips_unchanged(tmp_path):
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    _process(config, pkg, FakeSpeechProvider(), make_notes())

    second = FakeSpeechProvider()
    _process(config, pkg, second, make_notes())

    assert second.calls == []  # no re-spend on unchanged text


def test_process_package_changed_text_resynthesizes_only_that_segment(tmp_path):
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    _process(config, pkg, FakeSpeechProvider(), make_notes())

    second = FakeSpeechProvider()
    _process(config, pkg, second, make_notes(outro="a different outro"))

    assert second.calls == ["a different outro"]


def test_process_package_different_voice_resynthesizes(tmp_path):
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    _process(config, pkg, FakeSpeechProvider(), make_notes())

    second = FakeSpeechProvider()
    second.voice = "other-voice"  # cache key includes the voice
    _process(config, pkg, second, make_notes())

    assert len(second.calls) == 3  # set1-intro, set2-intro, outro


def test_process_package_force_rerenders_all_segments(tmp_path):
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    _process(config, pkg, FakeSpeechProvider(), make_notes())

    second = FakeSpeechProvider()
    _process(config, pkg, second, make_notes(), force=True)

    assert len(second.calls) == 3  # set1-intro, set2-intro, outro


def test_process_package_shrinking_set_intros_prunes_orphan_clips(tmp_path):
    pkg = _pkg(tmp_path, sets=("1", "2"), encore=True)
    config = _config(tmp_path)
    notes = make_notes(set_intros={"1": "a", "2": "b", "encore": "c"})
    _process(config, pkg, FakeSpeechProvider(), notes)
    dj = pkg.dir / "dj-audio"
    assert (dj / "set2-intro.mp3").exists()
    assert (dj / "setencore-intro.mp3").exists()

    fewer_notes = notes.model_copy(update={"set_intros": {"1": "a", "2": "b"}})
    _process(config, pkg, FakeSpeechProvider(), fewer_notes)

    assert (dj / "set2-intro.mp3").exists()
    assert not (dj / "setencore-intro.mp3").exists()  # orphan from the shrunk re-synth is gone
    assert (dj / "segments.json").exists()             # sidecar untouched
    m = pkg.manifest()
    assert m["dj_audio"]["set_intros"] == {"1": "dj-audio/set1-intro.mp3",
                                           "2": "dj-audio/set2-intro.mp3"}


def test_process_package_expands_segue_symbol_before_synthesis(tmp_path):
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    speech = FakeSpeechProvider()
    notes = make_notes(set_intros={"1": "We go Help on the Way > Slipknot now."})

    _process(config, pkg, speech, notes)

    spoken = " ".join(speech.calls)
    assert ">" not in spoken
    assert "Help on the Way into Slipknot" in spoken


def test_process_package_applies_baked_in_pronunciation_lexicon(tmp_path):
    # process_package always loads the baked-in seed lexicon
    # (emcee.data/pronunciations.csv, Sugaree -> Shugaree) via load_lexicon;
    # unlike llama's run_package it has no lexicon= injection parameter.
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    speech = FakeSpeechProvider()
    notes = make_notes(set_intros={"1": "They opened with Sugaree."})

    _process(config, pkg, speech, notes)

    assert any("Shugaree" in c for c in speech.calls)
    assert not any("Sugaree" in c and "Shugaree" not in c for c in speech.calls)


def test_process_package_leaves_human_notes_unnormalized(tmp_path):
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    notes = make_notes(set_intros={"1": "Help on the Way > Slipknot"})

    _process(config, pkg, FakeSpeechProvider(), notes)

    # The rendered human script keeps the readable ">" form -- only audio changed.
    assert ">" in (pkg.dir / "dj-notes.md").read_text()


def test_process_package_normalization_changes_only_affected_cache_key(tmp_path):
    # A clean segment keeps its cache across runs (normalize is identity on it).
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    notes = make_notes(set_intros={"1": "A perfectly clean lead-in here."})
    _process(config, pkg, FakeSpeechProvider(), notes)

    second = FakeSpeechProvider()
    _process(config, pkg, second, notes)

    assert second.calls == []  # nothing re-synthesized


# --- bed tests -------------------------------------------------------------


def _bed_file(tmp_path: Path, seconds: float = 1.0) -> Path:
    p = tmp_path / "bed.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(np.full(int(seconds * 24000), 500, dtype="<i2").tobytes())
    return p


def test_process_package_bed_active_produces_valid_mp3(tmp_path):
    pkg = _pkg(tmp_path)
    bed_path = _bed_file(tmp_path)
    config = _config(tmp_path, bed=str(bed_path), bed_gain_db=-20.0)

    _process(config, pkg, FakeSpeechProvider(), make_notes())

    audio = list((pkg.dir / "dj-audio").glob("*.mp3"))
    assert audio and all(f.stat().st_size > 0 for f in audio)


def test_process_package_bed_works_with_chunk(tmp_path):
    pkg = _pkg(tmp_path)
    bed_path = _bed_file(tmp_path)
    config = _config(tmp_path, bed=str(bed_path), bed_gain_db=-20.0, chunk=True)

    _process(config, pkg, FakeSpeechProvider(), make_notes())

    assert list((pkg.dir / "dj-audio").glob("*.mp3"))


def test_process_package_bed_gain_change_resynthesizes(tmp_path):
    pkg = _pkg(tmp_path)
    bed_path = _bed_file(tmp_path)
    config = _config(tmp_path, bed=str(bed_path), bed_gain_db=-20.0)
    _process(config, pkg, FakeSpeechProvider(), make_notes())

    same_config = _config(tmp_path, bed=str(bed_path), bed_gain_db=-20.0)
    same = FakeSpeechProvider()
    _process(same_config, pkg, same, make_notes())
    assert same.calls == []  # unchanged gain -> cache hit

    changed_config = _config(tmp_path, bed=str(bed_path), bed_gain_db=-10.0)
    changed = FakeSpeechProvider()
    _process(changed_config, pkg, changed, make_notes())
    assert changed.calls  # changed gain -> re-rendered


def test_process_package_no_bed_cache_key_unchanged(tmp_path):
    # A no-bed run's segment key must be byte-identical to pre-feature
    # behavior, so a no-bed repackage still skips unchanged clips.
    pkg = _pkg(tmp_path)
    config = _config(tmp_path)
    _process(config, pkg, FakeSpeechProvider(), make_notes())

    second = FakeSpeechProvider()
    _process(config, pkg, second, make_notes())
    assert second.calls == []


def test_process_package_bad_bed_hard_fails(tmp_path):
    pkg = _pkg(tmp_path)
    bad = tmp_path / "bad.wav"
    with wave.open(str(bad), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"\x00\x00\x00\x00")
    config = _config(tmp_path, bed=str(bad), bed_gain_db=-20.0)

    with pytest.raises(SpeechError, match="24kHz mono 16-bit"):
        _process(config, pkg, FakeSpeechProvider(), make_notes())


# --- chunk flag --------------------------------------------------------


def test_chunk_flag_is_part_of_the_cache_key(tmp_path):
    pkg = _pkg(tmp_path)
    _process(_config(tmp_path, chunk=False), pkg, FakeSpeechProvider(), make_notes())

    second = FakeSpeechProvider()
    _process(_config(tmp_path, chunk=True), pkg, second, make_notes())
    # Toggling chunk changed the cache key -> re-rendered, not skipped.
    assert len(second.calls) > 0


def test_chunk_true_synthesizes_via_chunked_path(tmp_path):
    pkg = _pkg(tmp_path)
    speech = FakeSpeechProvider()
    notes = make_notes(set_intros={
        "1": "Good evening, night owls. It's June 10th, 1973 at RFK Stadium. "
             "Let's dig in!",
        "2": "b",
    })

    _process(_config(tmp_path, chunk=True), pkg, speech, notes)

    mp3_path = pkg.dir / "dj-audio" / "set1-intro.mp3"
    data = mp3_path.read_bytes()
    assert len(data) > 0
    assert data[:3] == b"ID3" or data[0] == 0xFF  # valid MP3 framing

    # The set 1 lead-in yields 2 chunks (its short trailing "Let's dig in!"
    # folds back); set 2 and outro are single-sentence (1 chunk each).
    # Chunked mode makes one fmt="wav" synthesize call per chunk, so total
    # calls (4) exceed the 3 segments actually rendered.
    assert len(speech.calls) == 4


def test_chunk_false_uses_single_call_per_segment(tmp_path):
    pkg = _pkg(tmp_path)
    speech = FakeSpeechProvider()
    notes = make_notes()

    _process(_config(tmp_path, chunk=False), pkg, speech, notes)

    # One call per segment (set1-intro, set2-intro, outro), not per sentence.
    assert speech.calls == [notes.set_intros["1"], notes.set_intros["2"], notes.outro]
