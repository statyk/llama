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
    assert rh.main(["run", "--out", str(tmp_path / "arm.json"), "--all",
                    "--config", str(root / "config.toml")]) == 0
    assert seen == [logging.CRITICAL, logging.CRITICAL]
    assert logging.root.manager.disable == logging.NOTSET
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
    base, cand = _two_arms(tmp_path, needs_llm_hold, needs_llm_hold)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0   # 1/1, not 1/2
    assert "gratefuldead-1973-06-11" not in (out / "drift.txt").read_text()
    assert "gratefuldead-1973-06-11" in (out / "needs_llm.txt").read_text()
    assert "needs-LLM held: base 1, cand 1" in (out / "summary.txt").read_text()


def test_compare_counts_an_unreadable_state_unreplayable_row_as_not_reproducing(tmp_path, capsys):
    def unknown(arm):
        s = arm["shows"]["gratefuldead-1973-06-11"]
        s["state"], s["outcome"], s["reproduces"] = "unknown", "unreplayable", False
    base, cand = _two_arms(tmp_path, unknown, unknown)
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
    base, cand = _two_arms(tmp_path, cand_holds, both)
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
