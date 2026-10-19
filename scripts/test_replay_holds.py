"""scripts/replay_holds.py run: offline replay of a fixture library, zero writes
outside the scratch directory, identity check (spec slice 0 acceptance 3)."""
import json
import logging
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "llama" / "tests"))

import replay_holds as rh
from fixture_library import build_library


def _tree_state(root: Path) -> dict[str, tuple[int, int]]:
    return {str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def _read_only(path: Path):
    for p in [path, *path.rglob("*")]:
        p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _writable(path: Path):
    for p in [path, *path.rglob("*")]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)


def test_run_replays_the_library_under_a_read_only_root(tmp_path):
    root = tmp_path / "lib"
    build_library(root)
    before = _tree_state(root)
    _read_only(root)
    try:
        out = tmp_path / "arm.json"
        rc = rh.main(["run", "--out", str(out), "--all", "--config", str(root / "config.toml"),
                      "--scratch", str(tmp_path / "scratch")])
    finally:
        _writable(root)
    assert rc == 0
    assert _tree_state(root) == before
    arm = json.loads(out.read_text())
    assert set(arm) >= {"sha", "config_fingerprint", "setlistfm_configured", "scope", "shows", "llama_file"}
    held = arm["shows"]["gratefuldead-1973-06-10"]
    clean = arm["shows"]["gratefuldead-1973-06-11"]
    assert held["state"] == "held" and held["outcome"] == "clears" and held["reproduces"] is False
    assert clean["state"] == "packaged" and clean["outcome"] == "clean" and clean["reproduces"] is True
    assert set(held["digests"]) == {"show.json", "overrides.json", "provenance.json", "research.md", "vetting.extraction"}


def test_run_default_scope_is_held_only(tmp_path):
    root = tmp_path / "lib"
    build_library(root)
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--config", str(root / "config.toml")]) == 0
    assert list(json.loads(out.read_text())["shows"]) == ["gratefuldead-1973-06-10"]


def test_run_slugs_file_scopes_the_replay(tmp_path):
    root = tmp_path / "lib"
    build_library(root)
    (tmp_path / "slugs").write_text("gratefuldead-1973-06-11\n")
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--slugs", str(tmp_path / "slugs"),
                    "--config", str(root / "config.toml")]) == 0
    assert list(json.loads(out.read_text())["shows"]) == ["gratefuldead-1973-06-11"]


def test_cache_miss_marks_the_show_unreplayable_and_the_run_continues(tmp_path):
    root = tmp_path / "lib"
    shows = build_library(root)
    for p in (root / "cache").glob("md_*.json"):
        p.unlink()
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--all", "--config", str(root / "config.toml")]) == 0
    arm = json.loads(out.read_text())
    assert all(s["outcome"] == "unreplayable" and s["unreplayable"].startswith("cache miss")
               for s in arm["shows"].values())


def test_unreadable_overrides_marks_the_show_unreplayable_and_continues(tmp_path):
    # Review Focus 2.
    root = tmp_path / "lib"
    shows = build_library(root)
    shows["gratefuldead-1973-06-10"].overrides.write_text("[1, 2")
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--all", "--config", str(root / "config.toml")]) == 0
    arm = json.loads(out.read_text())
    assert arm["shows"]["gratefuldead-1973-06-10"]["unreplayable"] == "overrides.json unreadable"
    assert arm["shows"]["gratefuldead-1973-06-11"]["outcome"] == "clean"


def test_run_refuses_when_llama_imports_from_another_tree(tmp_path, monkeypatch, capsys):
    import llama
    monkeypatch.setattr(llama, "__file__", str(tmp_path / "elsewhere" / "llama" / "__init__.py"))
    rc = rh.main(["run", "--out", str(tmp_path / "arm.json"), "--config", str(tmp_path / "nope.toml")])
    assert rc == 2
    assert "refusing to run: llama imports from" in capsys.readouterr().err


