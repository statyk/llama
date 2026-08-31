# Title Correspondence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop an untagged tape shipping filenames as track titles when the setlist is documented, without ever silently adopting a wrong title.

**Architecture:** Two pieces at different trust levels. Piece 1 (Phase A) is an automatic `setlist-gap` rung in `gather` that fills runs of unresolved tracks only when the run is *count-forced* between tag-verified anchors — measured 2.4% wrong. Piece 2 (Phase B) is `llama fix --suggest-titles`, a correspondence DP that renders a proposal table and, on operator confirmation, writes every title into `overrides.json` in one shot — turning 24 manual `--set-title` calls into one. Phase C is the measurement gates that authorize shipping.

**Tech Stack:** Python 3.12+, Pydantic v2, Typer, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-30-title-correspondence-design.md`

## Global Constraints

- No new runtime dependencies.
- `parse_setlist` must not be modified — every existing corpus measurement is taken against its current behaviour.
- `titles.py:129`'s dead setlist rung stays; annotate, do not delete.
- Adopted titles are always the **canonical item's** text, never a model's or a synthesized string.
- No margins or scoring may gate an *automatic* adoption. Scoring is measurably unable to carry that decision (blind-the-tags: 41.8% wrong even at margin >= 240 s).
- `structure.py` must not import `stages/gather.py` — pass `metadata_norms` in as a parameter.
- Tests run offline against the `fake` LLM backend. Full suite: `pytest -q` — baseline measured 2026-08-31 on branch `title-correspondence`: **1479 passed, 7 deselected**.
- In a worktree, use that worktree's own `.venv` and run `./.venv/bin/pytest`.

## Deviation from the spec, already decided

The spec places Piece 1 between `resolve_titles` and the `overrides.titles` loop. **Implement it after the overrides loop instead**, skipping tracks whose `title_source == "override"`. At the spec's position no anchors exist yet, and an operator-forced title could not anchor a gap. Overrides still win; they can now also anchor.

## File Structure

| File | Responsibility |
|---|---|
| `packages/llama/src/llama/setlist.py` | Modify: promote `_is_junk_title` -> `is_junk_title` |
| `packages/llama/src/llama/structure.py` | Modify: add `adopt_gap_titles` + helpers (Piece 1, matching layer) |
| `packages/llama/src/llama/correspondence.py` | **Create**: the Piece 2 DP. Pure, no I/O, no LLM |
| `packages/llama/src/llama/models.py` | Modify: `title_source` comment; add `TitleProposal`, `ProposalRow` |
| `packages/llama/src/llama/stages/gather.py` | Modify: call `adopt_gap_titles` |
| `packages/llama/src/llama/titles.py` | Modify: annotate the dead rung |
| `packages/llama/src/llama/cli.py` | Modify: `fix --suggest-titles`; triage resolution |
| `packages/llama/tests/fixtures/ymsb2005_metadata.json` | **Create**: real 24-file untagged tape vs 25-item description |
| `packages/llama/tests/test_structure.py` | Modify: `adopt_gap_titles` unit tests |
| `packages/llama/tests/test_correspondence.py` | **Create**: DP unit tests |
| `packages/llama/tests/test_stage_gather.py` | Modify: integration + downstream pins |
| `packages/llama/tests/test_cli.py` | Modify: `--suggest-titles` tests |
| `docs/superpowers/2026-08-31-gap-fill-blind-test.md` | **Create**: M1 evidence doc |
| `scripts/blind_tag_gapfill.py`, `scripts/regather_diff.py` | **Create**: M1 / M2 harnesses |

---

# Phase A — Piece 1: the automatic gap-fill rung

### Task 1: `adopt_gap_titles` (pure function)

**Files:**
- Modify: `packages/llama/src/llama/setlist.py:353`
- Modify: `packages/llama/src/llama/structure.py` (append near `apply_llm_alignment`, ~line 940)
- Test: `packages/llama/tests/test_structure.py`

**Interfaces:**
- Consumes: `fuzzy_norm_title(title, aliases)`, `title_components(title, aliases)`, `_merge_run(norms, lo, hi, comps)` — all existing in `structure.py`. `is_real_title` from `titles.py`. `MAX_TITLE_LEN` from `setlist.py`.
- Produces: `structure.adopt_gap_titles(tracks, canonical, *, metadata_norms, aliases=None) -> list[Track]` and `setlist.is_junk_title(title) -> bool`.

**Design notes for the implementer:**

The anchor pass uses **exact normalized equality only**. Do NOT reuse `_window_match` here: its subphrase fallback is deliberately loose for structure recovery, and an anchor that matched by subphrase is too weak to license adopting titles either side of it. `_merge_run` IS reused, because a tagged track titled `"A > B"` consumes two canonical items, and mis-advancing the pointer past a merged anchor shifts every gap that follows.

- [ ] **Step 1: Promote the junk predicate**

In `packages/llama/src/llama/setlist.py`, rename `_is_junk_title` to `is_junk_title` and update its call sites within that file. Add below it:

```python
_is_junk_title = is_junk_title  # back-compat alias; prefer the public name
```

Run: `./.venv/bin/pytest packages/llama/tests/test_setlist.py -q`
Expected: PASS (rename only).

- [ ] **Step 2: Write the failing tests**

Add to `packages/llama/tests/test_structure.py`:

```python
from llama.models import ParsedSetlist, SetlistItem, Track
from llama.structure import adopt_gap_titles


def _items(*specs):
    """specs: (title, set, segue) triples."""
    return ParsedSetlist(
        items=[SetlistItem(title=t, normalized=t.lower(), set=s, segue=g)
               for t, s, g in specs],
        confidence="high")


def _tracks(*specs):
    """specs: (title, title_source) pairs."""
    return [Track(index=i + 1, set="1", title=t, filename=f"f{i + 1}.mp3",
                  duration_sec=300.0, title_source=src)
            for i, (t, src) in enumerate(specs)]


def test_count_forced_interior_gap_adopts():
    canonical = _items(("Alpha", "1", False), ("Bravo", "1", False),
                       ("Charlie", "1", False), ("Delta", "1", False))
    tracks = _tracks(("Alpha", "tags"), ("f2.mp3", "unresolved"),
                     ("f3.mp3", "unresolved"), ("Delta", "tags"))
    out = adopt_gap_titles(tracks, canonical, metadata_norms=set())
    assert [t.title for t in out] == ["Alpha", "Bravo", "Charlie", "Delta"]
    assert [t.title_source for t in out] == [
        "tags", "setlist-gap", "setlist-gap", "tags"]


