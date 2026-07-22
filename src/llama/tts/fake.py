from llama.tts.provider import SpeechError

# One silent 417-byte MPEG-1 Layer III frame (128 kbps, 44.1 kHz): a small but
# structurally valid MP3, so packaged dj-audio files are real audio in tests.
SILENT_MP3 = b"\xff\xfb\x90\x00" + bytes(413)


class FakeSpeechProvider:
    """Test backend: returns SILENT_MP3, records synthesized texts.

    voice/model are fixed placeholders (the factory ignores the resolved voice
    for the fake) so package-stage cache keys are deterministic in tests.
    Arm with fail=True for the hard-fail tests.
    """

    def __init__(self, fail: bool = False):
        self.voice = "fake-voice"
        self.model = "fake-model"
        self.fail = fail
        self.calls: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.calls.append(text)
        if self.fail:
            raise SpeechError("FakeSpeechProvider armed to fail")
        return SILENT_MP3
