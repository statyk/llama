"""`dj_audio.voiced_on` / `voiced_before`: when the newest clip was rendered.

A run that really renders a clip stamps today and clears `voiced_before`; a
run that renders nothing carries both unchanged; a failed attempt clears
`dj_audio`, so a retry that renders nothing has nothing to carry (R1).
"""

import json
from pathlib import Path

from herder import FakeProvider
from typer.testing import CliRunner

import emcee.process as process_mod
from emcee.cli import app

from tests.helpers import build_package, notes_json, station_home

runner = CliRunner()


def _manifest(pkg_dir: Path) -> dict:
    return json.loads((pkg_dir / "manifest.json").read_text())


def _write(pkg_dir: Path, manifest: dict) -> None:
    (pkg_dir / "manifest.json").write_text(json.dumps(manifest))


def _voice(pkg_dir: Path, monkeypatch, *args: str) -> None:
    monkeypatch.setattr(process_mod, "provider_for",
                        lambda settings, task: FakeProvider(completes=[notes_json()]))
    result = runner.invoke(app, ["voice", str(pkg_dir), *args])
    assert result.exit_code == 0, result.output


def _voiced(tmp_path, monkeypatch, today="2026-10-01") -> Path:
    _, station = station_home(tmp_path, monkeypatch)
    pkg_dir = build_package(station, slug="showA", voiced=False)
    monkeypatch.setattr(process_mod, "_today", lambda: today)
    _voice(pkg_dir, monkeypatch)
    return pkg_dir


def test_a_render_stamps_today(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch, today="2026-10-01")

    block = _manifest(pkg_dir)["dj_audio"]

    assert block["voiced_on"] == "2026-10-01"
    assert block["voiced_before"] is None


def test_a_render_clears_voiced_before(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    manifest["dj_audio"]["voiced_before"] = "2026-01-01"
    _write(pkg_dir, manifest)
    monkeypatch.setattr(process_mod, "_today", lambda: "2026-11-02")

    _voice(pkg_dir, monkeypatch, "--force")

    block = _manifest(pkg_dir)["dj_audio"]
    assert block["voiced_on"] == "2026-11-02"
    assert block["voiced_before"] is None


def test_a_run_that_renders_nothing_carries_both(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    manifest["dj_audio"]["voiced_on"] = "2026-03-03"
    manifest["dj_audio"]["voiced_before"] = "2026-02-02"
    _write(pkg_dir, manifest)
    monkeypatch.setattr(process_mod, "_today", lambda: "2026-11-02")

    _voice(pkg_dir, monkeypatch, "--keep-script")

    block = _manifest(pkg_dir)["dj_audio"]
    assert block["voiced_on"] == "2026-03-03"
    assert block["voiced_before"] == "2026-02-02"


def test_a_retry_after_a_failed_attempt_that_renders_nothing_has_nothing_to_carry(
        tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    manifest["dj_audio"] = None      # a failed attempt clears dj_audio (R1)
    _write(pkg_dir, manifest)
    monkeypatch.setattr(process_mod, "_today", lambda: "2026-11-02")

    _voice(pkg_dir, monkeypatch, "--keep-script")

    block = _manifest(pkg_dir)["dj_audio"]
    assert block["voiced_on"] is None
    assert block["voiced_before"] is None


def test_status_json_reports_both_fields(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    manifest["dj_audio"]["voiced_before"] = "2026-01-01"
    _write(pkg_dir, manifest)

    row = json.loads(runner.invoke(app, ["status", "--json"]).output)[0]

    assert row["voiced_on"] == "2026-10-01"
    assert row["voiced_before"] == "2026-01-01"


def test_status_json_tolerates_a_legacy_block_and_an_unvoiced_package(tmp_path, monkeypatch):
    _, station = station_home(tmp_path, monkeypatch)
    legacy = build_package(station, slug="legacy", voiced=True)    # voiced, no new keys
    block = _manifest(legacy)["dj_audio"]
    assert "voiced_on" not in block
    build_package(station, slug="unvoiced", voiced=False)

    rows = {r["slug"]: r for r in
            json.loads(runner.invoke(app, ["status", "--json"]).output)}

    for slug in ("legacy", "unvoiced"):
        assert rows[slug]["voiced_on"] is None
        assert rows[slug]["voiced_before"] is None
    assert "voiced_on" not in _manifest(legacy)["dj_audio"]   # status never rewrites it


def test_keep_script_fresh_renders_the_named_clip_so_it_stamps_today(tmp_path, monkeypatch):
    pkg_dir = _voiced(tmp_path, monkeypatch)
    manifest = _manifest(pkg_dir)
    manifest["dj_audio"]["voiced_on"] = "2026-03-03"
    manifest["dj_audio"]["voiced_before"] = "2026-02-02"
    _write(pkg_dir, manifest)
    monkeypatch.setattr(process_mod, "_today", lambda: "2026-11-02")

    _voice(pkg_dir, monkeypatch, "--keep-script", "--fresh", "99-outro")

    block = _manifest(pkg_dir)["dj_audio"]
    assert block["voiced_on"] == "2026-11-02"
    assert block["voiced_before"] is None
