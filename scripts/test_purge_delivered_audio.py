"""Tests for scripts/purge_delivered_audio.py (see test_stitch_m3u.py for the
sys.path idiom)."""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import purge_delivered_audio as pda
from llama.ledger import Ledger
from llama.models import LedgerEntry
from llama.workspace import ShowWorkspace, write_artifact

AUDIO = "01 - Song.mp3"


def make_show(root: Path, slug: str, pid: str, *, delivered_to: Path | None,
              in_ledger: bool = True) -> ShowWorkspace:
    ws = ShowWorkspace(root / "shows" / slug)
    write_artifact(ws.package_dir / "manifest.json", {
        "source": {"performance_id": pid},
        "tracks": [{"index": 1, "filename": AUDIO}]})
    write_artifact(ws.package_dir / "audio" / AUDIO, "abc")
    if delivered_to is not None:
        shutil.copytree(ws.package_dir, delivered_to / slug)
    if in_ledger:
        Ledger(root / "ledger.jsonl").record(LedgerEntry(
            performance_id=pid, artist="A", date="1973-06-10", status="delivered",
            run="r", recorded_at="2026-10-04T00:00:00+00:00"))
    return ws


def run(root: Path, dest: Path, *extra) -> int:
    cfg = root / "config.toml"
    cfg.write_text(f'root = "{root}"\n')
    return pda.main(["--config", str(cfg), "--dest", str(dest), *extra])


def _setup(tmp_path: Path):
    root, dest = tmp_path / "lib", tmp_path / "station"
    dest.mkdir(parents=True)
    ok = make_show(root, "ok-1973", "A/1973-06-10", delivered_to=dest)
    gone = make_show(root, "gone-1974", "A/1974-06-10", delivered_to=None)
    undelivered = make_show(root, "new-1975", "A/1975-06-10", delivered_to=dest,
                            in_ledger=False)
    return root, dest, ok, gone, undelivered


def _audio(ws: ShowWorkspace) -> bool:
    return (ws.package_dir / "audio" / AUDIO).exists()


def test_dry_run_touches_nothing(tmp_path, capsys):
    root, dest, ok, gone, undelivered = _setup(tmp_path)
    assert run(root, dest) == 0
    out = capsys.readouterr().out
    assert _audio(ok) and _audio(gone) and _audio(undelivered)
    assert "ok-1973: would purge (3 B)" in out
    assert f"gone-1974: kept ({AUDIO} missing at destination)" in out
    assert "new-1975" not in out
    assert "would free 3 B across 1 show(s)" in out
    assert "dry run: pass --apply to delete" in out


def test_apply_purges_only_verified_delivered_shows(tmp_path, capsys):
    root, dest, ok, gone, undelivered = _setup(tmp_path)
    assert run(root, dest, "--apply") == 0
    out = capsys.readouterr().out
    assert not _audio(ok)
    assert _audio(gone) and _audio(undelivered)
    assert (dest / "ok-1973" / "audio" / AUDIO).exists()
    assert "ok-1973: purged (3 B)" in out
    assert "freed 3 B across 1 show(s)" in out


def test_second_apply_counts_already_purged(tmp_path, capsys):
    root, dest, *_ = _setup(tmp_path)
    run(root, dest, "--apply")
    capsys.readouterr()
    assert run(root, dest, "--apply") == 0
    out = capsys.readouterr().out
    assert "ok-1973" not in out
    assert "1 already purged" in out


def test_no_destination_is_an_error(tmp_path, capsys):
    root = tmp_path / "lib"
    root.mkdir()
    cfg = root / "config.toml"
    cfg.write_text(f'root = "{root}"\n')
    assert pda.main(["--config", str(cfg)]) == 2
    assert "no destination" in capsys.readouterr().err
