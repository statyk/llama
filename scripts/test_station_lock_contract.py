"""The station lock is an on-disk contract between emcee and llama, which never
import each other: each keeps its own copy of the file name, the format and the
token-checked release. This checks the two copies against each other, from the
one place that may import both. Everything runs in tmp_path."""
import pytest
from typer.testing import CliRunner

import emcee.station_lock as esl
import llama.station_lock as lsl
from emcee.cli import app as emcee_app


@pytest.fixture(autouse=True)
def _no_held():
    esl._held = lsl._held = None
    yield
    esl._held = lsl._held = None


def _station(tmp_path):
    station = tmp_path / "station"
    station.mkdir()
    return station


def test_lock_constants_agree():
    assert esl.LOCK_NAME == lsl.LOCK_NAME == ".lma-station.lock"
    assert esl.MAGIC == lsl.MAGIC == "lma-station-lock 1"


def test_emcee_lock_refuses_llama_naming_emcee_holder(tmp_path):
    station = _station(tmp_path)
    with esl.station_lock(station, command="emcee run"):
        with pytest.raises(lsl.StationLocked) as exc:
            with lsl.for_package(station / "gd73", command="deliver gd73"):
                pytest.fail("llama acquired a lock emcee holds")
    assert "tool: emcee" in exc.value.holder
    assert "command: emcee run" in exc.value.holder
    assert "emcee lock show" in str(exc.value) and "emcee lock clear" in str(exc.value)
    assert not (station / lsl.LOCK_NAME).exists()      # emcee released its own


def test_llama_lock_refuses_emcee_naming_llama_holder(tmp_path):
    station = _station(tmp_path)
    with lsl.for_package(station / "gd73", command="bulk_apply mark"):
        with pytest.raises(esl.StationLocked) as exc:
            with esl.station_lock(station, command="emcee voice"):
                pytest.fail("emcee acquired a lock llama holds")
    assert "tool: llama" in exc.value.holder
    assert "command: bulk_apply mark" in exc.value.holder
    assert not (station / lsl.LOCK_NAME).exists()


def test_emcee_lock_show_and_clear_handle_a_llama_lock(tmp_path, monkeypatch):
    station = _station(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("EMCEE_ROOT", str(home))
    (home / "config.toml").write_text(f'[station]\nroot = "{station}"\n')
    lock = station / lsl.LOCK_NAME
    held = lsl.acquire(lock, command="deliver gd73")      # a llama writer that died holding it
    lsl._held = None
    raw = lock.read_bytes()
    assert lsl.token_of(raw) == held.token == esl.token_of(raw)
    runner = CliRunner()

    shown = runner.invoke(emcee_app, ["lock", "show"])
    assert shown.exit_code == 0, shown.output
    assert "tool: llama" in shown.stdout and "command: deliver gd73" in shown.stdout
    assert lock.read_bytes() == raw

    cleared = runner.invoke(emcee_app, ["lock", "clear", "--yes"])
    assert cleared.exit_code == 0, cleared.output
    assert "tool: llama" in cleared.stdout
    assert not lock.exists()


def test_release_of_one_tool_never_unlinks_the_others_lock(tmp_path, capsys):
    station = _station(tmp_path)
    lock = station / lsl.LOCK_NAME
    mine = lsl.acquire(lock, command="deliver gd73")
    lock.unlink()                                  # cleared by hand, then emcee took it
    lsl._held = None
    theirs = esl.acquire(lock, command="emcee run")
    esl._held = None
    emcee_bytes = lock.read_bytes()
    lsl.release(mine)
    assert lock.read_bytes() == emcee_bytes
    assert "was not ours" in capsys.readouterr().err

    lock.unlink()                                  # and the other way round
    llama_held = lsl.acquire(lock, command="deliver gd73")
    lsl._held = None
    llama_bytes = lock.read_bytes()
    esl.release(theirs)
    assert lock.read_bytes() == llama_bytes
    err = capsys.readouterr().err
    assert "was not ours" in err and "tool: llama" in err
    lsl.release(llama_held)
    assert not lock.exists()


def test_both_tools_write_the_same_body_lines_in_the_same_order(tmp_path):
    keys = []
    for tool, take in (("llama", lsl.acquire), ("emcee", esl.acquire)):
        lock = tmp_path / tool / lsl.LOCK_NAME
        lock.parent.mkdir()
        take(lock, command=f"{tool} test")
        raw = lock.read_bytes()
        assert raw.endswith(b"\n") and raw.count(b"\n") == 6
        first, *body = raw.decode("utf-8").splitlines()
        assert lsl.token_of(raw) is not None and esl.token_of(raw) is not None
        assert first.startswith(lsl.MAGIC + " ")
        keys.append([line.split(": ", 1)[0] for line in body])
        assert body[0] == f"tool: {tool}" and body[1] == f"command: {tool} test"
    esl._held = lsl._held = None
    assert keys[0] == keys[1] == ["tool", "command", "host", "pid", "started"]
