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

# Gross-mismatch thresholds. Measured: docs/superpowers/2026-10-12-mlx-audio-calibration.md.
# A script of n comparable words may lose up to max(MISS_FLOOR,
# int(MISS_FRACTION * n)) of them, and the transcript may run up to
# max(EXTRA_FLOOR, int(EXTRA_FRACTION * n)) words longer.
MISS_FLOOR = 2
MISS_FRACTION = 0.15
EXTRA_FLOOR = 4
EXTRA_FRACTION = 0.25

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
# A dropped g spelled with an apostrophe ("goin'", "feelin'"), read as its
# "-ing" form. The apostrophe must close a word of at least one letter
# before "in", so "in'" stays as it is; a word merely ending in "in"
# ("begin") has no apostrophe and is never touched. The same mark can
# instead close a single-quoted title ending in "in" ('Fire on the
# Mountain'): see _fold_dropped_g.
_DROPPED_G = re.compile(r"([^\W\d_]+in)['’](?!\w)")
# An opening quote, but not a leading elision ('cause, 'em, 'til, ...).
_OPEN_QUOTE = re.compile(r"(?:^|(?<=[\s(\[{\"“]))['‘]"
                         r"(?!(?:cause|cuz|cos|em|til|round|bout|nuff|fore|cept|neath"
                         r"|ol|n|tis|twas)\b)(?=[^\W\d_])")
# An unambiguous closing quote: after a letter that does not end "in" (a
# mark after "in" may be a dropped g instead), or after punctuation
# ('Scarlet Begonias,').
_CLOSE_QUOTE = re.compile(r"(?:(?<=[^\W\d_])(?<!in)|(?<=[.,!?;:]))['’](?!\w)")


def _fold_dropped_g(text: str) -> str:
    """`text` with each dropped g folded to "-ing", except a mark that
    closes a single quote:
    - a word directly after any quote mark ('Win', 'Goin' ..., `Win') is
      read as a one-word quoted title and never folded -- folding could
      only give false credit (win/wing);
    - otherwise the mark closes the quote when one opened before it is
      still open and no unambiguous close follows before the next opening
      quote ('Fire on the Mountain').
    A mark read as a close closes the quote for the marks after it, so
    "'Fire on the Mountain' > Goin' Down The Road Feelin' Bad" folds both."""
    opens = [m.start() for m in _OPEN_QUOTE.finditer(text)]
    closes = [m.start() for m in _CLOSE_QUOTE.finditer(text)]

    def fold(m: re.Match) -> str:
        mark = m.end() - 1
        if m.start() and text[m.start() - 1] in "'‘’`":
            closes.append(mark)
            return m.group(0)
        opened = max((o for o in opens if o < m.start()), default=None)
        if opened is not None and not any(opened < c < mark for c in closes):
            next_open = min((o for o in opens if o > mark), default=len(text))
            if not any(mark < c < next_open for c in closes):
                closes.append(mark)
                return m.group(0)
        return m.group(1) + "g"

    return _DROPPED_G.sub(fold, text)


def comparable_words(text: str) -> list[str]:
    """Lower-cased words with apostrophes and punctuation removed, minus every
    number-bearing token (digits or a spelled-out number word). A dropped g
    ("goin'") reads as "going"."""
    words = _WORD.findall(_fold_dropped_g(text.lower()).translate(_APOSTROPHES))
    return [w for w in words if w not in NUMBER_WORDS and not any(c.isdigit() for c in w)]


def match_words(want: list[str], heard: list[str]) -> tuple[int, Counter, Counter]:
    """How many script words (`want`) were heard, and the words left
    unmatched on each side. Words match as a bag, and a word joined or split
    by the transcriber still counts: a script bigram whose concatenation --
    or contraction, see `_joined` -- is one heard word ("l a" / "la",
    "here is" / "heres") counts both script words as found, and a heard
    bigram whose concatenation is one script word ("throw in" / "throwin")
    counts that script word. Every heard word is used at most once."""
    w, h = Counter(want), Counter(heard)
    exact = w & h
    found = sum(exact.values())
    w, h = w - exact, h - exact
    for a, b in zip(want, want[1:]):
        if w[a] and w[b] and (a != b or w[a] >= 2):
            joined = next((j for j in _joined(a, b) if h[j]), None)
            if joined:
                w[a] -= 1
                w[b] -= 1
                h[joined] -= 1
                found += 2
    for a, b in zip(heard, heard[1:]):
        if h[a] and h[b] and (a != b or h[a] >= 2):
            joined = next((j for j in _joined(a, b) if w[j]), None)
            if joined:
                h[a] -= 1
                h[b] -= 1
                w[joined] -= 1
                found += 1
    return found, +w, +h


# A contraction is a join too, once comparable_words has dropped the
# apostrophe: "here is" / "heres", "you are" / "youre", "do not" / "dont".
_CONTRACTED = {"is": "s", "has": "s", "us": "s", "are": "re", "am": "m", "have": "ve",
               "will": "ll", "would": "d", "had": "d", "not": "nt"}


def _joined(a: str, b: str) -> tuple[str, ...]:
    """The single words a bigram may be heard (or written) as; "throw in"
    is also "throwing", the dropped-g form comparable_words normalizes."""
    forms = (a + b, a + _CONTRACTED.get(b, b)) + ((a + "ing",) if b == "in" else ())
    return tuple(dict.fromkeys(forms))


def transcript_problem(script: str, transcript: str) -> str | None:
    """Why `transcript` grossly mismatches `script`, or None. Besides the
    thresholds, a script with any comparable word fails when none of them
    was heard: below MISS_FLOOR a total mishearing would otherwise pass."""
    want, heard = comparable_words(script), comparable_words(transcript)
    n = len(want)
    found = match_words(want, heard)[0]
    if n and not found:
        return f"none of the script's {n} words were heard"
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
