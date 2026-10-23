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


@pytest.fixture(autouse=True)
def _hermetic_default_config(tmp_path_factory, monkeypatch):
    """compare reads the default config for delivery_path: never ~/.llama in a test."""
    monkeypatch.setattr(rh, "DEFAULT_ROOT", tmp_path_factory.mktemp("default-root"))


def _tree_state(root: Path) -> dict[str, tuple]:
    """Every path under `root`: a file by (size, mtime), a directory by its
    mtime, so a created (even empty, or since-deleted) entry is visible."""
    state = {}
    for p in root.rglob("*"):
        st = p.lstat()
        key = str(p.relative_to(root))
        if p.is_dir() and not p.is_symlink():
            state[key] = ("dir", st.st_mtime_ns)
        else:
            state[key] = ("file", st.st_size, st.st_mtime_ns)
    state["."] = ("dir", root.stat().st_mtime_ns)
    return state


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
    # The writable-root half of the zero-writes check: under a read-only root
    # a write whose error is swallowed (SetlistFMClient's never-raise cache
    # write is the codebase's own pattern) just fails and leaves no trace, so
    # only a writable root can show it happened.
    root = tmp_path / "lib"
    build_library(root)
    before = _tree_state(root)
    outdir = tmp_path / "out"
    scratch = tmp_path / "scratch"
    assert rh.main(["run", "--out", str(outdir / "arm.json"), "--all",
                    "--config", str(root / "config.toml"), "--scratch", str(scratch)]) == 0
    assert _tree_state(root) == before
    assert [p.name for p in outdir.iterdir()] == ["arm.json"]
    assert list(scratch.iterdir()) == []
    arm = json.loads((outdir / "arm.json").read_text())
    assert {s["outcome"] for s in arm["shows"].values()} == {"clears", "clean"}


def test_tree_state_sees_an_empty_directory_and_a_deleted_file(tmp_path):
    root = tmp_path / "lib"
    build_library(root)
    before = _tree_state(root)
    (root / "shows" / "new-empty").mkdir()
    assert _tree_state(root) != before
    (root / "shows" / "new-empty").rmdir()
    before = _tree_state(root)
    (root / "cache" / "probe").write_text("x")
    (root / "cache" / "probe").unlink()
    assert _tree_state(root) != before        # the cache dir's mtime moved


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
    try:
        assert rh.main(["run", "--out", str(tmp_path / "arm.json"), "--all",
                        "--config", str(root / "config.toml")]) == 0
        assert seen == [logging.CRITICAL, logging.CRITICAL]
        assert logging.root.manager.disable == logging.NOTSET
    finally:
        logging.disable(logging.NOTSET)   # a failed assertion must not leak the disable
    err = capsys.readouterr().err
    assert "replayed 1/2" in err and "replayed 2/2" in err


def _two_arms(tmp_path, mutate_cand=None, mutate_base=None, held_for_real=True):
    """Both arms from one library and one code tree. By default the held show
    holds for real, so the base arm reproduces it and any "newly cleared"
    comes only from a cand mutation."""
    root = tmp_path / "lib"
    build_library(root, held_for_real=held_for_real)
    base, cand = tmp_path / "base.json", tmp_path / "cand.json"
    cfg = str(root / "config.toml")
    assert rh.main(["run", "--out", str(base), "--all", "--config", cfg]) == 0
    assert rh.main(["run", "--out", str(cand), "--all", "--config", cfg]) == 0
    for path, mutate in ((base, mutate_base), (cand, mutate_cand)):
        if mutate:
            arm = json.loads(path.read_text())
            mutate(arm)
            path.write_text(json.dumps(arm))
    return base, cand


def _clear_it(arm):
    s = arm["shows"]["gratefuldead-1973-06-10"]
    s["gather_flags"], s["vet_flags"], s["outcome"], s["briefing"] = [], [], "clears", "reuse"
    s["notes"] = ["venue differs from jerrybase: archive 'Hall A' vs 'Hall B' (same city)"]


def test_compare_writes_the_report_set_and_the_lists(tmp_path):
    base, cand = _two_arms(tmp_path, _clear_it)
    b = json.loads(base.read_text())["shows"]["gratefuldead-1973-06-10"]
    assert b["outcome"] == "still-held" and b["reproduces"] is True     # a real hold, reproduced
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    for name in ("summary.txt", "drift.txt", "flags.txt", "outcomes.txt", "packaged_exposure.txt",
                 "title_sources.txt", "structure_changed.txt", "hand_check_sample.txt",
                 "closest_calls.txt", "needs_llm.txt", "notes.txt", "briefings.txt",
                 "predicted_list.json", "structure_changed_list.json", "pilot_list.json"):
        assert (out / name).exists(), name
    predicted = json.loads((out / "predicted_list.json").read_text())
    assert [r["slug"] for r in predicted["rows"]] == ["gratefuldead-1973-06-10"]
    assert predicted["sha"] == json.loads(cand.read_text())["sha"]
    assert set(predicted["rows"][0]["digests"]) == {"show.json", "overrides.json", "provenance.json",
                                                     "research.md", "vetting.extraction"}
    assert "research-date: removed 1, added 0" in (out / "flags.txt").read_text()
    assert "gratefuldead-1973-06-10" in (out / "hand_check_sample.txt").read_text()
    assert "slice 1 (1c)" in (out / "closest_calls.txt").read_text()
    assert "Hall A" in (out / "closest_calls.txt").read_text()
    assert "Hall A" in (out / "notes.txt").read_text()
    assert [r["slug"] for r in json.loads((out / "pilot_list.json").read_text())["rows"]] == \
        ["gratefuldead-1973-06-10"]
    summary = (out / "summary.txt").read_text()
    assert "base reproduces 1/1 (held, not needs-LLM)" in summary
    assert "briefing guard reproduces" in summary and "needs-LLM held: base 0, cand 0" in summary


def test_compare_refuses_arms_whose_digests_differ(tmp_path, capsys):
    def touch(arm):
        arm["shows"]["gratefuldead-1973-06-11"]["digests"]["show.json"] = "deadbeef"
    base, cand = _two_arms(tmp_path, touch)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 2
    assert "arms differ" in capsys.readouterr().err
    assert not out.exists()


def test_compare_refuses_arms_whose_config_differs(tmp_path, capsys):
    def other_config(arm):
        arm["config_fingerprint"] = "0" * 64
    base, cand = _two_arms(tmp_path, other_config)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 2
    assert "arms differ" in capsys.readouterr().err
    assert not out.exists()


def test_compare_refuses_a_slug_in_one_arm_only_and_a_setlistfm_difference(tmp_path, capsys):
    def drop(arm):
        del arm["shows"]["gratefuldead-1973-06-11"]
    base, cand = _two_arms(tmp_path, drop)
    assert rh.main(["compare", str(base), str(cand), "--out", str(tmp_path / "c1")]) == 2
    assert "gratefuldead-1973-06-11" in capsys.readouterr().err
    def slfm(arm):
        arm["setlistfm_configured"] = not arm["setlistfm_configured"]
    base, cand = _two_arms(tmp_path, slfm)
    assert rh.main(["compare", str(base), str(cand), "--out", str(tmp_path / "c2")]) == 2
    assert not (tmp_path / "c2").exists()


def test_compare_refuses_a_baseline_that_does_not_reproduce(tmp_path, capsys):
    # the default library's hold is synthetic: the replay does not raise it
    base, cand = _two_arms(tmp_path, held_for_real=False)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 3
    assert "< 99%" in capsys.readouterr().err
    assert (out / "drift.txt").exists()
    assert "gratefuldead-1973-06-10" in (out / "drift.txt").read_text()


def test_compare_refuses_a_low_reproduction_base_with_no_flag_and_writes_no_reports(tmp_path, capsys):
    base, cand = _two_arms(tmp_path, held_for_real=False)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 3
    assert "gate skipped" not in capsys.readouterr().err
    assert not (out / "summary.txt").exists() and not (out / "predicted_list.json").exists()


def test_compare_no_repro_gate_reports_the_ratio_and_writes_everything(tmp_path, capsys):
    base, cand = _two_arms(tmp_path, held_for_real=False)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--no-repro-gate"]) == 0
    assert ("baseline reproduces 0/1 held shows that are not needs-LLM "
            "(gate skipped: --no-repro-gate)") in capsys.readouterr().err
    first = (out / "summary.txt").read_text().splitlines()[0]
    assert first == "base reproduces 0/1 (held, not needs-LLM; gate skipped: --no-repro-gate)"
    for name in rh.OUTPUT_FILES:
        assert (out / name).exists(), name


