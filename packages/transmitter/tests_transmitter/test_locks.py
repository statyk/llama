import pytest

from transmitter.errors import PlanLocked
from transmitter.locks import plan_lock
from transmitter.workspace import Workspace


def test_plan_lock_refuses_a_second_holder(tmp_path):
    ws = Workspace(tmp_path)
    with plan_lock(ws):
        with pytest.raises(PlanLocked):
            with plan_lock(ws):
                pass
    with plan_lock(ws):      # released
        pass


def test_plan_lock_creates_the_root_and_uses_plan_lock_file(tmp_path):
    ws = Workspace(tmp_path / "new" / "root")
    with plan_lock(ws):
        assert ws.plan_lock_path == ws.root / "plan.lock"
        assert ws.plan_lock_path.exists()
