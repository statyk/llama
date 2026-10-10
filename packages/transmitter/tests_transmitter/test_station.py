import json
import time
from pathlib import Path

import pytest

from tests_transmitter.helpers import build_package, make_root, set_age
from transmitter import station
from transmitter.errors import StationRootError
from transmitter.station import Entry, Ineligible, Show


def _eval(pkg, quiet_s=600.0):
    return station.evaluate(pkg, now_s=time.time(), quiet_s=quiet_s)


def test_ready_package_is_eligible(tmp_path):
    pkg = build_package(make_root(tmp_path))
    show = _eval(pkg)
    assert isinstance(show, Show)
    assert show.slug == "band-2005-11-01"
    assert show.entries[0] == Entry("dj-audio/set1-intro.mp3", "clip", "DJ intro (set 1)")
    assert show.entries[1] == Entry("audio/01 - Song 1.mp3", "track", "Song 1")
    assert show.entries[-1] == Entry("dj-audio/99-outro.mp3", "clip", "DJ outro")
    assert show.meta["artist"] == "Band" and show.meta["profile"] == "indie"
    assert len(show.key) == 20


def _break(pkg, how):
    m = json.loads((pkg / "manifest.json").read_text())
    if how == "unvoiced":
        m["dj_audio"] = None
    elif how == "no-notes-file":
        (pkg / "dj-notes.md").unlink()
    elif how == "clip-missing":
        (pkg / "dj-audio" / "99-outro.mp3").unlink()
    elif how == "no-m3u":
        (pkg / "broadcast.m3u").unlink()
    elif how == "track-missing":
        (pkg / "audio" / "02 - Song 2.mp3").unlink()
    elif how == "m3u-entry-missing":
        (pkg / "broadcast.m3u").write_text("audio/01 - Song 1.mp3\naudio/nope.mp3\n")
    elif how == "m3u-escapes":
        (pkg / "broadcast.m3u").write_text("../other/audio/01.mp3\n")
    elif how == "m3u-absolute":
        (pkg / "broadcast.m3u").write_text("/etc/passwd\n")
    elif how == "v2":
        m["schema_version"] = 2
    (pkg / "manifest.json").write_text(json.dumps(m))
    set_age(pkg, 3600)


@pytest.mark.parametrize("how,reason", [
    ("unvoiced", "no DJ audio"),
    ("no-notes-file", "no DJ script"),
    ("clip-missing", "DJ clip(s) missing"),
    ("no-m3u", "no broadcast.m3u"),
    ("track-missing", "track file(s) missing"),
    ("m3u-entry-missing", "entry missing: audio/nope.mp3"),
    ("m3u-escapes", "escapes the package"),
    ("m3u-absolute", "escapes the package"),
    ("v2", "unsupported manifest"),
])
def test_each_leg_makes_a_package_ineligible(tmp_path, how, reason):
    pkg = build_package(make_root(tmp_path))
    _break(pkg, how)
    result = _eval(pkg)
    assert isinstance(result, Ineligible)
    assert any(reason in r for r in result.reasons), result.reasons


def test_quiet_period(tmp_path):
    pkg = build_package(make_root(tmp_path), age_s=60)
    assert isinstance(_eval(pkg, quiet_s=600), Ineligible)
    assert isinstance(_eval(pkg, quiet_s=30), Show)


def test_key_tracks_the_file_set(tmp_path):
    pkg = build_package(make_root(tmp_path))
    k1 = _eval(pkg).key
    assert _eval(pkg).key == k1
    f = pkg / "audio" / "01 - Song 1.mp3"
    f.write_bytes(f.read_bytes() + b"x")
    set_age(pkg, 3600)
    assert _eval(pkg).key != k1


def test_emcee_temp_files_do_not_hold_the_quiet_period(tmp_path):
    pkg = build_package(make_root(tmp_path))
    (pkg / "dj-audio" / "99-outro.mp3.k2j3.tmp").write_bytes(b"partial")     # emcee's mkstemp name; mtime: now
    assert isinstance(_eval(pkg), Show)


def test_a_file_vanishing_mid_scan_is_changing_not_a_crash(tmp_path, monkeypatch):
    pkg = build_package(make_root(tmp_path))
    dj_dir = pkg / "dj-audio"
    real_iterdir = Path.iterdir

    def iterdir(self):                 # listed, then gone before evaluate stats it
        yield from real_iterdir(self)
        if self == dj_dir:
            yield dj_dir / "set2-intro.mp3"

    monkeypatch.setattr(Path, "iterdir", iterdir)
    result = _eval(pkg)
    assert isinstance(result, Ineligible)
    assert result.reasons[0].startswith("changing")


def test_scan_skips_dot_dirs_and_non_packages(tmp_path):
    root = make_root(tmp_path)
    build_package(root, "a-show")
    build_package(root, ".swap-a-show")
    (root / "not-a-package").mkdir()
    (root / "._junk").write_text("")
    shows, skipped = station.scan(root, now_s=time.time(), quiet_s=600)
    assert [s.slug for s in shows] == ["a-show"] and skipped == []


def test_empty_root_without_marker_is_refused(tmp_path):
    root = tmp_path / "nfs"
    root.mkdir()                      # what a down NFS mount looks like on hugo
    with pytest.raises(StationRootError, match="marker"):
        station.scan(root, now_s=time.time(), quiet_s=0)


def test_missing_or_unset_root_is_refused(tmp_path):
    with pytest.raises(StationRootError, match="missing"):
        station.require_root(tmp_path / "gone")
    with pytest.raises(StationRootError, match=r"\[station\] root"):
        station.require_root(None)