def test_compare_no_repro_gate_still_refuses_a_moved_library(tmp_path, capsys):
    def touch(arm):
        arm["shows"]["gratefuldead-1973-06-11"]["digests"]["show.json"] = "deadbeef"
    base, cand = _two_arms(tmp_path, touch, held_for_real=False)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--no-repro-gate"]) == 2
    assert "arms differ" in capsys.readouterr().err
    assert not out.exists()


def test_compare_gate_counts_only_held_shows_that_are_not_needs_llm(tmp_path):
    def needs_llm_hold(arm):
        s = arm["shows"]["gratefuldead-1973-06-11"]
        s["state"], s["outcome"], s["reproduces"] = "held", "needs-llm", False
        s["needs_llm"] = ["stored alignment llm"]
    base, cand = _two_arms(tmp_path, mutate_cand=needs_llm_hold, mutate_base=needs_llm_hold)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0   # 1/1, not 1/2
    assert "gratefuldead-1973-06-11" not in (out / "drift.txt").read_text()
    assert "gratefuldead-1973-06-11" in (out / "needs_llm.txt").read_text()
    assert "needs-LLM held: base 1, cand 1" in (out / "summary.txt").read_text()


def test_compare_counts_an_unreadable_state_unreplayable_row_as_not_reproducing(tmp_path, capsys):
    def unknown(arm):
        s = arm["shows"]["gratefuldead-1973-06-11"]
        s["state"], s["outcome"], s["reproduces"] = "unknown", "unreplayable", False
    base, cand = _two_arms(tmp_path, mutate_cand=unknown, mutate_base=unknown)
    assert rh.main(["compare", str(base), str(cand), "--out", str(tmp_path / "cmp")]) == 3   # 1/2
    assert "1/2" in capsys.readouterr().err


def test_packaged_exposure_lists_a_clean_show_whose_fields_would_change(tmp_path):
    def change(arm):
        s = arm["shows"]["gratefuldead-1973-06-11"]
        s["outcome"], s["venue"] = "clean-changed", {"old": "RFK Stadium", "new": "Robert F. Kennedy Stadium"}
        s["date"] = {"old": "1973-06-11", "new": "1973-06-12"}
    base, cand = _two_arms(tmp_path, change)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "packaged_exposure.txt").read_text()
    assert "gratefuldead-1973-06-11" in text and "Robert F. Kennedy Stadium" in text
    assert "1973-06-12" in text


def test_packaged_exposure_is_base_versus_cand_and_lists_newly_held_shows(tmp_path):
    same = {"old": "RFK Stadium", "new": "Robert F. Kennedy Stadium"}
    def both(arm):
        arm["shows"]["gratefuldead-1973-06-11"]["venue"] = same
    def cand_holds(arm):
        both(arm)
        s = arm["shows"]["gratefuldead-1973-06-11"]
        s["outcome"], s["gather_flags"] = "newly-held", ["venue mismatch: archive 'A' vs jerrybase 'B'"]
    base, cand = _two_arms(tmp_path, mutate_cand=cand_holds, mutate_base=both)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "packaged_exposure.txt").read_text()
    assert "Robert F. Kennedy Stadium" not in text          # the same diff in both arms is not exposure
    assert "gratefuldead-1973-06-11" in text and "venue mismatch: archive 'A' vs jerrybase 'B'" in text


def test_closest_calls_sections_and_notes_groups(tmp_path):
    notes = [
        "venue differs from jerrybase: archive 'Hall A' vs 'Hall B' (same city)",
        "accepted short tag title: track 3 '1999' corroborated by setlist.fm",
        "accepted short tag title: track 4 'Hey' corroborated by lma:x, setlist.fm",
        "unknown-song flags suppressed by the right-show gate: 9/10 tape tracks asserted (ratio 0.90), 1 unclaimed: Foo; research date: June 10, 1973",
        "format sibling tagged: 3 tracks",
        "something unforeseen",
    ]
    def mutate(arm):
        _clear_it(arm)
        s = arm["shows"]["gratefuldead-1973-06-10"]
        s["notes"] = notes
        s["alignment"] = {"old": "none", "new": "exact"}
    base, cand = _two_arms(tmp_path, mutate)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    cc = (out / "closest_calls.txt").read_text()
    assert "'1999' by setlist.fm (single source, numeric-only title)" in cc
    assert "'Hey'" not in cc
    assert "ratio 0.90, asserted 9/10" in cc
    assert "slice 4b" in cc and "slice 5a" in cc and "slice 5c" in cc
    assert '"exact"' in cc
    nt = (out / "notes.txt").read_text()
    assert "== format sibling tagged (1)" in nt and "== other (1)" in nt and "== 2a (2)" in nt


def test_pilot_list_swaps_in_reuse_rows():
    # reuse rows sit beyond sha1 position 10, so only the swap can bring them in
    ordered = sorted((f"s{i:02d}" for i in range(14)), key=rh._skey)
    rows = [{"slug": s, "briefing": "reuse" if i >= 10 else "fresh"} for i, s in enumerate(ordered)]
    pilot = rh._pilot(rows)
    # the last two non-reuse rows (positions 8, 9) give way to the first two reuse rows
    assert {r["slug"] for r in pilot} == set(ordered[:8]) | set(ordered[10:12])
    assert [r["slug"] for r in pilot] == sorted((r["slug"] for r in pilot), key=rh._skey)


def _synthetic_arm(n_held, n_reproducing):
    shows = {}
    for i in range(n_held):
        shows[f"s{i:03d}"] = {"slug": f"s{i:03d}", "state": "held", "outcome": "still-held",
                              "reproduces": i < n_reproducing, "digests": {}, "notes": [],
                              "gather_flags": [], "vet_flags": [], "stored_core_flags": []}
    return {"sha": "x", "config_fingerprint": "f", "setlistfm_configured": False,
            "root": "/nonexistent", "shows": shows}


@pytest.mark.parametrize("ok,rc", [(99, 0), (98, 3)])
def test_compare_gate_boundary_is_99_percent(tmp_path, capsys, ok, rc):
    arm = tmp_path / "arm.json"
    arm.write_text(json.dumps(_synthetic_arm(100, ok)))
    assert rh.main(["compare", str(arm), str(arm), "--out", str(tmp_path / "cmp")]) == rc
    if rc == 3:
        assert f"{ok}/100" in capsys.readouterr().err


def test_structure_changed_and_needs_llm_rows_reach_the_right_lists(tmp_path):
    def rows(arm):
        arm["shows"]["sc"] = {"slug": "sc", "state": "held", "outcome": "still-held", "reproduces": True,
                              "digests": {}, "notes": []}
        arm["shows"]["nl"] = dict(arm["shows"]["sc"], slug="nl")
    base = _synthetic_arm(1, 1)
    base["shows"]["s000"].update(reproduces=True)
    rows(base)
    cand = json.loads(json.dumps(base))
    cand["shows"]["sc"].update(outcome="structure-changed", would_be="needs-brief", briefing="fresh")
    cand["shows"]["nl"].update(outcome="needs-llm", needs_llm=["stored alignment llm"])
    b, c = tmp_path / "b.json", tmp_path / "c.json"
    b.write_text(json.dumps(base))
    c.write_text(json.dumps(cand))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(b), str(c), "--out", str(out)]) == 0
    sc = json.loads((out / "structure_changed_list.json").read_text())["rows"]
    assert [(r["slug"], r["outcome"]) for r in sc] == [("sc", "needs-brief")]
    for name in ("predicted_list.json", "pilot_list.json"):
        assert json.loads((out / name).read_text())["rows"] == []
    assert "nl" not in (out / "structure_changed_list.json").read_text()


def test_compare_clears_stale_outputs_before_a_failing_gate(tmp_path):
    base, cand = _two_arms(tmp_path, _clear_it)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    (out / "keep.txt").write_text("not ours")
    assert (out / "predicted_list.json").exists()
    # a second compare of a non-reproducing baseline into the same directory
    base2, cand2 = tmp_path / "b2.json", tmp_path / "c2.json"
    arm = json.loads(base.read_text())
    arm["shows"]["gratefuldead-1973-06-10"]["reproduces"] = False
    base2.write_text(json.dumps(arm))
    cand2.write_text(cand.read_text())
    assert rh.main(["compare", str(base2), str(cand2), "--out", str(out)]) == 3
    for name in ("predicted_list.json", "pilot_list.json", "structure_changed_list.json", "summary.txt"):
        assert not (out / name).exists(), name
    assert "gratefuldead-1973-06-10" in (out / "drift.txt").read_text()
    assert (out / "keep.txt").exists()


