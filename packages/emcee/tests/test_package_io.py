"""Tests for emcee.package_io: package read/validate + atomic manifest
rewrite. The `rewrite_manifest` tests are the "json" briefing-alias
regression test called out in the task brief -- they byte-compare every
manifest key other than `dj_notes`/`dj_audio` before and after a rewrite.
"""

import json

import pytest

from emcee.errors import EmceeError
from emcee.models import DJAudioBlock, ScriptNotes
from emcee.package_io import Package, UnsupportedPackage, atomic_write, rewrite_manifest
from emcee.workspace import atomic_write_text

from tests.helpers import build_package


# --- Package.manifest() ------------------------------------------------


def test_v3_manifest_parses(tmp_path):
    pkg_dir = build_package(tmp_path)
    pkg = Package(pkg_dir)
    manifest = pkg.manifest()
    assert manifest["schema_version"] == 3
    assert manifest["briefing"]["json"] == "briefing.json"
    assert len(manifest["tracks"]) == 5  # 2 + 2 + encore(1), default sets/encore


def test_v2_manifest_raises_unsupported_package(tmp_path):
    pkg_dir = build_package(tmp_path)
    manifest_path = pkg_dir / "manifest.json"
    data = json.loads(manifest_path.read_text())
    data["schema_version"] = 2
    manifest_path.write_text(json.dumps(data))

    pkg = Package(pkg_dir)
    with pytest.raises(UnsupportedPackage) as exc_info:
        pkg.manifest()
    assert "v2" in str(exc_info.value)
    assert "re-deliver from llama" in str(exc_info.value)


def test_missing_manifest_raises_emcee_error(tmp_path):
    pkg_dir = tmp_path / "no-such-package"
    pkg_dir.mkdir()
    pkg = Package(pkg_dir)
    with pytest.raises(EmceeError):
        pkg.manifest()


def test_missing_manifest_is_not_unsupported_package(tmp_path):
    # A missing file is a different failure mode than an old schema version;
    # callers must be able to tell them apart.
    pkg_dir = tmp_path / "no-such-package"
    pkg_dir.mkdir()
    pkg = Package(pkg_dir)
    with pytest.raises(EmceeError) as exc_info:
        pkg.manifest()
    assert not isinstance(exc_info.value, UnsupportedPackage)


def test_briefing_and_briefing_md(tmp_path):
    pkg_dir = build_package(tmp_path)
    pkg = Package(pkg_dir)
    briefing = pkg.briefing()
    assert briefing["narration"] == "full"
    assert "well-loved show" in pkg.briefing_md()


# --- rewrite_manifest ---------------------------------------------------


def test_rewrite_manifest_sets_exactly_the_two_blocks(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=False)
    pkg = Package(pkg_dir)
    before = json.loads(pkg.manifest_path.read_text())
    assert before.get("dj_notes") is None
    assert before.get("dj_audio") is None

    notes = ScriptNotes(
        context="Spring '73", set_intros={"1": "hi", "2": "hi again"}, outro="bye"
    )
    audio = DJAudioBlock(
        set_intros={"1": "dj-audio/set1-intro.mp3", "2": "dj-audio/set2-intro.mp3"},
        outro="dj-audio/99-outro.mp3",
    )
    rewrite_manifest(pkg, dj_notes=notes, dj_audio=audio)

    after = json.loads(pkg.manifest_path.read_text())

    # Every key other than the two blocks is byte-identical -- this is the
    # "json" briefing-alias regression test: a naive round-trip through a
    # pydantic Manifest model would rename briefing.json -> briefing.json_file
    # (or drop it under an unaliased dump), which this catches.
    other_keys = set(before) - {"dj_notes", "dj_audio"}
    assert other_keys == set(after) - {"dj_notes", "dj_audio"}
    for key in other_keys:
        assert after[key] == before[key], f"key {key!r} changed"
    assert before["briefing"] == {
        "file": "briefing.md",
        "json": "briefing.json",
        "narration": "full",
        "vetted": False,
    }
    assert after["briefing"] == before["briefing"]
    assert "json_file" not in after["briefing"]

    assert after["dj_notes"] == notes.model_dump()
    assert after["dj_audio"] == audio.model_dump()


def test_rewrite_manifest_round_trips_none_clearing_blocks(tmp_path):
    pkg_dir = build_package(tmp_path, voiced=True)
    pkg = Package(pkg_dir)
    before = json.loads(pkg.manifest_path.read_text())
    assert before["dj_notes"] is not None
    assert before["dj_audio"] is not None

    rewrite_manifest(pkg, dj_notes=None, dj_audio=None)

    after = json.loads(pkg.manifest_path.read_text())
    assert after["dj_notes"] is None
    assert after["dj_audio"] is None
    other_keys = set(before) - {"dj_notes", "dj_audio"}
    for key in other_keys:
        assert after[key] == before[key], f"key {key!r} changed"


def test_rewrite_manifest_is_atomic_no_partial_file_on_injected_failure(tmp_path, monkeypatch):
    pkg_dir = build_package(tmp_path, voiced=False)
    pkg = Package(pkg_dir)
    original_text = pkg.manifest_path.read_text()

    def boom(_tmp, _path):
        raise RuntimeError("injected failure")

    monkeypatch.setattr("emcee.workspace.os.replace", boom)

    with pytest.raises(RuntimeError):
        rewrite_manifest(
            pkg,
            dj_notes=ScriptNotes(set_intros={"1": "hi"}, outro="bye"),
            dj_audio=None,
        )

    # Original manifest untouched...
    assert pkg.manifest_path.read_text() == original_text
    # ...and no leftover temp file in the package dir.
    leftovers = [p for p in pkg_dir.iterdir() if p.name != "manifest.json" and p.suffix == ".tmp"]
    assert leftovers == []
    assert list(pkg_dir.glob("manifest.json.*.tmp")) == []


# --- atomic_write reuses emcee.workspace --------------------------------


def test_atomic_write_is_workspace_atomic_write_text():
    # package_io.atomic_write must be a thin alias, not a second
    # implementation of the unique-temp + os.replace pattern.
    assert atomic_write is atomic_write_text
