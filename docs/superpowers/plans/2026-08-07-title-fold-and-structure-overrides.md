# Title-fold and Structure Overrides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold `-in'`/`-ing` spelling variants at the matching layer, and give the operator an encore override plus a per-track "didn't match" cue.

**Architecture:** One regex fold added to `fuzzy_norm_title` *before* `norm_title` strips punctuation (the apostrophe is the safety signal). One new `Overrides` field (`encore_after`) threaded through `_sets_from_breaks` and the `llama fix` CLI. One new `Track` field (`matched`) populated from the already-computed `AlignResult.matched` and rendered by `_format_tracks`.

**Tech Stack:** Python 3.14, Pydantic v2, Typer, pytest.

**Spec:** `docs/superpowers/specs/2026-08-07-title-fold-and-structure-overrides-design.md`

## Global Constraints

- Run tests with `./.venv/bin/pytest` from the repo root. **In a git worktree, give the worktree its own `.venv`** — a bare `pytest` imports the main checkout's source and silently tests the wrong code.
- Baseline suite is **1416 green** at `2882773`. It must stay green after every task.
- **Do not touch `songs.normalize_song` or `songs.DEFAULT_ALIASES`.** Folding there would also move `grouping`, `vet_research`, `brief` and setlist.fm matching, none of which was measured.
- **Do not remove existing per-song alias patches.** `DEFAULT_ALIASES`' four GDTRFB entries and `GD_SHORTHAND`'s `throwin stones` cover apostrophe-less spellings the new fold deliberately cannot reach.
- `ManifestTrack` must not gain fields. The package contract and emcee stay untouched.
- Commit after every task. Commit messages: `feat:` / `fix:` / `test:` prefix, no trailing "Generated with" footer on these (the repo's own convention is a plain subject plus body).

---

### Task 1: The `-in'` → `-ing` fold in `fuzzy_norm_title`

**Files:**
- Modify: `packages/llama/src/llama/structure.py:61-74`
- Test: `packages/llama/tests/test_structure.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `structure._IN_APOSTROPHE` (compiled regex) and the changed behaviour of `structure.fuzzy_norm_title(title, aliases=None) -> str`. Tasks 2 and 3 rely on this behaviour; no signature change.

- [ ] **Step 1: Write the failing test**

Add to `packages/llama/tests/test_structure.py`:

```python
import pytest
from llama.structure import fuzzy_norm_title, fuzzy_title_eq


@pytest.mark.parametrize("dropped,spelled", [
    ("Knockin' On Heaven's Door", "Knocking On Heaven's Door"),
    ("Truckin'", "Trucking"),
    ("Doin' That Rag", "Doing That Rag"),
    ("Playin' In The Band", "Playing In The Band"),
    ("Dancin' In The Streets", "Dancing In The Streets"),
])
def test_dropped_g_folds_to_the_spelled_out_form(dropped, spelled):
    assert fuzzy_norm_title(dropped) == fuzzy_norm_title(spelled)


@pytest.mark.parametrize("a,b", [
    ("Sin City", "Sing Me Back Home"),
    ("The Thing", "Thin Man"),
    ("King Bee", "Kin Folk"),
    ("Ring Of Fire", "Rin Tin Tin"),
])
def test_words_without_an_apostrophe_are_never_folded(a, b):
    # The apostrophe is the whole safety mechanism. Folding normalized forms
    # instead would collide sing/sin, thing/thin, wing/win, king/kin.
    assert fuzzy_norm_title(a) != fuzzy_norm_title(b)
    assert not fuzzy_title_eq(fuzzy_norm_title(a), fuzzy_norm_title(b))


def test_fold_only_fires_at_a_word_ending():
    # An interior "in'" followed by a letter is not a dropped g.
    assert fuzzy_norm_title("Sin'ful Days") == fuzzy_norm_title("Sinful Days")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -k "dropped_g or without_an_apostrophe or word_ending" -v`

Expected: `test_dropped_g_folds_to_the_spelled_out_form` FAILS on all five params (the two sides normalize differently). The other two tests already PASS — they are regression guards for the rejected design, not new behaviour.

- [ ] **Step 3: Implement the fold**

In `packages/llama/src/llama/structure.py`, add near the other module-level regexes:

```python
# Tapers and canonical setlists disagree constantly on dropped g's
# ("Knockin'" vs "Knocking"). Fold BEFORE norm_title, because its punctuation
# strip removes the apostrophe that makes this rewrite safe: after the strip we
# could only guess from word shape, which manufactures sing->sin, thing->thin,
# wing->win and king->kin -- all collisions against real LMA titles. Requiring
# the apostrophe means a token is only rewritten where the source explicitly
# spells the dropped g, and only onto that same word's spelled-out form.
# Accepted gap: a taper writing "Knockin" with no apostrophe still will not
# match. Catching that needs exactly the unsafe blanket fold.
_IN_APOSTROPHE = re.compile(r"in'(?![A-Za-z])")
```

Then change `fuzzy_norm_title` (currently lines 61-74) so the body reads:

```python
    folded = _IN_APOSTROPHE.sub("ing", title.replace("&", " and "))
    norm = norm_title(folded)
    return (aliases or {}).get(norm, norm)
```

Extend the existing docstring with a sentence:

```
    Word-final "in'" is folded to "ing" first, for the same reason the "&"
    fold happens here: `norm_title`'s punctuation strip destroys the signal
    that makes the rewrite safe. See `_IN_APOSTROPHE`.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -v`
Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1416+ passed, 0 failed. **If any pre-existing test fails, stop and report it — do not adjust the test to fit.** A pre-existing failure here means the fold changed a real match, which is exactly what Task 2's sweep exists to characterize.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "fix(structure): fold word-final -in' to -ing before normalization

Tapers and jerrybase disagree on dropped g's; the apostrophe is the only
safe signal, and norm_title strips it. Folding the normalized forms instead
would collide sing/sin, thing/thin, wing/win, king/kin."
```

---

### Task 2: Validation sweep over the closer vocabulary

**Files:**
- Test: `packages/llama/tests/test_structure.py`
- Modify (only if the sweep finds a real pair): `packages/llama/src/llama/structure.py` (`_NEVER_EQUAL`)

**Interfaces:**
- Consumes: `structure.fuzzy_norm_title` and `structure.fuzzy_title_eq` from Task 1; `jerrybase._load()` returning `dict[tuple[str, str], list[JerrybaseEvent]]`, where each event has `.sets` and each set has `.closer: str`.
- Produces: nothing consumed by later tasks.

This is the `_NEVER_EQUAL`-grade validation the spec requires (section A4). It converts "I expect zero collisions" into evidence.

- [ ] **Step 1: Write the sweep test**

Add to `packages/llama/tests/test_structure.py`:

```python
def _fold_free_norm(title):
    """What fuzzy_norm_title produced BEFORE the -in' fold existed."""
    from llama.structure import norm_title
    return norm_title(title.replace("&", " and "))


def test_in_apostrophe_fold_introduces_no_cross_song_equality():
    """Every pair the fold newly makes equal must be one song under two
    spellings. Mirrors the exhaustive _NEVER_EQUAL validation.
    """
    from llama.jerrybase import _load

    closers = set()
    for events in _load().values():
        for ev in events:
            for st in ev.sets:
                if st.closer:
                    closers.add(st.closer)

    # Sanity: the sweep must be able to return non-empty at all. A check that
    # finds nothing and a check that never looked are indistinguishable.
    assert len(closers) > 400, f"closer vocabulary looks wrong: {len(closers)}"
    assert any("in'" in c for c in closers), "no apostrophe forms to fold"

    newly_equal = []
    ordered = sorted(closers)
    by_folded = {}
    for c in ordered:
        by_folded.setdefault(fuzzy_norm_title(c), []).append(c)
    for folded, group in by_folded.items():
        if len(group) < 2:
            continue
        # Equal after the fold. Were they equal before it?
        pre = {_fold_free_norm(c) for c in group}
        if len(pre) > 1:
            newly_equal.append(sorted(group))

    # Each surviving group must be one song spelled two ways. Record any
    # genuine cross-song pair in structure._NEVER_EQUAL and list it here.
    assert newly_equal == [], f"fold created new equalities, review each: {newly_equal}"
```

- [ ] **Step 2: Run the sweep**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py::test_in_apostrophe_fold_introduces_no_cross_song_equality -v`

Expected: PASS with an empty `newly_equal`.

**If it FAILS**, the assertion message lists the groups. For each group decide: same song under two spellings (expected — extend the test's allow-list with an inline comment naming the song), or genuinely different songs (add the pair to `structure._NEVER_EQUAL` and note it in that constant's comment, following the existing `It's All Over Now` / `... Baby Blue` precedent). Do not weaken the fold to make this pass.

- [ ] **Step 3: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add packages/llama/tests/test_structure.py packages/llama/src/llama/structure.py
git commit -m "test(structure): sweep the closer vocabulary for fold collisions

_NEVER_EQUAL-grade validation of the -in' fold, with a guard that the sweep
can return non-empty at all."
```

---

### Task 3: `gratefuldead-1990-03-29` closer regression

**Files:**
- Test: `packages/llama/tests/test_jerrybase.py`

**Interfaces:**
- Consumes: `structure.fuzzy_norm_title` (Task 1); `jerrybase._closer_candidates(tracks, closer) -> list[int]`; `jerrybase.anchor_breaks(tracks, event, aligned_sets=None) -> list[str] | None`; `llama.models.Track`.
- Produces: nothing consumed by later tasks.

This pins the exact failure that motivated the work.

- [ ] **Step 1: Write the failing test**

Add to `packages/llama/tests/test_jerrybase.py`:

```python
def test_dropped_g_encore_closer_no_longer_declines_anchoring():
    """gd1990-03-29: jerrybase says "Knockin' On Heaven's Door", the taper
    tagged "Knocking On Heaven's Door". anchor_breaks is all-or-nothing, so
    that one orthographic miss discarded two exactly-matching closers and let
    the closer tripwire fire on an unrelated song (Lovelight).
    """
    from llama.jerrybase import JerrybaseEvent, JerrybaseSet, _closer_candidates, anchor_breaks
    from llama.models import Track

    titles = [
        "Jack Straw ->", "Bertha", "We Can Run", "Ramble On Rose",
        "When I Paint My Masterpiece", "Bird Song ->", "The Promised Land",
        "Eyes Of The World ->", "Estimated Prophet ->", "Dark Star ->",
        "Drums ->", "Space ->", "Dark Star ->", "The Wheel ->",
        "Throwing Stones ->", "Turn On Your Lovelight",
        "Knocking On Heaven's Door",
    ]
    tracks = [Track(index=i + 1, set="1", title=t, filename=f"t{i + 1:02d}.mp3")
              for i, t in enumerate(titles)]
    event = JerrybaseEvent(
        event_id="4752", venue="Nassau Veterans Memorial Coliseum",
        city="Uniondale", state="NY",
        sets=[JerrybaseSet(name="1", closer="Promised Land", break_length="long"),
              JerrybaseSet(name="2", closer="Turn On Your Lovelight", break_length="short"),
              JerrybaseSet(name="encore", closer="Knockin' On Heaven's Door",
                           break_length="long")])

    assert _closer_candidates(tracks, "Knockin' On Heaven's Door") == [16]

    names = anchor_breaks(tracks, event)
    assert names is not None, "anchoring must no longer decline"
    assert names[-1] == "encore"
    breaks = [i + 1 for i in range(len(names) - 1) if names[i] != names[i + 1]]
    assert breaks == [7, 16]
```

If `JerrybaseSet` rejects the omitted `song_count`, pass `song_count=None` explicitly.

- [ ] **Step 2: Run it to verify it passes with Task 1's fold in place**

Run: `./.venv/bin/pytest packages/llama/tests/test_jerrybase.py::test_dropped_g_encore_closer_no_longer_declines_anchoring -v`
Expected: PASS.

To confirm the test actually pins the fold (that it is not vacuously green), temporarily revert `_IN_APOSTROPHE.sub("ing", ...)` to `title`, re-run, see it FAIL on `_closer_candidates(...) == [16]`, then restore.

- [ ] **Step 3: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add packages/llama/tests/test_jerrybase.py
git commit -m "test(jerrybase): pin the gd1990-03-29 dropped-g encore closer"
```

---

### Task 4: `Overrides.encore_after` and `_sets_from_breaks`

**Files:**
- Modify: `packages/llama/src/llama/models.py:184-195` (`Overrides`)
- Modify: `packages/llama/src/llama/stages/gather.py:27-36` (`_sets_from_breaks`), `:573-582` (override path), `:709-712` (`structure_info`)
- Test: `packages/llama/tests/test_stage_gather.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Overrides.encore_after: int | None`, and `gather._sets_from_breaks(n_tracks: int, breaks: list[int], encore_after: int | None = None) -> list[str]`. Task 5 sets the field from the CLI.

- [ ] **Step 1: Write the failing tests**

Add to `packages/llama/tests/test_stage_gather.py`:

```python
def test_sets_from_breaks_labels_the_encore():
    from llama.stages.gather import _sets_from_breaks

    labels = _sets_from_breaks(17, [7], encore_after=16)
    assert labels[:7] == ["1"] * 7
    assert labels[7:16] == ["2"] * 9
    assert labels[16] == "encore"


def test_sets_from_breaks_encore_without_numbered_breaks():
    from llama.stages.gather import _sets_from_breaks

    assert _sets_from_breaks(5, [], encore_after=4) == ["1", "1", "1", "1", "encore"]


def test_sets_from_breaks_unchanged_when_no_encore():
    from llama.stages.gather import _sets_from_breaks

    assert _sets_from_breaks(4, [2]) == ["1", "1", "2", "2"]


def test_overrides_accepts_encore_after():
    from llama.models import Overrides

    assert Overrides().encore_after is None
    assert Overrides(encore_after=16).encore_after == 16
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -k "encore" -v`
Expected: FAIL — `_sets_from_breaks() got an unexpected keyword argument 'encore_after'`, and `Overrides` has no `encore_after`.

- [ ] **Step 3: Add the model field**

In `packages/llama/src/llama/models.py`, inside `Overrides`, directly after `set_breaks`:

```python
    encore_after: int | None = None     # encore begins after this track number
```

Update the `Overrides` docstring's reader list from `(exclude, venue, city, date, titles, set_breaks)` to `(exclude, venue, city, date, titles, set_breaks, encore_after)`.

- [ ] **Step 4: Extend `_sets_from_breaks`**

Replace `packages/llama/src/llama/stages/gather.py:27-36` with:

```python
def _sets_from_breaks(n_tracks: int, breaks: list[int],
                      encore_after: int | None = None) -> list[str]:
    """Numbered set labels ("1","2",...) for each 1-based track, given the
    track numbers a break falls *after*. Break after track b closes a set.

    `encore_after` relabels every track past it "encore" -- the one label this
    function cannot otherwise emit. Without it, an operator forcing a break
    before a one-song encore gets set "3", which then contradicts jerrybase's
    numbered-set count (`expected_set_count` excludes encores) and trips
    `structure_guard`. That is a hold traded for a different hold, which is
    what this parameter exists to stop.
    """
    bset = set(breaks)
    labels, cur = [], 1
    for i in range(1, n_tracks + 1):
        labels.append(str(cur))
        if i in bset:
            cur += 1
    if encore_after is not None:
        for i in range(encore_after, n_tracks):
            labels[i] = "encore"
    return labels
```

- [ ] **Step 5: Run the unit tests to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -k "encore or sets_from_breaks" -v`
Expected: PASS.

- [ ] **Step 6: Write the failing gather-integration test**

Add to `packages/llama/tests/test_stage_gather.py`:

```python
def test_encore_override_labels_tracks_and_implies_a_break(tmp_path):
    """encore_after implies a break at that track, so the operator does not
    list it twice, and show.set_breaks reports it."""
    from llama.stages.gather import _sets_from_breaks

    labels = _sets_from_breaks(17, [7], encore_after=16)
    breaks = sorted({7} | {16})
    assert breaks == [7, 16]
    assert labels[16] == "encore"


def test_encore_override_out_of_range_is_rejected():
    from llama.errors import LlamaError
    from llama.stages.gather import _validate_structure_override

    with pytest.raises(LlamaError, match="encore_after"):
        _validate_structure_override(n_tracks=5, breaks=[2], encore_after=9)


def test_encore_override_must_follow_every_set_break():
    from llama.errors import LlamaError
    from llama.stages.gather import _validate_structure_override

    with pytest.raises(LlamaError, match="greater than"):
        _validate_structure_override(n_tracks=17, breaks=[7, 16], encore_after=7)
```

- [ ] **Step 7: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -k "encore_override" -v`
Expected: FAIL — `_validate_structure_override` does not exist.

- [ ] **Step 8: Add the validator and wire the override path**

Add to `packages/llama/src/llama/stages/gather.py`, next to `_sets_from_breaks`:

```python
def _validate_structure_override(n_tracks: int, breaks: list[int],
                                 encore_after: int | None) -> None:
    """Range- and order-check the structure overrides. Raises LlamaError."""
    bad = [n for n in breaks if not (1 <= n < n_tracks)]
    if bad:
        raise LlamaError(f"overrides.set_breaks: track number(s) out of range "
                         f"{bad} (show has {n_tracks} tracks)")
    if encore_after is None:
        return
    if not (1 <= encore_after < n_tracks):
        raise LlamaError(f"overrides.encore_after: track {encore_after} out of range "
                         f"(show has {n_tracks} tracks)")
    if breaks and encore_after <= max(breaks):
        raise LlamaError(f"overrides.encore_after ({encore_after}) must be greater "
                         f"than every set break {sorted(breaks)}")
```

Replace the override block at `packages/llama/src/llama/stages/gather.py:573-582` with:

```python
    if overrides.set_breaks is not None or overrides.encore_after is not None:
        breaks_in = list(overrides.set_breaks or [])
        _validate_structure_override(len(tracks), breaks_in, overrides.encore_after)
        labels = _sets_from_breaks(len(tracks), breaks_in, overrides.encore_after)
        tracks = [t.model_copy(update={"set": s}) for t, s in zip(tracks, labels)]
        breaks = sorted(set(breaks_in) | ({overrides.encore_after}
                                          if overrides.encore_after is not None else set()))
        alignment = "override"
        coverage, conflicts = 1.0, []
```

At `packages/llama/src/llama/stages/gather.py:709-712`, widen the `structure_info` condition the same way:

```python
    if overrides.set_breaks is not None or overrides.encore_after is not None:
        structure_info = StructureInfo(source="override", alignment="override",
                                       coverage=1.0, conflicts=[])
```

Confirm `LlamaError` is already imported in `gather.py`; it is used by the block being replaced.

- [ ] **Step 9: Run to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -v`
Expected: PASS.

- [ ] **Step 10: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 11: Commit**

```bash
git add packages/llama/src/llama/models.py packages/llama/src/llama/stages/gather.py packages/llama/tests/test_stage_gather.py
git commit -m "feat(gather): add overrides.encore_after

_sets_from_breaks emitted numbered labels only, so forcing a break before an
encore produced set \"3\" and tripped structure_guard against jerrybase's
numbered-set count -- one hold traded for another."
```

---

### Task 5: `llama fix --set-encore` / `--clear-encore`

**Files:**
- Modify: `packages/llama/src/llama/cli.py:558-589` (`_edit_overrides`), `:822-830` (overrides display), `:875-883` (`_print_show_json`), `:1149-1173` (`fix` signature), `:1194-1204` (parsing), `:1243-1252` (`_edit_overrides` call)
- Test: `packages/llama/tests/test_fix.py`

**Interfaces:**
- Consumes: `Overrides.encore_after` from Task 4.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Add to `packages/llama/tests/test_fix.py`. These mirror `test_set_breaks_and_clear` (line 138) and `test_set_breaks_non_numeric_errors_cleanly` (line 313) exactly — same helpers, same shape:

```python
def test_set_encore_and_clear(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--set-encore", "16")
    assert read_overrides(ws).encore_after == 16
    cli_invoke(cfg, "fix", "gratefuldead", "--clear-encore")
    assert read_overrides(ws).encore_after is None


def test_set_encore_composes_with_set_breaks(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    ws = _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    cli_invoke(cfg, "fix", "gratefuldead", "--set-breaks", "7", "--set-encore", "16")
    ov = read_overrides(ws)
    assert ov.set_breaks == [7]
    assert ov.encore_after == 16


def test_set_encore_redoes_from_gather(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    _stub_redo(monkeypatch)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-encore", "16", "--no-run")
    assert r.exit_code == 0, r.output
    assert "--from gather" in r.output


def test_set_encore_non_numeric_errors_cleanly(tmp_path):
    cfg = _cfg(tmp_path)
    _gathered_show(tmp_path)
    r = cli_invoke(cfg, "fix", "gratefuldead", "--set-encore", "sixteen")
    assert r.exit_code != 0
    assert "--set-encore expects" in r.output
    assert not isinstance(r.exception, ValueError)
```

`_cfg`, `_gathered_show`, `_stub_redo`, `cli_invoke` and `read_overrides` are all already imported/defined in that file.

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_fix.py -k encore -v`
Expected: FAIL — no such option `--set-encore`.

- [ ] **Step 3: Thread the field through `_edit_overrides`**

In `packages/llama/src/llama/cli.py`, add two keyword parameters to `_edit_overrides` (line 558-560), after `clear_set_breaks`:

```python
                    encore_after=_UNSET, clear_encore=False):
```

and, directly after the existing `clear_set_breaks` / `set_breaks` block (line 584-587):

```python
    if clear_encore:
        data = data.model_copy(update={"encore_after": None})
    elif encore_after is not _UNSET:
        data = data.model_copy(update={"encore_after": encore_after})
```

- [ ] **Step 4: Add the CLI options**

In the `fix` signature (line 1162-1165), after `clear_set_breaks`:

```python
    set_encore: str = typer.Option(
        None, "--set-encore",
        help="Mark the encore: it begins after track N (same convention as --set-breaks)"),
    clear_encore: bool = typer.Option(
        False, "--clear-encore", help="Clear the encore override"),
```

After the `set_breaks` parsing block (line 1194-1199):

```python
    encore_val = None
    if set_encore:
        if not set_encore.strip().isdigit():
            typer.echo(f"--set-encore expects a track number, got {set_encore!r}", err=True)
            raise typer.Exit(1)
        encore_val = int(set_encore.strip())
```

Extend `did_meta` (line 1202-1203) to include the new flags:

```python
    did_meta = bool(set_venue or set_city or set_date or parsed_titles
                    or clear_title_nums or set_breaks or clear_set_breaks
                    or set_encore or clear_encore)
```

And extend the `_edit_overrides` call (line 1243-1251):

```python
            set_breaks=breaks_val if set_breaks else _UNSET,
            clear_set_breaks=clear_set_breaks,
            encore_after=encore_val if set_encore else _UNSET,
            clear_encore=clear_encore)
```

`did_meta` already routes to `stage = "gather"`, so no change is needed there.

- [ ] **Step 5: Surface it in the two read-only displays**

After line 828-829 (`set_breaks` display):

```python
    if ov.encore_after is not None:
        parts.append(f"encore_after={ov.encore_after}")
```

And in `_print_show_json`'s `data["overrides"]` dict (line 878-882), add:

```python
            "encore_after": ov.encore_after,
```

- [ ] **Step 6: Run to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_fix.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_fix.py
git commit -m "feat(cli): add fix --set-encore / --clear-encore"
```

---

### Task 6: `Track.matched`, populated from `AlignResult.matched`

**Files:**
- Modify: `packages/llama/src/llama/models.py:150-157` (`Track`)
- Modify: `packages/llama/src/llama/stages/gather.py:631-633` (the post-align `model_copy`)
- Test: `packages/llama/tests/test_stage_gather.py`, `packages/llama/tests/test_models.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `Track.matched: bool | None`. Task 7 renders it.

- [ ] **Step 1: Write the failing tests**

Add to `packages/llama/tests/test_models.py`:

```python
def test_track_matched_defaults_to_unknown():
    from llama.models import Track

    t = Track(index=1, set="1", title="Bertha", filename="a.mp3")
    assert t.matched is None


def test_manifest_track_has_no_matched_field():
    """The cue is show-internal. ManifestTrack is the package contract emcee
    reads; adding a field there would be a contract change."""
    from llama.models import ManifestTrack

    assert "matched" not in ManifestTrack.model_fields
```

Add to `packages/llama/tests/test_stage_gather.py`:

These mirror `test_gather_recovers_structure_from_sibling` (line 121) — same helpers, same fixture. gd74 aligns deterministically at coverage 1.0 over 27 tracks, so every track is measured:

```python
def test_align_result_matched_reaches_the_track(tmp_path: Path):
    """AlignResult.matched was computed per track, used for coverage, and
    discarded. It is the only record of whether a title matched a canonical
    setlist item -- title_source says only where the title came from."""
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, gd74_ia(), FakeProvider(), gd74_candidate(), W_IDENT)
    assert show.structure.alignment == "deterministic"
    assert all(t.matched is not None for t in show.tracks), \
        "the deterministic path measures every track"
    assert any(t.matched is True for t in show.tracks)


def test_override_path_leaves_matched_unmeasured(tmp_path: Path):
    """The override path skips align() and forces coverage to 1.0, so there is
    no per-track match data. None must mean unknown, never matched."""
    sws = ShowWorkspace(tmp_path / "show")
    write_artifact(sws.overrides, Overrides(set_breaks=[11], encore_after=26))
    show = run_gather(sws, gd74_ia(), FakeProvider(), gd74_candidate(), W_IDENT)
    assert show.structure.alignment == "override"
    assert all(t.matched is None for t in show.tracks)
```

The second test also covers Task 4's override path end-to-end. `Overrides` and `write_artifact` may need importing at the top of the file — check and add if absent.

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_models.py -k "matched" packages/llama/tests/test_stage_gather.py -k "matched" -v`
Expected: FAIL — `Track` has no `matched`.

- [ ] **Step 3: Add the field**

In `packages/llama/src/llama/models.py`, inside `Track`, after `title_source`:

```python
    # Did this track match a canonical setlist item? None = not measured --
    # the override path skips align() entirely and forces coverage to 1.0, so
    # rendering unknown as "matched" would assert something never checked.
    matched: bool | None = None
```

- [ ] **Step 4: Populate it in gather**

At `packages/llama/src/llama/stages/gather.py:631-633`, extend the existing zip:

```python
        tracks = [t.model_copy(update={"set": s, "segue": g, "matched": m})
                  for t, s, g, m in zip(tracks, result.sets, result.segues, result.matched)]
```

Leave the override path (Task 4's block) untouched — `matched` stays `None` there by design.

- [ ] **Step 5: Run to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_models.py packages/llama/tests/test_stage_gather.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: all green. Watch for snapshot-style tests asserting exact `show.json` contents — if one fails purely because of the new key, update the expected fixture; do not drop the field.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/models.py packages/llama/src/llama/stages/gather.py packages/llama/tests/test_models.py packages/llama/tests/test_stage_gather.py
git commit -m "feat(models): carry AlignResult.matched through to Track

It was computed per track, used for coverage, and discarded. None means
not measured (the override path skips align), not matched."
```

---

### Task 7: Render the cue in `_format_tracks`

**Files:**
- Modify: `packages/llama/src/llama/cli.py:627-637` (`_format_tracks`)
- Test: `packages/llama/tests/test_cli.py`

**Interfaces:**
- Consumes: `Track.matched` from Task 6.
- Produces: nothing consumed by later tasks.

One renderer change covers `show --tracks` (line 841), `_pick_excludes` (line 642) and `triage`.

- [ ] **Step 1: Write the failing tests**

Add to `packages/llama/tests/test_cli.py`:

```python
def _show_with(matched_flags):
    from llama.models import Show, Track

    return Show(
        performance_id="x/1990-03-29", identifier="gd90-03-29", artist="Grateful Dead",
        date="1990-03-29",
        tracks=[Track(index=i + 1, set="1", title=f"Song {i + 1}",
                      filename=f"t{i + 1}.mp3", title_source="tags", matched=m)
                for i, m in enumerate(matched_flags)])


def test_format_tracks_flags_an_unmatched_track():
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([True, False]))
    assert "?" not in lines[1], "a matched track carries no marker"
    assert "?" in lines[2], "an unmatched track is marked"
    assert any("? = no setlist match" in ln for ln in lines), "legend must appear"


def test_format_tracks_renders_unknown_distinctly():
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([None, None]))
    assert "?" not in "".join(lines), "unknown must not read as unmatched"
    assert "-" in lines[1]


def test_format_tracks_omits_the_legend_when_everything_matched():
    from llama.cli import _format_tracks

    lines = _format_tracks(_show_with([True, True]))
    assert not any("no setlist match" in ln for ln in lines)
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_cli.py -k format_tracks -v`
Expected: FAIL — no marker rendered, no legend.

- [ ] **Step 3: Implement the cue**

Replace `packages/llama/src/llama/cli.py:627-637` with:

```python
def _format_tracks(show) -> list[str]:
    # title_source says where a title CAME FROM, not whether it MATCHED. The
    # gd1990-03-29 encore read "tags" -- the most ordinary value there is --
    # while matching nothing, so the only symptom was a hold naming a
    # different song. The two are orthogonal; this column carries the second.
    _MARK = {True: " ", False: "?", None: "-"}
    lines = ["tracks:"]
    for t in show.tracks:
        title = t.title if t.title_source != "unresolved" else "(unknown)"
        # duration before filename so a long filename can print in full without
        # misaligning the numeric column.
        # 14 is the width of the longest title_source, "sibling-format" - at 10
        # it rendered as "sibling-fo". Nothing wider exists: tags 4, setlist 7,
        # sibling 7, override 8, unresolved 10.
        lines.append(f"  {t.index:2d}. set {t.set:6.6s} {_MARK[t.matched]} {title:28.28s} "
                     f"{t.title_source:14.14s} {_fmt_dur(t.duration_sec):>6s}  {t.filename}")
    if any(t.matched is False for t in show.tracks):
        lines.append("  ? = no setlist match")
    return lines
```

- [ ] **Step 4: Run to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_cli.py -k format_tracks -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: all green. Several CLI tests assert on `--tracks` output; if any fail on column position rather than content, update the expected strings.

- [ ] **Step 6: Verify against the real held show**

Run: `./.venv/bin/llama show gratefuldead-1990-03-29 --tracks`
Expected: the track table renders with the new column. This show currently carries a title override, so `matched` will be `None` (`-`) until it is re-gathered — that is correct behaviour, not a bug. Report the actual output.

- [ ] **Step 7: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_cli.py
git commit -m "feat(cli): flag tracks that matched no setlist item

title_source says where a title came from, not whether it matched; the
gd1990-03-29 encore read 'tags' while matching nothing."
```

---

## Final verification

- [ ] **Full suite:** `./.venv/bin/pytest -q` — all green, count >= 1416 plus the new tests.
- [ ] **Corpus acceptance (spec A4.2):** re-gather the local library and confirm no show's set structure changes except `gratefuldead-1990-03-29`. Compare `set_breaks` and per-track `set` before and after across `~/.llama/shows/*/show.json`. Any other show that moves must be explained before merge, not after.
- [ ] **Docs:** update `CLAUDE.md`'s override list — `overrides.json` gains `encore_after`, and `llama fix` gains `--set-encore` / `--clear-encore`. The "Domain gotchas" title-cascade paragraph should note the `-in'` fold beside the existing `&`/`and` note.