SLUG = "gratefuldead-1973-06-10"
SINGLE = "single-set structure for a long show (160 min)"


def _hold_with(flags, gather_only=True):
    def hold_it(arm):
        s = arm["shows"][SLUG]
        s["gather_flags"], s["vet_flags"] = list(flags), []
        s["outcome"] = "still-held"
    return hold_it


def _page(tmp_path, mutate, edit_show=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    base, cand = _two_arms(tmp_path, mutate)
    if edit_show:
        p = tmp_path / "lib" / "shows" / SLUG / "show.json"
        d = json.loads(p.read_text())
        edit_show(d)
        p.write_text(json.dumps(d))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    return (out / "narration_candidates.html").read_text()


def test_narration_candidates_page_lists_unknowable_structure_holds(tmp_path):
    base, cand = _two_arms(tmp_path, _hold_with([SINGLE]))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    html = (out / "narration_candidates.html").read_text()
    assert "<table" in html and SLUG in html and "Grateful Dead" in html
    assert "gratefuldead-1973-06-11" not in html
    assert "<script>" in html and "http" not in html.split("<script>")[1]   # inline JS, no CDN


def test_narration_candidates_excludes_shows_with_other_flags_or_none(tmp_path):
    assert SLUG not in _page(tmp_path / "a", _hold_with([SINGLE, "unresolved track titles"]))
    assert SLUG not in _page(tmp_path / "b", _hold_with([]))


def test_low_confidence_setlist_counts_only_with_empty_canonical_proxy(tmp_path):
    def struct(source, cov):
        def edit(d):
            d["structure"] = {"source": source, "alignment": "deterministic", "coverage": cov,
                              "conflicts": []}
        return edit
    flag = _hold_with(["low-confidence setlist"])
    assert SLUG in _page(tmp_path / "a", flag, struct("none", 0.7))
    assert SLUG in _page(tmp_path / "b", flag, struct("chosen", 0.0))
    assert SLUG not in _page(tmp_path / "c", flag, struct("chosen", 0.7))


def test_narration_candidates_row_content_untitled_and_escaping(tmp_path):
    def edit(d):
        d["venue"] = "<b>Hall</b> & Co"
        for t in d["tracks"]:
            t["title_source"] = "unresolved"
    html = _page(tmp_path, _hold_with([SINGLE]), edit)
    assert "&lt;b&gt;Hall&lt;/b&gt; &amp; Co" in html and "<b>Hall</b>" not in html
    assert "unresolved:" in html and ">yes<" in html


def test_narration_candidates_degrades_when_show_json_is_unreadable(tmp_path):
    base, cand = _two_arms(tmp_path, _hold_with([SINGLE]))
    (tmp_path / "lib" / "shows" / SLUG / "show.json").write_text("{not json")
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    assert SLUG in (out / "narration_candidates.html").read_text()


def test_compare_writes_only_files_named_in_output_files(tmp_path):
    base, cand = _two_arms(tmp_path, _clear_it)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    assert {p.name for p in out.iterdir()} <= set(rh.OUTPUT_FILES)


def test_narration_sort_uses_whole_string_numeric_test():
    js = rh.NARRATION_JS
    assert "parseFloat(" not in js and "/^-?" in js


def test_narration_sort_comparator_is_correct_and_transitive():
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    start = rh.NARRATION_JS.index("var x = a.cells")
    end = rh.NARRATION_JS.index("return asc")
    body = rh.NARRATION_JS[start:end]
    prog = ("var cmp=function(a,b){var asc=true;" + body.replace("a.cells[i]", "{textContent:a}")
            .replace("b.cells[i]", "{textContent:b}") + "return c;};"
            "var v=['1973-06-10','1973-01-02','311-1995-01-01','abc','?','12','3'];"
            "console.log(JSON.stringify(v.slice().sort(cmp)));")
    res = subprocess.run([node, "-e", prog], capture_output=True, text=True, check=True)
    got = json.loads(res.stdout)
    assert got == ["3", "12", "1973-01-02", "1973-06-10", "311-1995-01-01", "?", "abc"] or \
        got == ["3", "12", "?", "1973-01-02", "1973-06-10", "311-1995-01-01", "abc"]


def test_briefings_lists_a_set_count_match_the_new_guard_suppresses(tmp_path):
    base, cand = _two_arms(tmp_path)
    root = tmp_path / "lib"
    ws = root / "shows" / "gratefuldead-1973-06-10"
    b = json.loads((ws / "briefing.json").read_text())
    b["context"] = "They played two electric sets that night, a long one and a short one."
    (ws / "briefing.json").write_text(json.dumps(b))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "briefings.txt").read_text()
    assert "suppressed set-count/ordinal matches" in text
    assert "gratefuldead-1973-06-10" in text and "two electric sets" in text


def test_suppressed_claims_lists_only_what_3c_drops_with_bounded_context(tmp_path):
    from fixture_library import CLEAN, HELD
    root = tmp_path / "lib"
    build_library(root)
    pad = "x" * 70
    held = json.loads((root / "shows" / HELD / "briefing.json").read_text())
    held["context"] = f"{pad} there is no second set and two excellent sets, {pad}"
    held["cautions"] = ["two night sets"]                  # cautions are not guard prose
    (root / "shows" / HELD / "briefing.json").write_text(json.dumps(held))
    clean = json.loads((root / "shows" / CLEAN / "briefing.json").read_text())
    clean["context"], clean["narration"] = "two electric sets", "vague"   # vague: not 3c's business
    (root / "shows" / CLEAN / "briefing.json").write_text(json.dumps(clean))
    lines, n = rh._suppressed_claims(root)
    assert n == 1 and lines[0] == "suppressed set-count/ordinal matches: 1"
    row = lines[1]
    assert row.startswith(f"  {HELD}  'second set'  ...")
    ctx = row.split("  ...", 1)[1].rstrip(".")
    at = held["context"].index("second set")
    assert ctx == held["context"][at - 60:at + len("second set") + 60]
    assert "excellent" in ctx and "night sets" not in row
    assert rh._suppressed_claims(tmp_path / "nowhere") == (
        ["suppressed set-count/ordinal matches: 0", rh.NONE, ""], 0)


def test_suppressed_claims_without_a_root_in_either_arm_reads_nothing(tmp_path, monkeypatch):
    def drop_root(arm):
        arm.pop("root", None)
    base, cand = _two_arms(tmp_path, mutate_cand=drop_root, mutate_base=drop_root)
    # a library-shaped tree in the caller's cwd that 3c would report if it were read
    cwd = tmp_path / "cwd"
    show = cwd / "shows" / "elsewhere-1999-01-01"
    show.mkdir(parents=True)
    (show / "show.json").write_text("{}")
    (show / "briefing.json").write_text(json.dumps(
        {"context": "two electric sets", "significance": "s"}))
    monkeypatch.chdir(cwd)
    assert rh._suppressed_claims(None) == (["suppressed set-count/ordinal matches: 0", rh.NONE, ""], 0)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "briefings.txt").read_text()
    assert "suppressed set-count/ordinal matches: 0" in text and "elsewhere" not in text


def test_4b_closest_calls_read_vetting_jsons_nested_asserted_dates(tmp_path):
    # Task 16c: VettingResult nests the dates under "vetting"; the row used to
    # read the top level and print "(vetting.json unavailable)" every time.
    def lose_flag(arm):
        _clear_it(arm)
    def hold_flag(arm):
        arm["shows"]["gratefuldead-1973-06-10"]["vet_flags"] = ["research asserts wrong date: 1973-06-11"]
    base, cand = _two_arms(tmp_path, mutate_cand=lose_flag, mutate_base=hold_flag)
    slug_dir = tmp_path / "lib" / "shows" / "gratefuldead-1973-06-10"
    slug_dir.mkdir(parents=True, exist_ok=True)
    (slug_dir / "vetting.json").write_text(json.dumps({
        "vetting": {"asserted_songs": ["Dark Star"], "asserted_dates": ["1973-06-10", "1973-06-11"]},
        "flags": [], "adopted_date": None}))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    cc = (out / "closest_calls.txt").read_text()
    sect = cc[cc.index("slice 4b"):].split("\n\n")[0]
    assert 'asserted_dates ["1973-06-10", "1973-06-11"]' in sect and "unavailable" not in sect


