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


def test_mtime_replace_sets_mtime_before_rename(tmp_path):
    name = run("mtime", "--dir", str(tmp_path), "--create").stdout.strip()
    assert name.startswith(".mtime-probe-")
    assert (tmp_path / name).stat().st_mtime != 1767225600
    r = run("mtime", "--dir", str(tmp_path), "--replace", name)
    assert r.returncode == 0, r.stderr
    assert int(r.stdout.strip()) == 1767225600
    assert int((tmp_path / name).stat().st_mtime) == 1767225600
    assert [p.name for p in tmp_path.iterdir()] == [name]


def test_mtime_remove_deletes_the_probe_file(tmp_path):
    name = run("mtime", "--dir", str(tmp_path), "--create").stdout.strip()
    assert (tmp_path / name).exists()
    assert run("mtime", "--dir", str(tmp_path), "--remove", name).returncode == 0
    assert list(tmp_path.iterdir()) == []


def test_cross_runs_one_side_and_cleans_up(tmp_path):
    r = run("cross", "--dir", str(tmp_path), "--role", "a", "--n", "5", "--tag", "t1")
    assert r.returncode == 0, r.stderr
    assert "acquired 5" in r.stdout
    assert list(tmp_path.iterdir()) == []


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
