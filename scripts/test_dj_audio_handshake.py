"""emcee's `DJAudioBlock` and llama's hand-kept `DJAudio` copy must stay
shape-compatible. The two packages never import each other, so the check
lives here, the one place that may import both."""
import pytest

from emcee.models import DJAudioBlock
from emcee.models import TTSRecord
from llama.models import DJAudio


@pytest.mark.parametrize("title", ["Gravel & Steel", None])
def test_emcee_dj_audio_block_parses_as_llama_dj_audio(title):
    block = DJAudioBlock(
        set_intros={"1": "dj-audio/set1-intro.mp3"}, outro="dj-audio/99-outro.mp3",
        presenter="casey", profile="bluegrass", profile_source="artist",
        tts=TTSRecord(backend="voxtral", model="m", voice="v"),
        voiced_on="2026-11-04", title=title).model_dump()
    parsed = DJAudio.model_validate(block)
    assert parsed.title == title
    assert parsed.model_dump() == block
