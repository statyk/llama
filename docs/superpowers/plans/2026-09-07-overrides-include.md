# `overrides.include` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the operator a supported way to re-admit a source file the junk
filter dropped, with the dropped files visible in the show listing.

**Architecture:** `Overrides` grows an `include` list of source filenames.
`junk.filter_files` grows a keyword-only `readmit` set, applied after the junk
arms and after duplicate-listing dedupe but before play-order derivation.
`run_gather` passes `overrides.include` in and stamps `Track.included` on the
re-admitted tracks. `cli.py` grows the `excluded (N):` section in
`_format_tracks`, a `+` marker column, a dropped count on the `recording:` line,
and `llama fix --include`, which addresses excluded files by `x`-handle or
filename.

**Tech Stack:** Python 3.11+, pydantic v2, typer, pytest.

**Spec:** `docs/superpowers/specs/2026-09-07-overrides-include-design.md`

## Global Constraints

- Run the suite as `./.venv/bin/python -m pytest -q` **from the tree you are
  editing**. Never run a `.venv/bin/*` console script from a copy of the tree —
  the shebang is an absolute path to the original interpreter, so it acts on the
  original tree. Verify with
  `./.venv/bin/python -c "import llama; print(llama.__file__)"`.
- **Do not change** `SHORT_FRACTION_OF_MEDIAN` (0.25), `MIN_PLAUSIBLE_SEC`
  (90.0) or `MIN_MEDIAN_SAMPLE` (5) in `packages/llama/src/llama/junk.py`. They
  were swept over 2,030 cached items. This feature exists precisely so those
  constants do not have to move.
- **Do not add fields to `ManifestTrack`.** The llama↔emcee package contract is
  out of scope; provenance lives in `show.json`.
- **Do not add `extra="forbid"` to `Overrides`.** It is a persisted state
  artifact; an `overrides.json` written before this feature (no `include` key)
  must keep loading.
- The whole suite is offline and deterministic (`fake` LLM backend). No test may
  reach the network.
- Conventional-commit subjects (`feat:`, `test:`, `docs:`), one commit per task.

---

### Task 1: `Overrides.include`, `Track.included`, and `filter_files(readmit=…)`

The pure layer: the two model fields and the re-admission itself. No CLI, no
gather wiring yet.

**Files:**
- Modify: `packages/llama/src/llama/models.py:150-167` (`Track`), `:193-205` (`Overrides`)
- Modify: `packages/llama/src/llama/junk.py:118-146` (`_keep_and_exclude`), `:148-172` (`_dedupe_duplicate_listings`), `:170-236` (`filter_files`)
- Test: `packages/llama/tests/test_junk.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Overrides.include: list[str]` — source filenames re-admitted past the junk filter.
  - `Track.included: bool = False`.
  - `junk.filter_files(files, want_format="VBR MP3", *, readmit: frozenset[str] = frozenset()) -> tuple[list[dict], list[dict], dict]` — unchanged return shape.
  - Every entry in the returned `excluded` list now also carries `"duration_sec": float | None`.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_junk.py`. The file already defines
`load_files()`, `_tape()`, `_short_reasons()` and
`_mp3(name, track=None, source="original", original=None, length="300.0")` —
reuse them, do not redefine them.

```python
# --- operator re-admission (overrides.include) ---

def test_readmit_returns_an_excluded_file_to_kept():
    """The gd73 fixture's spam file is dropped by two arms at once; naming it
    in `readmit` puts it back and takes it out of `excluded` entirely."""
    kept, excluded, _ = filter_files(
        load_files(), readmit=frozenset({"FOLLOW-ME @BYPIKENO.mp3"}))
    assert "FOLLOW-ME @BYPIKENO.mp3" in {f["name"] for f in kept}
    assert all(e["filename"] != "FOLLOW-ME @BYPIKENO.mp3" for e in excluded)


def test_readmit_of_an_unknown_filename_changes_nothing():
    base_kept, base_excluded, base_order = filter_files(load_files())
    kept, excluded, order = filter_files(load_files(), readmit=frozenset({"nope.mp3"}))
    assert [f["name"] for f in kept] == [f["name"] for f in base_kept]
    assert [e["filename"] for e in excluded] == [e["filename"] for e in base_excluded]
    assert order == base_order


