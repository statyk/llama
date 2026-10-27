"""`llama deliver` -- the deliver gate (packaged + not held + audio verified,
none of it overridable) and the removal of `--force`/`--allow-unvoiced`/any
deliver-time bypass.

Absorbs the deliver-command rows formerly in test_broadcast_ready.py and
test_cli_commands.py; `catalog.deliver_refusals` itself is unit-tested in
test_deliver_gate.py and is not re-tested here.
"""
import json
import shutil
from pathlib import Path

import pytest
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


def test_deliver_purges_library_audio_and_keeps_the_rest(tmp_path: Path):
    ws = build_ready(tmp_path, "gratefuldead-1973-06-10")
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "gratefuldead-1973-06-10", "--dest", str(dest)])
    assert r.exit_code == 0, r.output
    assert list((ws.package_dir / "audio").iterdir()) == []
    assert (ws.package_dir / "manifest.json").exists()
    assert ws.show.exists()
    out = dest / "gratefuldead-1973-06-10"
    assert (out / "audio" / "01 - Morning Dew.mp3").read_text() == "x"
    assert "library audio purged (1 B freed)" in r.output
    assert Ledger(tmp_path / "ledger.jsonl").entries()[0].status == "delivered"


def test_purge_skip_keeps_library_audio_and_still_delivers(tmp_path: Path, monkeypatch):
    import llama.catalog as catalog

    ws = build_ready(tmp_path, "gratefuldead-1973-06-10")
    monkeypatch.setattr(catalog, "purge_package_audio",
                        lambda ws, out: catalog.PurgeResult(skipped="nope"))
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "gratefuldead-1973-06-10", "--dest", str(dest)])
    assert r.exit_code == 0, r.output
    assert ("warning: kept library audio for gratefuldead-1973-06-10: nope"
            in r.output)
    assert (ws.package_dir / "audio" / "01 - Morning Dew.mp3").exists()
    assert "delivered:" in r.output
    assert Ledger(tmp_path / "ledger.jsonl").entries()[0].status == "delivered"


def test_purge_partial_failure_warns_and_still_delivers(tmp_path: Path, monkeypatch):
    import llama.catalog as catalog

    build_ready(tmp_path, "gratefuldead-1973-06-10")
    monkeypatch.setattr(catalog, "purge_package_audio",
                        lambda ws, out: catalog.PurgeResult(freed=5, warning="could not delete z"))
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "gratefuldead-1973-06-10", "--dest", str(dest)])
    assert r.exit_code == 0, r.output
    assert ("warning: library audio for gratefuldead-1973-06-10 partly purged: "
            "could not delete z") in r.output


def test_redelivering_a_purged_show_points_at_redo(tmp_path: Path):
    build_ready(tmp_path, "gratefuldead-1973-06-10")
    dest = tmp_path / "station-inbox"
    args = ["--config", _cfg(tmp_path), "deliver", "gratefuldead-1973-06-10",
            "--dest", str(dest)]
    assert runner.invoke(cli.app, args).exit_code == 0
    r = runner.invoke(cli.app, args)
    assert r.exit_code == 1
    assert "1 of 1 audio files missing" in r.output
    assert "re-package: llama redo gratefuldead-1973-06-10 --from package" in r.output


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
                        lambda config, ledger, e, dest, replace_voiced=False: picked.append(e.slug))
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--packaged", "--yes"])
    assert r.exit_code == 0, r.output
    assert picked == ["ready-1973-06-10"]


def _stamp_profile(ws, slug: str, profile: str | None) -> None:
    write_artifact(ws.provenance, Provenance(
        performance_id=f"P/{slug}", run="r", profile=profile, dossier="d",
        candidate=Candidate(performance_id=f"P/{slug}", collection="P",
                            date="1973-06-10",
                            recordings=[RecordingSummary(identifier="gd73")]),
        processed_at="2026-07-17T00:00:00+00:00"))


def test_deliver_packaged_profile_selector_ships_only_that_profile(tmp_path: Path, monkeypatch):
    for slug, profile in (("funk-1973-06-10", "funk"), ("funky-1973-06-11", "funky"),
                          ("oneoff-1973-06-12", None)):
        _stamp_profile(build_ready(tmp_path, slug), slug, profile)
    picked = []
    monkeypatch.setattr(cli, "_deliver_one",
                        lambda config, ledger, e, dest, replace_voiced=False: picked.append(e.slug))
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--packaged",
                                "--profile", "funk", "--yes"])
    assert r.exit_code == 0, r.output
    assert picked == ["funk-1973-06-10"]


def test_deliver_profile_alone_is_a_selector(tmp_path: Path, monkeypatch):
    _stamp_profile(build_ready(tmp_path, "funk-1973-06-10"), "funk-1973-06-10", "funk")
    picked = []
    monkeypatch.setattr(cli, "_deliver_one",
                        lambda config, ledger, e, dest, replace_voiced=False: picked.append(e.slug))
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--profile", "funk", "--yes"])
    assert r.exit_code == 0, r.output
    assert picked == ["funk-1973-06-10"]


def test_deliver_rejects_name_and_profile_together(tmp_path: Path):
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "someshow",
                                "--profile", "funk"])
    assert r.exit_code != 0
    assert "not both" in r.output.lower()


