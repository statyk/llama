"""Transcript verification (spec section 3).

Transcribes synthesized audio on the mlx-audio server and fails only on a
GROSS mismatch with the text sent: too few of the script's words heard, or a
transcript far longer than the script (babble, a repetition loop). It
tolerates a wrong word or two per sentence -- ASR misrenders proper nouns
("De Doelen" fails on Voxtral too) and the lexicon's respellings
("Shugaree") are sent as spelled -- and ignores number-bearing tokens on both
sides, since number formatting is open-ended.

A failed transcription request is a SpeechError, never a pass.
"""
import re
from collections import Counter
from importlib import resources

import httpx

from emcee.tts.provider import SpeechDefect, SpeechError

TRANSCRIBE_PATH = "/v1/audio/transcriptions"
MODELS_PATH = "/v1/models"
# A ~2 s clip of mlx_audio.PREFLIGHT_TEXT, rendered with an Apache-2.0
# preset-voice model (provenance: docs/superpowers/2026-10-12-mlx-audio-calibration.md).
PREFLIGHT_CLIP = "preflight_en.wav"

# Gross-mismatch thresholds. INTERIM values, replaced by the measured ones
# from the calibration run (implementation plan Task 12). A script of n
# comparable words may lose up to max(MISS_FLOOR, int(MISS_FRACTION * n))
# of them, and the transcript may run up to max(EXTRA_FLOOR,
# int(EXTRA_FRACTION * n)) words longer.
MISS_FLOOR = 2
MISS_FRACTION = 0.25
EXTRA_FLOOR = 4
EXTRA_FRACTION = 0.5

NUMBER_WORDS = frozenset("""
    zero one two three four five six seven eight nine ten eleven twelve thirteen
    fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty
    sixty seventy eighty ninety hundred thousand million billion first second third
    fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth
    fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth
    thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth hundredth
    thousandth millionth
""".split())
_APOSTROPHES = str.maketrans("", "", "'’‘`")
_WORD = re.compile(r"[^\W_]+")


def comparable_words(text: str) -> list[str]:
    """Lower-cased words with apostrophes and punctuation removed, minus every
    number-bearing token (digits or a spelled-out number word)."""
    words = _WORD.findall(text.lower().translate(_APOSTROPHES))
    return [w for w in words if w not in NUMBER_WORDS and not any(c.isdigit() for c in w)]


def transcript_problem(script: str, transcript: str) -> str | None:
    """Why `transcript` grossly mismatches `script`, or None."""
    want, heard = comparable_words(script), comparable_words(transcript)
    n = len(want)
    found = sum((Counter(want) & Counter(heard)).values())
    if n - found > max(MISS_FLOOR, int(MISS_FRACTION * n)):
        return f"only {found} of the script's {n} words were heard"
    if len(heard) - n > max(EXTRA_FLOOR, int(EXTRA_FRACTION * n)):
        return f"heard {len(heard)} words for a {n}-word script"
    return None


class SttClient:
    """The mlx-audio server's transcription endpoint. Used by verification
    and by `emcee presenter add/edit --transcribe`."""

    def __init__(self, *, url: str, model: str, timeout_s: float = 600.0,
                 transport: httpx.BaseTransport | None = None):
        self.url = url.rstrip("/")
        self.model = model
        self._client = httpx.Client(timeout=timeout_s, transport=transport)

    def transcribe(self, wav: bytes) -> str:
        # The server picks its temp-file format from the upload's suffix;
        # httpx's default file name maps to .mp3, which needs ffmpeg.
        files = {"file": ("clip.wav", wav, "audio/wav")}
        data = {"model": self.model, "language": "en", "response_format": "json"}
        try:
            resp = self._client.post(self.url + TRANSCRIBE_PATH, files=files, data=data)
        except httpx.ConnectError as e:
            raise SpeechError(f"mlx-audio server not reachable at {self.url} for transcription "
                              "(is the launchd service running?)") from e
        except httpx.HTTPError as e:
            raise SpeechError(f"transcription request failed: {e}") from e
        if resp.status_code != 200:
            raise SpeechError(f"mlx-audio transcription returned {resp.status_code}: "
                              f"{resp.text[:500]}")
        try:
            text = resp.json().get("text")
        except (ValueError, AttributeError) as e:
            raise SpeechError(f"mlx-audio transcription returned non-JSON: {resp.text[:200]}") from e
        if not isinstance(text, str):
            raise SpeechError("mlx-audio transcription returned no text")
        return text.strip()

    def unload(self) -> None:
        """Free the STT model on the server (it keeps every model it has
        served resident until restart)."""
        try:
            resp = self._client.delete(self.url + MODELS_PATH, params={"model_name": self.model})
        except httpx.HTTPError as e:
            raise SpeechError(f"could not unload {self.model!r} from mlx-audio: {e}") from e
        if resp.status_code not in (200, 204, 404):
            raise SpeechError(f"could not unload {self.model!r}: mlx-audio returned "
                              f"{resp.status_code}")

    def close(self) -> None:
        self._client.close()


class Verifier:
    def __init__(self, stt: SttClient):
        self.stt = stt

    def check(self, wav: bytes, text: str, *, backend: str) -> None:
        transcript = self.stt.transcribe(wav)
        problem = transcript_problem(text, transcript)
        if problem:
            raise SpeechDefect(backend, text=text, reason=f"transcript mismatch: {problem}",
                               transcript=transcript)

    def close(self) -> None:
        self.stt.close()


def preflight_clip_wav() -> bytes:
    """The bundled check clip a hosted backend's preflight transcribes. Fails
    closed: a build without it cannot verify, so it cannot voice."""
    try:
        return resources.files("emcee.data").joinpath(PREFLIGHT_CLIP).read_bytes()
    except OSError as e:
        raise SpeechError(f"verification preflight clip missing from this build "
                          f"(emcee/data/{PREFLIGHT_CLIP}); verification cannot be checked") from e
