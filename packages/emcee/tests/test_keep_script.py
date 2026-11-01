"""`emcee voice --keep-script`: re-voice a package from its existing script.

The failure path is a strict surface: nothing here may ever lose a script.
"""

import json
from pathlib import Path

from emcee.audio import _synthesize_dj_audio, adopt_clips
from emcee.models import ScriptNotes
from emcee.tts.fake import FakeSpeechProvider


def _notes(**overrides) -> ScriptNotes:
    fields = {"context": "Spring '73 tour",
              "set_intros": {"1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
                             "2": "China Cat Sunflower leads set two."},
              "outro": "I Know You Rider sends us off. Thanks for listening.",
              "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"]}
    return ScriptNotes(**{**fields, **overrides})


def _clips(pkg: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in (pkg / "dj-audio").glob("*.mp3")}


# --- adopt_clips -----------------------------------------------------------


def _stale_clips(pkg: Path) -> None:
    audio = pkg / "dj-audio"
    audio.mkdir()
    for name in ("set1-intro.mp3", "set2-intro.mp3", "99-outro.mp3"):
        (audio / name).write_bytes(f"take of {name}".encode())
    (audio / "segments.json").write_text(json.dumps({
        "set1-intro.mp3": "old", "set2-intro.mp3": "old", "99-outro.mp3": "old"}))


def test_adopted_clips_render_nothing_and_stay_out_of_rendered(tmp_path):
    _stale_clips(tmp_path)
    before = _clips(tmp_path)

    adopt_clips(tmp_path, _notes(), FakeSpeechProvider(), chunking=None)

    assert _clips(tmp_path) == before
    speech = FakeSpeechProvider()
    rendered: set[str] = set()
    _synthesize_dj_audio(tmp_path, _notes(), speech, False, chunking=None, rendered=rendered)
    assert speech.calls == []
    assert rendered == set()      # an adopted clip is not a real render
    assert _clips(tmp_path) == before


def test_a_skipped_stem_keeps_its_old_key(tmp_path):
    _stale_clips(tmp_path)

    adopt_clips(tmp_path, _notes(), FakeSpeechProvider(), chunking=None, skip={"set1-intro"})

    keys = json.loads((tmp_path / "dj-audio" / "segments.json").read_text())
    assert keys["set1-intro.mp3"] == "old"
    assert keys["set2-intro.mp3"] != "old" and keys["99-outro.mp3"] != "old"


def test_a_missing_clip_is_not_adopted(tmp_path):
    _stale_clips(tmp_path)
    (tmp_path / "dj-audio" / "99-outro.mp3").unlink()

    adopt_clips(tmp_path, _notes(), FakeSpeechProvider(), chunking=None)

    speech = FakeSpeechProvider()
    _synthesize_dj_audio(tmp_path, _notes(), speech, False, chunking=None)
    assert speech.calls == [_notes().outro]