def test_deliver_batch_continues_past_oserror(tmp_path, monkeypatch):
    """A per-show OSError (e.g. shutil.copytree hitting disk-full/permissions)
    must be reported as FAILED and not abort the rest of the batch."""
    build_ready(tmp_path, "aready")
    build_ready(tmp_path, "bready")

    def fake_deliver_one(config, ledger, e, dest, replace_voiced=False):
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


# --- re-delivery over an emcee-voiced destination --------------------------

SLUG = "gratefuldead-1973-06-10"


def _voice_destination(out: Path) -> None:
    """Fake what emcee leaves behind in a delivered package."""
    m = json.loads((out / "manifest.json").read_text())
    m["dj_notes"] = {"file": "dj-notes.md"}
    m["dj_audio"] = {"dir": "dj-audio"}
    (out / "manifest.json").write_text(json.dumps(m))
    (out / "dj-notes.md").write_text("script")
    (out / "dj-audio").mkdir()
    (out / "dj-audio" / "intro.mp3").write_bytes(b"voice")
    (out / "broadcast.m3u").write_text("#EXTM3U\n")


def _repackaged(tmp_path: Path, slug: str = SLUG) -> None:
    """Deliver purges the library audio; re-delivering first needs a
    `redo --from package` to re-fetch it. Stand in for that re-fetch."""
    audio = tmp_path / "shows" / slug / "package" / "audio" / "01 - Morning Dew.mp3"
    assert not audio.exists()
    audio.write_text("x")


def _tree(root: Path) -> dict:
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


def _deliver(tmp_path, dest, *extra, name=SLUG):
    return runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", name,
                                   "--dest", str(dest), *extra])


def _delivered_voiced(tmp_path):
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    _voice_destination(dest / SLUG)
    _repackaged(tmp_path)
    return dest, dest / SLUG


def test_redeliver_over_voiced_is_refused_and_changes_nothing(tmp_path: Path):
    dest, out = _delivered_voiced(tmp_path)
    before = _tree(dest)
    (tmp_path / "ledger.jsonl").unlink()   # append-once: clear so a new row is visible

    r = _deliver(tmp_path, dest)

    assert r.exit_code == 1
    assert "audio files missing" not in r.output
    assert (f"refusing to deliver {SLUG}: {out} is already voiced by emcee; "
            "re-delivering would un-voice it (pass --replace-voiced to replace "
            "it with a fresh, unvoiced copy)") in " ".join(r.output.split())
    assert _tree(dest) == before
    assert Ledger(tmp_path / "ledger.jsonl").entries() == []


def test_replace_voiced_swaps_in_a_fresh_unvoiced_copy(tmp_path: Path):
    dest, out = _delivered_voiced(tmp_path)
    (tmp_path / "ledger.jsonl").unlink()   # append-once: clear so a new row is visible

    r = _deliver(tmp_path, dest, "--replace-voiced")

    assert r.exit_code == 0, r.output
    m = json.loads((out / "manifest.json").read_text())
    assert m.get("dj_notes") is None and m.get("dj_audio") is None
    assert not (out / "dj-audio").exists()
    assert not (out / "dj-notes.md").exists()
    assert not (out / "broadcast.m3u").exists()
    assert [p.name for p in dest.iterdir()] == [SLUG]   # no leftover dot dirs
    assert len(Ledger(tmp_path / "ledger.jsonl").entries()) == 1


def test_unvoiced_existing_destination_still_overlays(tmp_path: Path):
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    (dest / SLUG / "extra.txt").write_text("keep me")

    _repackaged(tmp_path)
    r = _deliver(tmp_path, dest)            # no flag
    _repackaged(tmp_path)
    r2 = _deliver(tmp_path, dest, "--replace-voiced")   # flag, still unvoiced

    assert r.exit_code == 0 and r2.exit_code == 0
    assert (dest / SLUG / "extra.txt").read_text() == "keep me"


def test_batch_refusal_of_voiced_show_continues_with_the_rest(tmp_path: Path):
    build_ready(tmp_path, "aready-1973-06-10")
    build_ready(tmp_path, "bready-1973-06-11")
    dest = tmp_path / "inbox"
    cfg = _cfg(tmp_path)
    assert runner.invoke(cli.app, ["--config", cfg, "deliver", "aready-1973-06-10",
                                   "--dest", str(dest)]).exit_code == 0
    _voice_destination(dest / "aready-1973-06-10")
    _repackaged(tmp_path, "aready-1973-06-10")

    r = runner.invoke(cli.app, ["--config", cfg, "deliver", "--state", "packaged",
                                "--state", "delivered", "--yes", "--dest", str(dest)])

    assert r.exit_code == 0, r.output
    assert "is already voiced by emcee" in r.output
    assert "audio files missing" not in r.output
    assert "delivered:" in r.output and "bready-1973-06-11" in r.output
    assert (dest / "aready-1973-06-10" / "dj-audio").exists()   # untouched
    assert (dest / "bready-1973-06-11" / "manifest.json").exists()