def test_closest_calls_has_the_two_5c_subsections(tmp_path):
    base, cand = _two_arms(tmp_path)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "closest_calls.txt").read_text()
    assert "5c.3 second closer candidates" in text and "5c.1 short-track arm (not adopted)" in text


def test_closest_calls_5c_subsections_list_the_stored_tracks_rows(tmp_path):
    # jerrybase's 1973-06-10 event closes its sets on 'Playing In The Band',
    # 'Sugar Magnolia' and 'Johnny B. Goode'.
    def flag_it(arm):
        arm["shows"]["gratefuldead-1973-06-10"]["gather_flags"].append(
            "jerrybase set closer 'Playing In The Band' is not at a set break")
    base, cand = _two_arms(tmp_path, mutate_cand=flag_it)
    path = tmp_path / "lib" / "shows" / "gratefuldead-1973-06-10" / "show.json"
    show = json.loads(path.read_text())
    proto = show["tracks"][0]
    rows = [("Playing In The Band", "1", 900.0), ("Me And My Uncle", "1", 180.0),
            ("Tuning", "1", 60.0), ("(Part 1) Sugar Magnolia", "2", 400.0), ("Deal", "2", 300.0),
            ("(Part 2) Sugar Magnolia", "2", 200.0)]
    show["tracks"] = [{**proto, "index": i + 1, "title": t, "set": s, "duration_sec": d,
                       "filename": f"{i + 1:02d}.mp3"} for i, (t, s, d) in enumerate(rows)]
    path.write_text(json.dumps(show))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "closest_calls.txt").read_text()
    assert ("  gratefuldead-1973-06-10: closer 'Sugar Magnolia': candidates "
            '["(Part 1) Sugar Magnolia", "(Part 2) Sugar Magnolia"]') in text
    assert "5c.1 short-track arm (not adopted): 1 show(s)" in text
    assert ("  gratefuldead-1973-06-10: closer 'Playing In The Band': followed by "
            "'Me And My Uncle' 180s, 'Tuning' 60s") in text
    show["tracks"][1]["duration_sec"] = 420.0                    # not under 7 min: not in the arm
    path.write_text(json.dumps(show))
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    assert "5c.1 short-track arm (not adopted): 0 show(s)" in (out / "closest_calls.txt").read_text()


def _venue(arm, slug, new, state=None, old="RFK Stadium"):
    s = arm["shows"][slug]
    s["venue"] = {"old": old, "new": new}
    if state:
        s["state"] = state


def test_venue_changes_lists_both_strings_and_delivery(tmp_path):
    slug = "gratefuldead-1973-06-11"
    base, cand = _two_arms(tmp_path, mutate_cand=lambda a: _venue(a, slug, "R.F.K. Stadium", "delivered"),
                           mutate_base=lambda a: a["shows"][slug].update(state="delivered"))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "venue_changes.txt").read_text()
    assert f"{slug}  [delivered]  DELIVERED" in text
    assert 'venue: "RFK Stadium" -> "R.F.K. Stadium"' in text and "flags: unchanged" in text
    assert "venue_changes.txt: 1 show(s), 0 with a flag change" in (out / "summary.txt").read_text()
    assert "venue_changes.txt" in rh.OUTPUT_FILES


def test_venue_changes_ignores_an_identical_diff_and_counts_a_flag_change(tmp_path):
    slug = "gratefuldead-1973-06-11"
    def both(a): _venue(a, slug, "R.F.K. Stadium")
    def cand_m(a):
        both(a)
        a["shows"][slug]["city"] = {"old": "Washington, DC", "new": "Washington, D.C."}
        a["shows"][slug]["gather_flags"] = ["venue mismatch: archive 'A' vs jerrybase 'B'"]
    base, cand = _two_arms(tmp_path, mutate_cand=cand_m, mutate_base=both)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "venue_changes.txt").read_text()
    assert "R.F.K. Stadium" in text                                   # unchanged venue still shown on the row
    assert 'city: "Washington, DC" -> "Washington, D.C."' in text
    assert "flags CHANGED: added" in text
    assert "venue_changes.txt: 1 show(s), 1 with a flag change" in (out / "summary.txt").read_text()


# --- piece 2: --strip-structure-overrides, stamped arms ---

_OVERRIDES = {"exclude": ["nonexistent-track.mp3"], "titles": {"1": "Forced Title"},
              "set_breaks": [3], "encore_after": 5}


