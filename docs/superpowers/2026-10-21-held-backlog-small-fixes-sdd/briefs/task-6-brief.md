### Task 6: Slice C, `llama fix` as one unit; edits on a show with no `show.json`

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`fix`, `_untitled_resolution`)
- Modify: `packages/llama/tests/test_fix.py` (retarget `_stub_redo` and the two inline `monkeypatch.setattr(cli, "_redo_show", ...)` calls to `_redo_show_locked`, plus the new tests)
- Modify: `packages/llama/tests/test_triage.py` (`_stub_redo` retargeted to `_redo_show_locked`; see Step 3)
- Modify: `CLAUDE.md` (the `llama fix` entry in Commands)
- Test: `packages/llama/tests/test_fix.py`

**Interfaces:**
- Consumes: Task 4's `ShowView`, `capture_view`, `show_unit`, `ShowChanged`. Task 5's `_redo_show_locked`, `helpers.packaged_gd73`, `helpers.tree_bytes`. `test_cli._staged_ymsb_show` (24-track ymsb show).
- Produces: `cli._untitled_resolution(config, ia, ledger, entry, show: Show, view: ShowView) -> tuple[Literal["declined", "held", "packaged"], Path | None]`. It lists the tracks and confirms with no lock held, then runs in one `show_unit(entry.ws, view)`: `_edit_overrides(...)`, `_redo_show_locked(..., "gather")`, and if that returns None, `_clear_hold` followed by `_redo_show_locked(..., "brief")`. Task 7 calls it with triage's view.

New order inside `fix`:
1. `entry = _resolve_show(...)`, then `view = capture_view(sws)` immediately.
2. Today's argument-only refusals (flag combinations, parse errors), unchanged.
3. State gates and prompts, with no lock held:
   - `--untitled`: today's checks, then `_untitled_resolution(..., view)`.
   - `--suggest-titles`: today's checks, then `_propose_and_confirm_titles`.
   - `nothing to fix`.
   - The C4 gate. When `show.json` is absent, refuse `--narration`, `--overrule` and `--include` (and `--untitled`/`--suggest-titles` in their branches) with `f"no show.json in {sws.dir} (state: {entry.state}); rebuild it with: llama redo {entry.slug} --from gather"`, exit 1. `--set-*`/`--clear-*` and `--exclude`/`--unexclude` pass. A track-number `--exclude` keeps `_resolve_exclude_tokens`' own message (plan's call: it already names a remedy).
   - Plan's call: refusals that write nothing may stay before the lock, because the unit's view check re-verifies the state they judged.
4. `with show_unit(sws, view):` everything that writes, in today's order: token resolution and the `--exclude`/`--include` clash check (still `typer.Exit(1)` with today's text, which now also restores), `_split_include_targets` only when `inc` is non-empty (it reads `show.json` unconditionally, `cli.py:1467-1470`, and the no-`show.json` `--exclude <file>` test depends on skipping it), `_edit_overrides`, `_clear_hold`, then, unless `--no-run`, `_redo_show_locked(config, ia, ledger, entry, stage)`. The edit lines (today's echo text) are collected inside the unit, not printed there (plan's call: with `--no-run` they would otherwise follow the last show write).
5. After the block exits: the collected edit lines, then `staged; next: ...` (`--no-run`) or `packaged:`/`still held:`.
6. A failure propagates. `main_cli` prints `error: <msg>` and exits 1. Under `CliRunner`, that shows as `r.exit_code == 1` with `r.exception` set.

- [ ] **Step 1: Retarget the existing stubs, then write the failing tests**

Change `_stub_redo` and the inline stubs (around the `test_apply_prints_still_held_when_redo_returns_none` and `test_untitled_overrules_remaining_flags_then_continues_from_brief` tests) to patch `"_redo_show_locked"`. They stay green: after Task 5, `fix` still calls `_redo_show`, which calls the module-global `_redo_show_locked`, so the retargeted stubs are reached.