def test_replace_voiced_copy_failure_leaves_destination_and_no_temp(
        tmp_path: Path, monkeypatch):
    dest, out = _delivered_voiced(tmp_path)
    before = _tree(dest)
    real = shutil.copytree

    def boom(src, dst, *a, **k):
        real(src, dst)                      # a partial temp copy exists...
        (Path(dst) / "partial.bin").write_bytes(b"x")
        raise OSError("disk full")          # ...then the copy dies

    monkeypatch.setattr(shutil, "copytree", boom)
    r = _deliver(tmp_path, dest, "--replace-voiced")

    assert r.exit_code != 0
    assert isinstance(r.exception, OSError), r.output   # the swap failed, not the gate
    monkeypatch.undo()
    assert not [p for p in dest.iterdir() if ".deliver-" in p.name]
    assert _tree(dest) == before


def test_replace_voiced_rename_aside_failure_leaks_no_temp(tmp_path: Path, monkeypatch):
    dest, out = _delivered_voiced(tmp_path)
    before = _tree(dest)
    real = Path.rename

    def fake(self, target):
        if self == out:
            raise OSError("rename aside failed")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", fake)
    r = _deliver(tmp_path, dest, "--replace-voiced")

    assert r.exit_code != 0
    assert isinstance(r.exception, OSError), r.output   # the swap failed, not the gate
    monkeypatch.undo()
    assert [p.name for p in dest.iterdir()] == [SLUG]
    assert _tree(dest) == before


def test_replace_voiced_rename_in_failure_restores_original(tmp_path: Path, monkeypatch):
    dest, out = _delivered_voiced(tmp_path)
    before = _tree(dest)
    real = Path.rename

    def fake(self, target):
        if ".deliver-" in self.name and target == out:
            raise OSError("rename in failed")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", fake)
    r = _deliver(tmp_path, dest, "--replace-voiced")

    assert r.exit_code != 0
    assert isinstance(r.exception, OSError), r.output   # the swap failed, not the gate
    monkeypatch.undo()
    assert [p.name for p in dest.iterdir()] == [SLUG]
    assert _tree(dest) == before


def test_stale_deliver_sibling_is_swept_and_old_sibling_kept_with_warning(tmp_path: Path):
    dest, out = _delivered_voiced(tmp_path)
    stale = dest / f".{SLUG}.deliver-deadbeef"
    stale.mkdir()
    (stale / "manifest.json").write_text("{}")
    old = dest / f".{SLUG}.old-cafe"
    old.mkdir()
    (old / "dj.mp3").write_bytes(b"voiced")

    r = _deliver(tmp_path, dest, "--replace-voiced")

    assert r.exit_code == 0, r.output
    assert not stale.exists()
    assert (old / "dj.mp3").read_bytes() == b"voiced"
    assert (f"warning: leftover {old} from an interrupted replace; it may hold "
            "voiced audio") in " ".join(r.output.split())


def _batch_voiced(tmp_path):
    build_ready(tmp_path, "aready-1973-06-10")
    build_ready(tmp_path, "bready-1973-06-11")
    dest = tmp_path / "inbox"
    cfg = _cfg(tmp_path)
    assert runner.invoke(cli.app, ["--config", cfg, "deliver", "--packaged", "--yes",
                                   "--dest", str(dest)]).exit_code == 0
    _voice_destination(dest / "aready-1973-06-10")
    for slug in ("aready-1973-06-10", "bready-1973-06-11"):
        _repackaged(tmp_path, slug)
    return cfg, dest


def test_batch_replace_voiced_is_refused_and_a_single_name_replaces(tmp_path: Path):
    """Spec 5.5: a batch with --replace-voiced is refused outright (nothing
    delivered, the voiced copy untouched); the voiced show is replaced by a
    single-name invocation instead."""
    cfg, dest = _batch_voiced(tmp_path)
    before = tree_bytes(dest)

    r = runner.invoke(cli.app, ["--config", cfg, "deliver", "--state", "packaged",
                                "--state", "delivered", "--replace-voiced", "--yes",
                                "--dest", str(dest)])

    assert r.exit_code == 1, r.output
    assert SELECTOR_REFUSAL in r.output
    assert "(voiced:" not in r.output and "delivered:" not in r.output
    assert tree_bytes(dest) == before

    r = runner.invoke(cli.app, ["--config", cfg, "deliver", "aready-1973-06-10",
                                "--replace-voiced", "--dest", str(dest)])

    assert r.exit_code == 0, r.output
    assert not (dest / "aready-1973-06-10" / "dj-audio").exists()
    m = json.loads((dest / "aready-1973-06-10" / "manifest.json").read_text())
    assert m.get("dj_audio") is None


def test_batch_without_flag_notes_how_many_will_be_refused(tmp_path: Path):
    cfg, dest = _batch_voiced(tmp_path)

    r = runner.invoke(cli.app, ["--config", cfg, "deliver", "--state", "packaged",
                                "--state", "delivered", "--yes", "--dest", str(dest)])

    assert ("note: 1 destination(s) already voiced by emcee will be refused "
            "(re-deliver each by name with --replace-voiced)") in r.output
    assert "(voiced:" not in r.output
    assert (dest / "aready-1973-06-10" / "dj-audio").exists()