def test_gap_whose_counts_disagree_declines_whole():
    canonical = _items(("Alpha", "1", False), ("Bravo", "1", False),
                       ("Charlie", "1", False), ("Delta", "1", False))
    tracks = _tracks(("Alpha", "tags"), ("f2.mp3", "unresolved"), ("Delta", "tags"))
    out = adopt_gap_titles(tracks, canonical, metadata_norms=set())
    assert out[1].title_source == "unresolved"
    assert out[1].title == "f2.mp3"


def test_unanchored_run_declines():
    canonical = _items(("Alpha", "1", False), ("Bravo", "1", False))
    tracks = _tracks(("f1.mp3", "unresolved"), ("f2.mp3", "unresolved"))
    out = adopt_gap_titles(tracks, canonical, metadata_norms=set())
    assert all(t.title_source == "unresolved" for t in out)


def test_tail_edge_run_adopts_with_one_real_anchor():
    canonical = _items(("Alpha", "1", False), ("Bravo", "1", False))
    tracks = _tracks(("Alpha", "tags"), ("f2.mp3", "unresolved"))
    out = adopt_gap_titles(tracks, canonical, metadata_norms=set())
    assert out[1].title == "Bravo" and out[1].title_source == "setlist-gap"


def test_head_edge_run_adopts_with_one_real_anchor():
    canonical = _items(("Alpha", "1", False), ("Bravo", "1", False))
    tracks = _tracks(("f1.mp3", "unresolved"), ("Bravo", "tags"))
    out = adopt_gap_titles(tracks, canonical, metadata_norms=set())
    assert out[0].title == "Alpha" and out[0].title_source == "setlist-gap"


def test_a_merged_tag_anchor_consumes_both_its_items():
    # "Alpha > Bravo" is ONE file holding TWO items; without _merge_run the
    # pointer stops at Alpha and the gap adopts Bravo instead of Charlie.
    canonical = _items(("Alpha", "1", True), ("Bravo", "1", False),
                       ("Charlie", "1", False))
    tracks = _tracks(("Alpha > Bravo", "tags"), ("f2.mp3", "unresolved"))
    out = adopt_gap_titles(tracks, canonical, metadata_norms=set())
    assert out[1].title == "Charlie"


def test_override_titles_anchor_and_are_never_overwritten():
    canonical = _items(("Alpha", "1", False), ("Bravo", "1", False),
                       ("Charlie", "1", False))
    tracks = _tracks(("Alpha", "override"), ("f2.mp3", "unresolved"),
                     ("Charlie", "tags"))
    out = adopt_gap_titles(tracks, canonical, metadata_norms=set())
    assert out[0].title_source == "override"
    assert out[1].title == "Bravo" and out[1].title_source == "setlist-gap"


def test_hygiene_rejects_a_junk_item():
    canonical = _items(("Alpha", "1", False), ("Set List:", "1", False),
                       ("Charlie", "1", False))
    tracks = _tracks(("Alpha", "tags"), ("f2.mp3", "unresolved"), ("Charlie", "tags"))
    out = adopt_gap_titles(tracks, canonical, metadata_norms=set())
    assert out[1].title_source == "unresolved"


def test_hygiene_rejects_show_metadata_residue():
    canonical = _items(("Alpha", "1", False), ("Fillmore Auditorium", "1", False),
                       ("Charlie", "1", False))
    tracks = _tracks(("Alpha", "tags"), ("f2.mp3", "unresolved"), ("Charlie", "tags"))
    out = adopt_gap_titles(tracks, canonical, metadata_norms={"fillmore auditorium"})
    assert out[1].title_source == "unresolved"


def test_empty_canonical_is_a_no_op():
    tracks = _tracks(("f1.mp3", "unresolved"))
    out = adopt_gap_titles(tracks, ParsedSetlist(), metadata_norms=set())
    assert out[0].title_source == "unresolved"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -q -k adopt or gap or anchor or hygiene`
Expected: FAIL with `ImportError: cannot import name 'adopt_gap_titles'`

- [ ] **Step 4: Implement**

Append to `packages/llama/src/llama/structure.py`:

```python
def _unresolved_runs(tracks: list["Track"]) -> list[tuple[int, int]]:
    """Maximal inclusive [lo, hi] runs of consecutive unresolved tracks."""
    runs, lo = [], None
    for pos, t in enumerate(tracks):
        if t.title_source == "unresolved":
            lo = pos if lo is None else lo
        elif lo is not None:
            runs.append((lo, pos - 1))
            lo = None
    if lo is not None:
        runs.append((lo, len(tracks) - 1))
    return runs


def _hygienic(title: str, metadata_norms: set[str]) -> bool:
    """A canonical item fit to become a shipped title. Deliberately strict:
    this is the only silent adopter in the pipeline."""
    from llama.setlist import MAX_TITLE_LEN, is_junk_title
    from llama.titles import is_real_title
    t = title.strip()
    return (bool(t) and is_real_title(t) and not is_junk_title(t)
            and len(t) <= MAX_TITLE_LEN and not t.endswith(":")
            and fuzzy_norm_title(t) not in metadata_norms)


