"""Tests for station_probe.py (stdlib and pytest only: also run under Python 3.11)."""
import ast
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("station_probe.py")


def run(*args, env_extra=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True,
                          text=True, env=env, timeout=120)


def test_race_on_local_disk_reports_no_double_acquisition(tmp_path):
    r = run("race", "--dir", str(tmp_path), "--n", "50")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "double 0" in r.stdout
    assert list(tmp_path.iterdir()) == []


def test_race_detects_a_broken_exclusive_create(tmp_path):
    r = run("race", "--dir", str(tmp_path), "--n", "50",
            env_extra={"STATION_PROBE_TEST_DROP_EXCL": "1"})
    assert r.returncode == 1, r.stdout + r.stderr
    double = int(r.stdout.split("double ")[1].split()[0])
    assert double > 0
    assert list(tmp_path.iterdir()) == []


def _load():
    import importlib.util
    spec = importlib.util.spec_from_file_location("station_probe_inproc", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_mtime_replace_sets_mtime_before_rename(tmp_path, monkeypatch, capsys):
    sp = _load()
    sp.main(["mtime", "--dir", str(tmp_path), "--create"])
    name = capsys.readouterr().out.strip()
    assert name.startswith(".mtime-probe-")
    assert (tmp_path / name).stat().st_mtime != 1767225600
    seen = []
    real = os.rename

    def spy(src, dst):
        seen.append(os.stat(src).st_mtime)
        return real(src, dst)

    monkeypatch.setattr(sp.os, "rename", spy)
    assert sp.main(["mtime", "--dir", str(tmp_path), "--replace", name]) == 0
    assert int(capsys.readouterr().out.strip()) == 1767225600
    assert seen == [1767225600]
    assert int((tmp_path / name).stat().st_mtime) == 1767225600
    assert [p.name for p in tmp_path.iterdir()] == [name]


def test_mtime_replace_reapplies_when_rename_bumps_mtime(tmp_path, monkeypatch, capsys):
    sp = _load()
    sp.main(["mtime", "--dir", str(tmp_path), "--create"])
    name = capsys.readouterr().out.strip()
    real = os.rename

    def bumping(src, dst):
        real(src, dst)
        os.utime(dst, (1800000000, 1800000000))

    monkeypatch.setattr(sp.os, "rename", bumping)
    assert sp.main(["mtime", "--dir", str(tmp_path), "--replace", name]) == 0
    assert int((tmp_path / name).stat().st_mtime) == 1767225600


def test_mtime_remove_deletes_the_probe_file(tmp_path):
    name = run("mtime", "--dir", str(tmp_path), "--create").stdout.strip()
    assert (tmp_path / name).exists()
    assert run("mtime", "--dir", str(tmp_path), "--remove", name).returncode == 0
    assert list(tmp_path.iterdir()) == []


def test_cross_alone_sees_no_contention_and_exits_3(tmp_path):
    r = run("cross", "--dir", str(tmp_path), "--role", "a", "--n", "5", "--tag", "t1")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "acquired 5" in r.stdout
    assert "no contention was observed" in r.stderr
    assert list(tmp_path.iterdir()) == []


def test_cross_two_sides_with_start_at_contend_and_pass(tmp_path):
    import time
    start = str(time.time() + 2.5)
    cmd = [sys.executable, str(SCRIPT), "cross", "--dir", str(tmp_path), "--n", "50",
           "--tag", "t2", "--start-at", start]
    procs = [subprocess.Popen(cmd + ["--role", r], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) for r in "ab"]
    outs = [p.communicate(timeout=120) for p in procs]
    # One side may win every round and see no contention itself (exit 3); the
    # run proves something when neither side saw a double and one saw contention.
    codes = sorted(p.returncode for p in procs)
    assert codes[0] == 0 and codes[1] in (0, 3), outs
    assert list(tmp_path.iterdir()) == []


def test_cross_refuses_to_start_over_an_existing_lock_file(tmp_path):
    stale = tmp_path / ".lock-race-zz"
    stale.write_text("left by an earlier run")
    r = run("cross", "--dir", str(tmp_path), "--role", "a", "--n", "5", "--tag", "zz")
    assert r.returncode == 2, r.stdout + r.stderr
    assert str(stale) in r.stderr and "already exists" in r.stderr
    assert r.stdout == ""                                   # it never raced
    assert stale.read_text() == "left by an earlier run"    # and left it alone
    assert sorted(p.name for p in tmp_path.iterdir()) == [".lock-race-zz"]


def test_cross_that_never_acquired_exits_3_naming_the_lock_file(tmp_path, monkeypatch, capsys):
    # The lock file appears after the start check (e.g. during the --start-at
    # wait) and nobody releases it: every round is contended, none acquired.
    sp = _load()
    path = tmp_path / ".lock-race-zz"
    real_loop = sp._race_loop

    def loop(directory, name, *a, **k):
        path.write_text("stale")
        return real_loop(directory, name, *a, **k)

    monkeypatch.setattr(sp, "_race_loop", loop)
    rc = sp.main(["cross", "--dir", str(tmp_path), "--role", "a", "--n", "5", "--tag", "zz"])
    out, err = capsys.readouterr()
    assert rc == 3
    assert "acquired 0 contended 5" in out
    assert "never acquired" in err and str(path) in err and "stale" in err
    assert path.read_text() == "stale"                      # not ours: left alone


def test_cross_both_sides_acquire_and_contend(tmp_path):
    # Paced rounds: neither side spins through its rounds while the other holds,
    # so each side both acquires and is refused, and both pass.
    import time
    start = str(time.time() + 2.5)
    cmd = [sys.executable, str(SCRIPT), "cross", "--dir", str(tmp_path), "--n", "50",
           "--tag", "t3", "--start-at", start]
    procs = [subprocess.Popen(cmd + ["--role", r], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) for r in "ab"]
    outs = [p.communicate(timeout=120) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outs
    for out, _ in outs:
        assert "acquired 0 " not in out and "contended 0 " not in out, out
    assert list(tmp_path.iterdir()) == []


def test_race_line_keeps_field_order_and_adds_unreadable(tmp_path):
    r = run("race", "--dir", str(tmp_path), "--n", "5")
    import re
    assert re.match(r"acquired \d+ contended \d+ vanished \d+ double \d+ "
                    r"marker-overlap \d+ \(advisory\) unreadable \d+\n", r.stdout)


def test_unreadable_holder_is_counted(tmp_path, monkeypatch):
    sp = _load()
    name = ".lock-race-x"
    (tmp_path / name).write_text("someone")
    real_open = open

    def deny(path, *a, **k):
        if str(path).endswith(name):
            raise PermissionError(13, "denied")
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", deny)
    c = sp._race_loop(str(tmp_path), name, 3, "w0")
    assert c["contended"] == 3 and c["unreadable"] == 3


def test_cross_removes_its_own_lock_when_interrupted(tmp_path, monkeypatch):
    sp = _load()
    monkeypatch.setattr(sp.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))
    args = sp.build_parser().parse_args(
        ["cross", "--dir", str(tmp_path), "--role", "a", "--n", "3", "--tag", "k"])
    try:
        sp.cmd_cross(args)
    except KeyboardInterrupt:
        pass
    assert list(tmp_path.iterdir()) == []


def test_race_with_a_dead_worker_exits_2_promptly(tmp_path):
    import time
    t = time.time()
    r = run("race", "--dir", str(tmp_path), "--n", "5",
            env_extra={"STATION_PROBE_TEST_CRASH": "1"})
    assert r.returncode == 2, r.stdout + r.stderr
    assert "died" in r.stderr
    assert time.time() - t < 30
    assert list(tmp_path.iterdir()) == []


def test_race_warns_when_nothing_contended(tmp_path):
    r = run("race", "--dir", str(tmp_path), "--n", "1")
    if "contended 0" in r.stdout:
        assert "no contention" in r.stderr
    assert r.returncode == 0


def test_bad_counts_are_usage_errors(tmp_path):
    for extra in (["--workers", "1"], ["--workers", "0"], ["--n", "0"]):
        r = run("race", "--dir", str(tmp_path), *extra)
        assert r.returncode == 2 and "must be >=" in r.stderr, extra
    r = run("cross", "--dir", str(tmp_path), "--role", "a", "--n", "0", "--tag", "t")
    assert r.returncode == 2


def test_probe_imports_only_the_stdlib():
    tree = ast.parse(SCRIPT.read_text())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    assert mods
    assert mods <= set(sys.stdlib_module_names)
    assert not mods & {"emcee", "llama"}