def test_batch_voiced_refusal_names_the_single_name_route(tmp_path: Path):
    """FW2 item 6 (Task 16 Minor 6): inside a batch, where --replace-voiced is refused,
    the per-show refusal names the by-name re-delivery, never `pass --replace-voiced`.
    The single-name text is unchanged (test_redeliver_over_voiced_is_refused_...)."""
    cfg, dest = _batch_voiced(tmp_path)
    out = dest / "aready-1973-06-10"

    r = runner.invoke(cli.app, ["--config", cfg, "deliver", "--state", "packaged",
                                "--state", "delivered", "--yes", "--dest", str(dest)])

    text = " ".join(r.output.split())
    assert r.exit_code == 0, r.output
    assert (f"refusing to deliver aready-1973-06-10: {out} is already voiced by emcee; "
            "re-delivering would un-voice it (re-deliver it by name with "
            "--replace-voiced to replace it with a fresh, unvoiced copy)") in text
    assert "(pass --replace-voiced" not in text
    assert (dest / "aready-1973-06-10" / "dj-audio").exists()   # untouched
    assert "delivered:" in r.output and "bready-1973-06-11" in r.output


def test_purged_show_with_voiced_destination_names_voicing_first(tmp_path: Path):
    """Without --replace-voiced a re-delivery over a voiced copy is refused
    anyway, so pointing the operator at a full re-download first would cost a
    download only to be refused afterwards."""
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    _voice_destination(dest / SLUG)

    r = _deliver(tmp_path, dest)

    assert r.exit_code == 1
    assert "is already voiced by emcee" in " ".join(r.output.split())
    assert "audio files missing" not in r.output


def test_purged_show_with_replace_voiced_still_needs_its_audio(tmp_path: Path):
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    _voice_destination(dest / SLUG)

    r = _deliver(tmp_path, dest, "--replace-voiced")

    assert r.exit_code == 1
    assert "1 of 1 audio files missing" in r.output
    assert (dest / SLUG / "dj-audio").exists()


# --- Task 16 (spec 5.5): --replace-voiced takes one name; unreadable
# destinations refuse; a changed track list replaces an unvoiced destination ---

from helpers import tree_bytes  # noqa: E402

SELECTOR_REFUSAL = "--replace-voiced takes one named show, never a selector"


@pytest.mark.parametrize("selector", [["--held"], ["--packaged"], ["--state", "packaged"],
                                      ["--artist", "X"], ["--run", "R"], ["--profile", "P"],
                                      # two that match the voiced show, which today's code replaces
                                      ["--state", "delivered"], ["--artist", "Grateful Dead"]])
def test_replace_voiced_with_any_selector_refuses(tmp_path: Path, selector):
    dest, out = _delivered_voiced(tmp_path)
    before = tree_bytes(dest)
    ledger_before = (tmp_path / "ledger.jsonl").read_bytes()

    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", *selector,
                                "--replace-voiced", "--yes", "--dest", str(dest)])

    assert r.exit_code == 1, r.output
    assert SELECTOR_REFUSAL in r.output
    assert "show(s) to deliver" not in r.output
    assert tree_bytes(dest) == before
    assert (out / "dj-audio" / "intro.mp3").read_bytes() == b"voice"
    assert (tmp_path / "ledger.jsonl").read_bytes() == ledger_before


def test_replace_voiced_selector_refusal_comes_before_setup(tmp_path: Path, monkeypatch):
    def boom():
        raise AssertionError("_setup reached")
    monkeypatch.setattr(cli, "_setup", boom)
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--packaged",
                                "--replace-voiced"])
    assert r.exit_code == 1, r.output
    assert SELECTOR_REFUSAL in r.output


def test_replace_voiced_single_name_still_replaces(tmp_path: Path):
    """(pin) A single named show with --replace-voiced is unchanged."""
    dest, out = _delivered_voiced(tmp_path)
    r = _deliver(tmp_path, dest, "--replace-voiced")
    assert r.exit_code == 0, r.output
    m = json.loads((out / "manifest.json").read_text())
    assert m.get("dj_audio") is None
    assert not (out / "dj-audio").exists()
    assert [p.name for p in dest.iterdir()] == [SLUG]


def _make_unreadable(out: Path, how: str) -> None:
    mf = out / "manifest.json"
    if how == "invalid json":
        mf.write_text("{not json")
    elif how == "json list":
        mf.write_text("[1, 2]")
    elif how == "permission":
        mf.chmod(0)
    else:
        raise AssertionError(how)


@pytest.mark.parametrize("how", ["invalid json", "json list", "permission"])
def test_unreadable_destination_manifest_refuses_the_show(tmp_path: Path, how):
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    out = dest / SLUG
    _repackaged(tmp_path)
    (tmp_path / "ledger.jsonl").unlink()   # append-once: clear so a new row is visible
    _make_unreadable(out, how)
    if how == "permission":
        try:
            (out / "manifest.json").read_text()
        except PermissionError:
            pass
        else:
            pytest.skip("running as a user that ignores file permissions")
    try:
        before = tree_bytes(dest) if how != "permission" else None
        lib_audio = tmp_path / "shows" / SLUG / "package" / "audio" / "01 - Morning Dew.mp3"

        for extra in ([], ["--replace-voiced"]):
            r = _deliver(tmp_path, dest, *extra)
            assert r.exit_code == 1, r.output
            text = " ".join(r.output.split())
            assert (f"refusing to deliver {SLUG}: cannot read {out / 'manifest.json'} (") in text
            assert "); check the station copy by hand" in text
            assert "delivered:" not in r.output
            if before is not None:
                assert tree_bytes(dest) == before
            assert sorted(p.name for p in dest.iterdir()) == [SLUG]   # no swap siblings
            assert lib_audio.read_text() == "x"                       # nothing purged
            assert not (tmp_path / "ledger.jsonl").exists() or \
                Ledger(tmp_path / "ledger.jsonl").entries() == []
    finally:
        (out / "manifest.json").chmod(0o644)


