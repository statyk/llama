from helpers import build_ready   # lifted from test_broadcast_ready.py: `tests` has no
                                  # __init__.py, so `from tests.test_broadcast_ready import
                                  # ...` fails to collect under this suite's pytest
                                  # rootdir-insertion mode (confirmed RED as ImportError)
from llama.catalog import VOICE_BUNDLE_REASONS, deliver_refusals


def test_ready_show_has_no_refusals(tmp_path):
    assert deliver_refusals(build_ready(tmp_path)) == []


def test_unvoiced_show_blocked_then_allowed(tmp_path):
    ws = build_ready(tmp_path, voiced=False, broadcast_m3u=False, script=False)
    assert set(deliver_refusals(ws)) == set(VOICE_BUNDLE_REASONS)
    assert deliver_refusals(ws, allow_unvoiced=True) == []


def test_held_and_missing_audio_never_overridable(tmp_path):
    held = build_ready(tmp_path / "h", needs_review=True)
    assert deliver_refusals(held, allow_unvoiced=True) == ["held for review"]
    broken = build_ready(tmp_path / "b", drop_audio=True)
    assert deliver_refusals(broken, allow_unvoiced=True) == ["1 of 1 audio files missing"]


def test_unpackaged_never_overridable(tmp_path):
    ws = build_ready(tmp_path)
    (ws.package_dir / "manifest.json").unlink()
    assert deliver_refusals(ws, allow_unvoiced=True) == ["not packaged"]