def adopt_gap_titles(tracks: list["Track"], canonical: ParsedSetlist, *,
                     metadata_norms: set[str],
                     aliases: dict[str, str] | None = None) -> list["Track"]:
    """Fill runs of unresolved tracks that are COUNT-FORCED between
    tag-verified anchors.

    Count-forced is the whole safety argument: when a gap's item count equals
    its file count exactly, no merge, filler or skip is needed to make it fit,
    so there is no assignment freedom for an off-by-one shift to hide in.
    Unanchored monotone correspondence measured 45-52% wrong on the
    blind-the-tags corpus and margin could not discriminate; this evidence
    class measured 2.4%. See the spec.

    Anchors match by EXACT normalized equality. `_window_match` is deliberately
    NOT used: its subphrase fallback is right for structure recovery and too
    weak to license adopting titles on either side of the match.

    `metadata_norms` is passed in rather than imported: it is built in
    stages/gather.py, and structure.py must not depend on a stage.
    """
    items = canonical.items
    if not items or not tracks:
        return tracks
    norms = [fuzzy_norm_title(it.title, aliases) for it in items]

    # Anchor pass: monotone walk over tracks that already carry a title.
    anchors: dict[int, tuple[int, int]] = {}   # track pos -> half-open item span
    j = 0
    for pos, t in enumerate(tracks):
        if t.title_source == "unresolved":
            continue
        comps = title_components(t.title, aliases)
        if len(comps) > 1:
            run = _merge_run(norms, j, len(norms), comps)
            if run is not None:
                anchors[pos] = (run, run + len(comps))
                j = run + len(comps)
                continue
        nt = fuzzy_norm_title(t.title, aliases)
        hit = next((k for k in range(j, len(norms)) if norms[k] == nt), None)
        if hit is None:
            continue
        anchors[pos] = (hit, hit + 1)
        j = hit + 1

    out = list(tracks)
    for lo, hi in _unresolved_runs(tracks):
        left = anchors.get(lo - 1) if lo > 0 else None
        right = anchors.get(hi + 1) if hi + 1 < len(tracks) else None
        if left is not None and right is not None:
            span = (left[1], right[0])
        elif left is not None and hi == len(tracks) - 1:
            span = (left[1], len(items))
        elif right is not None and lo == 0:
            span = (0, right[0])
        else:
            continue
        gap = items[span[0]:span[1]]
        if len(gap) != hi - lo + 1:          # not count-forced
            continue
        if not all(_hygienic(it.title, metadata_norms) for it in gap):
            continue
        for off, it in enumerate(gap):
            out[lo + off] = out[lo + off].model_copy(
                update={"title": it.title.strip(), "title_source": "setlist-gap"})
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -q`
Expected: PASS, no regressions in the existing structure tests.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/src/llama/setlist.py packages/llama/tests/test_structure.py
git commit -m "feat(structure): adopt_gap_titles, count-forced anchored gap fill

Wired up in the next commit. pytest packages/llama/tests/test_structure.py -q green."
```

---

### Task 2: Wire into `gather`, add the `setlist-gap` source

**Files:**
- Create: `packages/llama/tests/fixtures/ymsb2005_metadata.json`
- Modify: `packages/llama/src/llama/models.py:157`
- Modify: `packages/llama/src/llama/titles.py:129` (comment only)
- Modify: `packages/llama/src/llama/stages/gather.py` (after the `overrides.titles` loop, ~line 602)
- Test: `packages/llama/tests/test_stage_gather.py`

**Interfaces:**
- Consumes: `structure.adopt_gap_titles` from Task 1.
- Produces: tracks may now carry `title_source == "setlist-gap"`; every later consumer in `run_gather` sees adopted titles.

- [ ] **Step 1: Capture the fixture**

```bash
python scripts/capture_fixture.py ymsb2005-12-31.flac16.wav \
  packages/llama/tests/fixtures/ymsb2005_metadata.json
```

Verify it is the expected shape:

```bash
./.venv/bin/python -c "
import json
from llama.junk import filter_files, FORMAT_BY_AUDIO
from llama.setlist import parse_setlist
md = json.load(open('packages/llama/tests/fixtures/ymsb2005_metadata.json'))
kept, _, _ = filter_files(md['files'], want_format=FORMAT_BY_AUDIO['mp3'])
d = md['metadata']['description']
p = parse_setlist(d if isinstance(d, str) else ' '.join(d))
print(len(kept), 'tracks;', len(p.items), 'items;', p.confidence)
assert (len(kept), len(p.items), p.confidence) == (24, 25, 'high')
print('fixture OK')"
```

Expected: `24 tracks; 25 items; high` then `fixture OK`.

- [ ] **Step 2: Write the failing tests**

Add to `packages/llama/tests/test_stage_gather.py` (`YMSB_FIXTURE = FIXTURES / "ymsb2005_metadata.json"`, `Y_IDENT = "ymsb2005-12-31.flac16.wav"` beside the existing constants):

```python
def _ymsb_candidate():
    return Candidate(
        performance_id="YonderMountainStringBand/2005-12-31",
        collection="YonderMountainStringBand", date="2005-12-31",
        venue="Fillmore Auditorium", city="Denver, CO",
        recordings=[RecordingSummary(identifier=Y_IDENT)])


def test_gap_fill_resolves_a_mixed_show(tmp_path: Path):
    """Tagged tracks anchor; the count-forced unresolved run between them fills."""
    md = json.loads(FIXTURE.read_text())
    mp3s = [f for f in md["files"] if f.get("format") == "VBR MP3"]
    for i, f in enumerate(mp3s):
        f["title"] = None if i in (1, 2) else f.get("title")
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    filled = [t for t in show.tracks if t.title_source == "setlist-gap"]
    assert filled, "expected the blanked run to be gap-filled"
    assert all(t.title_source != "unresolved" for t in show.tracks)


def test_a_fully_tagged_show_is_untouched(tmp_path: Path):
    md = json.loads(FIXTURE.read_text())
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT)
    assert not any(t.title_source == "setlist-gap" for t in show.tracks)


def test_a_wholly_untagged_tape_gets_no_gap_fill(tmp_path: Path):
    """ymsb2005 has no tagged track, therefore no anchor, therefore no
    adoption. Piece 1 deliberately does NOT solve the whole-tape case; that
    is Piece 2's job."""
    md = json.loads(YMSB_FIXTURE.read_text())
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), _ymsb_candidate(), Y_IDENT)
    assert all(t.title_source == "unresolved" for t in show.tracks)
    assert show.needs_review is True
    assert "unresolved track titles" in show.review_flags
```

- [ ] **Step 3: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -q -k "gap_fill or fully_tagged or wholly_untagged"`
Expected: FAIL — `test_gap_fill_resolves_a_mixed_show` asserts on a `setlist-gap` source nothing produces yet.

- [ ] **Step 4: Implement the wiring**

In `stages/gather.py`, immediately AFTER the `for n, forced in overrides.titles.items():` loop (so operator overrides both win and can anchor), insert:

```python
    # Fill count-forced runs of unresolved tracks between tag-verified anchors.
    # Runs here, after the overrides loop, so an operator-forced title can
    # ANCHOR a gap as well as survive it. metadata_norms is passed down
    # because structure.py must not import a stage.
    tracks = adopt_gap_titles(
        tracks, canonical,
        metadata_norms=_show_metadata_norms(artist, candidate, meta, events),
        aliases=GD_SHORTHAND if jerrybase.is_family_artist(artist) else {})