def test_batch_preflight_marks_an_unreadable_destination_and_continues(tmp_path: Path):
    build_ready(tmp_path, "aready-1973-06-10")
    build_ready(tmp_path, "bready-1973-06-11")
    dest = tmp_path / "inbox"
    cfg = _cfg(tmp_path)
    assert runner.invoke(cli.app, ["--config", cfg, "deliver", "aready-1973-06-10",
                                   "--dest", str(dest)]).exit_code == 0
    (dest / "aready-1973-06-10" / "manifest.json").write_text("{not json")
    _repackaged(tmp_path, "aready-1973-06-10")
    before_a = tree_bytes(dest / "aready-1973-06-10")

    r = runner.invoke(cli.app, ["--config", cfg, "deliver", "--state", "packaged",
                                "--state", "delivered", "--yes", "--dest", str(dest)])

    assert r.exit_code == 0, r.output
    lines = {ln.split()[0]: ln for ln in r.output.splitlines() if ln.startswith("  ")
             and ln.split() and ln.split()[0].endswith(("-10", "-11"))}
    assert lines["aready-1973-06-10"] == \
        "  aready-1973-06-10  (refused: destination manifest unreadable)"
    assert lines["bready-1973-06-11"] == "  bready-1973-06-11"
    assert f"delivered: {dest / 'bready-1973-06-11'}" in r.output
    assert f"delivered: {dest / 'aready-1973-06-10'}" not in r.output
    assert tree_bytes(dest / "aready-1973-06-10") == before_a
    assert (tmp_path / "shows" / "aready-1973-06-10" / "package" / "audio"
            / "01 - Morning Dew.mp3").read_text() == "x"
    assert (dest / "bready-1973-06-11" / "manifest.json").exists()


def test_missing_destination_manifest_is_unvoiced(tmp_path: Path):
    """(pin) A destination directory without a manifest is not voiced: the
    copy merges into it as today."""
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    out = dest / SLUG
    out.mkdir(parents=True)
    (out / "extra.txt").write_text("keep me")

    r = _deliver(tmp_path, dest)

    assert r.exit_code == 0, r.output
    assert (out / "manifest.json").exists()
    assert (out / "extra.txt").read_text() == "keep me"
    assert cli._destination_is_voiced(tmp_path / "nowhere") is False
    assert cli._destination_is_voiced(out / "no-such-dir") is False


def _retrack_library(tmp_path: Path, slug: str = SLUG) -> None:
    """Re-package the library show with a changed track list: a restored
    short track ahead of the old one renumbers it."""
    pkg = tmp_path / "shows" / slug / "package"
    m = json.loads((pkg / "manifest.json").read_text())
    m["tracks"] = [{"index": 1, "set": "1", "title": "Intro", "filename": "01 - Intro.mp3"},
                   {"index": 2, "set": "1", "title": "Morning Dew",
                    "filename": "02 - Morning Dew.mp3"}]
    (pkg / "manifest.json").write_text(json.dumps(m))
    for f in (pkg / "audio").iterdir():
        f.unlink()
    (pkg / "audio" / "01 - Intro.mp3").write_text("i")
    (pkg / "audio" / "02 - Morning Dew.mp3").write_text("x")


def test_changed_track_list_replaces_an_unvoiced_destination(tmp_path: Path):
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    out = dest / SLUG
    assert (out / "audio" / "01 - Morning Dew.mp3").exists()
    (out / "extra.txt").write_text("stale")
    _retrack_library(tmp_path)

    r = _deliver(tmp_path, dest)

    assert r.exit_code == 0, r.output
    assert sorted(p.name for p in (out / "audio").iterdir()) == \
        ["01 - Intro.mp3", "02 - Morning Dew.mp3"]
    assert not (out / "audio" / "01 - Morning Dew.mp3").exists()   # the old-numbered copy
    assert not (out / "extra.txt").exists()                         # wholesale, not merged
    m = json.loads((out / "manifest.json").read_text())
    assert [t["filename"] for t in m["tracks"]] == ["01 - Intro.mp3", "02 - Morning Dew.mp3"]
    assert [p.name for p in dest.iterdir()] == [SLUG]               # no swap siblings


def test_changed_track_list_replace_failure_leaves_the_old_destination(
        tmp_path: Path, monkeypatch):
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    out = dest / SLUG
    _retrack_library(tmp_path)
    before = tree_bytes(dest)
    real = Path.rename

    def fake(self, target):
        if ".deliver-" in self.name and target == out:
            raise OSError("rename in failed")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", fake)
    r = _deliver(tmp_path, dest)

    assert r.exit_code != 0
    assert isinstance(r.exception, OSError), r.output
    monkeypatch.undo()
    assert [p.name for p in dest.iterdir()] == [SLUG]
    assert tree_bytes(dest) == before


