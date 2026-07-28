from pathlib import Path

from llama.workspace import ShowWorkspace, RunWorkspace


def test_show_workspace_exposes_lock_path(tmp_path: Path):
    ws = RunWorkspace(tmp_path, "run-1")
    show = ws.show_ws("gd1973-06-10")
    assert show.lock == show.dir / ".lock"