def test_readmit_does_not_move_the_duration_floor():
    """The two-pass invariant: the floor is the median of files passing every
    OTHER arm, computed before any re-admission. Re-admitting the 40s file must
    NOT license the 50s one -- otherwise one operator override would quietly
    lower the junk threshold for the whole tape."""
    files = [_mp3(f"band1t0{i}.mp3") for i in range(1, 6)] + [
        _mp3("band1t06.mp3", length="40.0"), _mp3("band1t07.mp3", length="50.0")]
    kept, excluded, _ = filter_files(files, readmit=frozenset({"band1t06.mp3"}))
    assert "band1t06.mp3" in {f["name"] for f in kept}
    assert {e["filename"] for e in excluded
            if "implausibly short" in e["reasons"]} == {"band1t07.mp3"}


def test_readmit_lands_in_filename_play_order():
    files = [_mp3("band1t01.mp3"), _mp3("band1t02.mp3", length="40.0"),
             _mp3("band1t03.mp3"), _mp3("band1t04.mp3"), _mp3("band1t05.mp3"),
             _mp3("band1t06.mp3")]
    kept, _, _ = filter_files(files, readmit=frozenset({"band1t02.mp3"}))
    assert [f["name"] for f in kept] == [f"band1t0{i}.mp3" for i in range(1, 7)]


def test_readmitting_an_untagged_file_falls_back_to_filename_order():
    """Play order is derived ONCE, over the final kept set. A re-admitted file
    with no track tag therefore breaks the completeness test at junk.py's
    ordering block and the whole recording reverts to filename order. This is
    the accepted price of not splicing a file into an order derived without it
    (spec section 2)."""
    files = [_mp3("band1t01.mp3", track="5", length="310.0"),
             _mp3("band1t02.mp3", track="4", length="288.0"),
             _mp3("band1t03.mp3", track="3", length="340.0"),
             _mp3("band1t04.mp3", track="2", length="295.0"),
             _mp3("band1t05.mp3", track="1", length="302.0"),
             _mp3("band1t06.mp3", length="40.0")]
    _, _, base_order = filter_files(files)
    assert base_order["order_source"] == "track-tags"
    kept, _, order = filter_files(files, readmit=frozenset({"band1t06.mp3"}))
    assert order["order_source"] == "filename"
    assert [f["name"] for f in kept] == [f"band1t0{i}.mp3" for i in range(1, 7)]


def test_readmit_of_a_duplicate_listing_ships_the_track_twice():
    """Owner decision 2026-09-07: no reason is refused. Re-admitting a
    duplicate listing therefore ships that recording twice, deliberately --
    the excluded table names the reason next to the handle."""
    files = [
        _mp3("band1t01.mp3", length="300.0"),
        {**_mp3("band99/band1t01.mp3", length="300.0"), "title": "Alpha"},
    ]
    kept, excluded, _ = filter_files(files, readmit=frozenset({"band1t01.mp3"}))
    assert {f["name"] for f in kept} == {"band1t01.mp3", "band99/band1t01.mp3"}
    assert excluded == []


def test_excluded_entries_carry_a_duration():
    """The operator has to judge a dropped file from the listing, so every
    excluded entry records how long it was (None when the item had no length,
    which is itself one of the exclusion reasons)."""
    _, excluded, _ = filter_files(load_files())
    spam = next(e for e in excluded if e["filename"] == "FOLLOW-ME @BYPIKENO.mp3")
    assert isinstance(spam["duration_sec"], float)
    assert all("duration_sec" in e for e in excluded)
```

Add the two model assertions to `packages/llama/tests/test_models.py`:

```python
def test_overrides_include_defaults_empty_and_survives_an_old_file():
    from llama.models import Overrides
    assert Overrides().include == []
    # An overrides.json written before this feature has no `include` key.
    assert Overrides.model_validate({"exclude": ["a.mp3"]}).include == []