def test_changed_track_list_copy_failure_leaves_the_old_destination(
        tmp_path: Path, monkeypatch):
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    _retrack_library(tmp_path)
    before = tree_bytes(dest)
    real = shutil.copytree

    def boom(src, dst, *a, **k):
        if k.get("dirs_exist_ok"):
            raise AssertionError("merged copy used for a changed track list")
        real(src, dst)
        raise OSError("disk full")

    monkeypatch.setattr(shutil, "copytree", boom)
    r = _deliver(tmp_path, dest)

    assert r.exit_code != 0
    assert isinstance(r.exception, OSError), r.output
    monkeypatch.undo()
    assert [p.name for p in dest.iterdir()] == [SLUG]
    assert tree_bytes(dest) == before


def test_unchanged_track_list_still_overlays(tmp_path: Path):
    """(pin) Today's overlay for an unvoiced destination with the same track list."""
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    (dest / SLUG / "extra.txt").write_text("keep me")

    _repackaged(tmp_path)
    r = _deliver(tmp_path, dest)

    assert r.exit_code == 0, r.output
    assert (dest / SLUG / "extra.txt").read_text() == "keep me"


def test_voiced_destination_still_refuses_without_the_flag(tmp_path: Path):
    """(pin) A voiced destination refuses without --replace-voiced, even when the
    library's track list changed."""
    dest, out = _delivered_voiced(tmp_path)
    _retrack_library(tmp_path)
    before = tree_bytes(dest)

    r = _deliver(tmp_path, dest)

    assert r.exit_code == 1
    assert "is already voiced by emcee" in " ".join(r.output.split())
    assert tree_bytes(dest) == before


def test_destination_without_a_usable_track_list_is_replaced(tmp_path: Path):
    """An unvoiced destination manifest whose `tracks` is not a list of objects
    cannot be compared: it is replaced wholesale, never merged."""
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    out = dest / SLUG
    (out / "manifest.json").write_text(json.dumps({"dj_audio": None, "tracks": "bogus"}))
    (out / "audio" / "00 - stale.mp3").write_text("old")
    _repackaged(tmp_path)

    r = _deliver(tmp_path, dest)

    assert r.exit_code == 0, r.output
    assert sorted(p.name for p in (out / "audio").iterdir()) == ["01 - Morning Dew.mp3"]


# --- Task 4: awaiting fix (bulk-apply spec, "The library side") ----------------

def _mark(ws, *, start="gather", at="2026-10-26T10:00:00.000000Z",
          reason="changed by the held-backlog fixes: titles"):
    from llama import campaign
    campaign.add_mark(ws, reason=reason, start_stage=start, batch="b1", at=at)


def test_deliver_refuses_awaiting_fix_by_name(tmp_path: Path):
    ws = build_ready(tmp_path, "gratefuldead-1973-06-10")
    _mark(ws)
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "gratefuldead-1973-06-10", "--dest", str(dest)])
    assert r.exit_code == 1
    assert ("refusing to deliver gratefuldead-1973-06-10: awaiting fix (marked "
            "2026-10-26T10:00:00.000000Z: changed by the held-backlog fixes: titles)") in r.output
    assert ("  re-process it first: llama reapply gratefuldead-1973-06-10 "
            "--allow-structure-change") in r.output
    assert not dest.exists()
    assert not (tmp_path / "ledger.jsonl").exists() or not Ledger(tmp_path / "ledger.jsonl").entries()

    ws2 = build_ready(tmp_path, "gratefuldead-1973-06-11")
    _mark(ws2, start="select", reason="recording re-selection: a -> b")
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "gratefuldead-1973-06-11", "--dest", str(dest)])
    assert r.exit_code == 1
    assert "  re-process it first: llama redo gratefuldead-1973-06-11 --from select" in r.output
    assert not dest.exists()


def test_deliver_pointer_names_with_gather_llm_for_a_frozen_show(tmp_path: Path):
    ws = build_ready(tmp_path, "gratefuldead-1973-06-10")
    _mark(ws)
    (tmp_path / "campaign").mkdir()
    froz = tmp_path / "campaign" / "needs-llm-frozen.json"
    froz.write_text(json.dumps({"slugs": ["gratefuldead-1973-06-10"]}))
    args = ["--config", _cfg(tmp_path), "deliver", "gratefuldead-1973-06-10",
            "--dest", str(tmp_path / "in")]
    r = runner.invoke(cli.app, args)
    assert r.exit_code == 1
    assert any(ln.endswith("--allow-structure-change --with-gather-llm")
               for ln in r.output.splitlines())
    froz.write_text("{corrupt")
    r = runner.invoke(cli.app, args)
    assert r.exit_code == 1
    assert "--with-gather-llm" not in r.output
    assert any(ln.endswith("--allow-structure-change") for ln in r.output.splitlines())


def test_deliver_batch_skips_awaiting_fix(tmp_path: Path):
    ws = build_ready(tmp_path, "gratefuldead-1973-06-10")
    build_ready(tmp_path, "gratefuldead-1973-06-11")
    _mark(ws)
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--packaged",
                                "--yes", "--dest", str(dest)])
    assert "  gratefuldead-1973-06-10  (refused: awaiting fix)" in r.output
    assert (dest / "gratefuldead-1973-06-11" / "manifest.json").exists()
    assert not (dest / "gratefuldead-1973-06-10").exists()


