"""Tests for emcee.station: scan() over a delivered-packages folder and
readiness() legs on a single package."""

import json
from collections import Counter

import pytest

from emcee import station
from emcee.cli import _scan_broad
from emcee.config import EmceeConfig
from emcee.package_io import Package
from emcee.station import PackageStatus, readiness, scan

from tests.helpers import build_package, no_moves


# --- scan -----------------------------------------------------------------


def test_scan_finds_packages_one_level_deep(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=True)
    build_package(tmp_path, slug="show-b", voiced=False)

    statuses = scan(tmp_path, EmceeConfig(), no_moves())

    assert {s.path.name for s in statuses} == {"show-a", "show-b"}
    assert all(isinstance(s, PackageStatus) for s in statuses)


def test_scan_skips_non_package_dirs_and_stray_files(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=True)
    (tmp_path / "not-a-package").mkdir()
    (tmp_path / "not-a-package" / "readme.txt").write_text("hi")
    (tmp_path / "stray-file.txt").write_text("hi")

    statuses = scan(tmp_path, EmceeConfig(), no_moves())

    assert {s.path.name for s in statuses} == {"show-a"}


def test_scan_does_not_descend_into_subdirs_of_subdirs(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=True)
    nested_pkg = tmp_path / "not-a-package" / "nested-show"
    build_package(tmp_path / "not-a-package", slug="nested-show", voiced=True)
    assert nested_pkg.exists()

    statuses = scan(tmp_path, EmceeConfig(), no_moves())

    assert {s.path.name for s in statuses} == {"show-a"}


def test_scan_missing_station_root_returns_empty_list(tmp_path):
    assert scan(tmp_path / "does-not-exist", EmceeConfig(), no_moves()) == []


def test_scan_station_root_that_is_a_file_returns_empty_list(tmp_path):
    f = tmp_path / "not-a-dir"
    f.write_text("hi")
    assert scan(f, EmceeConfig(), no_moves()) == []


def test_scan_reports_v2_package_as_unsupported_with_redeliver_message(tmp_path):
    pkg_dir = build_package(tmp_path, slug="old-show")
    data = json.loads((pkg_dir / "manifest.json").read_text())
    data["schema_version"] = 2
    (pkg_dir / "manifest.json").write_text(json.dumps(data))
    before = (pkg_dir / "manifest.json").read_text()

    statuses = scan(tmp_path, EmceeConfig(), no_moves())

    assert len(statuses) == 1
    status = statuses[0]
    assert status.state == "unsupported"
    assert any("v2" in r and "re-deliver from llama" in r for r in status.reasons)
    # never modified
    assert (pkg_dir / "manifest.json").read_text() == before


def test_scan_ready_package_reports_ready(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=True)
    statuses = scan(tmp_path, EmceeConfig(), no_moves())
    assert statuses[0].state == "ready"
    assert statuses[0].reasons == []


def test_scan_unvoiced_package_reports_pending(tmp_path):
    build_package(tmp_path, slug="show-a", voiced=False)
    statuses = scan(tmp_path, EmceeConfig(), no_moves())
    assert statuses[0].state == "pending"
    assert statuses[0].reasons != []


# --- readiness --------------------------------------------------------