```

Add `adopt_gap_titles` to the existing `from llama.structure import (...)` block.

**Ordering note:** `events` is resolved above this point in `run_gather`; `canonical` has already been through `_strip_head_banner` and `_drop_artist_items`. Both are required — the head-banner strip is what stops a taper banner becoming an adopted title.

In `models.py:157`, extend the comment:

```python
    title_source: str  # "tags" | "sibling-format" | "setlist" | "setlist-gap" | "sibling" | "unresolved" | "override"
```

In `titles.py`, above line 129, add:

```python
    # The whole-tape setlist rung. MEASURED DEAD: 0 of 2,015 tracks across the
    # 89-show library (2026-08-30) — exact count equality between a parsed
    # description and a tape's file list is close to a measure-zero event.
    # Kept because structure.adopt_gap_titles is its localized successor
    # (count-forced GAPS between anchors), which makes this rung's deadness a
    # design property rather than a defect to re-diagnose.
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -q && ./.venv/bin/pytest -q`
Expected: PASS, 1479 + new tests, zero regressions.

- [ ] **Step 6: Commit**

```bash
git add -A packages/llama
git commit -m "feat(gather): setlist-gap title rung

Fills count-forced runs of unresolved tracks between tag-verified anchors.
Runs after the overrides loop so operator titles anchor as well as win.
pytest -q green."
```

---

### Task 3: Pin the downstream behaviour change

Adopted titles make three previously-inert checks live on these shows: the closer tripwire, the multi-event spans check, and `vet_research.grounding_flags`. That is desirable, and an unstated behaviour change is a bug report waiting to be filed.

**Files:**
- Test: `packages/llama/tests/test_stage_gather.py`

- [ ] **Step 1: Write the test**

```python
def test_adopted_titles_make_the_closer_tripwire_reachable(tmp_path: Path):
    """With filenames as titles the closer check matches nothing and is
    silently inert. Once a gap is filled, a wrong closer must be able to
    speak. Pins the behaviour change so it is owned, not discovered."""
    md = json.loads(FIXTURE.read_text())
    mp3s = [f for f in md["files"] if f.get("format") == "VBR MP3"]
    for i, f in enumerate(mp3s):
        if i in (1, 2):
            f["title"] = None
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), make_candidate(), IDENT,
                      jerrybase_enabled=True)
    adopted = [t for t in show.tracks if t.title_source == "setlist-gap"]
    assert adopted
    # every adopted title is a real song name, so norm_title comparisons in the
    # closer/spans checks now have something to match against
    assert all(not t.title.endswith(".mp3") for t in adopted)