def test_strip_mode_removes_only_structure_overrides(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    shows = build_library(root)
    live = shows["gratefuldead-1973-06-10"].overrides
    live.write_text(json.dumps(_OVERRIDES))
    live_bytes = live.read_bytes()
    seen = {}
    real = rh.replay_show

    def spy(ws, **kw):
        if ws.dir.name == "gratefuldead-1973-06-10":
            seen["dir"] = ws.dir
            seen["overrides"] = json.loads(ws.overrides.read_text())
        return real(ws, **kw)

    monkeypatch.setattr(rh, "replay_show", spy)
    out = tmp_path / "arm.json"
    scratch = tmp_path / "scratch"
    assert rh.main(["run", "--out", str(out), "--all", "--strip-structure-overrides",
                    "--config", str(root / "config.toml"), "--scratch", str(scratch)]) == 0
    assert seen["overrides"] == {"exclude": ["nonexistent-track.mp3"],
                                 "titles": {"1": "Forced Title"}}
    assert scratch in seen["dir"].parents                  # the shadow lives under the scratch root
    assert live.read_bytes() == live_bytes                 # the live file is untouched
    arm = json.loads(out.read_text())
    assert arm["structure_overrides_stripped"] is True
    row = arm["shows"]["gratefuldead-1973-06-10"]
    assert row["state"] == "held" and row["unreplayable"] is None
    assert row["stripped"] == {"set_breaks": [3], "encore_after": 5}
    assert "stripped" not in json.loads(
        (lambda p: (rh.main(["run", "--out", str(p), "--all", "--config",
                             str(root / "config.toml")]), p.read_text())[1])(
            tmp_path / "plain.json"))["shows"]["gratefuldead-1973-06-10"]
    # the digests are the REAL show's, so a stripped arm stays comparable with an unstripped base
    import hashlib
    assert row["digests"]["overrides.json"] == hashlib.sha256(live_bytes).hexdigest()
    assert not any(p.name == ".shadow" and any(p.iterdir()) for p in scratch.iterdir())


def test_unstripped_arm_is_stamped_false_and_replays_the_real_overrides(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    shows = build_library(root)
    shows["gratefuldead-1973-06-10"].overrides.write_text(json.dumps(_OVERRIDES))
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--all", "--config", str(root / "config.toml")]) == 0
    assert json.loads(out.read_text())["structure_overrides_stripped"] is False


def _stripped_arms(tmp_path, base_stripped, cand_stripped):
    root = tmp_path / "lib"
    build_library(root, held_for_real=True)
    cfg = str(root / "config.toml")
    paths = []
    for name, stripped in (("base", base_stripped), ("cand", cand_stripped)):
        p = tmp_path / f"{name}.json"
        argv = ["run", "--out", str(p), "--all", "--config", cfg]
        assert rh.main(argv + (["--strip-structure-overrides"] if stripped else [])) == 0
        paths.append(p)
    return paths


def test_compare_refuses_mixed_strip_arms_and_writes_no_lists_for_stripped(tmp_path, capsys):
    base, cand = _stripped_arms(tmp_path, False, True)
    assert rh.main(["compare", str(base), str(cand), "--out", str(tmp_path / "mixed")]) == 2
    assert "structure_overrides_stripped differs" in capsys.readouterr().err
    assert rh.main(["compare", str(cand), str(base), "--out", str(tmp_path / "mixed2")]) == 2

    # a base-code arm has no key at all: it reads as unstripped
    arm = json.loads(base.read_text())
    del arm["structure_overrides_stripped"]
    base.write_text(json.dumps(arm))
    out = tmp_path / "plain"
    assert rh.main(["compare", str(base), str(base), "--out", str(out)]) == 0
    assert (out / "predicted_list.json").exists()

    sb, sc = _stripped_arms(tmp_path / "s", True, True)
    out = tmp_path / "stripped"
    out.mkdir()
    for name in ("predicted_list.json", "structure_changed_list.json", "pilot_list.json"):
        (out / name).write_text("stale")                       # a stale list must not outlive it
    assert rh.main(["compare", str(sb), str(sc), "--out", str(out)]) == 0
    assert not list(out.glob("*_list.json"))
    assert "apply lists: not written" in (out / "summary.txt").read_text()


# --- piece 3: --strip-title-overrides ---

def _run_strip(tmp_path, monkeypatch, flags):
    root = tmp_path / "lib"
    shows = build_library(root)
    live = shows["gratefuldead-1973-06-10"].overrides
    live.write_text(json.dumps(_OVERRIDES))
    live_bytes = live.read_bytes()
    seen = {}
    real = rh.replay_show

    def spy(ws, **kw):
        if ws.dir.name == "gratefuldead-1973-06-10":
            seen["overrides"] = json.loads(ws.overrides.read_text())
        return real(ws, **kw)

    monkeypatch.setattr(rh, "replay_show", spy)
    out = tmp_path / "arm.json"
    assert rh.main(["run", "--out", str(out), "--all", *flags,
                    "--config", str(root / "config.toml"),
                    "--scratch", str(tmp_path / "scratch")]) == 0
    assert live.read_bytes() == live_bytes
    return seen["overrides"], json.loads(out.read_text())


def test_strip_titles_removes_only_titles(tmp_path, monkeypatch):
    seen, arm = _run_strip(tmp_path, monkeypatch, ["--strip-title-overrides"])
    assert seen == {"exclude": ["nonexistent-track.mp3"], "set_breaks": [3], "encore_after": 5}
    assert arm["title_overrides_stripped"] is True
    assert arm["structure_overrides_stripped"] is False
    assert arm["shows"]["gratefuldead-1973-06-10"]["stripped"] == {"titles": {"1": "Forced Title"}}


def test_both_strip_flags_together(tmp_path, monkeypatch):
    seen, arm = _run_strip(tmp_path, monkeypatch,
                           ["--strip-title-overrides", "--strip-structure-overrides"])
    assert seen == {"exclude": ["nonexistent-track.mp3"]}
    assert arm["title_overrides_stripped"] is True and arm["structure_overrides_stripped"] is True
    assert arm["shows"]["gratefuldead-1973-06-10"]["stripped"] == {
        "titles": {"1": "Forced Title"}, "set_breaks": [3], "encore_after": 5}


def test_shadow_takes_the_keys_as_a_contract(tmp_path):
    root = tmp_path / "lib"
    shows = build_library(root)
    d = shows["gratefuldead-1973-06-10"].dir
    d.joinpath("overrides.json").write_text(json.dumps(_OVERRIDES))
    ws, stripped = rh._shadow(d, tmp_path / "sh", ("titles", "set_breaks", "encore_after"))
    assert json.loads(ws.overrides.read_text()) == {"exclude": ["nonexistent-track.mp3"]}
    assert set(stripped) == {"titles", "set_breaks", "encore_after"}


def _title_arms(tmp_path, base_flag, cand_flag):
    root = tmp_path / "lib"
    build_library(root, held_for_real=True)
    cfg = str(root / "config.toml")
    paths = []
    for name, flag in (("base", base_flag), ("cand", cand_flag)):
        p = tmp_path / f"{name}.json"
        assert rh.main(["run", "--out", str(p), "--all", "--config", cfg]
                       + (["--strip-title-overrides"] if flag else [])) == 0
        paths.append(p)
    return paths


def test_compare_refuses_mixed_title_strip_arms(tmp_path, capsys):
    base, cand = _title_arms(tmp_path, False, True)
    assert rh.main(["compare", str(base), str(cand), "--out", str(tmp_path / "m")]) == 2
    assert "title_overrides_stripped differs" in capsys.readouterr().err
    assert rh.main(["compare", str(cand), str(base), "--out", str(tmp_path / "m2")]) == 2
    arm = json.loads(base.read_text())
    del arm["title_overrides_stripped"]          # a pre-piece-3 arm reads as unstripped
    base.write_text(json.dumps(arm))
    assert rh.main(["compare", str(base), str(base), "--out", str(tmp_path / "ok")]) == 0


def test_no_apply_lists_for_title_stripped_arms(tmp_path):
    sb, sc = _title_arms(tmp_path, True, True)
    out = tmp_path / "stripped"
    out.mkdir()
    for name in ("predicted_list.json", "structure_changed_list.json", "pilot_list.json"):
        (out / name).write_text("stale")
    assert rh.main(["compare", str(sb), str(sc), "--out", str(out)]) == 0
    assert not list(out.glob("*_list.json"))
    assert "apply lists: not written" in (out / "summary.txt").read_text()


# --- Piece 2 (taper markers): taper_cleared / taper_changes / the `taper` note group ---

HELD_SLUG = "gratefuldead-1973-06-10"
CLEAN_SLUG = "gratefuldead-1973-06-11"


def _write(path, arm):
    path.write_text(json.dumps(arm))


def _row(arm, slug):
    return arm["shows"][slug]


def test_taper_cleared_includes_structure_changed_clears(tmp_path):
    base, cand = _two_arms(tmp_path)
    arm = json.loads(cand.read_text())
    # one held base show, three candidate outcomes, then a still-held one
    row = _row(arm, HELD_SLUG)
    others = {}
    for i, outcome in enumerate(("clears", "needs-brief", "structure-changed", "still-held")):
        slug = f"extra-{i}"
        others[slug] = outcome
        arm["shows"][slug] = dict(row, slug=slug, outcome=outcome, state="held")
    barm = json.loads(base.read_text())
    for slug in others:
        barm["shows"][slug] = dict(_row(barm, HELD_SLUG), slug=slug, outcome="still-held")
    del arm["shows"][HELD_SLUG], barm["shows"][HELD_SLUG]
    cand.write_text(json.dumps(arm))
    base.write_text(json.dumps(barm))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--no-repro-gate"]) == 0
    text = (out / "taper_cleared.txt").read_text()
    assert "extra-0" in text and "extra-1" in text and "extra-2" in text
    assert "extra-3" not in text
    assert "taper_cleared.txt" in rh.OUTPUT_FILES and "taper_changes.txt" in rh.OUTPUT_FILES
    assert "taper_cleared.txt: 3 show(s)" in (out / "summary.txt").read_text()


def _owned(slug_row, sets, filler=None, source="notes", step1="deterministic"):
    slug_row.update(taper_owned=True, sets=sets, filler=filler or [False] * len(sets),
                    taper_source=source, step1_alignment=step1, outcome="clears")


def _clone(arm, src, slug, state):
    arm["shows"][slug] = dict(arm["shows"][src], slug=slug, state=state)


def _clone_slugs(tmp_path, arms_fn):
    """Build both arms, clone the clean show into extra slugs in both arms and
    the library, then let `arms_fn(base_arm, cand_arm)` shape the rows."""
    base, cand = _two_arms(tmp_path)
    root = tmp_path / "lib"
    return base, cand, root


def test_taper_changes_report_tiers_and_states(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    cfg = str(root / "config.toml")
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    deliver = tmp_path / "station"
    labels = {"moved": ["1", "1", "1", "2", "2"], "renamed": ["1", "1", "2", "2", "2"],
              "fill": ["1", "1", "1", "2", "2"], "prov": ["1", "1", "2", "2", "2"]}
    for name, lab in labels.items():
        slug = f"show-{name}"
        for arm in (b, c):
            _clone(arm, CLEAN_SLUG, slug, "delivered" if name == "moved" else "packaged")
            _row(arm, slug).update(outcome="clears", set_changes=[], segue_changes=[], notes=[])
        (root / "shows" / slug).mkdir(parents=True)
        (root / "shows" / slug / "show.json").write_text(json.dumps(
            {"tracks": [{"index": i + 1, "set": s} for i, s in enumerate(lab)]}))
        _row(b, slug)["sets"] = lab
        _row(b, slug)["filler"] = [False] * 5
    _owned(_row(c, "show-moved"), ["1", "1", "2", "2", "2"], source="notes", step1="jerrybase")
    _owned(_row(c, "show-renamed"), ["1", "1", "3", "3", "3"], source="description")
    _owned(_row(c, "show-fill"), ["1", "1", "1", "2", "E"], filler=[False] * 4 + [True])
    _row(b, "show-fill")["sets"] = ["1", "1", "1", "2", "2"]
    _owned(_row(c, "show-prov"), labels["prov"])
    (deliver / "show-moved").mkdir(parents=True)
    (deliver / "show-moved" / "manifest.json").write_text(json.dumps({"dj_audio": {"profile": "x"}}))
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--config", cfg_with(tmp_path, root, deliver)]) == 0
    text = (out / "taper_changes.txt").read_text()
    sec = {name: text.split(f"== {name}")[1].split("\n== ")[0] for name in
           ("songs moved", "labels renamed", "filler labels only", "provenance only")}
    assert "show-moved" in sec["songs moved"] and "show-renamed" not in sec["songs moved"]
    assert "show-renamed" in sec["labels renamed"]
    assert "show-fill" in sec["filler labels only"]
    assert "show-prov" in sec["provenance only"]
    moved = [l for l in sec["songs moved"].splitlines() if "show-moved" in l][0]
    assert "voiced" in moved and "notes" in moved and "overruled step1 mechanism: jerrybase" in moved
    assert "before [3]" in moved and "after [2]" in moved and "stored [3]" in moved
    assert "packaged" in sec["labels renamed"] and "voiced" not in sec["labels renamed"]
    assert "description" in sec["labels renamed"]


def cfg_with(tmp_path, root, deliver):
    p = tmp_path / "compare.toml"
    p.write_text(f'root = "{root}"\ndelivery_path = "{deliver}"\n\n[jerrybase]\nenabled = false\n')
    return str(p)


def test_taper_changes_before_is_stored_labels_with_base_set_changes(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    slug = "show-old"
    for arm in (b, c):
        _clone(arm, CLEAN_SLUG, slug, "packaged")
        _row(arm, slug).update(outcome="clears", notes=[], set_changes=[], segue_changes=[])
    (root / "shows" / slug).mkdir(parents=True)
    (root / "shows" / slug / "show.json").write_text(json.dumps(
        {"tracks": [{"index": i + 1, "set": s} for i, s in enumerate(["1", "1", "1", "1"])]}))
    # base code moved track 3 and 4 to set 2 (a base row has no `sets` key)
    _row(b, slug).pop("sets", None)
    _row(b, slug)["set_changes"] = [{"index": 3, "old": "1", "new": "2"}, {"index": 4, "old": "1", "new": "2"}]
    _owned(_row(c, slug), ["1", "1", "2", "2"])
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--config",
                    cfg_with(tmp_path, root, tmp_path / "st")]) == 0
    text = (out / "taper_changes.txt").read_text()
    # before == candidate, so the base had already moved it: not a change of this piece
    assert slug not in text.split("== songs moved")[1].split("\n== ")[0]
    # and the stored label view differs from the candidate only by what base changed
    _owned(_row(c, slug), ["1", "2", "2", "2"])
    _write(cand, c)
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--config",
                    cfg_with(tmp_path, root, tmp_path / "st")]) == 0
    moved = (out / "taper_changes.txt").read_text().split("== songs moved")[1].split("\n== ")[0]
    assert slug in moved and "before [2]" in moved and "stored []" in moved and "after [1]" in moved


