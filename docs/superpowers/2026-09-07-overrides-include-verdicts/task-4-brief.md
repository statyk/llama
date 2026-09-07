### Task 4: `llama fix --include`

**Files:**
- Modify: `packages/llama/src/llama/cli.py:1208-1228` (`_resolve_exclude_tokens` neighbourhood — add `_resolve_include_tokens`), `:1170-1206` (`_edit_overrides`), `:2255-2262` (the `fix` options), `:2327-2352` (the `--suggest-titles` refusal), `:2397-2420` (the exclude edit block)
- Test: `packages/llama/tests/test_fix.py`

**Interfaces:**
- Consumes: `_excluded_handles` (Task 3), `Overrides.include` (Task 1).
- Produces: `cli._resolve_include_tokens(show_ws, tokens) -> list[str]`; `_edit_overrides(..., add_include=())`; the `fix --include` option.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_fix.py`, reusing its `_cfg`,
`_gathered_show`, `_held_show` and `_stub_redo` helpers.

```python
# --- --include: re-admitting a junk-filtered file ---

def _show_with_excluded(tmp_path: Path):
    """A gathered show carrying three excluded files: two junk-filtered and one
    the operator excluded earlier (already in overrides.exclude)."""
    from llama.models import Overrides, Show
    from llama.workspace import read_model, write_artifact

    ws = _gathered_show(tmp_path)
    s = read_model(ws.show, Show)
    s.excluded_files = [
        {"filename": "intro.mp3", "reasons": ["implausibly short"], "duration_sec": 37.0},
        {"filename": "spam.mp3", "reasons": ["filename convention mismatch"],
         "duration_sec": 72.0},
        {"filename": "dropped.mp3", "reasons": ["operator-excluded"], "duration_sec": 300.0},
    ]
    write_artifact(ws.show, s)
    write_artifact(ws.overrides, Overrides(exclude=["dropped.mp3"]))
    return ws


