import json
import time
from pathlib import Path

import pytest

from tests_transmitter.helpers import build_package, make_root, mark_awaiting_fix, set_age
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


def _assert_changing(result):
    assert isinstance(result, Ineligible)
    assert result.reasons[0].startswith("changing")


def test_m3u_vanishing_between_exists_and_read_is_changing(tmp_path, monkeypatch):
    pkg = build_package(make_root(tmp_path))

    def gone(path):
        raise FileNotFoundError(str(path))

    monkeypatch.setattr(station, "read_m3u", gone)
    _assert_changing(_eval(pkg))


def test_m3u_with_invalid_utf8_is_unreadable(tmp_path):
    pkg = build_package(make_root(tmp_path))
    (pkg / "broadcast.m3u").write_bytes(b"audio/\xff\xfe.mp3\n")
    set_age(pkg, 3600)
    result = _eval(pkg)
    assert isinstance(result, Ineligible)
    assert result.reasons[0].startswith("unreadable broadcast.m3u")


def test_estale_on_exists_is_changing(tmp_path, monkeypatch):
    import errno
    pkg = build_package(make_root(tmp_path))
    real_exists = Path.exists

    def exists(self, *a, **k):
        if self.name == "dj-notes.md":
            raise OSError(errno.ESTALE, "Stale file handle")
        return real_exists(self, *a, **k)

    monkeypatch.setattr(Path, "exists", exists)
    _assert_changing(_eval(pkg))


def test_symlink_loop_runtimeerror_is_changing(tmp_path, monkeypatch):
    pkg = build_package(make_root(tmp_path))

    def boom(self, *a, **k):
        raise RuntimeError("Symlink loop")

    monkeypatch.setattr(Path, "resolve", boom)
    _assert_changing(_eval(pkg))


def test_require_root_maps_oserror_on_marker_to_station_root_error(tmp_path, monkeypatch):
    import errno
    root = make_root(tmp_path)
    real_exists = Path.exists

    def exists(self, *a, **k):
        if self.name == station.MARKER:
            raise OSError(errno.ESTALE, "Stale file handle")
        return real_exists(self, *a, **k)

    monkeypatch.setattr(Path, "exists", exists)
    with pytest.raises(StationRootError, match=str(root)):
        station.require_root(root)


