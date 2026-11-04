"""`emcee retitle`: the program-title backfill command.

STRICT surface: on go-live it runs against the live station share. The order
is plan, confirm, `ps` check, lock, drift check, then backups and writes; no
lock is held while it asks, the lock covers the whole write phase, and each
backup is durable before its show's write (a SIGTERM under the lock ends the
process with `os._exit`, so no cleanup runs after it)."""
import hashlib
import json
import os
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

import emcee.cli as cli_mod
import emcee.station_lock as sl
from emcee.cli import app
from emcee.retitle import TitleWriteFailed
from emcee.station_lock import LOCK_NAME

from tests.helpers import build_package, mark_awaiting_fix, set_dj_audio, station_home

runner = CliRunner()
OLD_NS = 1_700_000_000_123_456_789
FOREIGN = (b"lma-station-lock 1 " + b"b" * 32 + b"\ntool: llama\ncommand: deliver gd73\n"
           b"host: mac\npid: 999\nstarted: 2026-11-04T09:00:00-08:00\n")
ASSIGN = ('[assign.profiles.dead]\npresenter = "p"\ntitle = "Dead Hour"\n\n'
          '[assign.profiles.other]\npresenter = "p"\n')


@pytest.fixture(autouse=True)
def _no_held_lock_and_no_other_tools(monkeypatch):
    sl._held = None
    monkeypatch.setattr(cli_mod, "other_tool_processes", lambda: [])
    yield
    sl._held = None


def _station(tmp_path, monkeypatch, assign: str = ASSIGN) -> tuple[Path, Path]:
    return station_home(tmp_path, monkeypatch, assign=assign)


def _voiced(station: Path, slug: str, *, profile: str = "dead", **dj) -> Path:
    pkg = build_package(station, slug, voiced=True, profile=profile)
    set_dj_audio(pkg, profile=profile, profile_source="llama", **dj)
    os.utime(pkg / "manifest.json", ns=(OLD_NS, OLD_NS))
    return pkg


