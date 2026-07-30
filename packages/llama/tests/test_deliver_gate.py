"""`catalog.deliver_refusals` — llama's entire deliver gate post-cut: packaged +
not held + every manifest track's audio verified on disk. Voice readiness
(DJ script/audio/broadcast.m3u) moved to emcee; there is no override flag.

Absorbs the still-relevant cases from the deleted test_broadcast_ready.py
(the voice-bundle-only cases there have no post-cut equivalent).
"""
from helpers import build_ready   # lifted from the old test_broadcast_ready.py: `tests`
                                  # has no __init__.py, so `from tests.helpers import ...`
                                  # fails to collect under this suite's pytest
                                  # rootdir-insertion mode (confirmed RED as ImportError)
from llama.catalog import deliver_refusals


def test_ready_show_has_no_refusals(tmp_path):
    assert deliver_refusals(build_ready(tmp_path)) == []


def test_not_packaged_refuses(tmp_path):
    ws = build_ready(tmp_path)
    (ws.package_dir / "manifest.json").unlink()
    assert deliver_refusals(ws) == ["not packaged"]


def test_held_for_review_refuses(tmp_path):
    ws = build_ready(tmp_path, needs_review=True)
    assert deliver_refusals(ws) == ["held for review"]


def test_missing_audio_refuses_with_n_of_m_shape(tmp_path):
    ws = build_ready(tmp_path, drop_audio=True)
    assert deliver_refusals(ws) == ["1 of 1 audio files missing"]