def test_track_included_defaults_false():
    from llama.models import Track
    t = Track(index=1, set="1", title="Dark Star", filename="a.mp3", title_source="tags")
    assert t.included is False
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_junk.py packages/llama/tests/test_models.py -q
```

Expected: the new tests fail — `TypeError: filter_files() got an unexpected
keyword argument 'readmit'`, `KeyError: 'duration_sec'`, and
`AttributeError`/`ValidationError` on the two model fields.

- [ ] **Step 3: Add the two model fields**

In `packages/llama/src/llama/models.py`, inside `class Track`, after the
`matched` field:

```python
    # True when overrides.include re-admitted this file past the junk filter.
    # Recorded here and NOT in ManifestTrack: the manifest is the broadcast
    # contract with emcee and stays lean; show.json is the operator's record.
    included: bool = False
```

Inside `class Overrides`, after `exclude`:

```python
    include: list[str] = Field(default_factory=list)   # filenames re-admitted past the junk filter
```

and extend that class's docstring's stage list from
`(exclude, venue, city, date, titles, set_breaks, encore_after)` to
`(exclude, include, venue, city, date, titles, set_breaks, encore_after)`.

- [ ] **Step 4: Record a duration on every excluded entry**

In `packages/llama/src/llama/junk.py`, `_keep_and_exclude`, the final loop:

```python
        if reasons:
            excluded.append({"filename": f["name"], "reasons": reasons,
                             "duration_sec": secs})
        else:
            kept.append(f)
```

and both `excluded.append` calls in `_dedupe_duplicate_listings`:

```python
            excluded.append({"filename": incumbent["name"], "reasons": ["duplicate-listing"],
                             "duration_sec": length_seconds(incumbent.get("length"))})
```

```python
            excluded.append({"filename": f["name"], "reasons": ["duplicate-listing"],
                             "duration_sec": length_seconds(f.get("length"))})
```

- [ ] **Step 5: Add `readmit` to `filter_files`**

Change the signature to:

```python
def filter_files(
    files: list[dict], want_format: str | Sequence[str] = "VBR MP3",
    *, readmit: frozenset[str] = frozenset(),
) -> tuple[list[dict], list[dict], dict]:
```

Insert this block immediately after the two dedupe lines
(`kept, dup_excluded = _dedupe_duplicate_listings(kept)` /
`excluded = excluded + dup_excluded`) and immediately before
`orig_tracks = {...}`:

```python
    # Operator re-admission (overrides.include). All three positions are
    # load-bearing:
    #   AFTER _keep_and_exclude - the duration floor is the median of files
    #     passing every OTHER arm, so a re-admitted 37s track can never move
    #     the threshold that decides what junk is (see the two-pass note in
    #     _keep_and_exclude).
    #   AFTER _dedupe_duplicate_listings - otherwise a re-admitted duplicate
    #     listing would be immediately re-dropped, and no reason is refused.
    #   BEFORE the ordering block below - play order is derived over the FINAL
    #     kept set rather than splicing a file into an order derived without
    #     it. Consequence: re-admitting a file with no track tag reverts the
    #     whole recording to filename order.
    # `readmit` names the WINNING format's files only; anything else matches
    # nothing here and is warned about by the caller.
    if readmit:
        by_name = {f["name"]: f for f in files if f.get("format") == matched}
        back = [by_name[e["filename"]] for e in excluded
                if e["filename"] in readmit and e["filename"] in by_name]
        if back:
            readmitted = {f["name"] for f in back}
            kept = sorted(kept + back, key=lambda f: f["name"])
            excluded = [e for e in excluded if e["filename"] not in readmitted]
```

Extend the `filter_files` docstring with one paragraph:

```
    `readmit` is `overrides.include`: source filenames the operator has ruled
    back in. They are returned to `kept` and removed from `excluded` after the
    junk arms and after duplicate-listing dedupe, and before play order is
    derived. No exclusion reason is refused.
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_junk.py packages/llama/tests/test_models.py -q
```

Expected: PASS.

- [ ] **Step 7: Run the whole suite**

```bash
./.venv/bin/python -m pytest -q
```

Expected: all green. `duration_sec` is a new key on excluded entries; if any
existing test asserts an excluded entry by whole-dict equality, update that
assertion to include the new key rather than dropping the key.

- [ ] **Step 8: Commit**

```bash
git add packages/llama/src/llama/models.py packages/llama/src/llama/junk.py \
        packages/llama/tests/test_junk.py packages/llama/tests/test_models.py