def _snapshot(station: Path) -> dict[str, tuple[bytes, int]]:
    return {p.parent.name: (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(station.glob("*/manifest.json"))}


def _title(pkg: Path):
    return json.loads((pkg / "manifest.json").read_bytes())["dj_audio"].get("title", "ABSENT")


def _backup_dirs(home: Path) -> list[Path]:
    root = home / "title-backups"
    return sorted(root.iterdir()) if root.exists() else []


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _records(run_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (run_dir / "record.jsonl").read_text().splitlines()]


def _three(station: Path) -> list[Path]:
    """Three shows, each needing a write."""
    return [_voiced(station, "a"), _voiced(station, "b", title="Old"),
            _voiced(station, "c", profile="other", title="Old")]


def _refused(station: Path, slug: str) -> Path:
    pkg = _voiced(station, slug)
    path = pkg / "manifest.json"
    path.write_bytes(path.read_bytes().rstrip(b"\n"))          # not emcee's encoding
    os.utime(path, ns=(OLD_NS, OLD_NS))
    return pkg


def _wrap_write_title(monkeypatch, on_call):
    """Wrap `cli.write_title`: `on_call(pkg_dir, real)` decides what happens."""
    real = cli_mod.write_title
    calls: list[str] = []

    def wrapped(pkg_dir, *, expect, title):
        calls.append(Path(pkg_dir).name)
        return on_call(Path(pkg_dir), lambda: real(pkg_dir, expect=expect, title=title))

    monkeypatch.setattr(cli_mod, "write_title", wrapped)
    return calls


# ---- the plan --------------------------------------------------------------


def test_dry_run_lists_writes_awaiting_and_refused_and_writes_nothing(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    _voiced(station, "a")
    marked = _voiced(station, "b")
    mark_awaiting_fix(marked)
    _refused(station, "c")
    build_package(station, "d", voiced=False)
    _voiced(station, "e", title="Dead Hour")
    before = _snapshot(station)

    def no_ps():
        raise AssertionError("the dry run ran the ps check")

    monkeypatch.setattr(cli_mod, "other_tool_processes", no_ps)
    result = runner.invoke(app, ["retitle", "--dry-run"])

    assert result.exit_code == 1, result.output          # a refused package
    out = result.stdout
    assert "would write a: (none) -> Dead Hour" in out
    assert "skip b: awaiting fix from llama" in out
    assert "refused c: not in emcee's encoding" in out
    assert "1 to write, 1 unchanged, 1 awaiting fix, 1 refused, 1 unvoiced" in out
    assert _snapshot(station) == before
    assert not (station / LOCK_NAME).exists()
    assert _backup_dirs(home) == []


def test_dry_run_lists_stray_temps_and_leaves_them(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    pkg = _voiced(station, "a")
    stray = pkg / ".manifest.json.emcee-0123456789abcdef.tmp"
    stray.write_bytes(b"half")

    result = runner.invoke(app, ["retitle", "--dry-run"])

    assert result.exit_code == 0, result.output          # a listing only
    assert "stray temp: a/.manifest.json.emcee-0123456789abcdef.tmp" in result.stdout
    assert stray.read_bytes() == b"half"


# ---- confirm, ps, lock -----------------------------------------------------


def test_yes_prints_every_write_and_stamps_titles(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    a, b, c = _three(station)

    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 0, result.output
    out = result.stdout
    assert "a: (none) -> Dead Hour" in out
    assert "b: Old -> Dead Hour" in out
    assert "c: Old -> (none)" in out
    assert "3 written" in out
    assert (_title(a), _title(b), _title(c)) == ("Dead Hour", "Dead Hour", None)
    for pkg in (a, b, c):
        assert (pkg / "manifest.json").stat().st_mtime_ns == OLD_NS
    assert not (station / LOCK_NAME).exists()


def test_no_tty_without_yes_refuses(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    _three(station)
    before = _snapshot(station)
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: False)

    result = runner.invoke(app, ["retitle"])

    assert result.exit_code == 1
    assert "error: refusing to write without confirmation; pass --yes" in result.stderr
    assert "would write a: (none) -> Dead Hour" in result.stdout     # the plan was shown
    assert _snapshot(station) == before
    assert _backup_dirs(home) == []


def test_no_lock_is_held_while_asking_proceed(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    a = _voiced(station, "a")
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)
    asked: list[str] = []

    def confirm(text, *args, **kwargs):
        asked.append(text)
        assert not (station / LOCK_NAME).exists()
        assert sl._held is None
        return True

    monkeypatch.setattr(cli_mod.typer, "confirm", confirm)
    result = runner.invoke(app, ["retitle"])

    assert result.exit_code == 0, result.output
    assert asked == ["Proceed?"]
    assert _title(a) == "Dead Hour"


def test_declining_writes_nothing(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    _three(station)
    before = _snapshot(station)
    monkeypatch.setattr(cli_mod, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(cli_mod.typer, "confirm", lambda *a, **k: False)

    result = runner.invoke(app, ["retitle"])

    assert result.exit_code == 0, result.output
    assert "nothing written" in result.stdout
    assert _snapshot(station) == before
    assert _backup_dirs(home) == []


def test_lock_is_held_for_the_whole_write_phase(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    _three(station)
    seen: list[tuple[str, bytes | None]] = []

    def check(pkg_dir, real):
        path = station / LOCK_NAME
        seen.append((pkg_dir.name, path.read_bytes() if path.exists() else None))
        return real()

    _wrap_write_title(monkeypatch, check)
    real_save = cli_mod._save_backup
    backup_saw_lock: list[bool] = []

    def save(*a, **k):
        backup_saw_lock.append((station / LOCK_NAME).exists())
        return real_save(*a, **k)

    monkeypatch.setattr(cli_mod, "_save_backup", save)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 0, result.output
    assert [s for s, _ in seen] == ["a", "b", "c"]
    raws = [raw for _, raw in seen]
    assert all(raw is not None and b"\ncommand: emcee retitle\n" in raw for raw in raws)
    assert len(set(raws)) == 1                         # one hold, not one per show
    assert backup_saw_lock == [True, True, True]
    assert not (station / LOCK_NAME).exists()


def test_held_lock_refuses_and_writes_nothing(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    _three(station)
    (station / LOCK_NAME).write_bytes(FOREIGN)
    before = _snapshot(station)

    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert "the station is locked by another writer" in result.stderr
    assert "  pid: 999" in result.stderr
    assert "emcee lock clear" in result.stderr
    assert _snapshot(station) == before
    assert _backup_dirs(home) == []
    assert (station / LOCK_NAME).read_bytes() == FOREIGN


def test_ps_refusal_writes_nothing_and_takes_no_lock(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    _three(station)
    before = _snapshot(station)
    monkeypatch.setattr(cli_mod, "other_tool_processes",
                        lambda: ["4242 1 llama deliver gd73", "4343 1 emcee run"])
    locked: list[bool] = []
    monkeypatch.setattr(cli_mod, "station_lock", lambda *a, **k: locked.append(True))

    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert "refusing: other emcee or llama processes are running" in result.stderr
    assert "  4242 1 llama deliver gd73" in result.stderr
    assert "  4343 1 emcee run" in result.stderr
    assert locked == []
    assert _snapshot(station) == before
    assert _backup_dirs(home) == []


def test_ps_check_that_cannot_run_refuses(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    _three(station)
    before = _snapshot(station)

    def broken():
        raise FileNotFoundError(2, "No such file or directory", "ps")

    monkeypatch.setattr(cli_mod, "other_tool_processes", broken)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert "refusing: cannot check for other emcee or llama processes" in result.stderr
    assert _snapshot(station) == before
    assert not (station / LOCK_NAME).exists()


def test_plan_drift_under_the_lock_refuses_the_whole_run(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    a, b, c = _three(station)

    planned = False
    reread: list[tuple[str, bool]] = []     # (slug, lock held) for each read after the plan
    real_read = Path.read_bytes

    def read_bytes(self):
        if planned and self.name == "manifest.json":
            lock = station / LOCK_NAME
            held = (sl._held is not None and lock.exists()
                    and b"\ncommand: emcee retitle\n" in real_read(lock))
            reread.append((self.parent.name, held))
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    def llama_writes_b_after_the_plan():
        nonlocal planned
        path = b / "manifest.json"
        path.write_bytes(real_read(path).replace(b"Some Venue", b"Other Venue"))
        planned = True
        return []

    monkeypatch.setattr(cli_mod, "other_tool_processes", llama_writes_b_after_the_plan)
    before = None
    real_lock = cli_mod.station_lock

    def lock(*args, **kwargs):
        nonlocal before, planned
        planned = False                        # the test's own reads are not recorded
        before = _snapshot(station)            # after the change, as the lock is taken
        planned = True
        return real_lock(*args, **kwargs)

    monkeypatch.setattr(cli_mod, "station_lock", lock)
    calls = _wrap_write_title(monkeypatch, lambda d, real: real())
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert ("refusing: 1 manifest(s) changed since the plan; nothing written; run again"
            in result.stderr)
    assert "  b" in result.stderr.splitlines()
    assert calls == []
    # R2: every planned manifest was re-read, each one under the lock.
    assert reread == [("a", True), ("b", True), ("c", True)]
    assert _snapshot(station) == before
    assert _backup_dirs(home) == []
    assert not (station / LOCK_NAME).exists()


# ---- backups and writes ----------------------------------------------------


def test_backup_dirs_and_entries_are_fsynced_before_the_first_write(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    _voiced(station, "a")
    _voiced(station, "b")
    synced: list[tuple[int, int]] = []          # (st_dev, st_ino) of each fsynced fd
    events: list[str] = []
    real_fsync = os.fsync

    def fsync(fd):
        st = os.fstat(fd)
        synced.append((st.st_dev, st.st_ino))
        return real_fsync(fd)

    def ident(path: Path) -> tuple[int, int]:
        st = path.stat()
        return st.st_dev, st.st_ino

    def check(pkg_dir, real):
        run_dir, = _backup_dirs(home)
        for d in (home, home / "title-backups", run_dir):
            assert ident(d) in synced, d
        # The run dir was fsynced again after this show's backup entries.
        last_entry = max(i for i, s in enumerate(synced)
                         if s in (ident(run_dir / f"{pkg_dir.name}.json"),
                                  ident(run_dir / "record.jsonl")))
        assert ident(run_dir) in synced[last_entry + 1:], pkg_dir.name
        events.append(pkg_dir.name)
        return real()

    monkeypatch.setattr(os, "fsync", fsync)
    _wrap_write_title(monkeypatch, check)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 0, result.output
    assert events == ["a", "b"]


def test_a_dir_fsync_failure_is_a_backup_failure(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    a, b = _voiced(station, "a"), _voiced(station, "b")
    before = _snapshot(station)
    real_fsync_dir = cli_mod._fsync_dir

    def fsync_dir(path):
        if (Path(path) / "a.json").exists():
            raise OSError(5, "Input/output error")
        return real_fsync_dir(path)

    monkeypatch.setattr(cli_mod, "_fsync_dir", fsync_dir)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert "error: a: backup failed ([Errno 5] Input/output error)" in result.stderr
    assert "not attempted: a, b" in result.stderr
    assert _snapshot(station) == before


def test_backup_saved_before_each_write_with_sha(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    a, b, c = _three(station)
    original = _snapshot(station)
    order: list[str] = []

    def check(pkg_dir, real):
        run_dir, = _backup_dirs(home)
        # The backup and its record line exist (durable) before the write.
        assert (run_dir / f"{pkg_dir.name}.json").read_bytes() == original[pkg_dir.name][0]
        assert _records(run_dir)[-1]["slug"] == pkg_dir.name
        order.append(pkg_dir.name)
        return real()

    _wrap_write_title(monkeypatch, check)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 0, result.output
    assert order == ["a", "b", "c"]
    run_dir, = _backup_dirs(home)
    assert re.fullmatch(r"\d{8}T\d{6}Z", run_dir.name)
    expected = []
    for pkg in (a, b, c):
        raw, mtime = original[pkg.name]
        assert (run_dir / f"{pkg.name}.json").read_bytes() == raw
        expected += [{"slug": pkg.name, "before_sha256": _sha(raw), "mtime_ns": mtime},
                     {"slug": pkg.name,
                      "after_sha256": _sha((pkg / "manifest.json").read_bytes())}]
    assert _records(run_dir) == expected
    assert all(m == OLD_NS for _, m in original.values())


def test_backup_failure_aborts_before_writing_that_show(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    a, b, c = _three(station)
    before = _snapshot(station)
    real_save = cli_mod._save_backup

    def save(run_dir, slug, raw, mtime_ns):
        if slug == "b":
            raise OSError(28, "No space left on device")
        return real_save(run_dir, slug, raw, mtime_ns)

    monkeypatch.setattr(cli_mod, "_save_backup", save)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert ("error: b: backup failed ([Errno 28] No space left on device); "
            "stopping before writing it") in result.stderr
    assert "not attempted: b, c" in result.stderr
    assert _title(a) == "Dead Hour"
    after = _snapshot(station)
    assert after["b"] == before["b"] and after["c"] == before["c"]
    assert not (station / LOCK_NAME).exists()


def test_backup_failure_of_the_real_writer_on_an_existing_backup_file(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    a, b, c = _three(station)
    before = _snapshot(station)
    real_save = cli_mod._save_backup

    def save(run_dir, slug, raw, mtime_ns):
        if slug == "b":
            (run_dir / "b.json").write_bytes(b"in the way")    # "xb" refuses it
        return real_save(run_dir, slug, raw, mtime_ns)

    monkeypatch.setattr(cli_mod, "_save_backup", save)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert "error: b: backup failed (" in result.stderr
    assert "not attempted: b, c" in result.stderr
    after = _snapshot(station)
    assert after["b"] == before["b"] and after["c"] == before["c"]


@pytest.mark.parametrize("exc", [TitleWriteFailed("b: the title write failed before its "
                                                  "rename (boom); the file is unchanged"),
                                 RuntimeError("a bug")])
def test_write_failure_stops_the_run_non_zero(tmp_path, monkeypatch, exc):
    _, station = _station(tmp_path, monkeypatch)
    a, b, c = _three(station)
    before = _snapshot(station)

    def fail_b(pkg_dir, real):
        if pkg_dir.name == "b":
            raise exc
        return real()

    calls = _wrap_write_title(monkeypatch, fail_b)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert calls == ["a", "b"]
    if isinstance(exc, TitleWriteFailed):
        assert f"error: {exc}" in result.stderr
    else:
        assert "error: b: RuntimeError: a bug" in result.stderr
    assert "not attempted: c" in result.stderr
    assert _title(a) == "Dead Hour"
    assert _snapshot(station)["c"] == before["c"]
    assert not (station / LOCK_NAME).exists()


def test_write_failure_on_the_last_show_says_nothing_is_left(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    _three(station)

    def fail_c(pkg_dir, real):
        if pkg_dir.name == "c":
            raise TitleWriteFailed("c: boom")
        return real()

    _wrap_write_title(monkeypatch, fail_c)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert "not attempted: (none)" in result.stderr


def test_changed_before_rename_is_skipped_and_listed(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    a, b, c = _three(station)

    def b_changed(pkg_dir, real):
        return None if pkg_dir.name == "b" else real()

    _wrap_write_title(monkeypatch, b_changed)
    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert "skip b: changed since the plan" in result.stdout
    assert "changed since the plan: b" in result.stderr
    assert (_title(a), _title(c)) == ("Dead Hour", None)
    run_dir, = _backup_dirs(home)
    # b's backup is there, but no after_sha256: a hand restore never touches it.
    assert [r["slug"] for r in _records(run_dir) if "after_sha256" in r] == ["a", "c"]


def test_awaiting_fix_shows_are_never_written(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    marked = _voiced(station, "a")
    mark_awaiting_fix(marked)
    os.utime(marked / "manifest.json", ns=(OLD_NS, OLD_NS))
    b = _voiced(station, "b")
    before = _snapshot(station)

    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 0, result.output
    assert "skip a: awaiting fix from llama" in result.stdout
    assert _snapshot(station)["a"] == before["a"]
    assert _title(b) == "Dead Hour"
    run_dir, = _backup_dirs(home)
    assert not (run_dir / "a.json").exists()


def test_rerun_after_success_has_nothing_to_write(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    _three(station)
    assert runner.invoke(app, ["retitle", "--yes"]).exit_code == 0
    after = _snapshot(station)

    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 0, result.output
    assert "nothing to write" in result.stdout
    assert "0 to write, 3 unchanged" in result.stdout
    assert _snapshot(station) == after
    assert len(_backup_dirs(home)) == 1


def test_exit_code_ignores_awaiting_unchanged_and_unvoiced(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    marked = _voiced(station, "a")
    mark_awaiting_fix(marked)
    _voiced(station, "b", title="Dead Hour")
    build_package(station, "c", voiced=False)
    _voiced(station, "d")

    dry = runner.invoke(app, ["retitle", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "1 to write, 1 unchanged, 1 awaiting fix, 0 refused, 1 unvoiced" in dry.stdout

    result = runner.invoke(app, ["retitle", "--yes"])
    assert result.exit_code == 0, result.output
    assert _title(station / "d") == "Dead Hour"


def test_exit_code_is_1_when_a_package_is_refused(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    _refused(station, "a")
    b = _voiced(station, "b")
    before = _snapshot(station)

    dry = runner.invoke(app, ["retitle", "--dry-run"])
    assert dry.exit_code == 1
    assert _snapshot(station) == before

    result = runner.invoke(app, ["retitle", "--yes"])
    assert result.exit_code == 1
    assert "refused a: not in emcee's encoding" in result.stdout
    assert _title(b) == "Dead Hour"
    assert _snapshot(station)["a"] == before["a"]


def test_exit_code_is_1_when_only_refused_and_nothing_to_write(tmp_path, monkeypatch):
    _, station = _station(tmp_path, monkeypatch)
    _refused(station, "a")

    result = runner.invoke(app, ["retitle", "--yes"])

    assert result.exit_code == 1
    assert "nothing to write" in result.stdout


def test_retitle_after_rename_in_config_changes_and_clears(tmp_path, monkeypatch):
    home, station = _station(tmp_path, monkeypatch)
    a = _voiced(station, "a")
    config = home / "config.toml"
    assert runner.invoke(app, ["retitle", "--yes"]).exit_code == 0
    assert _title(a) == "Dead Hour"

    config.write_text(config.read_text().replace('title = "Dead Hour"', 'title = "Night Hour"'))
    result = runner.invoke(app, ["retitle", "--yes"])
    assert result.exit_code == 0, result.output
    assert "a: Dead Hour -> Night Hour" in result.stdout
    assert _title(a) == "Night Hour"

    config.write_text(config.read_text().replace('title = "Night Hour"\n', ""))
    result = runner.invoke(app, ["retitle", "--yes"])
    assert result.exit_code == 0, result.output
    assert "a: Night Hour -> (none)" in result.stdout
    assert _title(a) is None
    assert (a / "manifest.json").stat().st_mtime_ns == OLD_NS
    assert len(_backup_dirs(home)) == 3           # same-second runs never share a dir
