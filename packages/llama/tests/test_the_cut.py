"""Durable guard: asserts the emcee cut stays cut.

Task 4 (this task) deletes llama's synthesize stage; Task 5 deletes the
remaining moved-to-emcee modules (llama.tts, llama.speech_text,
llama.presenters) and the TTS/presenter config & model fields. Extend this
file in Task 5 rather than relaxing anything already asserted here.
"""
import importlib.util


def test_synthesize_stage_module_is_gone():
    assert importlib.util.find_spec("llama.stages.synthesize") is None


# TASK 5 TODO: once llama/tts/, speech_text.py, and presenters.py are
# deleted, add:
#   assert importlib.util.find_spec("llama.tts") is None
#   assert importlib.util.find_spec("llama.speech_text") is None
#   assert importlib.util.find_spec("llama.presenters") is None
# They are NOT asserted here because those three modules still exist at the
# end of Task 4 (Task 5's job to delete them).


def test_show_stage_order_has_no_synthesize():
    from llama.workspace import SHOW_STAGE_ORDER

    assert "synthesize" not in SHOW_STAGE_ORDER
    assert SHOW_STAGE_ORDER == ["select", "gather", "research", "vet", "brief", "package"]


def test_synthesize_is_not_a_default_tiers_task():
    from llama.config import DEFAULT_TIERS

    assert "synthesize" not in DEFAULT_TIERS


def test_manifest_still_accepts_dj_notes_and_dj_audio_passthrough():
    # llama never writes these anymore, but the schema must still ACCEPT them
    # -- emcee writes dj_notes/dj_audio into the same manifest.json post-cut.
    from llama.models import DJAudio, DJNotes, Manifest, ManifestBriefing

    m = Manifest(
        show={}, source={}, tracks=[], set_breaks=[],
        briefing=ManifestBriefing(),
        dj_notes=DJNotes(set_intros={"1": "hi"}, outro="bye"),
        dj_audio=DJAudio(set_intros={"1": "dj-audio/set1-intro.mp3"},
                         outro="dj-audio/99-outro.mp3"),
        total_duration_sec=0.0, set_durations_sec={},
    )
    assert m.dj_notes is not None and m.dj_audio is not None
