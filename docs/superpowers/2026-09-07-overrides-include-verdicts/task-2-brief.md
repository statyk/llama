### Task 2: `run_gather` honours `overrides.include`

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py:833-849` (file selection + the existing exclude block), `:1124` (the `Show(...)` construction)
- Test: `packages/llama/tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `filter_files(..., readmit=…)`, `Overrides.include`, `Track.included` (Task 1).
- Produces: `run_gather` writes `show.json` with re-admitted files in `tracks` (not `excluded_files`) and `included=True` on exactly those tracks.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_stage_gather.py`. The file already
imports `Overrides`, `write_artifact`, `ShowWorkspace`, `StubIA`, `FakeProvider`,
`make_candidate`, `IDENT` and `run_gather` — reuse them.

```python
# --- overrides.include (operator re-admission) ---

def test_gather_readmits_an_operator_included_file(tmp_path: Path):
    """gd73's spam file is the fixture's junk-filtered file. Naming it in
    overrides.include puts it in the track list, marks it, and takes it out of
    excluded_files."""
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"]))
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert "FOLLOW-ME @BYPIKENO.mp3" in [t.filename for t in show.tracks]
    assert [t.filename for t in show.tracks if t.included] == ["FOLLOW-ME @BYPIKENO.mp3"]
    assert all(e["filename"] != "FOLLOW-ME @BYPIKENO.mp3" for e in show.excluded_files)


def test_gather_leaves_ordinary_tracks_unmarked(tmp_path: Path):
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert all(t.included is False for t in show.tracks)


def test_exclude_wins_when_a_file_is_in_both_override_lists(tmp_path: Path):
    """The CLI makes this state unreachable; gather still needs a defined
    answer for a hand-mangled overrides.json. include re-admits, exclude then
    drops -- so the file is out, with reason operator-excluded."""
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(include=["FOLLOW-ME @BYPIKENO.mp3"],
                                            exclude=["FOLLOW-ME @BYPIKENO.mp3"]))
    show = run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert "FOLLOW-ME @BYPIKENO.mp3" not in [t.filename for t in show.tracks]
    dropped = next(e for e in show.excluded_files
                   if e["filename"] == "FOLLOW-ME @BYPIKENO.mp3")
    assert dropped["reasons"] == ["operator-excluded"]


def test_gather_warns_when_an_include_entry_matches_no_file(tmp_path: Path, caplog):
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(include=["not-on-this-tape.mp3"]))
    with caplog.at_level("WARNING"):
        run_gather(sws, StubIA(), FakeProvider(), make_candidate(), IDENT)
    assert any("not-on-this-tape.mp3" in r.message % r.args if r.args else
               "not-on-this-tape.mp3" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k "readmit or included or both_override or include_entry"
```

Expected: FAIL — the spam file is still in `excluded_files`, `t.included` is
never set, and no warning is logged.

- [ ] **Step 3: Wire `readmit` into the file selection**

In `run_gather`, replace

```python
    kept, excluded, ordering = filter_files(md.get("files", []), want_format=want)
```

with

```python
    # read_overrides is hoisted above filter_files (it only reads the show dir)
    # so operator re-admission can be applied inside the filter, where play
    # order is derived. The exclude block below still runs AFTER, so a file
    # named in both lists ends up excluded.
    overrides = read_overrides(show_ws)
    kept, excluded, ordering = filter_files(
        md.get("files", []), want_format=want,
        readmit=frozenset(overrides.include))
    for missing in sorted(set(overrides.include) - {f["name"] for f in kept}):
        log.warning("overrides.include entry %r matched no file", missing)
```

and delete the now-duplicated `overrides = read_overrides(show_ws)` line that
currently sits just above the `if overrides.exclude:` block.

- [ ] **Step 4: Stamp `Track.included`**

Immediately before the `show = Show(` construction:

```python
    # Stamped here rather than in titles.resolve_titles so no intermediate
    # rebuild of `tracks` between there and here can drop it.
    if overrides.include:
        forced = set(overrides.include)
        for t in tracks:
            t.included = t.filename in forced
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q
```

Expected: PASS.

- [ ] **Step 6: Run the whole suite**

```bash
./.venv/bin/python -m pytest -q
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/tests/test_stage_gather.py
git commit -m "feat(gather): re-admit files named in overrides.include"
```

---

