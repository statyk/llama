"""Tests for emcee.station: scan() over a delivered-packages folder and
readiness() legs on a single package."""

import json

from emcee.package_io import Package
from emcee.station import PackageStatus, readiness, scan

from tests.helpers import build_package


# --- scan -----------------------------------------------------------------


def test_scan_finds_packages_one_level_deep(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=True)
    build_package(tmp_path, slug="show-b", voiced=False)

    statuses = scan(tmp_path)

    assert {s.path.name for s in statuses} == {"show-a", "show-b"}
    assert all(isinstance(s, PackageStatus) for s in statuses)


def test_scan_skips_non_package_dirs_and_stray_files(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=True)
    (tmp_path / "not-a-package").mkdir()
    (tmp_path / "not-a-package" / "readme.txt").write_text("hi")
    (tmp_path / "stray-file.txt").write_text("hi")

    statuses = scan(tmp_path)

    assert {s.path.name for s in statuses} == {"show-a"}


def test_scan_does_not_descend_into_subdirs_of_subdirs(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=True)
    nested_pkg = tmp_path / "not-a-package" / "nested-show"
    build_package(tmp_path / "not-a-package", slug="nested-show", voiced=True)
    assert nested_pkg.exists()

    statuses = scan(tmp_path)

    assert {s.path.name for s in statuses} == {"show-a"}


def test_scan_missing_station_root_returns_empty_list(tmp_path):
    assert scan(tmp_path / "does-not-exist") == []


def test_scan_station_root_that_is_a_file_returns_empty_list(tmp_path):
    f = tmp_path / "not-a-dir"
    f.write_text("hi")
    assert scan(f) == []


def test_scan_reports_v2_package_as_unsupported_with_redeliver_message(tmp_path):
    pkg_dir = build_package(tmp_path, slug="old-show")
    data = json.loads((pkg_dir / "manifest.json").read_text())
    data["schema_version"] = 2
    (pkg_dir / "manifest.json").write_text(json.dumps(data))
    before = (pkg_dir / "manifest.json").read_text()

    statuses = scan(tmp_path)

    assert len(statuses) == 1
    status = statuses[0]
    assert status.state == "unsupported"
    assert any("v2" in r and "re-deliver from llama" in r for r in status.reasons)
    # never modified
    assert (pkg_dir / "manifest.json").read_text() == before


def test_scan_ready_package_reports_ready(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=True)
    statuses = scan(tmp_path)
    assert statuses[0].state == "ready"
    assert statuses[0].reasons == []


def test_scan_unvoiced_package_reports_pending(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=False)
    statuses = scan(tmp_path)
    assert statuses[0].state == "pending"
    assert statuses[0].reasons != []


# --- readiness --------------------------------------------------------


def test_readiness_voiced_fixture_is_ready(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    ok, reasons = readiness(Package(pkg_dir))
    assert ok is True
    assert reasons == []


def test_readiness_unvoiced_fixture_fails_the_three_voice_legs(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=False)
    ok, reasons = readiness(Package(pkg_dir))
    assert ok is False
    assert len(reasons) == 3
    assert any("DJ script" in r for r in reasons)
    assert any("DJ audio" in r for r in reasons)
    assert any("broadcast.m3u" in r for r in reasons)
    # the audio-files leg must NOT fail -- build_package always stubs the
    # track audio, voiced or not
    assert not any("audio file" in r for r in reasons)


def test_readiness_missing_dj_notes_md_fails_script_leg_even_with_block(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    (pkg_dir / "dj-notes.md").unlink()
    ok, reasons = readiness(Package(pkg_dir))
    assert ok is False
    assert any("DJ script" in r for r in reasons)


def test_readiness_missing_dj_audio_clip_fails_only_that_leg(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    (pkg_dir / "dj-audio" / "set1-intro.mp3").unlink()
    ok, reasons = readiness(Package(pkg_dir))
    assert ok is False
    assert len(reasons) == 1
    assert "DJ audio clip" in reasons[0]
    assert "set1-intro.mp3" in reasons[0]


def test_readiness_missing_broadcast_m3u_fails_only_that_leg(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    (pkg_dir / "broadcast.m3u").unlink()
    ok, reasons = readiness(Package(pkg_dir))
    assert ok is False
    assert reasons == ["no broadcast.m3u"]


def test_readiness_missing_music_file_fails_only_the_audio_leg(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    manifest = json.loads((pkg_dir / "manifest.json").read_text())
    first_filename = manifest["tracks"][0]["filename"]
    (pkg_dir / "audio" / first_filename).unlink()

    ok, reasons = readiness(Package(pkg_dir))

    assert ok is False
    assert len(reasons) == 1
    assert "audio file" in reasons[0]
    assert first_filename in reasons[0]


def test_readiness_narration_vague_does_not_affect_readiness_legs(tmp_path):
    # narration is a scriptwriting concern (Task 7), not a readiness leg.
    pkg_dir = build_package(tmp_path, voiced=True, narration="vague")
    ok, reasons = readiness(Package(pkg_dir))
    assert ok is True
    assert reasons == []