def test_batch_deliver_does_not_report_a_show_processed_meanwhile_as_refused(
        tmp_path: Path, monkeypatch):
    from llama import campaign
    ws = build_ready(tmp_path, "gratefuldead-1973-06-10")
    _mark(ws)
    dest = tmp_path / "station-inbox"
    real = cli._confirm_plan

    def confirm_then_process(*a, **k):        # processed between the scan and the lock
        ok = real(*a, **k)
        assert campaign.mark_processed(ws, held=False)
        return ok
    monkeypatch.setattr(cli, "_confirm_plan", confirm_then_process)
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--packaged",
                                "--yes", "--dest", str(dest)])
    assert r.exit_code == 0, r.output
    assert (dest / "gratefuldead-1973-06-10" / "manifest.json").exists()
    assert ("gratefuldead-1973-06-10: processed since the plan was listed; delivering"
            in r.output)
    assert "refusing" not in r.output


def test_processed_show_delivers(tmp_path: Path):
    from llama import campaign
    ws = build_ready(tmp_path, "gratefuldead-1973-06-10")
    _mark(ws)
    assert campaign.mark_processed(ws, held=False)
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "gratefuldead-1973-06-10", "--dest", str(dest)])
    assert r.exit_code == 0, r.output
    assert (dest / "gratefuldead-1973-06-10" / "manifest.json").exists()


def test_unreadable_campaign_record_counts_as_awaiting(tmp_path: Path):
    ws = build_ready(tmp_path, "gratefuldead-1973-06-10")
    ws.campaign.write_text("{not json")
    dest = tmp_path / "station-inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver",
                                "gratefuldead-1973-06-10", "--dest", str(dest)])
    assert r.exit_code == 1
    assert "gratefuldead-1973-06-10: cannot read campaign.json (" in r.output
    assert "); check it by hand" in r.output
    assert not dest.exists()
    s = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "status", "--awaiting-fix"])
    assert s.exit_code == 0, s.output
    assert "gratefuldead-1973-06-10" in s.output and "[awaiting-fix]" in s.output


# --- Task 5: a marked station copy (bulk-apply spec, "It clears by
# re-delivery", the `--replace-voiced` paragraph, "Delivery after the fix") ---

EQUAL_REFUSAL = ("refusing to replace {slug}: the re-processed show equals the voiced "
                 "station copy; keep the voicing with: llama clear-mark {slug}")
LONG_AGO = "2026-01-01T00:00:00.000000Z"


def _station_mark(out: Path) -> None:
    from llama.station_mark import write_mark
    write_mark(out, reason="changed by the held-backlog fixes: titles", marked_at=LONG_AGO)


def _processed(ws) -> None:
    from llama import campaign
    campaign.add_mark(ws, reason="changed by the held-backlog fixes: titles",
                      start_stage="gather", batch="b1", at=LONG_AGO)
    assert campaign.mark_processed(ws, held=False)


def test_marked_destination_is_always_replaced(tmp_path: Path):
    """Same track list, unvoiced, marked: the staged swap runs (never the
    overlay), so the mark goes with a complete copy."""
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    out = dest / SLUG
    _station_mark(out)
    (out / "extra.txt").write_text("an overlay would keep me")
    _repackaged(tmp_path)

    r = _deliver(tmp_path, dest)

    assert r.exit_code == 0, r.output
    m = json.loads((out / "manifest.json").read_text())
    assert "awaiting_fix" not in m
    assert not (out / "extra.txt").exists()
    assert [p.name for p in dest.iterdir()] == [SLUG]       # no .old-* / .deliver-* left
    assert (out / "audio" / "01 - Morning Dew.mp3").read_text() == "x"


def test_replace_voiced_refuses_an_equal_marked_copy(tmp_path: Path):
    dest, out = _delivered_voiced(tmp_path)
    _station_mark(out)
    before = tree_bytes(dest)

    r = _deliver(tmp_path, dest, "--replace-voiced")

    assert r.exit_code == 1
    assert EQUAL_REFUSAL.format(slug=SLUG) in " ".join(r.output.split())
    assert tree_bytes(dest) == before
    assert not (tmp_path / "ledger.jsonl").exists() or len(
        Ledger(tmp_path / "ledger.jsonl").entries()) == 1


def test_replace_voiced_replaces_a_changed_marked_copy(tmp_path: Path):
    """(pin) A marked, voiced copy whose re-processed show differs is replaced
    wholesale by `--replace-voiced`, as today; the mark goes with it."""
    dest, out = _delivered_voiced(tmp_path)
    _station_mark(out)
    _retrack_library(tmp_path)

    r = _deliver(tmp_path, dest, "--replace-voiced")

    assert r.exit_code == 0, r.output
    m = json.loads((out / "manifest.json").read_text())
    assert m.get("awaiting_fix") is None and m.get("dj_audio") is None
    assert [t["filename"] for t in m["tracks"]] == ["01 - Intro.mp3", "02 - Morning Dew.mp3"]
    assert not (out / "dj-audio").exists()
    assert [p.name for p in dest.iterdir()] == [SLUG]


