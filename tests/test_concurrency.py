import multiprocessing as mp
from pathlib import Path

from llama.locks import file_lock
from llama.workspace import RunWorkspace

CTX = mp.get_context("fork")


def _build_once_marker(show_ws):
    """Simulate a show build guarded by the per-show lock: append to a shared
    counter file only if the 'show' isn't already built."""
    with file_lock(show_ws.lock):
        if not show_ws.show.exists():
            with (show_ws.dir.parent / "build_count.txt").open("a") as f:
                f.write("x")
            show_ws.show.write_text("{}")  # mark built


def _run(root, start):
    start.wait(5)
    ws = RunWorkspace(Path(root), "r")
    _build_once_marker(ws.show_ws("gd1973-06-10"))


def test_same_show_built_once_across_processes(tmp_path: Path):
    (tmp_path / "shows").mkdir(parents=True)
    start = CTX.Event()
    procs = [CTX.Process(target=_run, args=(str(tmp_path), start)) for _ in range(4)]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(5)
    # The expensive build ran exactly once despite 4 concurrent runners.
    assert (tmp_path / "shows" / "build_count.txt").read_text() == "x"
