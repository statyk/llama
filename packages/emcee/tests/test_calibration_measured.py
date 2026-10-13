"""The measured constants (docs/superpowers/2026-10-12-mlx-audio-calibration.md):
the first calibrated mlx model and the verification thresholds, pinned on
the edges of the calibration data and on the bake-off's known runaways."""
import io
import math
import wave
from importlib import resources

import pytest

from emcee.tts import verify
from emcee.tts.calibration import (CALIBRATED_MODELS, QWEN3_TTS_1_7B_BASE, cap_seconds,
                                   guard_problem, max_tokens_for)
from emcee.tts.mlx_audio import PREFLIGHT_TEXT
from emcee.tts.verify import transcript_problem

CAL = CALIBRATED_MODELS[QWEN3_TTS_1_7B_BASE]

# From the calibration data file (selection rules in the plan, Task 12 Step 6).
CLEAN_EDGES: list[tuple[int, float]] = [
    # (chars, seconds), copied verbatim
    (20, 1.68),     # unit 0, phil_ex: the shortest text
    (130, 9.76),    # unit 26, phil_ex: highest seconds per character
    (142, 9.84),    # unit 30, phil_ex
    (34, 1.52),     # unit 1, monroe1: lowest seconds per character
    (126, 5.68),    # unit 25, monroe1
    (81, 3.76),     # unit 11, kurt1
    (1200, 66.88),  # unit 52, phil_ex: the longest text (an unchunked segment)
]
CLEAN_TRANSCRIPTS: list[tuple[str, str]] = [
    # (text, transcript), copied verbatim (Whisper)
    ("From there the band runs continuously through Wharfrat and Goin' Down The Road Feelin' "
     "Bad into Around and Around.",
     "From there, the band runs continuously through Warfrat and going down the road feeling "
     "bad into Around and Around."),
    ("After Drumz and the Jam, the band charged through The Other One, Jerry sang Wharf Rat for "
     "all he was worth, and Bob Weir hollered the set home with Turn On Your Lovelight.",
     "After drums and the jam, the band charged through the other one. Jerry sang Warfrat for "
     "all he was worth. And Bob Weir hollered the set home with Turn On Your Love Light."),
    ("There is Sunrise, Donna Godchaux's only song for the band, written in memory of their "
     "road manager Rex Jackson, and still unreleased at the time.",
     "There is Sunrise, Don Agacho's only song for the band, written in memory of their road "
     "manager Rex Jackson and still unreleased at the time."),
    ("Throwin' Stones and Not Fade Away brought it all home.",
     "Throw in stones and not fade away brought it all home."),
    ("Throwin' Stones and Not Fade Away brought it all home.",
     "Throw in stones and not fade away. Brought it all home."),
    ("Passenger carries music by the bass player, Phil Lesh, but his voice was ailing that "
     "year, so Bob Weir and Donna Jean Godchaux take the vocal.",
     "Passenger carries music by the bass player Phil Lesh, but his voice was ailing that "
     "year, so Bob Weir and Donna Jean Dodd show take the vocal."),
]
RUNAWAY_TRANSCRIPTS: list[tuple[str, str]] = [
    # (text, transcript), copied verbatim (Whisper, cut from the bake-off's mixes)
    ("This was the fifteenth show of the Europe seventy-two tour, and the band played it the "
     "night after their concert at the Concertgebouw in Amsterdam.",
     "This was the 15th show of the Europe, 72 Tour, and the band played it the night after "
     "their concert. However, the beds that have included the wings of, theád worshnova gal. "
     "Oh, my God. Oh, my God. Oh, my God. Oh, my God. Oh, my God. Oh, my God. Oh, my God. "
     "Oh, my God. Oh, my God."),
    ("Here is Morning Dew.",
     "This morning due. Tourists are full of body press with Siri a full away depressus."),
]
# The bake-off's known runaways (~/tts-bakeoff/out/*.metrics.json):
CHATTERBOX_MORNING_DEW = ("Here is Morning Dew.", 10.1)
QWEN_06B_RUNAWAY_TEXT = ("This was the fifteenth show of the Europe seventy-two tour, and the "
                         "band played it the night after their concert at the Concertgebouw "
                         "in Amsterdam.")
