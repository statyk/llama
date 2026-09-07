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