def test_taper_changes_lists_unreplayable_and_slfm_miss_shipped_rows(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    for arm in (b, c):
        _clone(arm, CLEAN_SLUG, "show-unrep", "packaged")
        _clone(arm, CLEAN_SLUG, "show-miss", "delivered")
        _clone(arm, CLEAN_SLUG, "show-held-unrep", "held")
    _row(c, "show-unrep").update(outcome="unreplayable", unreplayable="cache miss: x")
    _row(b, "show-miss")["slfm_miss"] = True
    _row(c, "show-held-unrep").update(outcome="unreplayable", unreplayable="cache miss: y")
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--no-repro-gate"]) == 0
    text = (out / "taper_changes.txt").read_text()
    sec = text.split("== unreplayable or setlist.fm-miss shipped shows")[1]
    assert "show-unrep" in sec and "cache miss: x" in sec and "show-miss" in sec
    assert "show-held-unrep" not in sec


def test_taper_changes_counts_not_owned_needs_llm_rows(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    stored = ["1", "1", "1", "1"]
    for slug in ("nl-unowned", "nl-owned"):
        for arm in (b, c):
            _clone(arm, CLEAN_SLUG, slug, "packaged")
            _row(arm, slug).update(set_changes=[], segue_changes=[], notes=[])
        (root / "shows" / slug).mkdir(parents=True)
        (root / "shows" / slug / "show.json").write_text(json.dumps(
            {"tracks": [{"index": i + 1, "set": s} for i, s in enumerate(stored)]}))
        _row(b, slug).update(outcome="needs-llm", needs_llm=["stored alignment llm"])
    _row(c, "nl-unowned").update(outcome="needs-llm", needs_llm=["stored alignment llm"],
                                 taper_owned=False)
    _owned(_row(c, "nl-owned"), ["1", "1", "2", "2"])
    _row(c, "nl-owned")["segue_changes"] = [{"index": 2, "old": True, "new": False}]
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--no-repro-gate"]) == 0
    text = (out / "taper_changes.txt").read_text()
    assert "needs-LLM in the candidate and not taper-owned (unchanged by this piece, not listed): 1" in text
    songs = text.split("== songs moved")[1].split("\n== ")[0]
    assert "nl-owned" in songs and "nl-unowned" not in text
    assert "before [] after [2] stored []" in songs      # the stored structure is "before"


def test_stored_llm_moved_shows_listed_with_segue_changes(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    for slug in ("llm-moved", "llm-stays"):
        for arm in (b, c):
            _clone(arm, CLEAN_SLUG, slug, "packaged")
        _row(b, slug).update(outcome="needs-llm", needs_llm=["stored alignment llm"])
    _row(c, "llm-stays").update(outcome="needs-llm", needs_llm=["stored alignment llm"])
    _owned(_row(c, "llm-moved"), ["1", "1", "2", "2"])
    _row(c, "llm-moved")["segue_changes"] = [{"index": 2, "old": True, "new": False}]
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--no-repro-gate"]) == 0
    text = (out / "taper_changes.txt").read_text()
    sec = text.split("== stored-llm shows now replayable")[1].split("\n== ")[0]
    assert "llm-moved" in sec and "llm-stays" not in sec
    assert '"index": 2' in sec and "segue" in sec


def test_taper_note_group(tmp_path):
    notes = [
        "set breaks from the taper's markers (was [3] ['1', '1', '2'])",
        "structure has 3 sets but jerrybase shows 2 (taper's markers)",
        "jerrybase set closer 'Sugar Magnolia' is not at a set break (taper's markers)",
        "jerrybase set closer 'Sugar Magnolia' is not at a set break",
    ]
    def mutate(arm):
        _clear_it(arm)
        _row(arm, HELD_SLUG)["notes"] = notes
    base, cand = _two_arms(tmp_path, mutate)
    groups = rh._notes_by_group(json.loads(cand.read_text()))
    assert [n for _, n in groups["taper"]] == notes[:3]
    assert [n for _, n in groups["5c.1"]] == notes[3:]
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    assert "== taper (3)" in (out / "notes.txt").read_text()
    assert "== 5c.1 (1)" in (out / "notes.txt").read_text()


def test_taper_reports_not_written_for_stripped_arms(tmp_path):
    sb, sc = _stripped_arms(tmp_path, True, True)
    out = tmp_path / "stripped"
    assert rh.main(["compare", str(sb), str(sc), "--out", str(out)]) == 0
    assert not (out / "taper_cleared.txt").exists() and not (out / "taper_changes.txt").exists()


def test_taper_changes_numbered_to_encore_is_not_a_plain_rename_and_rows_show_labels(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    slug = "show-enc"
    for arm in (b, c):
        _clone(arm, CLEAN_SLUG, slug, "packaged")
        _row(arm, slug).update(outcome="clears", set_changes=[], segue_changes=[], notes=[])
    (root / "shows" / slug).mkdir(parents=True)
    (root / "shows" / slug / "show.json").write_text(json.dumps(
        {"tracks": [{"index": i + 1, "set": s} for i, s in enumerate(["1", "1", "2"])]}))
    _row(b, slug)["sets"] = ["1", "1", "2"]
    _row(b, slug)["filler"] = [False] * 3
    _owned(_row(c, slug), ["1", "1", "encore"])
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "taper_changes.txt").read_text()
    renamed = text.split("== labels renamed")[1].split("\n== ")[0]
    moved = text.split("== songs moved")[1].split("\n== ")[0]
    assert slug not in renamed and slug in moved
    row = [l for l in moved.splitlines() if slug in l][0]
    assert "before [2] after [2]" in row
    assert "before 1x2 2x1 | after 1x2 encorex1 | stored 1x2 2x1" in row


def test_provenance_only_row_says_step1_not_overruled(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    slug = "show-prov2"
    for arm in (b, c):
        _clone(arm, CLEAN_SLUG, slug, "packaged")
        _row(arm, slug).update(outcome="clears", set_changes=[], segue_changes=[], notes=[])
    (root / "shows" / slug).mkdir(parents=True)
    (root / "shows" / slug / "show.json").write_text(json.dumps(
        {"tracks": [{"index": i + 1, "set": s} for i, s in enumerate(["1", "2"])]}))
    _row(b, slug)["sets"] = ["1", "2"]
    _owned(_row(c, slug), ["1", "2"], step1="jerrybase")
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    row = [l for l in (out / "taper_changes.txt").read_text().splitlines() if slug in l][0]
    assert "step1 mechanism: jerrybase" in row and "overruled" not in row
    assert "step1: " not in row


def test_stored_llm_section_excludes_an_unreplayable_candidate(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    for arm in (b, c):
        _clone(arm, CLEAN_SLUG, "llm-unrep", "packaged")
    _row(b, "llm-unrep").update(outcome="needs-llm", needs_llm=["stored alignment llm"])
    _row(c, "llm-unrep").update(outcome="unreplayable", unreplayable="cache miss: z")
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "taper_changes.txt").read_text()
    assert "stored-llm shows now replayable (0)" in text


def test_compare_refuses_a_missing_config_before_writing_and_summary_names_delivery(tmp_path, capsys):
    base, cand = _two_arms(tmp_path)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out),
                    "--config", str(tmp_path / "nope.toml")]) == 2
    assert "no such config" in capsys.readouterr().err
    assert not out.exists()
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    assert "voiced check: off (no delivery_path in config)" in (out / "summary.txt").read_text()
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'delivery_path = "{tmp_path / "st"}"\n')
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--config", str(cfg)]) == 0
    assert f"voiced check: delivery_path {tmp_path / 'st'}" in (out / "summary.txt").read_text()