QWEN_06B_RUNAWAY_SECONDS = 320.0  # per_call[5][1] of qwen3tts-0.6b-bf16-set1-intro.metrics.json


def text_of(chars: int) -> str:
    return "x" * chars  # the guard measures only whitespace-collapsed length


def visible(rows: list[tuple[str, str]], what: str) -> list:
    """Parametrize rows, or one visibly skipped case: never zero collected."""
    return rows or [pytest.param("", "", marks=pytest.mark.skip(reason=f"no {what} recorded"))]


def test_qwen_1_7b_is_the_calibrated_model():
    assert QWEN3_TTS_1_7B_BASE == "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
    assert CAL.frame_rate_hz == 12.5  # qwen3_tts/config.py


def test_the_edges_of_the_clean_data_pass_the_guard():
    assert CLEAN_EDGES
    for chars, seconds in CLEAN_EDGES:
        text = text_of(chars)
        assert guard_problem(CAL, text, seconds, max_tokens_for(CAL, text)) is None, (chars, seconds)


def test_chatterbox_morning_dew_babble_fails_the_guard():
    text, seconds = CHATTERBOX_MORNING_DEW
    assert guard_problem(CAL, text, float(seconds), max_tokens_for(CAL, text)) is not None


def test_a_capped_runaway_fails_the_guard():
    # The cap-margin check: satisfied by construction (the clip is placed AT the cap).
    mt = max_tokens_for(CAL, QWEN_06B_RUNAWAY_TEXT)
    assert "token cap" in guard_problem(CAL, QWEN_06B_RUNAWAY_TEXT, cap_seconds(CAL, mt), mt)


def test_the_measured_qwen_0_6b_runaway_exceeds_the_long_limit():
    # The runaway's measured duration against the non-cap limit: give it a
    # cap above the clip, so only the "implausibly long" check can catch it.
    mt = math.ceil((QWEN_06B_RUNAWAY_SECONDS + CAL.cap_margin_s + 1.0) * CAL.frame_rate_hz)
    assert "implausibly long" in guard_problem(CAL, QWEN_06B_RUNAWAY_TEXT,
                                               QWEN_06B_RUNAWAY_SECONDS, mt)


def test_a_synthetic_cap_length_clip_fails_for_every_length():
    for chars in (5, 20, 60, 150, 400, 1200):
        text = text_of(chars)
        mt = max_tokens_for(CAL, text)
        assert "token cap" in guard_problem(CAL, text, cap_seconds(CAL, mt), mt)
        assert "token cap" in guard_problem(CAL, text, cap_seconds(CAL, mt) - CAL.cap_margin_s, mt)


def test_measured_thresholds_tolerate_a_wrong_word_or_two():
    assert 2 <= verify.MISS_FLOOR <= 3
    assert verify.EXTRA_FLOOR <= 6
    # ... and still detect gross mismatch (Step 3's STOP ceilings).
    assert verify.MISS_FRACTION <= 0.4 and verify.EXTRA_FRACTION <= 1.0


@pytest.mark.parametrize("text, transcript", visible(CLEAN_TRANSCRIPTS, "clean transcripts"))
def test_the_worst_clean_transcripts_pass(text, transcript):
    assert transcript_problem(text, transcript) is None


@pytest.mark.parametrize("text, transcript", visible(RUNAWAY_TRANSCRIPTS, "runaway transcripts"))
def test_the_known_runaway_transcripts_fail(text, transcript):
    assert transcript_problem(text, transcript) is not None


def test_the_bundled_preflight_clip():
    data = resources.files("emcee.data").joinpath(verify.PREFLIGHT_CLIP).read_bytes()
    with wave.open(io.BytesIO(data), "rb") as w:
        assert (w.getsampwidth(), w.getnchannels(), w.getframerate()) == (2, 1, 24000)
        assert 1.0 <= w.getnframes() / w.getframerate() <= 4.0
    assert PREFLIGHT_TEXT == "Good evening, and welcome to the show."