def test_deliver_fixed_selects_marked_and_processed(tmp_path: Path):
    from llama import campaign
    slugs = {k: f"{k}-1973-06-10" for k in ("afixed", "bawait", "cunmarked", "dnorec",
                                            "evoiced")}
    wss = {k: build_ready(tmp_path, s) for k, s in slugs.items()}
    dest = tmp_path / "inbox"
    cfg = _cfg(tmp_path)
    assert runner.invoke(cli.app, ["--config", cfg, "deliver", "--packaged", "--yes",
                                   "--dest", str(dest)]).exit_code == 0
    for k, s in slugs.items():
        _repackaged(tmp_path, s)
        if k != "cunmarked":
            _station_mark(dest / s)
    for k in ("afixed", "cunmarked", "evoiced"):
        _processed(wss[k])
    campaign.add_mark(wss["bawait"], reason="r", start_stage="gather", batch="b1",
                      at="2099-01-01T00:00:00.000000Z")
    _voice_destination(dest / slugs["evoiced"])
    evoiced = dest / slugs["evoiced"] / "manifest.json"
    ev_bytes = evoiced.read_bytes()
    untouched = {k: tree_bytes(dest / slugs[k]) for k in ("bawait", "cunmarked", "dnorec")}

    r = runner.invoke(cli.app, ["--config", cfg, "deliver", "--fixed", "--yes",
                                "--dest", str(dest)])

    listed = [ln.strip() for ln in r.output.splitlines() if ln.startswith("  ")]
    assert "2 show(s) to deliver:" in r.output, r.output
    assert listed[:2] == [slugs["afixed"], slugs["evoiced"]]
    m = json.loads((dest / slugs["afixed"] / "manifest.json").read_text())
    assert "awaiting_fix" not in m
    assert f"delivered: {dest / slugs['afixed']}" in r.output
    text = " ".join(r.output.split())
    assert "is already voiced by emcee" in text and "re-deliver it by name with" in text
    assert evoiced.read_bytes() == ev_bytes
    assert json.loads(ev_bytes)["dj_audio"] == {"dir": "dj-audio"}
    assert json.loads(ev_bytes)["awaiting_fix"]["marked_at"] == LONG_AGO
    for k, before in untouched.items():
        assert tree_bytes(dest / slugs[k]) == before, k


def test_deliver_fixed_combines_with_other_selectors(tmp_path: Path):
    a, b = "aready-1973-06-10", "bready-1973-06-11"
    wa, wb = build_ready(tmp_path, a), build_ready(tmp_path, b)
    dest = tmp_path / "inbox"
    cfg = _cfg(tmp_path)
    assert runner.invoke(cli.app, ["--config", cfg, "deliver", "--packaged", "--yes",
                                   "--dest", str(dest)]).exit_code == 0
    for s, ws in ((a, wa), (b, wb)):
        _repackaged(tmp_path, s)
        _station_mark(dest / s)
        _processed(ws)
    _stamp_profile(wa, a, "dead")
    r = runner.invoke(cli.app, ["--config", cfg, "deliver", "--fixed", "--profile", "dead",
                                "--yes", "--dest", str(dest)])
    assert "1 show(s) to deliver:" in r.output, r.output
    assert "awaiting_fix" not in json.loads((dest / a / "manifest.json").read_text())
    assert "awaiting_fix" in json.loads((dest / b / "manifest.json").read_text())


def test_deliver_fixed_refuses_replace_voiced_and_a_name(tmp_path: Path):
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--fixed",
                                "--replace-voiced"])
    assert r.exit_code == 1
    assert SELECTOR_REFUSAL in r.output
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", SLUG, "--fixed"])
    assert r.exit_code == 1
    assert "give a show OR selectors, not both" in r.output


def test_deliver_fixed_with_no_marked_copy_delivers_nothing(tmp_path: Path):
    build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--fixed", "--yes",
                                "--dest", str(dest)])
    assert r.exit_code == 0, r.output
    assert "no matching shows" in r.output
    assert not dest.exists()


def test_unmarked_voiced_destination_keeps_todays_route(tmp_path: Path):
    """(pin) An unmarked voiced destination: refused without the flag; with
    `--replace-voiced` replaced even though nothing changed (no equality test)."""
    dest, out = _delivered_voiced(tmp_path)
    before = tree_bytes(dest)
    r = _deliver(tmp_path, dest)
    assert r.exit_code == 1
    assert "is already voiced by emcee" in " ".join(r.output.split())
    assert tree_bytes(dest) == before

    r = _deliver(tmp_path, dest, "--replace-voiced")
    assert r.exit_code == 0, r.output
    m = json.loads((out / "manifest.json").read_text())
    assert m.get("dj_audio") is None
    assert not (out / "dj-audio").exists()


def test_deliver_fixed_lists_an_unreadable_station_copy_as_refused(tmp_path: Path):
    """A processed show whose station manifest cannot be read: whether it is marked
    is unknown, so the `--fixed` batch lists it as refused (never drops it silently)
    and writes nothing to it."""
    ws = build_ready(tmp_path, SLUG)
    dest = tmp_path / "inbox"
    assert _deliver(tmp_path, dest).exit_code == 0
    _repackaged(tmp_path)
    _processed(ws)
    (dest / SLUG / "manifest.json").write_text("{not json")
    before = tree_bytes(dest)
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--fixed", "--yes",
                                "--dest", str(dest)])
    assert f"  {SLUG}  (refused: destination manifest unreadable)" in r.output, r.output
    assert "delivered:" not in r.output
    assert tree_bytes(dest) == before


def test_deliver_fixed_needs_a_station(tmp_path: Path):
    build_ready(tmp_path, SLUG)
    r = runner.invoke(cli.app, ["--config", _cfg(tmp_path), "deliver", "--fixed", "--yes"])
    assert r.exit_code == 1
    assert "no --dest given and no delivery_path in config" in r.output