```

- [ ] **Step 2: Run to verify it fails, then passes**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py -q -k closer_tripwire_reachable`
Expected: PASS once Task 2 has landed (this is a characterization test — if it fails, Task 2's wiring is wrong).

- [ ] **Step 3: Commit**

```bash
git add packages/llama/tests/test_stage_gather.py
git commit -m "test(gather): pin that adopted titles make downstream checks live"
```

---

### Task 4: M1 — the blind-the-tags evidence doc (gates Phase A shipping unflagged)

**Files:**
- Create: `scripts/blind_tag_gapfill.py`
- Create: `docs/superpowers/2026-08-31-gap-fill-blind-test.md`

- [ ] **Step 1: Write the harness**

`scripts/blind_tag_gapfill.py` — for every cached item under `~/.llama/cache/md_*.json` with usable tags:

1. Build the **real gather canonical**, not raw `parse_setlist`: run `_collect_parses` -> `rank_parses` -> `_strip_head_banner` -> `_drop_artist_items` -> `blend_segues`. The pilot's use of raw `parse_setlist` is why its 45-52% figure is a bound rather than truth.
2. For each item, blank the tags of every maximal run of length 1-3 that has real-titled neighbours, one run at a time.
3. Call `adopt_gap_titles` and compare each adoption against the hidden tag via `fuzzy_norm_title` equality.
4. Emit per-adoption rows: identifier, track index, adopted, hidden, verdict.

- [ ] **Step 2: Run it and hand-triage**

```bash
./.venv/bin/python scripts/blind_tag_gapfill.py > /tmp/gapfill.tsv
```

Classify **every** wrong adoption into one of: `scorer-artifact`, `tag-typo-adoption-superior` (e.g. `Loset` -> `Loser`), `genuinely-wrong`. Counting is not enough — the pilot's headline number contained all three classes.

- [ ] **Step 3: Write the evidence doc**

`docs/superpowers/2026-08-31-gap-fill-blind-test.md`, to the standard of `docs/superpowers/2026-08-03-tail-guard-sanity-check.md`: name the snapshot commit, state the exact command, spy on the real function (never a reimplementation), and record the three-way triage with examples.

**Ship gate:** Phase A ships unflagged only if `genuinely-wrong` is at or below the tag rung's own typo baseline. Otherwise adopt but add a review flag, or do not ship Phase A. Record the standing caveat: offline runs have `setlistfm=None`, so these are bounds.

- [ ] **Step 4: Commit**

```bash
git add scripts/blind_tag_gapfill.py docs/superpowers/2026-08-31-gap-fill-blind-test.md
git commit -m "docs: M1 blind-the-tags evidence for the setlist-gap rung"
```

---

# Phase B — Piece 2: proposal and one-shot adoption

### Task 5: The correspondence DP

**Files:**
- Create: `packages/llama/src/llama/correspondence.py`
- Modify: `packages/llama/src/llama/models.py`
- Test: `packages/llama/tests/test_correspondence.py`

**Interfaces:**
- Consumes: `fuzzy_norm_title`; `ParsedSetlist`, `SetlistItem`, `Track`.
- Produces:
  - `models.ProposalRow(index: int, duration_sec: float | None, item_span: tuple[int, int] | None, title: str, evidence: str, margin_sec: float | None)`
  - `models.TitleProposal(rows: list[ProposalRow], feasible: bool, reason: str = "", evidence_source: str = "")`
  - `correspondence.propose_titles(tracks, canonical, *, item_durations=None, max_merge=3) -> TitleProposal`

- [ ] **Step 1: Add the models**

In `models.py`:

```python
class ProposalRow(BaseModel):
    index: int                                   # 1-based track number
    duration_sec: float | None = None
    item_span: tuple[int, int] | None = None     # half-open canonical range; None = filler
    title: str = ""                              # "" when the row is a decline
    evidence: str = ""                           # "sibling-duration" | "duration-model" | "filler"
    margin_sec: float | None = None


class TitleProposal(BaseModel):
    rows: list[ProposalRow] = Field(default_factory=list)
    feasible: bool = False
    reason: str = ""            # why not, when feasible is False
    evidence_source: str = ""   # "sibling-duration" | "duration-model"
```

- [ ] **Step 2: Write the failing tests**

`packages/llama/tests/test_correspondence.py`:

```python
from llama.correspondence import propose_titles
from llama.models import ParsedSetlist, SetlistItem, Track


def _canon(*specs):
    return ParsedSetlist(
        items=[SetlistItem(title=t, normalized=t.lower(), set=s, segue=g)
               for t, s, g in specs], confidence="high")


def _tracks(*durations):
    return [Track(index=i + 1, set="1", title=f"f{i + 1}.mp3",
                  filename=f"f{i + 1}.mp3", duration_sec=d,
                  title_source="unresolved")
            for i, d in enumerate(durations)]


def test_one_to_one_maps_straight_through():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    prop = propose_titles(_tracks(300.0, 300.0), canonical)
    assert prop.feasible
    assert [r.title for r in prop.rows] == ["Alpha", "Bravo"]


def test_a_segued_pair_merges_into_one_long_file():
    canonical = _canon(("Alpha", "1", True), ("Bravo", "1", False),
                       ("Charlie", "1", False))
    prop = propose_titles(_tracks(600.0, 300.0),
                          canonical, item_durations=[300.0, 300.0, 300.0])
    assert prop.rows[0].title == "Alpha > Bravo"
    assert prop.rows[1].title == "Charlie"


def test_a_merge_is_never_proposed_across_a_non_segue():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False),
                       ("Charlie", "1", False))
    prop = propose_titles(_tracks(600.0, 300.0),
                          canonical, item_durations=[300.0, 300.0, 300.0])
    # Alpha does not segue, so no merge is legal and the assignment cannot fit
    assert not prop.feasible


def test_a_short_filler_track_consumes_no_item():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    prop = propose_titles(_tracks(300.0, 20.0, 300.0),
                          canonical, item_durations=[300.0, 300.0])
    assert prop.rows[1].item_span is None
    assert prop.rows[1].evidence == "filler"


def test_infeasible_when_merges_needed_exceed_segue_markers():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False),
                       ("Charlie", "1", False), ("Delta", "1", False))
    prop = propose_titles(_tracks(300.0, 300.0), canonical)
    assert not prop.feasible
    assert "no consistent correspondence" in prop.reason


def test_margins_are_reported_per_row():
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    prop = propose_titles(_tracks(300.0, 300.0), canonical,
                          item_durations=[300.0, 300.0])
    assert all(r.margin_sec is not None for r in prop.rows)
```

- [ ] **Step 3: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_correspondence.py -q`
Expected: FAIL — `ModuleNotFoundError: llama.correspondence`

- [ ] **Step 4: Implement**

`packages/llama/src/llama/correspondence.py`:

```python
"""Whole-tape title correspondence: a proposal generator, never an adopter.

This DP is deliberately NOT wired into the pipeline. Measured on the
blind-the-tags corpus, unanchored monotone correspondence is 45-52% wrong and
margin does not discriminate, so its output requires a human. It exists to
render a proposal an operator confirms; the confirmation lands in
overrides.json. See docs/superpowers/specs/2026-08-30-title-correspondence-design.md.
"""
from llama.models import ParsedSetlist, ProposalRow, TitleProposal, Track
from llama.structure import fuzzy_norm_title

_INF = float("inf")


def _merge_legal(items, lo: int, k: int) -> bool:
    """A k-item merge is legal only if every item but the last segues on."""
    return k == 1 or all(items[i].segue for i in range(lo, lo + k - 1))


def _item_durations(tracks, items, given):
    if given is not None:
        return list(given), "sibling-duration"
    total = sum(t.duration_sec or 0.0 for t in tracks)
    mu = total / len(items) if items else 0.0
    return [mu] * len(items), "duration-model"


def _solve(tracks, items, idur, max_merge, forbid=None):
    """Min-cost monotone assignment. Returns (cost, spans) or (inf, None).
    `forbid` is an optional {track_pos: (lo, hi)} span the solution must avoid,
    used to compute per-row margins."""
    nt, ni = len(tracks), len(items)
    best = [[_INF] * (ni + 1) for _ in range(nt + 1)]
    back = [[None] * (ni + 1) for _ in range(nt + 1)]
    best[0][0] = 0.0
    for a in range(nt):
        dur = tracks[a].duration_sec or 0.0
        for b in range(ni + 1):
            if best[a][b] == _INF:
                continue
            for k in range(0, max_merge + 1):
                if b + k > ni:
                    break
                if k >= 1 and not _merge_legal(items, b, k):
                    continue
                if forbid and forbid.get(a) == (b, b + k):
                    continue
                cost = dur if k == 0 else abs(dur - sum(idur[b:b + k]))
                if best[a][b] + cost < best[a + 1][b + k]:
                    best[a + 1][b + k] = best[a][b] + cost
                    back[a + 1][b + k] = k
    if best[nt][ni] == _INF:
        return _INF, None
    spans, b = [], ni
    for a in range(nt, 0, -1):
        k = back[a][b]
        spans.append(None if k == 0 else (b - k, b))
        b -= k
    spans.reverse()
    return best[nt][ni], spans


def propose_titles(tracks: list[Track], canonical: ParsedSetlist, *,
                   item_durations: list[float] | None = None,
                   max_merge: int = 3) -> TitleProposal:
    items = canonical.items
    if not items:
        return TitleProposal(feasible=False, reason="no usable canonical setlist")
    idur, source = _item_durations(tracks, items, item_durations)
    cost, spans = _solve(tracks, items, idur, max_merge)
    if spans is None:
        return TitleProposal(
            feasible=False, evidence_source=source,
            reason="no consistent correspondence - parse quality too low")

    rows = []
    for pos, (t, span) in enumerate(zip(tracks, spans)):
        if span is None:
            rows.append(ProposalRow(index=t.index, duration_sec=t.duration_sec,
                                    item_span=None, title="", evidence="filler"))
            continue
        title = " > ".join(items[i].title.strip() for i in range(*span))
        alt, _ = _solve(tracks, items, idur, max_merge, forbid={pos: span})
        rows.append(ProposalRow(
            index=t.index, duration_sec=t.duration_sec, item_span=span,
            title=title, evidence=source,
            margin_sec=None if alt == _INF else alt - cost))
    return TitleProposal(rows=rows, feasible=True, evidence_source=source)
```

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/pytest packages/llama/tests/test_correspondence.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/correspondence.py packages/llama/src/llama/models.py packages/llama/tests/test_correspondence.py
git commit -m "feat(correspondence): title proposal DP (proposal only, never adopts)

pytest packages/llama/tests/test_correspondence.py -q green."
```

---

### Task 6: Extract the canonical builder; sibling item durations

Task 7 needs the same canonical setlist `gather` builds, and the same per-item
durations the sibling provides. Both are currently unreachable: the canonical
block is inline in `run_gather` (lines 524-546), and nothing computes item
durations at all. This task makes both callable without changing any behaviour.

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py:524-546`
- Modify: `packages/llama/src/llama/correspondence.py`
- Test: `packages/llama/tests/test_stage_gather.py`, `packages/llama/tests/test_correspondence.py`

**Interfaces:**
- Produces: `gather.build_canonical(ia, candidate, identifier, meta, kept, artist, events, *, setlistfm=None, provider=None) -> tuple[ParsedSetlist, list[str]]` — returns `(canonical, notes)`. The canonical is CLEANED (head banner stripped, artist items dropped), i.e. exactly what `run_gather` consumes; `notes` is the sibling-fetch failure list `run_gather` already collects and must keep. **`provider=None` skips the `extract_setlist` LLM fallback**, so a CLI edit command never fires an LLM call.
- Produces: `correspondence.sibling_item_durations(ia, candidate, identifier, canonical, want) -> list[float] | None` — per-canonical-item durations lifted from a tagged sibling recording, or None when no sibling resolves every item.

- [ ] **Step 1: Write the failing tests**

Add to `packages/llama/tests/test_stage_gather.py`:

```python
def test_build_canonical_matches_what_gather_uses(tmp_path: Path):
    """The extraction must be behaviour-preserving: same items, same order."""
    from llama.stages.gather import build_canonical
    md = json.loads(FIXTURE.read_text())
    kept, _, _ = filter_files(md["files"], want_format=("VBR MP3",))
    cand = make_candidate()
    canonical, notes = build_canonical(StubIA(md), cand, IDENT, md["metadata"],
                                       kept, "Grateful Dead", [])
    sws = ShowWorkspace(tmp_path / "show")
    show = run_gather(sws, StubIA(md), FakeProvider(), cand, IDENT)
    assert [i.title for i in canonical.items]
    assert len(canonical.items) >= len([t for t in show.tracks if t.matched])


def test_build_canonical_makes_no_llm_call_without_a_provider():
    from llama.stages.gather import build_canonical
    md = json.loads(FIXTURE.read_text())
    kept, _, _ = filter_files(md["files"], want_format=("VBR MP3",))
    fake = FakeProvider()
    build_canonical(StubIA(md), make_candidate(), IDENT, md["metadata"],
                    kept, "Grateful Dead", [], provider=None)
    # the fallback is the only LLM path in this function; without a provider
    # it must not be reached
    assert not fake.calls
```

Add to `packages/llama/tests/test_correspondence.py`:

```python
def test_sibling_item_durations_returns_none_without_a_tagged_sibling():
    from llama.correspondence import sibling_item_durations
    canonical = _canon(("Alpha", "1", False), ("Bravo", "1", False))
    cand = Candidate(performance_id="X/2000-01-01", collection="X",
                     date="2000-01-01",
                     recordings=[RecordingSummary(identifier="only")])
    assert sibling_item_durations(None, cand, "only", canonical, ("VBR MP3",)) is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_stage_gather.py packages/llama/tests/test_correspondence.py -q -k "build_canonical or sibling_item_durations"`
Expected: FAIL with `ImportError: cannot import name 'build_canonical'`.

- [ ] **Step 3: Extract `build_canonical`**

Move `stages/gather.py` lines 524-546 (canonical assembly) plus the two cleaning
calls (`_strip_head_banner`, `_drop_artist_items`) into a module-level function,
and have `run_gather` call it. The body is unchanged except the LLM guard:

```python
def build_canonical(ia, candidate: Candidate, identifier: str, meta: dict,
                    kept: list[dict], artist: str, events, *,
                    setlistfm=None, provider=None) -> tuple[ParsedSetlist, list[str]]:
    """The cleaned canonical performance setlist: every recording's
    description, plus setlist.fm when configured, ranked pick-best, then
    head-banner-stripped and artist-item-dropped.

    provider=None skips the extract_setlist LLM fallback, so callers outside
    the pipeline (llama fix --suggest-titles) never trigger an LLM call.
    """
    parses, notes, descriptions = _collect_parses(ia, candidate, identifier, meta)
    if setlistfm is not None:
        raw = setlistfm.setlist(artist, candidate.date,
                                venue=candidate.venue, city=candidate.city)
        converted = from_setlistfm(raw) if raw else None
        if converted is not None:
            parses.insert(0, SourcedParse(source="setlist.fm", parsed=converted))
    best = rank_parses(parses, target_count=len(kept))
    if best is None and provider is not None:
        longest = max(descriptions, key=len, default="")
        if longest.strip():
            parsed = run_json_task(provider, "extract_setlist", ParsedSetlist,
                                   template=load_prompt("extract_setlist"),
                                   description=longest)
            best = SourcedParse(source="llm", parsed=parsed)
    canonical = best.parsed if best else ParsedSetlist()
    if best is not None and best.source == "setlist.fm":
        best_lma = rank_parses([p for p in parses if p.source != "setlist.fm"],
                               target_count=len(kept))
        canonical = blend_segues(canonical, best_lma.parsed if best_lma else None)
    canonical = _strip_head_banner(
        canonical, _show_metadata_norms(artist, candidate, meta, events))
    return _drop_artist_items(canonical, artist), notes
```

**`run_gather` must keep `notes`.** It is returned as the second element rather
than re-derived: calling `_collect_parses` twice would re-fetch every sibling
recording's metadata. `run_gather`'s call site becomes:

```python
    canonical, notes = build_canonical(
        ia, candidate, identifier, meta, kept, artist, events,
        setlistfm=setlistfm, provider=provider)
```

Delete the now-duplicated `_strip_head_banner` / `_drop_artist_items` calls from
`run_gather` — they moved inside. The existing gather tests must stay green;
this extraction is behaviour-preserving.

- [ ] **Step 4: Implement `sibling_item_durations`**

Append to `packages/llama/src/llama/correspondence.py`:

```python
def sibling_item_durations(ia, candidate, identifier: str,
                           canonical: ParsedSetlist, want) -> list[float] | None:
    """Per-canonical-item durations lifted from a TAGGED sibling recording of
    the same performance.

    Requires every canonical item to match exactly one sibling track by
    normalized title. Anything less returns None rather than guessing by
    position - a partially-matched donor is exactly the 20%-wrong case the
    blind test measured.
    """
    from llama.junk import filter_files
    from llama.titles import clean_tag_titles
    if ia is None:
        return None
    norms = [fuzzy_norm_title(it.title) for it in canonical.items]
    for rec in candidate.recordings:
        if rec.identifier == identifier:
            continue
        try:
            kept, _, _ = filter_files(
                ia.metadata(rec.identifier).get("files", []), want_format=want)
        except Exception:
            continue
        by_norm: dict[str, float] = {}
        for f, title in zip(kept, clean_tag_titles(kept)):
            n = fuzzy_norm_title(title)
            if not n:
                continue
            if n in by_norm:          # ambiguous donor; refuse it
                by_norm[n] = -1.0
                continue
            from llama.util import length_seconds
            by_norm[n] = length_seconds(f.get("length")) or 0.0
        if all(by_norm.get(n, -1.0) > 0 for n in norms):
            return [by_norm[n] for n in norms]
    return None
```

Note the repeated-song limitation: a setlist with `On The Run` twice makes that
norm ambiguous and the donor is refused. That is deliberate and conservative;
the duration model is the fallback.

- [ ] **Step 5: Run the tests**

Run: `./.venv/bin/pytest -q`
Expected: PASS, 1479 + new, zero regressions. The extraction is behaviour-preserving.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/src/llama/correspondence.py packages/llama/tests
git commit -m "refactor(gather): extract build_canonical; add sibling_item_durations

build_canonical is behaviour-preserving and skips the extract_setlist LLM
fallback when given no provider, so CLI callers never trigger an LLM call.
pytest -q green."
```

---

### Task 7: `llama fix --suggest-titles`

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (the `fix` command, ~1183-1315)
- Test: `packages/llama/tests/test_cli.py`

**Interfaces:**
- Consumes: `correspondence.propose_titles` and `correspondence.sibling_item_durations` (Tasks 5, 6); `gather.build_canonical` (Task 6); `_edit_overrides(sws, set_titles={...})`.
- Produces: a `--suggest-titles` flag that is a `did_meta` edit, so the existing redo selector runs `gather`.

- [ ] **Step 1: Write the failing tests**

First the shared helper (put it beside the other builders in `test_cli.py`):

```python
def _staged_ymsb_show(tmp_path):
    """A ShowWorkspace holding the real 24-track untagged ymsb show, all
    titles unresolved, plus the provenance fix needs to rebuild the
    canonical."""
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    sws = ShowWorkspace(tmp_path / "ymsb2005-12-31")
    show = run_gather(sws, StubIA(md), FakeProvider(), _ymsb_candidate(),
                      "ymsb2005-12-31.flac16.wav")
    assert all(t.title_source == "unresolved" for t in show.tracks)
    return sws


def _staged_show_with_unusable_canonical(tmp_path):
    """Same tape, description replaced by prose that parses to nothing."""
    md = json.loads((FIXTURES / "ymsb2005_metadata.json").read_text())
    md["metadata"]["description"] = "A great night. Recorded from the balcony."
    sws = ShowWorkspace(tmp_path / "nocanon")
    run_gather(sws, StubIA(md), FakeProvider(), _ymsb_candidate(),
               "ymsb2005-12-31.flac16.wav")
    return sws
```

Then the tests:

```python
def test_suggest_titles_writes_every_row_into_overrides(tmp_path, monkeypatch):
    """One confirmation replaces 24 --set-title calls."""
    sws = _staged_ymsb_show(tmp_path)          # helper: show.json with 24 unresolved
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = runner.invoke(app, ["fix", str(sws.dir), "--suggest-titles", "--no-run"])
    assert result.exit_code == 0
    ov = read_overrides(sws)
    assert len(ov.titles) == 22
    assert ov.titles[1] == "Granny Woncha Smoke Some > Ride The Wild Turkey"
    assert 11 not in ov.titles and 22 not in ov.titles   # the two filler tracks


def test_declining_the_proposal_writes_nothing(tmp_path, monkeypatch):
    sws = _staged_ymsb_show(tmp_path)
    monkeypatch.setattr("typer.confirm", lambda *a, **k: False)
    result = runner.invoke(app, ["fix", str(sws.dir), "--suggest-titles"])
    assert result.exit_code == 0
    assert read_overrides(sws).titles == {}


def test_an_infeasible_show_declines_without_writing(tmp_path, monkeypatch):
    sws = _staged_show_with_unusable_canonical(tmp_path)
    result = runner.invoke(app, ["fix", str(sws.dir), "--suggest-titles"])
    assert "no consistent correspondence" in result.output
    assert read_overrides(sws).titles == {}
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_cli.py -q -k suggest_titles`
Expected: FAIL — `No such option: --suggest-titles`

- [ ] **Step 3: Implement**

Add the option to `fix`:

```python
    suggest_titles: bool = typer.Option(
        False, "--suggest-titles",
        help="Propose titles for unresolved tracks from the setlist and, on "
             "confirmation, write them all into overrides.titles at once"),
```

Before the `did_meta` computation, add the proposal branch. It renders every row, including declines, and writes only the titled ones:

```python
    if suggest_titles:
        show = read_model(sws.show, Show)
        cand = entry.provenance.candidate
        meta = ia.metadata(show.identifier).get("metadata", {})
        kept, _, _ = filter_files(ia.metadata(show.identifier).get("files", []),
                                  want_format=FORMAT_BY_AUDIO[config.audio_format])
        canonical, _ = build_canonical(ia, cand, show.identifier, meta, kept,
                                       show.artist, [], provider=None)
        prop = propose_titles(
            show.tracks, canonical,
            item_durations=sibling_item_durations(
                ia, cand, show.identifier, canonical,
                FORMAT_BY_AUDIO[config.audio_format]))
        if not prop.feasible:
            typer.echo(f"{entry.slug}: {prop.reason}")
            raise typer.Exit(0)
        typer.echo(f"{entry.slug}: proposal ({prop.evidence_source})")
        for r in prop.rows:
            cur = show.tracks[r.index - 1]
            shown = r.title or "(unresolved - hand-edit)"
            margin = f"{r.margin_sec:5.0f}s" if r.margin_sec is not None else "    -"
            typer.echo(f"  {r.index:2d}. {_fmt_dur(r.duration_sec):>6s} "
                       f"{margin}  {shown}")
        picks = {r.index: r.title for r in prop.rows
                 if r.title and show.tracks[r.index - 1].title_source == "unresolved"}
        if not picks:
            typer.echo("nothing to adopt: every track already has a title")
            raise typer.Exit(0)
        if not typer.confirm(f"write {len(picks)} titles into overrides?"):
            typer.echo("declined; nothing written")
            raise typer.Exit(0)
        parsed_titles.update(picks)
```

**Partial rendering is required:** rows the DP cannot title render as
`(unresolved - hand-edit)` and are simply absent from `picks`. Declining
wholesale would leave the `2002-12-31` class at 38 manual edits when a subset is
recoverable.

Add `suggest_titles` to the `did_meta` expression so the existing redo selector
picks `gather`:

```python
    did_meta = bool(set_venue or set_city or set_date or parsed_titles
                    or clear_title_nums or set_breaks or clear_set_breaks
                    or set_encore or clear_encore)
```

(`parsed_titles` is already in that expression — populating it above is
sufficient. Confirm this rather than adding a redundant term.)

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/pytest packages/llama/tests/test_cli.py -q && ./.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_cli.py
git commit -m "feat(cli): llama fix --suggest-titles

Renders a correspondence proposal and writes it to overrides.titles in one
confirmation. pytest -q green."
```

---

### Task 8: The `triage` resolution

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (the `triage` walkthrough, ~1321+)
- Test: `packages/llama/tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
def test_triage_offers_suggest_titles_on_an_unresolved_hold(tmp_path, monkeypatch):
    sws = _staged_ymsb_show(tmp_path)
    prompts = iter(["s", "y", "q"])       # suggest, confirm, quit
    monkeypatch.setattr("typer.prompt", lambda *a, **k: next(prompts))
    monkeypatch.setattr("typer.confirm", lambda *a, **k: True)
    result = runner.invoke(app, ["triage", str(sws.dir)])
    assert "suggest titles" in result.output.lower()
    assert read_overrides(sws).titles
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/pytest packages/llama/tests/test_cli.py -q -k triage_offers_suggest`
Expected: FAIL — the option is not offered.

- [ ] **Step 3: Implement**

In the triage walkthrough, offer `s) suggest titles` **only when** the show's
`review_flags` contain `"unresolved track titles"`. Reuse the exact rendering and
write path from Task 6 — extract it into a helper called by both, rather than
duplicating (DRY; a divergence between the two surfaces would be invisible).

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/pytest packages/llama/tests/test_cli.py -q && ./.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/cli.py packages/llama/tests/test_cli.py
git commit -m "feat(cli): offer suggest-titles inside triage for unresolved holds"
```