def test_readiness_voiced_fixture_is_ready(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    ok, reasons = readiness(Package(pkg_dir), EmceeConfig(), no_moves())
    assert ok is True
    assert reasons == []


def test_readiness_unvoiced_fixture_fails_the_three_voice_legs(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=False)
    ok, reasons = readiness(Package(pkg_dir), EmceeConfig(), no_moves())
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
    ok, reasons = readiness(Package(pkg_dir), EmceeConfig(), no_moves())
    assert ok is False
    assert any("DJ script" in r for r in reasons)


def test_readiness_missing_dj_audio_clip_fails_only_that_leg(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    (pkg_dir / "dj-audio" / "set1-intro.mp3").unlink()
    ok, reasons = readiness(Package(pkg_dir), EmceeConfig(), no_moves())
    assert ok is False
    assert len(reasons) == 1
    assert "DJ audio clip" in reasons[0]
    assert "set1-intro.mp3" in reasons[0]


def test_readiness_missing_broadcast_m3u_fails_only_that_leg(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    (pkg_dir / "broadcast.m3u").unlink()
    ok, reasons = readiness(Package(pkg_dir), EmceeConfig(), no_moves())
    assert ok is False
    assert reasons == ["no broadcast.m3u"]


def test_readiness_missing_music_file_fails_only_the_audio_leg(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    manifest = json.loads((pkg_dir / "manifest.json").read_text())
    first_filename = manifest["tracks"][0]["filename"]
    (pkg_dir / "audio" / first_filename).unlink()

    ok, reasons = readiness(Package(pkg_dir), EmceeConfig(), no_moves())

    assert ok is False
    assert len(reasons) == 1
    assert "audio file" in reasons[0]
    assert first_filename in reasons[0]


def test_readiness_narration_vague_does_not_affect_readiness_legs(tmp_path):
    # narration is a scriptwriting concern (Task 7), not a readiness leg.
    pkg_dir = build_package(tmp_path, voiced=True, narration="vague")
    ok, reasons = readiness(Package(pkg_dir), EmceeConfig(), no_moves())
    assert ok is True
    assert reasons == []


def test_scan_populates_profile_for_every_state(tmp_path):
    import json
    from tests.helpers import build_package
    from emcee.station import scan

    build_package(tmp_path, slug="a", profile="dead")
    build_package(tmp_path, slug="b", profile=None)
    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "manifest.json").write_text(json.dumps(
        {"schema_version": 2, "source": {"profile": "old"}}))
    v2n = tmp_path / "v2n"
    v2n.mkdir()
    (v2n / "manifest.json").write_text(json.dumps({"schema_version": 2}))

    got = {s.path.name: s.profile for s in scan(tmp_path, EmceeConfig(), no_moves())}

    assert got == {"a": "dead", "b": None, "v2": "old", "v2n": None}


def test_manifest_voiced_by_four_states():
    from emcee.station import manifest_voiced_by

    assert manifest_voiced_by({"dj_audio": None}) is None
    assert manifest_voiced_by({}) is None
    assert manifest_voiced_by({"dj_audio": {"outro": "x"}}) == "?"
    assert manifest_voiced_by({"dj_audio": {"presenter": None}}) == "house"
    assert manifest_voiced_by({"dj_audio": {"presenter": "casey"}}) == "casey"
    assert manifest_voiced_by("garbage") is None


def test_scan_populates_voiced_by(tmp_path):
    import json

    from emcee.station import scan

    pkg_dir = build_package(tmp_path, slug="v", voiced=True)
    m = json.loads((pkg_dir / "manifest.json").read_text())
    m["dj_audio"]["presenter"] = "casey"
    (pkg_dir / "manifest.json").write_text(json.dumps(m))
    build_package(tmp_path, slug="u", voiced=False)

    by = {s.path.name: s for s in scan(tmp_path, EmceeConfig(), no_moves())}

    assert by["v"].voiced_by == "casey"
    assert by["u"].voiced_by is None


def test_scan_skips_dot_prefixed_dirs_even_with_a_manifest(tmp_path):
    # llama's replace-voiced swap stages `.<slug>.deliver-<hex>` /
    # `.<slug>.old-<hex>` siblings that contain a manifest.json.
    build_package(tmp_path, slug="show-a", voiced=True)
    build_package(tmp_path, slug=".show-a.deliver-abc123", voiced=False)
    build_package(tmp_path, slug=".show-a.old-abc123", voiced=True)

    assert {s.path.name for s in scan(tmp_path, EmceeConfig(), no_moves())} == {"show-a"}


# --- concurrent scan + single manifest read ---------------------------------


def _mixed_station(root):
    build_package(root, slug="a-ready", voiced=True)
    build_package(root, slug="b-pending", voiced=False)
    old = build_package(root, slug="c-old")
    data = json.loads((old / "manifest.json").read_text())
    data["schema_version"] = 2
    (old / "manifest.json").write_text(json.dumps(data))
    build_package(root, slug=".d-swap", voiced=True)
    (root / "e-no-manifest").mkdir()
    (root / "f-file.txt").write_text("x")
    for i in range(20):
        build_package(root, slug=f"g-{i:02d}", voiced=bool(i % 2))


def test_scan_concurrent_matches_sequential_in_order(tmp_path, monkeypatch):
    _mixed_station(tmp_path)
    concurrent = scan(tmp_path, EmceeConfig(), no_moves())
    monkeypatch.setattr(station, "SCAN_WORKERS", 1)
    sequential = scan(tmp_path, EmceeConfig(), no_moves())

    assert concurrent == sequential
    names = [s.path.name for s in concurrent]
    assert names == sorted(names)
    assert names[:3] == ["a-ready", "b-pending", "c-old"]
    assert [s.state for s in concurrent[:3]] == ["ready", "pending", "unsupported"]


def test_scan_reads_each_manifest_once(tmp_path, monkeypatch):
    _mixed_station(tmp_path)
    reads = Counter()
    real = Package.manifest

    def spy(self):
        reads[self.dir.name] += 1
        return real(self)

    monkeypatch.setattr(Package, "manifest", spy)
    scan(tmp_path, EmceeConfig(), no_moves())

    assert reads["a-ready"] == reads["b-pending"] == reads["g-00"] == 1
    assert reads["c-old"] == 1
    assert set(reads.values()) == {1}


def test_scan_worker_exception_propagates(tmp_path):
    _mixed_station(tmp_path)
    bad = build_package(tmp_path, slug="g-10a")
    data = json.loads((bad / "manifest.json").read_text())
    del data["tracks"][0]["filename"]
    (bad / "manifest.json").write_text(json.dumps(data))

    with pytest.raises(KeyError):
        scan(tmp_path, EmceeConfig(), no_moves())


def test_scan_broad_reads_each_manifest_once(tmp_path, monkeypatch):
    # The fallback walk (taken whenever one package makes scan() raise)
    # passes its validated manifest on rather than re-reading it.
    _mixed_station(tmp_path)
    reads = Counter()
    real = Package.manifest

    def spy(self):
        reads[self.dir.name] += 1
        return real(self)

    monkeypatch.setattr(Package, "manifest", spy)
    statuses = _scan_broad(tmp_path, EmceeConfig(), no_moves())

    assert len(statuses) == 23
    assert set(reads.values()) == {1}


# --- awaiting_fix (llama's station mark) --------------------------------


def test_marked_package_is_awaiting_fix(tmp_path):
    from tests.helpers import mark_awaiting_fix
    pkg = build_package(tmp_path, slug="show-a", voiced=True)
    mark_awaiting_fix(pkg)
    st = scan(tmp_path, EmceeConfig(), no_moves())[0]
    assert st.state == station.AWAITING == "awaiting-fix"
    assert st.reasons == ["awaiting fix from llama: changed by the held-backlog fixes: titles"]
    assert st.awaiting_fix == st.reasons[0]


def test_malformed_mark_is_awaiting_fix_without_raising(tmp_path):
    from tests.helpers import mark_awaiting_fix
    pkg = build_package(tmp_path, slug="show-a", voiced=True)
    mark_awaiting_fix(pkg, "yes")
    st = scan(tmp_path, EmceeConfig(), no_moves())[0]
    assert st.state == "awaiting-fix"
    assert st.reasons == ["awaiting fix from llama"]


def test_awaiting_fix_reason_shapes():
    f = station.awaiting_fix_reason
    assert f({}) is None and f({"awaiting_fix": None}) is None and f("x") is None
    for bad in ("yes", ["a"], 3, True, {}, {"reason": ""}, {"reason": 5}):
        assert f({"awaiting_fix": bad}) == "awaiting fix from llama"
    assert f({"awaiting_fix": {"reason": " a \n  b "}}) == "awaiting fix from llama: a b"
    long = f({"awaiting_fix": {"reason": "x" * 500}})
    assert long.startswith("awaiting fix from llama: xxx") and len(long) == len(
        "awaiting fix from llama: ") + 200