New tests (`from helpers import packaged_gd73, tree_bytes`; `from test_cli import _staged_ymsb_show`):
```python
def _billy_shape(tmp_path, monkeypatch):
    """The billystrings-2021-12-04 sequence on a real 24-track tape: overrides already
    carrying edits, then the bad structure fix (pre-repair overrides set_breaks [10, 20],
    encore_after 20)."""
    from test_pipeline import fake_providers
    (tmp_path / "config.toml").write_text(f'root = "{tmp_path}"\n\n[jerrybase]\nenabled = false\n')
    sws = _staged_ymsb_show(tmp_path, monkeypatch)
    write_artifact(sws.selection, {"identifier": "ymsb2005-12-31.flac16.wav"})
    write_artifact(sws.overrides, Overrides(narration="vague", titles={1: "Kirby Hill"}))
    monkeypatch.setattr(cli, "make_providers", fake_providers)
    return tmp_path / "config.toml", sws

def test_a_refused_structure_fix_leaves_every_file_byte_identical(tmp_path, monkeypatch):
    cfg, sws = _billy_shape(tmp_path, monkeypatch); before = tree_bytes(sws.dir)
    r = cli_invoke(cfg, "fix", "ymsb", "--set-breaks", "10,20", "--set-encore", "20")
    assert r.exit_code == 1 and isinstance(r.exception, LlamaError)
    assert "overrides.encore_after (20) must be greater than every set break [10, 20]" in str(r.exception)
    assert tree_bytes(sws.dir) == before            # provenance.json and overrides.json included
    r2 = cli_invoke(cfg, "fix", "ymsb", "--clear-encore", "--no-run")   # still editable afterwards
    assert r2.exit_code == 0, r2.output

def test_no_run_stages_bad_overrides_and_the_redo_restores_and_names_the_field(tmp_path, monkeypatch):   # C3
    cfg, sws = _billy_shape(tmp_path, monkeypatch)
    assert cli_invoke(cfg, "fix", "ymsb", "--set-breaks", "10,20", "--set-encore", "20", "--no-run").exit_code == 0
    assert read_overrides(sws).encore_after == 20
    before = tree_bytes(sws.dir)
    r = cli_invoke(cfg, "redo", "ymsb", "--from", "gather")
    assert r.exit_code == 1 and "encore_after" in str(r.exception) and tree_bytes(sws.dir) == before

def test_a_fix_adding_one_override_keeps_the_others(tmp_path, monkeypatch):   # (pin)
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); _stub_redo(monkeypatch)
    write_artifact(ws.overrides, Overrides(exclude=["junk.mp3"], venue="Hall", titles={2: "Dew"}, narration="vague"))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-city", "Austin, TX").exit_code == 0
    ov = read_overrides(ws)
    assert (ov.exclude, ov.venue, ov.titles, ov.narration, ov.city) == (["junk.mp3"], "Hall", {2: "Dew"}, "vague", "Austin, TX")

def _held(ws):
    s = read_model(ws.show, Show); s.needs_review = True; s.review_flags = ["research asserts wrong date: 1974-01-01"]
    write_artifact(ws.show, s)

def test_failed_accept_vague_restores_the_hold_and_the_overrides(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); _held(ws); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_brief", lambda *a, **k: (_ for _ in ()).throw(RateLimited("limit")))
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague")
    assert r.exit_code == 1 and isinstance(r.exception, RateLimited)
    assert tree_bytes(ws.dir) == before and read_model(ws.show, Show).needs_review is True

def test_failed_overrule_restores_every_file(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); _held(ws); before = tree_bytes(ws.dir)
    monkeypatch.setattr(pipeline, "run_package", lambda *a, **k: (_ for _ in ()).throw(IAError("archive down")))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--overrule").exit_code == 1
    assert tree_bytes(ws.dir) == before

def test_a_multi_flag_fix_whose_redo_fails_leaves_nothing_of_the_first_edits(tmp_path, monkeypatch):
    cfg, ws = packaged_gd73(tmp_path, monkeypatch); _held(ws); before = tree_bytes(ws.dir)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--narration", "vague", "--set-breaks", "2,4", "--set-encore", "4")
    assert r.exit_code == 1 and "encore_after" in str(r.exception)
    assert tree_bytes(ws.dir) == before            # no narration, no cleared hold, no breaks

def test_a_failed_first_edit_removes_the_overrides_file_it_created(tmp_path, monkeypatch):   # Review Focus 2
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); assert not ws.overrides.exists()
    monkeypatch.setattr(cli, "_redo_show_locked", lambda *a, **k: (_ for _ in ()).throw(LlamaError("boom")))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "Hall").exit_code == 1
    assert not ws.overrides.exists()

def test_fix_writes_overrides_under_the_show_lock(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); seen = []; real = cli._edit_overrides
    def probe(show_ws, **kw):
        try:
            with file_lock(show_ws.lock, blocking=False): seen.append("free")
        except Locked:
            seen.append("held")
        return real(show_ws, **kw)
    monkeypatch.setattr(cli, "_edit_overrides", probe)
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "Hall", "--no-run").exit_code == 0
    assert seen == ["held"]

def test_fix_refuses_when_the_show_changed_after_the_prompt(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); calls = _stub_redo(monkeypatch)
    def other_command_meanwhile(ia, config, entry, show):
        write_artifact(entry.ws.overrides, Overrides(venue="Elsewhere")); return {1: "Dew"}
    monkeypatch.setattr(cli, "_propose_and_confirm_titles", other_command_meanwhile)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--suggest-titles")
    assert r.exit_code == 1 and "changed by another command; run it again" in str(r.exception)
    assert read_overrides(ws) == Overrides(venue="Elsewhere") and calls == []

def test_untitled_failure_after_the_overrule_restores_everything(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path); ws = _all_unresolved_show(tmp_path); before = tree_bytes(ws.dir)
    def fake(config, ia, ledger, e, stage, **kw):
        if stage == "gather":
            s = read_model(e.ws.show, Show); s.needs_review = True; s.review_flags = ["x"]; write_artifact(e.ws.show, s)
            return None
        raise LlamaError("brief failed")
    monkeypatch.setattr(cli, "_redo_show_locked", fake)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--untitled", input="y\n")
    assert r.exit_code == 1 and tree_bytes(ws.dir) == before

def test_fix_on_a_show_with_no_show_json_takes_metadata_and_filename_edits(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select"})
    write_artifact(ws.overrides, Overrides(set_breaks=[10, 20], encore_after=20))
    assert cli_invoke(cfg, "fix", "gratefuldead", "--clear-encore", "--no-run").exit_code == 0
    assert read_overrides(ws).encore_after is None
    assert cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "junk.mp3", "--no-run").exit_code == 0
    calls = _stub_redo(monkeypatch)
    assert cli_invoke(cfg, "fix", "gratefuldead", "--set-venue", "Hall").exit_code == 0 and calls == ["gather"]

@pytest.mark.parametrize("args", [["--overrule"], ["--narration", "vague"], ["--include", "junk.mp3"],
                                  ["--suggest-titles"], ["--untitled"]])
def test_fix_on_a_show_with_no_show_json_refuses_the_rest_and_names_the_remedy(tmp_path, args):
    cfg = _cfg(tmp_path); build(tmp_path, "gratefuldead-1973-06-10", stages={"select"})
    r = cli_invoke(cfg, "fix", "gratefuldead", *args)
    assert r.exit_code == 1 and "rebuild it with: llama redo gratefuldead-1973-06-10 --from gather" in r.output
```
(Imports needed: `import llama.pipeline as pipeline`, `from llama.errors import LlamaError`, `from llama.ia_client import IAError`, `from herder.limits import RateLimited`, `from llama.locks import Locked, file_lock`, `from test_catalog import build`. `_all_unresolved_show` already exists in this file.)

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_fix.py -q`
Expected: the new restore, lock, changed-view and no-`show.json` tests FAIL, because today the overrides are written and the files dropped with no restore, and every flag is refused without `show.json`. The pin and the retargeted existing tests pass.

- [ ] **Step 3: Implement `fix` and `_untitled_resolution` in the order specified above**

Triage's `[u]` branch also calls `_untitled_resolution`. In this task, pass it `capture_view(entry.ws)` so the suite stays green; Task 7 replaces that with the show session's view. Triage's other branches still call `_redo_show`, which now wraps its own unit, so they keep working until Task 7. Because `[u]` now calls `_redo_show_locked` directly, retarget `test_triage.py`'s `_stub_redo` to patch `_redo_show_locked` only: the other branches reach it through `_redo_show`, so one patch covers every branch, including the three `[u]` tests (`test_triage_offers_u_only_when_every_track_is_unresolved`, `test_triage_u_declined_writes_nothing_and_returns_to_the_prompt`, `test_triage_u_confirmed_but_still_held_says_still_held`). Add `packages/llama/tests/test_triage.py` to this task's `git add`.

Then replace the `llama fix <name> <edit-flags>` description in `CLAUDE.md`'s Commands with this addition (keep the existing text): "**One unit (2026-10-21):** `fix`, triage's edits and `redo` (single and batch, per show) each run as one unit under the show lock. `fix` and triage ask any prompts first with no lock held, then take the lock and refuse with `changed by another command; run it again` if `overrides.json`/`show.json` changed since (or `the show was removed`). `redo` shows nothing, so it reads the show once it holds the lock: it waits behind another writer rather than refusing, and refuses only a show removed meanwhile. Each unit snapshots every file outside `package/audio/` into `<show>/.txn/`, then does the work. Any exception, including Ctrl-C, restores those files byte-identical and removes new audio. A single `fix`/`redo` then exits 1 with the error. A stale `.txn/` (SIGKILL) is deleted, never restored, by the next unit. With no `show.json`, `fix` still accepts `--set-*`/`--clear-*` and filename `--exclude`/`--unexclude`. Every other flag refuses and names `llama redo <show> --from gather`, which is also the repair for any show left part-way. `--no-run` validates nothing: a later redo that refuses the overrides rolls back and names the field."

- [ ] **Step 4: Run the file's tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_fix.py packages/llama/tests/test_cli.py -q`, then `./.venv/bin/python -m pytest -q`
Expected: PASS. `test_cli.py`'s `--suggest-titles` tests are unchanged and green.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_fix.py packages/llama/tests/test_triage.py CLAUDE.md
git commit -m "feat(fix): one restoring unit per invocation; edits on a show with no show.json (slice C)"
```

---