---

# Phase C — Gates

### Task 9: M2 and M3

**Files:**
- Create: `scripts/regather_diff.py`

- [ ] **Step 1: M2 — full-library no-op check**

`scripts/regather_diff.py` re-gathers all 89 shows offline from cache and asserts
**zero changes to any track that is currently resolved**. Adopted `setlist-gap`
titles on currently-unresolved tracks are the only permitted diff.

```bash
./.venv/bin/python scripts/regather_diff.py --assert-no-regressions
```

Expected: `0 regressions; N newly resolved`.

- [ ] **Step 2: M3 — render proposals for all 6 held shows**

```bash
for s in yondermountainstringband-2002-12-31 yondermountainstringband-2005-12-31 \
         delmccouryband-2003-04-19 infamousstringdusters-2014-03-15 \
         greenskybluegrass-2007-08-05 trampledbyturtles-2007-07-20; do
  ./.venv/bin/llama fix "$s" --suggest-titles --no-run < /dev/null
done
```

Check every table by hand. Expected: `ymsb2005-12-31` renders the exactly-correct
24 rows (22 titled, tracks 11 and 22 as `(unresolved - hand-edit)`);
`ymsb2002-12-31` renders either a partial table or the decline message, and must
not render a confident-looking wrong one.

- [ ] **Step 3: Record and commit**

Append the M2 and M3 results to
`docs/superpowers/2026-08-31-gap-fill-blind-test.md`.

```bash
git add scripts/regather_diff.py docs/superpowers/2026-08-31-gap-fill-blind-test.md
git commit -m "docs: M2 no-op check and M3 proposal review results"
```

---

## Notes for the executor

- **Phase A and Phase B ship independently.** Phase A is gated on M1; Phase B is gated on M3. M2 gates both. If M1 fails, Phase A is abandoned or ships flagged — that does not block Phase B, which is where the value is.
- **Do not make Piece 2's DP automatic**, however good its proposals look on a given show. The single-show 0/24 result that motivated this work did not survive contact with a 258-show blind test.
- **`ymsb2005-12-31` is not fixed by Phase A** and that is correct — it has no tagged track, so no anchor. Task 2 pins this.