def test_run_passes_no_setlistfm_client_when_no_key_is_configured(tmp_path, monkeypatch):
    # prediction/apply parity: the harness half (Task 19 pins the reapply half)
    monkeypatch.delenv("SETLISTFM_API_KEY", raising=False)
    root = tmp_path / "lib"
    build_library(root)
    seen = []
    real = rh.replay_show
    def spy(ws, **kw):
        seen.append(kw["slfm"])
        return real(ws, **kw)
    monkeypatch.setattr(rh, "replay_show", spy)
    assert rh.main(["run", "--out", str(tmp_path / "arm.json"), "--all",
                    "--config", str(root / "config.toml")]) == 0
    assert seen and all(s is None for s in seen)


# --- beyond the brief: the guards that keep the harness off the library ---

def test_run_refuses_a_llama_from_a_worktree_nested_in_this_tree(tmp_path, monkeypatch, capsys):
    # Orchestrator ruling M2: a worktree lives under <repo>/.claude/worktrees/,
    # so "under the repo root" is not enough; it must be this tree's src.
    import llama
    nested = (Path(rh.__file__).resolve().parents[1] / ".claude" / "worktrees" / "other"
              / "packages" / "llama" / "src" / "llama" / "__init__.py")
    monkeypatch.setattr(llama, "__file__", str(nested))
    rc = rh.main(["run", "--out", str(tmp_path / "arm.json"), "--config", str(tmp_path / "x.toml")])
    err = capsys.readouterr().err
    assert rc == 2 and f"llama: {nested}" in err and "refusing to run" in err
    assert not (tmp_path / "arm.json").exists()


def test_run_prints_llama_file_and_records_the_arm_header(tmp_path, monkeypatch, capsys):
    import llama
    monkeypatch.setenv("SETLISTFM_API_KEY", "k")
    root = tmp_path / "lib"
    build_library(root)
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--config", str(root / "config.toml")]) == 0
    err = capsys.readouterr().err
    assert f"llama: {llama.__file__}" in err
    assert "replayed 1 show(s): clears=1" in err
    arm = json.loads(out.read_text())
    assert arm["scope"] == "held" and arm["root"] == str(root)
    assert arm["llama_file"] == llama.__file__ and arm["setlistfm_configured"] is True
    assert arm["generated_at"].endswith("+00:00")
    assert list(arm["shows"]["gratefuldead-1973-06-10"])[:2] == ["slug", "state"]
    assert "date" in arm["shows"]["gratefuldead-1973-06-10"]
    # A configured key: a cache-only client, whose miss on this show is recorded.
    assert arm["shows"]["gratefuldead-1973-06-10"]["slfm_miss"] is True


def test_run_writes_only_the_arm_and_empties_its_scratch(tmp_path):
    root = tmp_path / "lib"
    build_library(root)
    outdir = tmp_path / "out"
    scratch = tmp_path / "scratch"
    assert rh.main(["run", "--out", str(outdir / "arm.json"), "--all",
                    "--config", str(root / "config.toml"), "--scratch", str(scratch)]) == 0
    assert [p.name for p in outdir.iterdir()] == ["arm.json"]
    assert list(scratch.iterdir()) == []


def test_run_default_scratch_is_removed_at_exit(tmp_path, monkeypatch):
    import tempfile
    root = tmp_path / "lib"
    build_library(root)
    made = []
    real = tempfile.mkdtemp
    def mkdtemp(**kw):
        made.append(Path(real(dir=tmp_path, **kw)))
        return str(made[-1])
    monkeypatch.setattr(rh.tempfile, "mkdtemp", mkdtemp)
    assert rh.main(["run", "--out", str(tmp_path / "arm.json"), "--config",
                    str(root / "config.toml")]) == 0
    assert len(made) == 1 and made[0].name.startswith("replay-") and not made[0].exists()