git commit -m "feat(junk): filter_files readmit + overrides.include/Track.included fields"
```

---

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

### Task 3: show the dropped files

The `excluded (N):` section, the `+` marker, the dropped count and the
`include=` override line. `_excluded_handles` is created here and is the single
producer of the `x`-handles Task 4's resolver consumes.

**Files:**
- Modify: `packages/llama/src/llama/cli.py:1243-1265` (`_format_tracks`), `:1499` (the `recording:` line), `:1503-1524` (the `overrides:` line), `:1536-1578` (`_print_show_json`)
- Test: `packages/llama/tests/test_show_cmd.py`

**Interfaces:**
- Consumes: `Track.included`, `Show.excluded_files` entries carrying `duration_sec` (Tasks 1-2).
- Produces: `cli._excluded_handles(show) -> list[tuple[str, dict]]` — `[("x1", entry), ("x2", entry), …]` in `show.excluded_files` order.

- [ ] **Step 1: Write the failing tests**

Append to `packages/llama/tests/test_show_cmd.py`, following that file's
existing `_cfg`/`build`/`cli_invoke` pattern:

```python
def _show_with_excluded(tmp_path: Path):
    """A gathered show whose show.json carries two junk-filtered files and one
    re-admitted track."""
    from llama.models import Show, Track
    from llama.workspace import write_artifact
    from test_catalog import build

    ws = build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    s = read_model(ws.show, Show)
    s.tracks = [
        Track(index=1, set="1", title="Introduction", filename="intro.mp3",
              title_source="override", duration_sec=37.0, included=True),
        Track(index=2, set="1", title="Morning Dew", filename="a.mp3",
              title_source="tags", duration_sec=300.0),
    ]
    s.excluded_files = [
        {"filename": "spam.mp3", "reasons": ["filename convention mismatch"],
         "duration_sec": 72.0},
        {"filename": "tuning.mp3", "reasons": ["implausibly short"],
         "duration_sec": 12.0},
    ]
    write_artifact(ws.show, s)
    return ws


def test_excluded_handles_number_from_one_in_show_json_order():
    from llama.cli import _excluded_handles

    class _S:
        excluded_files = [{"filename": "a.mp3"}, {"filename": "b.mp3"}]

    assert [(h, e["filename"]) for h, e in _excluded_handles(_S())] == [
        ("x1", "a.mp3"), ("x2", "b.mp3")]


