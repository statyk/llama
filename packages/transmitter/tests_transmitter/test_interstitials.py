import os
import time

from tests_transmitter.helpers import build_package, make_root
from transmitter import interstitials, station
from transmitter.config import TransmitterConfig


def _clip(folder, name, data=b"ID3clip"):
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    p.write_bytes(data)
    os.utime(p, (time.time() - 3600,) * 2)
    return p


def test_scan_finds_ids_and_announcements(tmp_path):
    f = tmp_path / "i"
    _clip(f, "id-hello.mp3")
    _clip(f, "ann-0123456789ab.mp3", b"ID3abcd")
    _clip(f, "notes.txt")
    shows = interstitials.scan(f, now_s=time.time(), quiet_s=600)
    assert [s.slug for s in shows] == ["ann-0123456789ab", "id-hello"]
    ann, idc = shows
    assert (ann.meta["role"], ann.meta["ann_id"]) == ("ann", "0123456789ab")
    assert (idc.meta["role"], idc.meta["ann_id"]) == ("id", None)
    assert ann.entries[0].kind == "clip" and ann.entries[0].path == "ann-0123456789ab.mp3"
    assert ann.dir == f
    assert ann.meta["sizes"] == {"ann-0123456789ab.mp3": 7}
    assert ann.key == station.file_set_key(f, ["ann-0123456789ab.mp3"])


def test_missing_folder_is_an_empty_pool(tmp_path):
    assert interstitials.scan(tmp_path / "nope", now_s=time.time(), quiet_s=0) == []
    assert interstitials.scan(None, now_s=time.time(), quiet_s=0) == []


def test_clip_inside_quiet_period_is_not_eligible(tmp_path):
    p = tmp_path / "id-a.mp3"
    p.write_bytes(b"x")
    assert interstitials.scan(tmp_path, now_s=time.time(), quiet_s=600) == []
    assert len(interstitials.scan(tmp_path, now_s=time.time(), quiet_s=0)) == 1


def test_zero_byte_clip_is_skipped(tmp_path):
    _clip(tmp_path, "id-a.mp3", b"")
    assert interstitials.scan(tmp_path, now_s=time.time(), quiet_s=0) == []


def test_row_dir_inside_and_outside_root(tmp_path):
    root = make_root(tmp_path)
    cfg = TransmitterConfig(station={"root": root})
    inside = interstitials.folder(cfg)
    assert inside == root / "interstitials"
    assert interstitials.row_dir(cfg, inside) == "interstitials"
    outside = tmp_path / "elsewhere"
    cfg2 = TransmitterConfig(station={"root": root}, interstitials={"dir": outside})
    assert interstitials.folder(cfg2) == outside
    assert interstitials.row_dir(cfg2, outside) == str(outside)
    assert root / interstitials.row_dir(cfg2, outside) == outside
    assert interstitials.folder(TransmitterConfig()) is None


def test_interstitials_folder_is_invisible_to_the_package_scan(tmp_path):
    root = make_root(tmp_path)
    build_package(root)
    _clip(root / "interstitials", "id-a.mp3")
    shows, skipped = station.scan(root, now_s=time.time(), quiet_s=0)
    assert [s.slug for s in shows] == ["band-2005-11-01"] and skipped == []


def test_oserror_on_one_file_skips_only_that_file(tmp_path, monkeypatch):
    _clip(tmp_path, "id-a.mp3")
    _clip(tmp_path, "id-b.mp3")
    real = os.stat

    def flaky(path, *a, **kw):
        if str(path).endswith("id-a.mp3"):
            raise OSError("gone")
        return real(path, *a, **kw)

    monkeypatch.setattr(os, "stat", flaky)
    assert [s.slug for s in interstitials.scan(tmp_path, now_s=time.time(), quiet_s=0)] == ["id-b"]


def test_a_directory_named_like_a_clip_is_skipped(tmp_path):
    (tmp_path / "id-x.mp3").mkdir()
    _clip(tmp_path, "id-y.mp3")
    assert [s.slug for s in interstitials.scan(tmp_path, now_s=time.time(), quiet_s=0)] == ["id-y"]


def test_relative_interstitials_dir_is_a_config_error():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="absolute"):
        TransmitterConfig(interstitials={"dir": "relative/dir"})