def test_taper_changes_segues_changed_tier(tmp_path):
    # R1 (pre3-llm): labels unchanged but segues changed is its own tier, between filler
    # labels only and provenance only, with each row's segue changes and a summary count.
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    lost = [{"index": 2, "old": True, "new": False}]
    for slug in ("seg-llm", "seg-det", "seg-same", "prov-only"):
        for arm in (b, c):
            _clone(arm, CLEAN_SLUG, slug, "packaged")
            _row(arm, slug).update(outcome="clears", set_changes=[], segue_changes=[], notes=[])
        (root / "shows" / slug).mkdir(parents=True)
        (root / "shows" / slug / "show.json").write_text(json.dumps(
            {"tracks": [{"index": i + 1, "set": s} for i, s in enumerate(["1", "1", "2"])]}))
        _owned(_row(c, slug), ["1", "1", "2"])
    # a stored-llm show: the base is needs-LLM, so "before" is stored (no segue change).
    # Its row still carries the step-1 segue diff `compute_legs` computed before marking it
    # needs-LLM, the same one as the candidate's: the realistic shape (t9-rev, M1).
    _row(b, "seg-llm").update(outcome="needs-llm", needs_llm=["stored alignment llm"])
    _row(b, "seg-llm")["segue_changes"] = lost
    _row(c, "seg-llm")["segue_changes"] = lost
    # a replayed base whose segues differ from the candidate's
    _row(b, "seg-det")["sets"] = ["1", "1", "2"]
    _row(c, "seg-det")["segue_changes"] = lost
    # the same segue change in both arms: base drift, not this piece
    for arm in (b, c):
        _row(arm, "seg-same")["segue_changes"] = lost
    _row(b, "seg-same")["sets"] = ["1", "1", "2"]
    _row(b, "prov-only")["sets"] = ["1", "1", "2"]
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--no-repro-gate"]) == 0
    text = (out / "taper_changes.txt").read_text()
    assert text.index("== filler labels only") < text.index("== segues changed") < text.index(
        "== provenance only")
    seg = text.split("== segues changed")[1].split("\n== ")[0]
    prov = text.split("== provenance only")[1].split("\n== ")[0]
    assert "seg-llm" in seg and "seg-det" in seg
    assert "seg-same" in prov and "prov-only" in prov
    assert "seg-llm" not in prov and "seg-det" not in prov
    row = [l for l in seg.splitlines() if "seg-llm" in l][0]
    assert 'segue changes: before [] after [{"index": 2' in row
    assert "segue changes" not in prov
    assert "segues changed 2" in (out / "summary.txt").read_text()


# --- Task 19 (piece 3): acceptance reports -----------------------------------------------------

def _stored(root, slug, titles):
    d = root / "shows" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "show.json").write_text(json.dumps({"tracks": [
        {"index": i + 1, "title": t, "title_source": "tags"} for i, t in enumerate(titles)]}))


def _p3(arm, slug, src, state, **row):
    """A clone of the clean row in `arm` standing for a piece-3 row."""
    _clone(arm, src, slug, state)
    r = _row(arm, slug)
    r.update(outcome="clean", set_changes=[], segue_changes=[], title_changes=[], notes=[],
             gather_flags=[], vet_flags=[], brief_flags=[], needs_llm=[], cascade={},
             titles=[], title_sources=[], title_paths=[])
    r.update(row)
    return r


def test_holds_delta_three_way_split(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    # held now: base still-held -> cand clears (slice 2 fills); fresh-get: a shipped show whose
    # overrides masked a hold in the stripped arm; currently packaged: a packaged show with a hold.
    for arm, out in ((b, "still-held"), (c, "clears")):
        _p3(arm, "held-now", CLEAN_SLUG, "held", outcome=out,
            cascade={"d_fills": [1, 2]} if arm is c else {})
    for arm, out in ((b, "newly-held"), (c, "clean")):
        _p3(arm, "fresh", CLEAN_SLUG, "packaged", outcome=out, stripped={"titles": {"1": "x"}},
            gather_flags=["unresolved track titles"] if arm is b else [],
            cascade={"c_changed": {"2": "T"}} if arm is c else {})
        _p3(arm, "pkg", CLEAN_SLUG, "packaged", outcome=out,
            gather_flags=["unresolved track titles"] if arm is b else [],
            cascade={"short4": [3], "s_fills": [1]} if arm is c else {})
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "holds_delta.txt").read_text()
    sec = {}
    cur = None
    for ln in text.splitlines():
        if ln.startswith("-- "):
            cur = ln[3:].split(" (")[0]
            sec[cur] = []
        elif cur and ln.startswith("  "):
            sec[cur].append(ln)
    assert any("held-now" in l and "slice2" in l for l in sec["held now"])
    assert any("fresh " in l + " " and "slice3" in l for l in sec["would-hold on a fresh get"])
    assert any("pkg" in l and "slice1" in l and "slice4" in l for l in sec["currently shipped"])
    assert not any("pkg" in l for l in sec["held now"])
    assert "holds cleared" in text


def test_holds_added_by_flag_and_state(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    for slug, state in (("add-pkg", "packaged"), ("add-del", "delivered")):
        _p3(b, slug, CLEAN_SLUG, state)
        _p3(c, slug, CLEAN_SLUG, state, outcome="newly-held",
            gather_flags=["unresolved track titles"], cascade={"d_failed": "tape agreement"})
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "holds_delta.txt").read_text()
    added = text.split("== holds added")[1]
    assert "-- packaged (1)" in added and "-- delivered (1)" in added
    row = [l for l in added.splitlines() if "add-pkg" in l][0]
    assert "unresolved track titles" in row


def test_added_hold_attributed_from_declines(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    _p3(b, "decl", CLEAN_SLUG, "packaged")
    _p3(c, "decl", CLEAN_SLUG, "packaged", outcome="newly-held", title_paths=[],
        gather_flags=["unresolved track titles"], cascade={"d_failed": "tape agreement"})
    _p3(b, "multi", CLEAN_SLUG, "packaged")
    _p3(c, "multi", CLEAN_SLUG, "packaged", outcome="newly-held", title_paths=[],
        gather_flags=["unresolved track titles"],
        cascade={"s_declined": [2], "c_declined": "x", "short4_declined": {"3": "nb"}})
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "holds_delta.txt").read_text()
    by = text.split("== holds added by slice")[1]
    s2 = by.split("slice2")[1].split("slice")[0]
    assert "decl" in s2
    for s in ("slice1", "slice3", "slice4"):
        assert "multi" in by.split(s)[1].split("slice")[0]