def test_tracks_listing_shows_the_excluded_section(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert r.exit_code == 0, r.output
    assert "excluded (2):" in r.output
    assert "x1" in r.output and "spam.mp3" in r.output
    assert "filename convention mismatch" in r.output
    assert "x2" in r.output and "tuning.mp3" in r.output
    assert "0:12" in r.output


def test_tracks_listing_marks_a_re_admitted_track(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead", "--tracks")
    assert "+ = re-admitted by operator" in r.output
    intro = next(ln for ln in r.output.splitlines() if "intro.mp3" in ln)
    dew = next(ln for ln in r.output.splitlines() if "Morning Dew" in ln)
    assert "1.+" in intro
    assert "2.+" not in dew


def test_dropped_count_shows_without_the_tracks_flag(tmp_path: Path):
    cfg = _cfg(tmp_path)
    _show_with_excluded(tmp_path)
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert "(2 tracks, 2 dropped)" in r.output
    assert "excluded (2):" not in r.output


def test_no_dropped_clause_when_nothing_was_dropped(tmp_path: Path):
    cfg = _cfg(tmp_path)
    build(tmp_path, "gratefuldead-1973-06-10", stages={"select", "gather"})
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert "dropped" not in r.output


def test_overrides_line_and_json_carry_include(tmp_path: Path):
    import json as _json

    from llama.models import Overrides
    from llama.workspace import write_artifact

    cfg = _cfg(tmp_path)
    ws = _show_with_excluded(tmp_path)
    write_artifact(ws.overrides, Overrides(include=["intro.mp3"]))
    r = cli_invoke(cfg, "show", "gratefuldead")
    assert "include=['intro.mp3']" in r.output
    r = cli_invoke(cfg, "show", "gratefuldead", "--json", "--tracks")
    data = _json.loads(r.output)
    assert data["overrides"]["include"] == ["intro.mp3"]
    assert [e["filename"] for e in data["excluded"]] == ["spam.mp3", "tuning.mp3"]
    assert data["tracks"][0]["included"] is True
```

If `read_model` / `build` / `_cfg` are not already imported at the top of
`test_show_cmd.py`, add the imports the file's existing tests use.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_show_cmd.py -q -k "excluded or dropped or re_admitted or include"
```

Expected: FAIL — `ImportError` on `_excluded_handles`, and none of the strings
appear in the output.

- [ ] **Step 3: Add `_excluded_handles` and extend `_format_tracks`**

In `packages/llama/src/llama/cli.py`, immediately above `_format_tracks`:

```python
def _excluded_handles(show) -> list[tuple[str, dict]]:
    """`x`-handles for the junk-filtered files, in show.json order.

    ONE producer, consumed by both the `--tracks` listing and `fix --include`'s
    token resolver, so the handle an operator reads is always the handle the
    resolver means."""
    return [(f"x{i}", e) for i, e in enumerate(show.excluded_files, start=1)]
```

Rewrite the body of `_format_tracks` (keep the existing `_MARK` comment block
verbatim, and correct its last two lines — see Step 5):

```python
    _MARK = {True: " ", False: "?", None: "-"}
    lines = ["tracks:"]
    for t in show.tracks:
        title = t.title if t.title_source != "unresolved" else "(unknown)"
        lines.append(f"  {t.index:2d}.{'+' if t.included else ' '} set {t.set:6.6s} "
                     f"{_MARK[t.matched]} {title:28.28s} "
                     f"{t.title_source:14.14s} {_fmt_dur(t.duration_sec):>6s}  {t.filename}")
    if any(t.matched is False for t in show.tracks):
        lines.append("  ? = no setlist match")
    if any(t.matched is None for t in show.tracks):
        lines.append("  - = not measured")
    if any(t.included for t in show.tracks):
        lines.append("  + = re-admitted by operator (the junk filter had dropped it)")
    handles = _excluded_handles(show)
    if handles:
        width = max(len(e["filename"]) for _, e in handles)
        lines.append(f"excluded ({len(handles)}):")
        for handle, e in handles:
            lines.append(f"  {handle:>3s}  {e['filename']:<{width}s}  "
                         f"{_fmt_dur(e.get('duration_sec')):>6s}  "
                         f"{', '.join(e.get('reasons', []))}")
        lines.append(f"  re-admit one with: llama fix <show> --include {handles[0][0]}")
    return lines
```

- [ ] **Step 4: Add the dropped count, the `include=` override line and the JSON fields**

In `_print_show_entry`, replace the `recording:` line with:

```python
    dropped = f", {len(s.excluded_files)} dropped" if s.excluded_files else ""
    typer.echo(f"recording: {s.identifier}  ({len(s.tracks)} tracks{dropped})")
```

In the same function, immediately after the `if ov.exclude:` clause:

```python
    if ov.include:
        parts.append(f"include={ov.include}")
```

In `_print_show_json`, add `"include": ov.include,` to the `data["overrides"]`
dict (next to `"exclude"`), and inside the `if show_tracks:` block add:

```python
        data["excluded"] = s.excluded_files if s is not None else None
```

- [ ] **Step 5: Correct the stale duration comment**

The comment above `_MARK` in `_format_tracks` ends:

```
    # the duration column's own "?" (_fmt_dur) can't co-occur: junk drops
    # files with no length.
```

That is now false — `--include` can re-admit a file excluded for
`missing duration`. Replace those two lines with:

```
    # the duration column's own "?" (_fmt_dur) means no length in the item
    # metadata. Junk drops such files, so it appears only on a track the
    # operator re-admitted via overrides.include; package.py re-probes the
    # real duration from the downloaded file at package time.
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
./.venv/bin/python -m pytest packages/llama/tests/test_show_cmd.py -q
```

Expected: PASS.

- [ ] **Step 7: Run the whole suite**

```bash
./.venv/bin/python -m pytest -q
```

Expected: all green. Existing tests that assert on `--tracks` output may pin
the old column layout (the `+` column shifts every track line by one
character); update those assertions to the new layout rather than reverting the
column.

- [ ] **Step 8: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_show_cmd.py
git commit -m "feat(show): list junk-filtered files with x-handles and mark re-admitted tracks"
```

---

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

### Task 5: documentation

**Files:**
- Modify: `README.md:150-152` (the `llama fix` example block), `:180-195` (the three resolutions)
- Modify: `docs/workflow.md:281` (the Correct row), `:594-596` (the `fix` flag table), `:613` (the `--suggest-titles` refusal sentence)
- Modify: `CLAUDE.md:49` (the `llama fix` command summary), `:196` (the overrides paragraph), `:242` (the `--suggest-titles` refusal)

- [ ] **Step 1: README**

After the `--exclude` example at `README.md:150`, add:

```
    llama fix 1973-06-10 --include x1         # re-admit a file the junk filter dropped
                                              # (x-handles come from `llama show ... --tracks`)
```

In the "Correct the data" bullet (around `README.md:183`), append a sentence:

> The reverse also works: `llama show <s> --tracks` lists every file the junk
> filter dropped with an `x`-handle, and `llama fix <s> --include x1` puts one
> back — the junk thresholds are measured and stay put, so a wrongly-dropped
> track is fixed per show, not by loosening the filter.

- [ ] **Step 2: `docs/workflow.md`**

Add a row to the `fix` flag table, directly under the `--unexclude` row:

```
| `--unexclude FILE\|N` | remove from `overrides.exclude` | gather |
| `--include xN\|FILE` (repeatable, comma groups) | add to `overrides.include` — re-admit a file the junk filter dropped; on a row whose reason is `operator-excluded` it un-excludes instead | gather |
```

In the Correct row at `:281`, after the `--unexclude` parenthetical, add
`; --include xN re-admits a file the junk filter dropped`.

At `:613`, change `--exclude`/`--unexclude` to
`--exclude`/`--unexclude`/`--include`.

Add a short subsection under the `fix` reference:

```markdown
#### Seeing what was dropped

`llama show <show> --tracks` ends with an `excluded (N):` section — one line per
file the junk filter removed, with an `x`-handle, its duration and the reasons.
A re-admitted track carries a `+` in the track table. The count also appears on
the always-visible `recording:` line (`(24 tracks, 3 dropped)`).

No exclusion reason is refused: re-admitting a `duplicate-listing` row will ship
that recording twice. The reason is printed next to the handle so the choice is
made with it in view.
```

- [ ] **Step 3: `CLAUDE.md`**

At `:49`, extend the `fix` flag list from `--exclude`/`--unexclude` to
`--exclude`/`--unexclude`/`--include`.

In the `overrides.json` paragraph at `:196`, after the `--exclude`/`--unexclude`
clause, add:

> and `--include xN|FILE` (`overrides.include`), which re-admits a file the junk
> filter dropped — applied inside `filter_files` after the junk arms and after
> duplicate-listing dedupe but **before** play-order derivation, so the floor
> cannot move and order is derived over the final set (a re-admitted file with
> no track tag reverts the recording to filename order). A file in both lists is
> excluded; the CLI keeps the lists mutually exclusive so that never happens
> through it. `--include` on an `operator-excluded` row un-excludes instead.
> **Do not loosen the junk constants instead** — this override is why they
> stay put.

At `:242`, add `--include` to the `--suggest-titles` refusal list.

- [ ] **Step 4: Verify the docs match the code**

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m llama fix --help
```

Expected: suite green; `--include`'s help text in the CLI output matches what
the docs describe.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/workflow.md CLAUDE.md
git commit -m "docs: llama fix --include and the excluded-files listing"
```

---

## Verification checklist (run before declaring the feature done)

- [ ] `./.venv/bin/python -m pytest -q` — whole suite green, and the count is
      higher than the pre-feature baseline by the number of tests added.
- [ ] `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves
      inside the tree you edited.
- [ ] `git grep -n "SHORT_FRACTION_OF_MEDIAN\|MIN_PLAUSIBLE_SEC\|MIN_MEDIAN_SAMPLE"`
      shows the values unchanged (0.25 / 90.0 / 5).
- [ ] `git grep -n "class ManifestTrack" -A 8` shows no new field.
- [ ] Manual smoke on a real workspace, if one is available:
      `llama show <a show with excluded files> --tracks` prints the
      `excluded (N):` section, and `llama fix <show> --include x1` writes
      `overrides.include` and redoes from gather.
