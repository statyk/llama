from transmitter.state import (PublishState, load_fallback_version, load_publish_state,
                               save_fallback_version, save_publish_state)
from transmitter.workspace import Workspace


def test_publish_state_round_trip(tmp_path):
    ws = Workspace(tmp_path)
    assert load_publish_state(ws) == PublishState()
    state = PublishState(epoch_id="e1", first=10, last=20, runs=[[10, 20]], notes={"s": "abc"})
    save_publish_state(ws, state)
    assert load_publish_state(ws) == state


def test_fallback_version_round_trip(tmp_path):
    ws = Workspace(tmp_path)
    assert load_fallback_version(ws) is None
    save_fallback_version(ws, "3fa9c1d2e0b1")
    assert load_fallback_version(ws) == "3fa9c1d2e0b1"