def test_title_changes_text_vs_source_only(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    _stored(root, "chg", ["Track 01", "Same", "Foo"])
    _p3(b, "chg", CLEAN_SLUG, "packaged")
    _p3(c, "chg", CLEAN_SLUG, "packaged", outcome="clean-changed",
        titles=["Dark Star", "Same", "Foo"], title_sources=["desc-position", "tags", "setlist"],
        title_paths=["D", "", "S+5"])
    # stored 'Foo' came from 'tags'; replayed 'Foo' now 'setlist' -> source only
    out = tmp_path / "cmp"
    _write(base, b)
    _write(cand, c)
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "title_changes.txt").read_text()
    text_part, src_part = text.split("-- source only")
    assert "chg" in text_part and "'Track 01'" in text_part and "'Dark Star'" in text_part
    assert "chg" in src_part and "'Foo'" in src_part and "'Track 01'" not in src_part
    assert "by path" in text and "D 1" in text


def test_voiced_marked_from_station_manifest(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    st = tmp_path / "station"
    for slug, voiced in (("v-yes", True), ("v-no", False)):
        _stored(root, slug, ["A"])
        _p3(b, slug, CLEAN_SLUG, "delivered")
        _p3(c, slug, CLEAN_SLUG, "delivered", outcome="clean-changed", titles=["B"],
            title_sources=["tags"], title_paths=["C1"])
        (st / slug).mkdir(parents=True)
        (st / slug / "manifest.json").write_text(json.dumps({"dj_audio": {"x": 1} if voiced else None}))
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'delivery_path = "{st}"\n')
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out), "--config", str(cfg)]) == 0
    text = (out / "title_changes.txt").read_text()
    assert "== voiced" in text and "== delivered" in text
    voiced_part = text.split("== voiced")[1].split("== delivered")[0]
    assert "v-yes" in voiced_part and "v-no" not in voiced_part
    assert "v-no" in text.split("== delivered")[1]


def test_needs_llm_counts_d_agreement_and_llm_branch(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    _p3(b, "agree", CLEAN_SLUG, "held", outcome="still-held")
    _p3(c, "agree", CLEAN_SLUG, "held", outcome="still-held",
        cascade={"d_failed": "agreement"})
    _p3(b, "llmb", CLEAN_SLUG, "held", outcome="needs-llm", needs_llm=["align_structure"])
    _p3(c, "llmb", CLEAN_SLUG, "held", outcome="needs-llm", needs_llm=["align_structure"],
        desc_position=4)
    _p3(b, "plain", CLEAN_SLUG, "held", outcome="needs-llm", needs_llm=["align_structure"])
    _p3(c, "plain", CLEAN_SLUG, "held", outcome="needs-llm", needs_llm=["align_structure"])
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "needs_llm.txt").read_text()
    d = text.split("D shows reaching")[1]
    assert "agreement decline: 1" in d and "LLM branch: 1" in d
    assert "agree" in d and "llmb" in d and "plain" not in d
    assert "needs_llm.txt: base" in (out / "summary.txt").read_text()


def test_note_groups_for_piece3():
    names = [g for g, _ in rh.NOTE_GROUPS]
    for g in ("positional", "lossless", "short4", "cosmetic"):
        assert g in names
    arm = {"shows": {"s": {"notes": [
        "positional fill declined: desc-position tape agreement (track 3 'x')",
        "lossless title: track 2 'a' -> 'b' (C1)", "lossless titles declined: no sibling",
        "short tag title confirmed by the taper's list: track 4 'J'",
        "cosmetic title strip: track 1 'a' -> 'b'", "something else"]}}}
    g = rh._notes_by_group(arm)
    assert len(g["positional"]) == 1 and len(g["lossless"]) == 2
    assert len(g["short4"]) == 1 and len(g["cosmetic"]) == 1 and len(g["other"]) == 1


def test_disable_slices_stamped_and_applied(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    build_library(root)
    seen = []
    real = rh.replay_show

    def spy(ws, **kw):
        seen.append(kw.get("enabled_slices"))
        return real(ws, **kw)

    monkeypatch.setattr(rh, "replay_show", spy)
    before = rh.title_hygiene.ENABLED_SLICES
    out = tmp_path / "arm.json"
    cfg = str(root / "config.toml")
    assert rh.main(["run", "--out", str(out), "--all", "--config", cfg,
                    "--disable-slices", "slice5,slice4"]) == 0
    assert seen and all(s == before - {"slice4", "slice5"} for s in seen)
    assert rh.title_hygiene.ENABLED_SLICES == before      # no module global rebound
    assert json.loads(out.read_text())["disabled_slices"] == ["slice4", "slice5"]
    out2 = tmp_path / "arm2.json"
    assert rh.main(["run", "--out", str(out2), "--all", "--config", cfg]) == 0
    assert json.loads(out2.read_text())["disabled_slices"] == []
    assert seen[-1] == before
    assert rh.main(["run", "--out", str(tmp_path / "x.json"), "--all", "--config", cfg,
                    "--disable-slices", "slice9"]) == 2


def test_title_rows_newly_cleared_uses_the_holds_delta_predicate(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    _p3(b, "sc-self", CLEAN_SLUG, "held", outcome="still-held")
    _p3(c, "sc-self", CLEAN_SLUG, "held", outcome="structure-changed", self_filled=True,
        cascade={"d_fills": [1, 2]})
    _p3(b, "fresh-clr", CLEAN_SLUG, "packaged", outcome="newly-held",
        gather_flags=["unresolved track titles"])
    _p3(c, "fresh-clr", CLEAN_SLUG, "packaged", outcome="clean-changed")
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    rows = json.loads((out / "title_rows.json").read_text())["shows"]
    assert rows["sc-self"]["newly_cleared"] and rows["fresh-clr"]["newly_cleared"]
    assert "sc-self" in (out / "holds_delta.txt").read_text()
    # and the probe puts them in the strata
    import title_hygiene_probe as thp
    dump = tmp_path / "dump.jsonl"
    row = lambda s, w: {"slug": s, "unreplayable": None, "identifier": "i", "description": "d",  # noqa: E731
                        "today": [], "canonical": {}, "arms": {"all": {"tracks": [], "record": {"wholly_untagged": w}}}}
    dump.write_text("\n".join(json.dumps(x) for x in [{"_meta": {}}, row("sc-self", True),
                                                      row("fresh-clr", False)]) + "\n")
    pk = tmp_path / "pk"
    assert thp.main(["packets", "--cmp", str(out), "--dump", str(dump), "--out", str(pk)]) == 0
    assert (pk / "wholly_untagged_d3" / "sc-self.md").exists()
    assert (pk / "newly_cleared_sample" / "fresh-clr.md").exists()


def test_needs_llm_counts_as_a_hold_added_in_any_state(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    _p3(b, "pk-llm", CLEAN_SLUG, "packaged", outcome="clean")
    _p3(c, "pk-llm", CLEAN_SLUG, "packaged", outcome="needs-llm", needs_llm=["align_structure"])
    _p3(b, "was-llm", CLEAN_SLUG, "packaged", outcome="needs-llm")
    _p3(c, "was-llm", CLEAN_SLUG, "packaged", outcome="needs-llm")
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    added = (out / "holds_delta.txt").read_text().split("== holds added")[1]
    assert any("pk-llm" in l and "(needs-llm)" in l for l in added.splitlines())
    assert "was-llm" not in added


def test_cosmetic_only_clear_is_slice5_and_unreplayable_rows_are_skipped(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    b, c = json.loads(base.read_text()), json.loads(cand.read_text())
    _p3(b, "cos", CLEAN_SLUG, "packaged", outcome="newly-held")
    _p3(c, "cos", CLEAN_SLUG, "packaged", outcome="clean", title_paths=["", "+5"])
    _stored(root, "unrep", ["A"])
    _p3(b, "unrep", CLEAN_SLUG, "packaged", outcome="unreplayable")
    _p3(c, "unrep", CLEAN_SLUG, "packaged", outcome="clean-changed", titles=["B"], title_sources=["tags"])
    _write(base, b)
    _write(cand, c)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    assert "cos  [packaged]  slices: slice5" in (out / "holds_delta.txt").read_text()
    assert "unrep" not in (out / "title_changes.txt").read_text()
    s = (out / "summary.txt").read_text()
    assert "voiced check" in s and "empty in an as-is arm" in s


def test_disable_slices_refuses_a_slice_not_enabled():
    assert rh._parse_disabled("slice1", enabled=frozenset({"slice1"})) == frozenset({"slice1"})
    with pytest.raises(rh.Refusal, match="not enabled"):
        rh._parse_disabled("slice2", enabled=frozenset({"slice1"}))


def test_title_rows_records_the_arm_view(tmp_path):
    base, cand, root = _clone_slugs(tmp_path, None)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    assert json.loads((out / "title_rows.json").read_text())["view"].startswith("as-is")
