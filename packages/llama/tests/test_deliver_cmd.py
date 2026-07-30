"""`llama deliver` -- the deliver gate (packaged + not held + audio verified,
none of it overridable) and the removal of `--force`/`--allow-unvoiced`/any
deliver-time bypass.

Absorbs the deliver-command rows formerly in test_broadcast_ready.py and
test_cli_commands.py; `catalog.deliver_refusals` itself is unit-tested in
test_deliver_gate.py and is not re-tested here.
"""
from pathlib import Path

from typer.testing import CliRunner

import llama.cli as cli
from llama.ledger import Ledger
from llama.models import Candidate, Provenance, RecordingSummary
from llama.workspace import write_artifact

from helpers import build_ready

runner = CliRunner()


def _cfg(tmp_path: Path) -> str:
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n')
    return str(tmp_path / "config.toml")


def test_ready_show_delivers_and_records_ledger_row(tmp_path: Path):
    build_ready(tmp_path, "gratefuldead-1973-06-10")
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "gratefuldead-1973-06-10", "--dest", str(dest)])
    assert r.exit_code == 0, r.output
    assert (dest / "gratefuldead-1973-06-10" / "manifest.json").exists()
    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    assert entries[0].status == "delivered"
    assert entries[0].performance_id == "GratefulDead/1973-06-10"


def test_deliver_by_name_records_provenance_run(tmp_path: Path):
    ws = build_ready(tmp_path, "gratefuldead-1973-06-10")
    write_artifact(ws.provenance, Provenance(
        performance_id="GratefulDead/1973-06-10", run="myrun", dossier="d",
        candidate=Candidate(performance_id="GratefulDead/1973-06-10",
                            collection="GratefulDead", date="1973-06-10",
                            recordings=[RecordingSummary(identifier="gd73")]),
        processed_at="2026-07-17T00:00:00+00:00"))
    dest = tmp_path / "inbox"
    result = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                     "gratefuldead-1973-06-10", "--dest", str(dest)])
    assert result.exit_code == 0, result.output
    entries = Ledger(tmp_path / "ledger.jsonl").entries()
    assert entries[0].status == "delivered" and entries[0].run == "myrun"


def test_held_show_refused(tmp_path: Path):
    build_ready(tmp_path, "held-1973-06-12", needs_review=True)
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "held-1973-06-12", "--dest", str(dest)])
    assert r.exit_code == 1
    assert "refusing to deliver held-1973-06-12: held for review" in r.output
    assert "resolve it: llama triage held-1973-06-12" in r.output
    assert not dest.exists()


def test_missing_audio_refused(tmp_path: Path):
    build_ready(tmp_path, "broken-1973-06-13", drop_audio=True)
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "broken-1973-06-13", "--dest", str(dest)])
    assert r.exit_code == 1
    assert "refusing to deliver broken-1973-06-13: 1 of 1 audio files missing" in r.output
    assert "re-package: llama redo broken-1973-06-13 --from package" in r.output
    assert not dest.exists()


def test_unpackaged_show_refused(tmp_path: Path):
    ws = build_ready(tmp_path, "bare-1973-06-14")
    (ws.package_dir / "manifest.json").unlink()
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "bare-1973-06-14", "--dest", str(dest)])
    assert r.exit_code == 1
    assert "refusing to deliver bare-1973-06-14: not packaged" in r.output
    assert "re-package: llama redo bare-1973-06-14 --from package" in r.output
    assert not dest.exists()


def test_force_and_allow_unvoiced_options_no_longer_exist(tmp_path: Path):
    build_ready(tmp_path, "held-1973-06-12", needs_review=True)
    dest = tmp_path / "station-inbox"
    for flag in ("--force", "--allow-unvoiced"):
        r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                    "held-1973-06-12", "--dest", str(dest), flag])
        assert r.exit_code != 0, flag
        assert "no such option" in r.output.lower(), (flag, r.output)


def test_voiced_and_broadcast_ready_selectors_are_gone(tmp_path: Path):
    cfg = _cfg(tmp_path)
    for flag in ("--voiced", "--unvoiced", "--broadcast-ready"):
        r = runner.invoke(cli.app, ["--config", cfg, "deliver", flag])
        assert r.exit_code != 0, flag
        assert "no such option" in r.output.lower(), (flag, r.output)


def test_deliver_packaged_selector_ships_only_ready_shows(tmp_path: Path, monkeypatch):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "held-1973-06-11", needs_review=True)
    picked = []
    monkeypatch.setattr(cli, "_deliver_one",
                        lambda config, ledger, e, dest: picked.append(e.slug))
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--packaged", "--yes"])
    assert r.exit_code == 0, r.output
    assert picked == ["ready-1973-06-10"]


def test_deliver_batch_continues_past_oserror(tmp_path, monkeypatch):
    """A per-show OSError (e.g. shutil.copytree hitting disk-full/permissions)
    must be reported as FAILED and not abort the rest of the batch."""
    build_ready(tmp_path, "aready")
    build_ready(tmp_path, "bready")

    def fake_deliver_one(config, ledger, e, dest):
        if e.slug == "aready":
            raise OSError("disk full")
        return Path("/dest") / e.slug

    monkeypatch.setattr(cli, "_deliver_one", fake_deliver_one)
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--packaged", "--yes"])
    assert r.exit_code == 0, r.output
    assert "FAILED aready" in r.output


def test_deliver_rejects_name_and_selector_together(tmp_path: Path):
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "someshow", "--packaged"])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_deliver_batch_excludes_held(tmp_path: Path):
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "held-1973-06-11", needs_review=True)
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--packaged",
                                "--dest", str(dest), "--yes"])
    assert r.exit_code == 0, r.output
    assert (dest / "ready-1973-06-10").exists()
    assert not (dest / "held-1973-06-11").exists()


def test_deliver_batch_excludes_held_via_nonstate_selector(tmp_path: Path):
    """Both shows match `--artist` (no `--state`/`--packaged` involved), so the
    held one can only be dropped by `split_held`'s post-filter, not by the
    `select_shows(states=...)` filter -- and its note is the proof."""
    build_ready(tmp_path, "ready-1973-06-10")
    build_ready(tmp_path, "held-1973-06-11", needs_review=True)
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--artist", "Grateful Dead",
                                "--dest", str(dest), "--yes"])
    assert r.exit_code == 0, r.output
    assert (dest / "ready-1973-06-10").exists()
    assert not (dest / "held-1973-06-11").exists()
    assert "note: 1 held show(s) excluded" in r.output


def test_deliver_by_name_single_refusal_exits_1(tmp_path: Path):
    build_ready(tmp_path, "held-1973-06-12", needs_review=True)
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "held-1973-06-12", "--dest", str(dest)])
    assert r.exit_code == 1
