import io
import wave

from llama.tts.provider import SpeechError

# One silent 417-byte MPEG-1 Layer III frame (128 kbps, 44.1 kHz): a small but
# structurally valid MP3, so packaged dj-audio files are real audio in tests.
SILENT_MP3 = b"\xff\xfb\x90\x00" + bytes(413)


def _silent_wav(seconds: float = 0.3, rate: int = 24000) -> bytes:
    """A short, structurally valid silent WAV for the fmt="wav" path (16-bit
    mono PCM at 24kHz, matching Voxtral's real output rate).
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(int(seconds * rate) * 2))
    return buf.getvalue()


SILENT_WAV = _silent_wav()


class FakeSpeechProvider:
    """Test backend: returns SILENT_MP3 (or SILENT_WAV for fmt="wav"),
    records synthesized texts.

    voice/model are fixed placeholders (the factory ignores the resolved voice
    for the fake) so package-stage cache keys are deterministic in tests.
    Arm with fail=True for the hard-fail tests.
    """

    def __init__(self, fail: bool = False):
        self.voice = "fake-voice"
        self.model = "fake-model"
        self.fail = fail
        self.calls: list[str] = []

    def synthesize(self, text: str, fmt: str = "mp3") -> bytes:
        self.calls.append(text)
        if self.fail:
            raise SpeechError("FakeSpeechProvider armed to fail")
        return SILENT_WAV if fmt == "wav" else SILENT_MP3

    def close(self) -> None:
        """No-op: lets callers close ANY speech provider uniformly."""
