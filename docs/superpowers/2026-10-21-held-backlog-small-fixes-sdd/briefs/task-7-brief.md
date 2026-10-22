### Task 7: Slice C, triage edits as units

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`_interactive_resolve`, `_metadata_editor`)
- Modify: `packages/llama/tests/test_triage.py` (the new tests)
- Modify: `CLAUDE.md` (one sentence on `llama triage` in Commands)
- Test: `packages/llama/tests/test_triage.py`

**Interfaces:**
- Consumes: Task 4's `capture_view`, `show_unit`. Task 5's `_redo_show_locked`. `_resolve_show`. Task 6's `_untitled_resolution(config, ia, ledger, entry, show, view)`.
- Produces: `cli._metadata_editor(entry) -> dict | None`. It returns the `_edit_overrides` keyword arguments (everything except `show_ws`) without writing anything, or None when nothing changed or the input was invalid (today's echo texts unchanged). Plan's call: the editor stops writing, so the write moves into the unit.

Behaviour:
- At the start of each show's turn, before `_print_show_entry`, re-resolve the entry with `entry = _resolve_show(config, ledger, str(entry.ws.dir))` (the path form is an exact match while the directory exists, and a removed show matches nothing, so it never lands on a show whose slug merely contains this one) and take `view = capture_view(entry.ws)` from it. The held check and the `[t]`/`[i]`/`[u]` offers read the fresh entry. The view is kept for the whole show session, with a one-line comment: every successful edit leaves the show, so the session-long view stays valid.
- Plan's call: if the re-resolve raises `LlamaError` (the show was removed since the listing), print `f"error: {exc}"` to stderr and move on to the next show.
- Each branch runs its prompts with no lock held (`_pick_excludes`, `_pick_includes` + `_split_include_targets`, `_metadata_editor`, `_propose_and_confirm_titles`, `[u]`'s confirmation inside `_untitled_resolution`). It then builds the edit as a no-argument callable plus the stage, for example `lambda: _edit_overrides(entry.ws, add_exclude=files)` with `"gather"`, or `[o]` as `lambda: _clear_hold(entry.ws)` with `"package"`.
- The common tail is `with show_unit(entry.ws, view): edit(); echo-if-any; pkg = _redo_show_locked(config, ia, ledger, entry, stage)`, then, after the block exits, today's `packaged:`/`still held:` and `return`. The echo inside the block comes before the redo's writes, so it is never after the last show write.
- `except (LlamaError, HerderError) as exc:` prints `f"error: {exc}"` to stderr and `continue`s to the same show's prompt. `ShowChanged`, `IAError`, `TaskFailed` and `RateLimited` all fall in these two classes.
- `KeyboardInterrupt` and any other exception propagate after the restore, ending the walkthrough. `[u]` is wrapped in the same `try`.
- Plan's call: the view is not re-captured after a failure. A show that another command changed keeps refusing until the operator skips it and re-runs triage, so nothing is applied against content the operator was not shown.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_failed_triage_edit_prints_the_error_restores_and_returns_to_the_prompt(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); before = tree_bytes(ws.dir)
    monkeypatch.setattr(cli, "_redo_show_locked", lambda *a, **k: (_ for _ in ()).throw(LlamaError("boom")))
    r = cli_invoke(cfg, "triage", input="o\ns\n")
    assert r.exit_code == 0, r.output
    assert "error: boom" in r.output and r.output.count(PROMPT) == 2
    assert tree_bytes(ws.dir) == before            # still held

def test_a_triage_edit_whose_show_changed_meanwhile_refuses_and_changes_nothing(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); calls = _stub_redo(monkeypatch)
    def picker(show):
        write_artifact(ws.overrides, Overrides(exclude=["other.mp3"])); return ["a.mp3"], False
    monkeypatch.setattr(cli, "_pick_excludes", picker)
    r = cli_invoke(cfg, "triage", input="e\ns\n")
    assert "changed by another command; run it again" in r.output
    assert read_overrides(ws).exclude == ["other.mp3"] and calls == []

def test_triage_prompts_are_answered_without_the_show_lock(tmp_path, tty, monkeypatch):   # (pin)
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path); _stub_redo(monkeypatch); seen = []
    def picker(show):
        with file_lock(ws.lock, blocking=False):
            seen.append("free")
        return ["a.mp3"], False
    monkeypatch.setattr(cli, "_pick_excludes", picker)
    assert cli_invoke(cfg, "triage", input="e\n").exit_code == 0 and seen == ["free"]

def _second_held_show(tmp_path):
    return build(tmp_path, "gratefuldead-1974-01-01", stages={"select", "gather"}, needs_review=True,
                 pid="GratefulDead/1974-01-01")

def test_ctrl_c_in_a_triage_edit_restores_and_ends_the_walkthrough(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); shows = [_held_show(tmp_path), _second_held_show(tmp_path)]
    before = [tree_bytes(ws.dir) for ws in shows]
    monkeypatch.setattr(cli, "_redo_show_locked", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    r = cli_invoke(cfg, "triage", input="v\ns\n")
    assert r.exit_code != 0 and r.output.count(PROMPT) == 1      # the second show is never offered
    assert [tree_bytes(ws.dir) for ws in shows] == before

def test_a_successful_triage_edit_moves_on_to_the_next_show(tmp_path, tty, monkeypatch):   # (pin)
    cfg = _cfg(tmp_path); _held_show(tmp_path); _second_held_show(tmp_path); calls = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "triage", input="o\ns\n")
    assert r.exit_code == 0, r.output
    assert r.output.count(PROMPT) == 2 and calls == ["package"]

def test_a_retry_after_a_failed_edit_applies_against_the_restored_show(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); _held_show(tmp_path); outcomes = iter([LlamaError("boom"), Path("/pkg")])
    def fake(config, ia, ledger, e, stage, **kw):
        out = next(outcomes)
        if isinstance(out, Exception):
            raise out
        return out
    monkeypatch.setattr(cli, "_redo_show_locked", fake)
    r = cli_invoke(cfg, "triage", input="o\no\n")
    assert "error: boom" in r.output and "packaged: /pkg" in r.output
    assert "changed by another command" not in r.output

def test_a_show_removed_before_its_turn_is_reported_and_skipped(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); _held_show(tmp_path); second = _second_held_show(tmp_path)
    def fake(config, ia, ledger, e, stage, **kw):
        shutil.rmtree(second.dir); return Path("/pkg")   # another command removes the next show
    monkeypatch.setattr(cli, "_redo_show_locked", fake)
    r = cli_invoke(cfg, "triage", input="o\n")
    assert r.exit_code == 0, r.output
    assert "error: " in r.output and r.output.count(PROMPT) == 1

def test_a_failed_metadata_edit_restores_the_overrides(tmp_path, tty, monkeypatch):
    cfg = _cfg(tmp_path); ws = _held_show(tmp_path)
    monkeypatch.setattr(cli, "_redo_show_locked", lambda *a, **k: (_ for _ in ()).throw(LlamaError("refused")))
    r = cli_invoke(cfg, "triage", input="m\nNew Hall\n\n\n\n\ns\n")
    assert "error: refused" in r.output and not ws.overrides.exists()
```
(Imports: `import shutil`, `from helpers import tree_bytes`, `from llama.errors import LlamaError`, `from llama.locks import file_lock`, `from llama.models import Overrides`. `build` and `Path` are already imported. The second show gets its own `pid=` because `build`'s default pid is the first show's.)

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_triage.py -q`
Expected: the new tests FAIL, except the two **(pin)** tests, which pass. The error escapes triage instead of returning to the prompt, nothing restores, and `_metadata_editor` writes before the redo.

- [ ] **Step 3: Implement `_interactive_resolve`/`_metadata_editor` as specified above**

Add to `CLAUDE.md`'s `llama triage` entry: "each edit is one unit like `fix`'s. A failure prints `error: …`, restores the show and returns to the same show's prompt. Ctrl-C ends the walkthrough after the restore."

- [ ] **Step 4: Run the file's tests, then the full suite**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_triage.py packages/llama/tests/test_cli.py -q`, then `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_triage.py CLAUDE.md
git commit -m "feat(triage): edits run as restoring units and a failure returns to the prompt (slice C)"
```

---