@pytest.mark.parametrize("where", ["root", "shows", "inside", "parent"])
def test_run_refuses_a_scratch_overlapping_the_library(tmp_path, where, capsys):
    root = tmp_path / "lib"
    build_library(root)
    before = _tree_state(root)
    scratch = {"root": root, "shows": root / "shows", "inside": root / "tmp" / "s",
               "parent": tmp_path}[where]
    rc = rh.main(["run", "--out", str(tmp_path / "arm.json"), "--all",
                  "--config", str(root / "config.toml"), "--scratch", str(scratch)])
    assert rc == 2 and "refusing scratch" in capsys.readouterr().err
    assert _tree_state(root) == before and not (root / "tmp").exists()
    assert not (tmp_path / "arm.json").exists()


def test_run_refuses_an_out_file_inside_the_library(tmp_path, capsys):
    root = tmp_path / "lib"
    build_library(root)
    before = _tree_state(root)
    rc = rh.main(["run", "--out", str(root / "arm.json"), "--config", str(root / "config.toml")])
    assert rc == 2 and "refusing --out" in capsys.readouterr().err
    assert _tree_state(root) == before


def test_run_refuses_a_missing_config_file(tmp_path, capsys):
    # load_config falls back to the defaults (root ~/.llama) on a missing
    # file; an explicit --config that is not there must not do that.
    rc = rh.main(["run", "--out", str(tmp_path / "arm.json"), "--config", str(tmp_path / "no.toml")])
    assert rc == 2 and "no such config" in capsys.readouterr().err


def test_slugs_file_missing_slug_is_recorded_and_bad_slugs_refused(tmp_path, capsys):
    root = tmp_path / "lib"
    build_library(root)
    slugs = tmp_path / "slugs"
    slugs.write_text("gratefuldead-1973-06-11\n\n  gone-1999-01-01 \ngratefuldead-1973-06-11\n")
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--slugs", str(slugs),
                    "--config", str(root / "config.toml")]) == 0
    shows = json.loads(out.read_text())["shows"]
    assert list(shows) == ["gone-1999-01-01", "gratefuldead-1973-06-11"]
    assert shows["gone-1999-01-01"]["outcome"] == "unreplayable"
    assert shows["gone-1999-01-01"]["unreplayable"] == "show directory missing"
    for bad in ("../lib", "a/b", ".."):
        slugs.write_text(bad + "\n")
        assert rh.main(["run", "--out", str(out), "--slugs", str(slugs),
                        "--config", str(root / "config.toml")]) == 2
        assert "invalid slug" in capsys.readouterr().err


def test_held_scope_includes_a_show_whose_state_cannot_be_read(tmp_path):
    # Ruling M3: derive_state runs inside the per-show error handling.
    root = tmp_path / "lib"
    shows = build_library(root)
    shows["gratefuldead-1973-06-11"].show.write_text("{broken")
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--config", str(root / "config.toml")]) == 0
    arm = json.loads(out.read_text())["shows"]
    assert arm["gratefuldead-1973-06-11"]["state"] == "unknown"
    assert arm["gratefuldead-1973-06-11"]["unreplayable"].startswith("ValidationError: ")
    assert arm["gratefuldead-1973-06-10"]["outcome"] == "clears"


def test_run_restores_logging_and_reports_progress(tmp_path, monkeypatch, capsys):
    root = tmp_path / "lib"
    build_library(root)
    monkeypatch.setattr(rh, "PROGRESS_EVERY", 1)
    seen = []
    real = rh.replay_show
    def spy(ws, **kw):
        seen.append(logging.root.manager.disable)
        return real(ws, **kw)
    monkeypatch.setattr(rh, "replay_show", spy)
    assert rh.main(["run", "--out", str(tmp_path / "arm.json"), "--all",
                    "--config", str(root / "config.toml")]) == 0
    assert seen == [logging.CRITICAL, logging.CRITICAL]
    assert logging.root.manager.disable == logging.NOTSET
    err = capsys.readouterr().err
    assert "replayed 1/2" in err and "replayed 2/2" in err
