import multiprocessing as mp
from pathlib import Path

from llama.workspace import atomic_write_text

CTX = mp.get_context("fork")


def _writer(path, text, start):
    start.wait(5)
    atomic_write_text(Path(path), text)


def test_concurrent_writes_never_interleave(tmp_path: Path):
    target = tmp_path / "out.json"
    a, b = "A" * 20000, "B" * 20000
    start = CTX.Event()
    procs = [CTX.Process(target=_writer, args=(str(target), t, start)) for t in (a, b)]
    for p in procs:
        p.start()
    start.set()
    for p in procs:
        p.join(5)
    # File equals exactly one writer's content — never a byte-mix.
    assert target.read_text() in (a, b)
    # No temp files left behind.
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_text_roundtrip(tmp_path: Path):
    target = tmp_path / "sub" / "x.txt"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"