def test_include_by_handle_writes_overrides_include(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    stages = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == ["intro.mp3"]
    assert stages == ["gather"]


def test_include_by_filename_and_comma_group(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1,spam.mp3")
    assert r.exit_code == 0, r.output
    assert read_overrides(ws).include == ["intro.mp3", "spam.mp3"]


def test_include_of_an_operator_excluded_file_unexcludes_it(tmp_path, monkeypatch):
    """Owner decision: --include is the single undo. On a row whose reason is
    operator-excluded it edits overrides.exclude, NOT overrides.include -- the
    two lists must never both name a file."""
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x3")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.exclude == []
    assert ov.include == []


def test_excluding_an_included_file_removes_it_from_include(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1")
    assert read_overrides(ws).include == ["intro.mp3"]
    r = cli_invoke(cfg, "fix", "gratefuldead", "--exclude", "intro.mp3")
    assert r.exit_code == 0, r.output
    ov = read_overrides(ws)
    assert ov.include == []
    assert ov.exclude == ["intro.mp3"]


def test_same_file_in_both_flags_errors(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    stages = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead",
                   "--include", "x1", "--exclude", "intro.mp3")
    assert r.exit_code != 0
    assert "name the same file" in r.output
    assert stages == []


def test_out_of_range_handle_errors(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x9")
    assert r.exit_code != 0
    assert "no excluded file x9" in r.output


def test_include_refuses_to_combine_with_suggest_titles(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    stages = _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--include", "x1", "--suggest-titles")
    assert r.exit_code != 0
    assert "--suggest-titles cannot be combined with" in r.output
    assert "--include" in r.output
    assert stages == []
```

Update the existing `test_old_show_flags_are_not_fix_flags`: `--include` is a
real `fix` flag again, with a **different** meaning from the old `llama show
--include` (which was an un-exclude and became `--unexclude` in the UX
redesign). Remove `("--include", "x.mp3")` from its list and leave a comment
saying so:

```python
    # `--include` is deliberately absent from this list: the UX redesign
    # renamed the old show-level `--include` (an un-exclude) to `--unexclude`,
    # and 2026-09-07 reintroduced `--include` on `fix` with its literal
    # meaning -- re-admit a file the junk filter dropped.
    for flag, value in [("--title", "1=Song")]:
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_fix.py -q
```

Expected: FAIL — `no such option: --include`.

- [ ] **Step 3: Add `_resolve_include_tokens`**

In `packages/llama/src/llama/cli.py`, immediately after
`_resolve_exclude_tokens`:

```python
_HANDLE = re.compile(r"x\d+")


def _resolve_include_tokens(show_ws, tokens) -> list[str]:
    """Expand comma groups and map `xN` handles to that excluded file's
    filename, via the same `_excluded_handles` numbering `show --tracks`
    prints. Non-handle tokens pass through as filenames."""
    parts = [p.strip() for tok in tokens for p in str(tok).split(",") if p.strip()]
    if not any(_HANDLE.fullmatch(p) for p in parts):
        return parts
    if not show_ws.show.exists():
        raise LlamaError("resolving an x-handle needs show.json; "
                         "reference the file by name instead")
    by_handle = {h: e["filename"]
                 for h, e in _excluded_handles(read_model(show_ws.show, Show))}
    out = []
    for p in parts:
        if _HANDLE.fullmatch(p):
            if p not in by_handle:
                raise LlamaError(
                    f"no excluded file {p} (show has {len(by_handle)} excluded files)")
            out.append(by_handle[p])
        else:
            out.append(p)
    return out
```

Add `import re` at the top of `cli.py` if it is not already imported.

- [ ] **Step 4: Teach `_edit_overrides` the include list**

Change the signature's first line to:

```python
def _edit_overrides(show_ws, *, add_exclude=(), rm_exclude=(), add_include=(),
                    narration=None,
```

and replace the exclude-building lines with:

```python
    # The two lists are mutually exclusive by construction: adding to one
    # removes from the other, so gather's "exclude wins" tiebreak (a defined
    # answer for a hand-mangled file) is never reached through the CLI.
    exclude = [f for f in ov.exclude if f not in set(rm_exclude) | set(add_include)]
    for f in add_exclude:
        if f not in exclude:
            exclude.append(f)
    include = [f for f in ov.include if f not in set(add_exclude)]
    for f in add_include:
        if f not in include:
            include.append(f)
```

and add `"include": include,` to the `ov.model_copy(update={...})` dict.

- [ ] **Step 5: Add the `--include` option and wire the edit**

In the `fix` command signature, immediately after the `unexclude` option:

```python
    include: list[str] = typer.Option(
        None, "--include",
        help="Re-admit a file the junk filter dropped: an x-handle from "
             "`llama show <show> --tracks` (e.g. x1) or the source filename"),
```

Extend the `--suggest-titles` refusal from `if exclude or unexclude:` to
`if exclude or unexclude or include:` and change the two message strings from
`--exclude/--unexclude` to `--exclude/--unexclude/--include` (both the leading
sentence and the remedy sentence).

Rename `did_exclude` to `did_files` at its definition and at both use sites
(the `if not (…)` guard and the `stage = "gather" if …` line), and define it as:

```python
    did_files = bool(exclude or unexclude or include)
```

Replace the `if did_exclude:` edit block with:

```python
    if did_files:
        try:
            add = _resolve_exclude_tokens(sws, exclude or [])
            rm = _resolve_exclude_tokens(sws, unexclude or [])
            inc = _resolve_include_tokens(sws, include or [])
        except LlamaError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1)
        clash = sorted(set(add) & set(inc))
        if clash:
            typer.echo(f"--exclude and --include name the same file(s): "
                       f"{', '.join(clash)}", err=True)
            raise typer.Exit(1)
        # A row whose reason is operator-excluded was never junk-filtered, so
        # re-admitting it means editing overrides.exclude -- that is the
        # --unexclude case, which --include folds in.
        was_operator = {e["filename"] for e in read_model(sws.show, Show).excluded_files
                        if "operator-excluded" in e.get("reasons", [])}
        undo = [f for f in inc if f in was_operator]
        readmit = [f for f in inc if f not in was_operator]
        ov = _edit_overrides(sws, add_exclude=add, rm_exclude=list(rm) + undo,
                             add_include=readmit)
        if add or rm or undo:
            typer.echo(f"{entry.slug}: overrides.exclude = {ov.exclude} "
                       "(the hold clears itself if a clean re-gather results)")
        if readmit:
            typer.echo(f"{entry.slug}: overrides.include = {ov.include} "
                       "(the hold clears itself if a clean re-gather results)")
        real_edit = True
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_fix.py -q
```

Expected: PASS.

- [ ] **Step 7: Run the whole suite**

```bash
./.venv/bin/python -m pytest -q
```

Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_fix.py
git commit -m "feat(fix): --include re-admits a file the junk filter dropped"
```

---