def test_scan_survives_one_vanishing_package(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    build_package(root, "a-show")
    build_package(root, "b-show")
    real = station.read_m3u

    def read(path):
        if path.parent.name == "a-show":
            raise FileNotFoundError(str(path))
        return real(path)

    monkeypatch.setattr(station, "read_m3u", read)
    shows, skipped = station.scan(root, now_s=time.time(), quiet_s=600)
    assert [s.slug for s in shows] == ["b-show"]
    assert [s.slug for s in skipped] == ["a-show"]
    assert skipped[0].reasons[0].startswith("changing")


def test_scan_skips_a_package_whose_manifest_check_raises(tmp_path, monkeypatch):
    import errno
    root = make_root(tmp_path)
    build_package(root, "a-show")
    build_package(root, "b-show")
    real_exists = Path.exists

    def exists(self, *a, **k):
        if self.parent.name == "a-show" and self.name == "manifest.json":
            raise OSError(errno.ESTALE, "Stale file handle")
        return real_exists(self, *a, **k)

    monkeypatch.setattr(Path, "exists", exists)
    shows, skipped = station.scan(root, now_s=time.time(), quiet_s=600)
    assert [s.slug for s in shows] == ["b-show"]
    assert [s.slug for s in skipped] == ["a-show"]
    assert skipped[0].reasons[0].startswith("changing")


def test_scan_skips_a_package_whose_is_dir_raises(tmp_path, monkeypatch):
    import errno
    root = make_root(tmp_path)
    build_package(root, "a-show")
    build_package(root, "b-show")
    real_is_dir = Path.is_dir

    def is_dir(self, *a, **k):
        if self.name == "a-show":
            raise OSError(errno.ESTALE, "Stale file handle")
        return real_is_dir(self, *a, **k)

    monkeypatch.setattr(Path, "is_dir", is_dir)
    shows, skipped = station.scan(root, now_s=time.time(), quiet_s=600)
    assert [s.slug for s in shows] == ["b-show"]
    assert skipped[0].slug == "a-show" and skipped[0].reasons[0].startswith("changing")


def test_scan_listing_failure_is_station_root_error(tmp_path, monkeypatch):
    import errno
    root = make_root(tmp_path)
    real_iterdir = Path.iterdir

    def iterdir(self):
        if self == root:
            raise OSError(errno.ESTALE, "Stale file handle")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    with pytest.raises(StationRootError, match=str(root)):
        station.scan(root, now_s=time.time(), quiet_s=0)


def test_require_root_is_dir_oserror_is_station_root_error(tmp_path, monkeypatch):
    import errno
    root = make_root(tmp_path)

    def is_dir(self, *a, **k):
        raise OSError(errno.ESTALE, "Stale file handle")

    monkeypatch.setattr(Path, "is_dir", is_dir)
    with pytest.raises(StationRootError, match=str(root)):
        station.require_root(root)


def test_show_meta_carries_estimate_inputs(tmp_path):
    root = make_root(tmp_path)
    pkg = build_package(root, "band-2005-11-01")
    m = json.loads((pkg / "manifest.json").read_text())
    m["total_duration_sec"] = 180.0
    m["dj_audio"]["profile"] = "funk"
    (pkg / "manifest.json").write_text(json.dumps(m))
    set_age(pkg, 3600)
    show = station.evaluate(pkg, now_s=time.time(), quiet_s=0)
    assert show.meta["total_duration_sec"] == 180.0 and show.meta["voiced_profile"] == "funk"
    assert set(show.meta["sizes"]) == {e.path for e in show.entries}
    assert all(v == (pkg / k).stat().st_size for k, v in show.meta["sizes"].items())


def test_voiced_profile_falls_back_to_source_profile(tmp_path):
    pkg = build_package(make_root(tmp_path))
    show = _eval(pkg)
    assert show.meta["voiced_profile"] == "indie" and show.meta["total_duration_sec"] is None


def test_file_set_key_unchanged(tmp_path):
    import hashlib
    pkg = build_package(make_root(tmp_path))
    rels = station.read_m3u(pkg / "broadcast.m3u")
    h = hashlib.sha256()          # the pre-task formula, computed independently
    for rel in rels:
        st = (pkg / rel).stat()
        h.update(json.dumps([rel, st.st_size, st.st_mtime_ns]).encode() + b"\n")
    expected = h.hexdigest()[:20]
    key, sizes = station.file_set_key_and_sizes(pkg, rels)
    assert key == expected and station.file_set_key(pkg, rels) == expected
    assert sizes == {rel: (pkg / rel).stat().st_size for rel in rels}


def test_non_finite_total_duration_is_none(tmp_path):
    pkg = build_package(make_root(tmp_path))
    for bad in ("NaN", "Infinity", "-5"):
        m = json.loads((pkg / "manifest.json").read_text())
        m["total_duration_sec"] = 1
        text = json.dumps(m).replace('"total_duration_sec": 1', f'"total_duration_sec": {bad}')
        (pkg / "manifest.json").write_text(text)
        set_age(pkg, 3600)
        assert _eval(pkg).meta["total_duration_sec"] is None, bad


@pytest.mark.parametrize("value,reason", [
    ({"reason": "bulk apply", "marked_at": "2026-10-25T00:00:00Z"}, "awaiting fix from llama: bulk apply"),
    ({"reason": "  two\nlines \r\n here  "}, "awaiting fix from llama: two lines here"),
    ({"marked_at": "2026-10-25T00:00:00Z"}, "awaiting fix from llama"),
    ({"reason": ""}, "awaiting fix from llama"),
    ({"reason": "   "}, "awaiting fix from llama"),
    ({"reason": 7}, "awaiting fix from llama"),
    ({}, "awaiting fix from llama"),
    ("later", "awaiting fix from llama"),
    ("", "awaiting fix from llama"),
    (["x"], "awaiting fix from llama"),
    (0, "awaiting fix from llama"),
    (True, "awaiting fix from llama"),
    (False, "awaiting fix from llama"),
])
def test_awaiting_fix_makes_a_voiced_package_ineligible(tmp_path, value, reason):
    pkg = build_package(make_root(tmp_path))
    mark_awaiting_fix(pkg, value)
    result = _eval(pkg)
    assert isinstance(result, Ineligible)
    assert result.reasons[0] == reason, result.reasons


@pytest.mark.parametrize("present", [False, True])
def test_absent_or_null_awaiting_fix_is_eligible(tmp_path, present):
    pkg = build_package(make_root(tmp_path))
    if present:
        mark_awaiting_fix(pkg, None)
    assert isinstance(_eval(pkg), Show)


def test_awaiting_fix_is_reported_alongside_other_legs_and_first(tmp_path):
    pkg = build_package(make_root(tmp_path), voiced=False)
    mark_awaiting_fix(pkg)
    result = _eval(pkg)
    assert isinstance(result, Ineligible)
    assert result.reasons[0] == "awaiting fix from llama: pending re-processing"
    assert any("no DJ audio" in r for r in result.reasons)


def test_scan_lists_a_marked_package_as_ineligible_with_its_reason(tmp_path):
    root = make_root(tmp_path)
    build_package(root, "band-2005-11-01")
    mark_awaiting_fix(build_package(root, "band-2005-11-02"))
    shows, skipped = station.scan(root, now_s=time.time(), quiet_s=600.0)
    assert [s.slug for s in shows] == ["band-2005-11-01"]
    assert [(i.slug, i.reasons[0]) for i in skipped] == [
        ("band-2005-11-02", "awaiting fix from llama: pending re-processing")]


def test_a_long_awaiting_fix_reason_is_capped(tmp_path):
    pkg = build_package(make_root(tmp_path))
    mark_awaiting_fix(pkg, {"reason": "word " * 200})
    got = _eval(pkg).reasons[0]
    prefix = "awaiting fix from llama: "
    assert got.startswith(prefix) and got.endswith("\u2026")
    assert len(got) - len(prefix) == 200


def test_a_reason_of_exactly_the_cap_is_not_truncated(tmp_path):
    pkg = build_package(make_root(tmp_path))
    mark_awaiting_fix(pkg, {"reason": "x" * 200})
    assert _eval(pkg).reasons[0] == "awaiting fix from llama: " + "x" * 200
