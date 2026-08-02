# Header truncation, parse ranking, and track-side prefixes (phase 4a) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `parse_setlist` discarding a whole setlist above a marker that cannot start a show, land the coupled encore-marker tolerance with it, stop a truncated parse outranking a complete one, and strip track-side numeric/duration prefixes at the matching layer.

Spec: `docs/superpowers/specs/2026-08-02-phase4a-truncation-design.md`

**Tech Stack:** Python 3.11+, Pydantic v2, pytest. No new dependencies.

## Global Constraints

- **No new dependencies.**
- **Tasks 1 and 2 are ONE change and land in ONE commit.** The coupling is a hard constraint from the spec: `_LEAD_DECOR` on `_ENCORE_LINE` alone costs 26 real songs. Never commit the encore tolerance without the truncation rule.
- **`songs.normalize_song` and `songs.DEFAULT_ALIASES` must not be edited** (standing invariant from phase 2). `Track.title` as stored is never modified — Task 3 works at the matching layer only.
- **Baseline: 1261 passed / 7 deselected** at `d431dd2`. **In a worktree, create its own venv and run `./.venv/bin/pytest`** — the repo-root `.venv` resolves `llama` to the main checkout and silently tests the wrong source.
- **Never verify library behavior with `llama show`** — it renders stored state and never re-runs `gather`.
- **Every number in a report or commit message states its baseline pair and its preprocessing.**
- **Commit after every task**, conventional-commit prefixes. Do not push, do not merge.

## Corrections to the spec, already executed — read before Task 1

The spec's §3 acceptance gate names two canaries with numbers that **do not reproduce at HEAD**. I ran them; both are stale, and an implementer who takes them literally will chase a phantom.

| spec says | actually at `d431dd2` | why |
|---|---|---|
| `nmas2013-02-13.16.44` → **≥32 items** with encore labelled | HEAD is 32 items, `sets=['1']`; **correct post-fix result is 31** | the one dropped item is the literal junk title `'---encore:'`, which becomes a *marker* instead of an item. Count goes DOWN by one; six songs gain `encore`. |
| `spindoctors2001-09-07` → **unchanged (53 items)** | HEAD is **37 items** | 53 was measured at C1 (`059c549`); later phase-3 tasks removed 16 junk items. Correct at the time, stale now. |

**Use the corrected gates in Task 1 Step 5.** Both were caught by executing the assertion rather than reading it — which is the discipline this plan exists to institutionalize (spec §"Measurement protocol"; phase-3 post-mortem: *unexecuted assertion* was the root cause of every phase-3 error).

---

### Task 1: Truncation rule + the coupled encore tolerance (spec §1 + §2)

Only a marker that can plausibly START a show may truncate the header. An encore marker or a `Set ≥2` marker cannot; when one is the first marker, probe the block above and keep it if it parses to ≥5 items on its own.

**Files:**
- Modify: `packages/llama/src/llama/setlist.py` (`_ENCORE_LINE`, its `SET MARKERS ONLY` comment block, and `parse_setlist`'s truncation)
- Test: `packages/llama/tests/test_setlist.py`, and retarget one test in `packages/llama/tests/test_structure.py`

**Interfaces:**
- Produces module-privates `_RECOVER_FLOOR: int` and `_may_start_a_show(line: str) -> bool`.
- No signature change to `parse_setlist`.

- [ ] **Step 1: Write the failing tests**

Determine the true end of the file (`wc -l`) before appending — phase 3 had three mid-file insertion incidents from a truncated `Read`.

```python
def test_encore_first_marker_does_not_discard_the_setlist():
    desc = ("Shimmy She Wobble\nBack Back Train\nCypress Grove\nDeep Ellum\n"
            "Goin' Down South\nRolling Stone\nSkinny Woman\nStanding In My Doorway\n"
            "Encore:\nRollin' N Tumblin'\n")
    items = parse_setlist(desc).items
    assert len(items) == 9
    assert [i.title for i in items][:2] == ["Shimmy She Wobble", "Back Back Train"]
    assert {i.set for i in items} == {"1", "encore"}
    assert [i.set for i in items][-1] == "encore"


def test_set_two_first_marker_does_not_discard_the_setlist():
    # A show does not start at Set 2; the block above IS set 1.
    desc = ("Bertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Set 2:\nTruckin'\nStella Blue\n")
    items = parse_setlist(desc).items
    assert [i.title for i in items][:5] == [
        "Bertha", "Jack Straw", "Sugaree", "Row Jimmy", "Big River"]
    assert [i.set for i in items] == ["1"] * 5 + ["2"] * 2


def test_set_one_first_marker_still_truncates_its_header():
    # Deliberately unchanged: content above a Set 1 marker is header/support-act
    # material (measured: 43 non-Dead descriptions, sampled, header-dominated).
    desc = ("Blues Traveler\nH.O.R.D.E. Festival\nsoundboard master\n"
            "Runaround\nHook\nSet 1:\nBertha\nJack Straw\n")
    assert [i.title for i in parse_setlist(desc).items] == ["Bertha", "Jack Straw"]


def test_block_below_the_floor_still_truncates():
    # Fewer than 5 parseable items above is junk, not a lost setlist.
    desc = ("One Set: (1:39:44)\n1. intro\n2.\n3.\nEncore:\nBertha\n")
    items = parse_setlist(desc).items
    assert all(i.set == "encore" for i in items)


def test_decorated_encore_marker_is_recognized():
    # The coupled half: "---encore:" is a marker, not a song title.
    desc = ("Bertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "---encore:\nOne More Saturday Night\n")
    items = parse_setlist(desc).items
    assert not any("encore" in i.title.lower() for i in items)
    assert [i.set for i in items][-1] == "encore"
    assert len(items) == 6
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_setlist.py -k "first_marker or floor or decorated_encore" -q`
Expected: the encore/set-two/decorated tests FAIL; `test_set_one_first_marker_still_truncates_its_header` and `test_block_below_the_floor_still_truncates` should already PASS (they pin behavior that must not change — if either fails now, stop and report).

- [ ] **Step 3: Implement**

This exact shape was prototyped and executed against the real corpus before this plan was written; it produces the results in Step 5.

In `packages/llama/src/llama/setlist.py`, give `_ENCORE_LINE` the same tolerance set markers already have:

```python
_ENCORE_LINE = re.compile(_LEAD_DECOR + r"(?:encore|e\d?)\s*(?::|-\s|$)\s*(.*)$", re.I)
```

Add above `parse_setlist`:

```python
# A block above a non-show-starting marker is kept when it parses to at least
# this many items on its own - the parser's own confidence floor. Below it, the
# block is junk (track-number stubs, a duration header) and truncating is right.
_RECOVER_FLOOR = 5


def _may_start_a_show(line: str) -> bool:
    """True when this marker could plausibly be the FIRST marker of a show.

    "Set 1" can. An encore marker cannot - no show opens with its encore - and
    neither can "Set 2". A labeled set line whose ordinal the parser does not
    recognize resolves to set 1 in the parse loop below, so it gets the same
    answer here rather than a second, divergent opinion.
    """
    m = _SET_LINE.match(line)
    if m:
        token = (m.group(1) or m.group(2)).lower()
        return _SET_TOKEN.get(token, token) == "1"
    lm = _LABELED_SET_LINE.match(line)
    if lm:
        return _LABELED_ORDINAL.get(lm.group(1).lower(), "1") == "1"
    return False
```

Replace the truncation block in `parse_setlist`:

```python
    if first_marker is not None and not _may_start_a_show(raw_lines[first_marker]):
        # The marker cannot open a show, so the block above is the main body,
        # not a header. Probe it: the recursive parse cannot itself truncate,
        # because by construction the block contains no markers.
        above = [ln for ln in raw_lines[:first_marker] if ln]
        if len(parse_setlist("\n".join(above)).items) >= _RECOVER_FLOOR:
            first_marker = None
    if first_marker is not None:
        raw_lines = raw_lines[first_marker:]
```

Untruncated pre-marker items flow through the loop with `current_set = None` and land in set `"1"` — correct for the set≥2 shape, and the honest answer for the encore shape.

- [ ] **Step 4: Discharge the patch header's two obligations**

1. Rewrite the `SET MARKERS ONLY` comment paragraph above `_LEAD_DECOR` — it justifies an omission this task removes. Replace it with a note that the coupling is now discharged, naming the truncation rule as its partner.
2. Retarget `test_encore_rule_above_a_tracklist_does_not_truncate` (its docstring says to do exactly this when the coupled fix lands): assert the tracklist survives AND the encore song is labelled `encore`. **Do not delete it.**

Then sweep both test files for any other test pinning encore-first truncation as correct. Retarget with a comment; never delete.

- [ ] **Step 5: Verify against the real corpus, with the CORRECTED canaries**

`iacache` is at `~/projects/llama-setlist-analysis/iacache` (2095 entries). Feed descriptions to `parse_setlist` directly — it does `<br>`→newline and `html.unescape` internally; add generic `<[^>]+>` stripping only if you also apply it to the baseline side, and say so.

| canary | required |
|---|---|
| `nmas2013-02-13.16.44` | **31 items**, `sets` includes `encore`, and the only item lost vs HEAD is the literal `'---encore:'` |
| `spindoctors2001-09-07.akg391.duro.flac24` | **37 items, unchanged from HEAD** |
| `gd74_windsor` fixture test | byte-identical, still 34 (26 + 8) |

Then sweep all 2095 descriptions old-vs-new and report: descriptions changed, gained, and **songs lost**.

**Songs lost must be 0 — and the unit is SONGS.** Compare **normalized** titles (`structure.norm_title`), not raw strings: the enumerated-prefix gate rewrites `04 Randy Described Eternity` → `Randy Described Eternity`, and a raw-string diff scores that as a lost song. My prototype sweep showed 42 descriptions "losing" 66 titles under a raw-string comparison; re-check every one under normalized comparison and enumerate anything that survives. Any genuinely lost song is stop-and-escalate, never netted against wins.

- [ ] **Step 6: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1261 + 5 new = 1266 passed, 7 deselected. Treat the count as a guide; **absence of failures is the gate**. If a test outside the two named above changes behavior, investigate before blessing it.

- [ ] **Step 7: Commit (ONE commit, both halves)**

```bash
git add packages/llama/src/llama/setlist.py packages/llama/tests/
git commit -m "fix(setlist): only a show-starting marker may truncate the header"
```

---

### Task 2: `rank_parses` plausibility tier (spec §3)

A truncated parse has *higher* confidence than a complete unmarked sibling (`saw_marker` true), and confidence outranks completeness — that is how an 8-item encore-only parse beat a complete 34-item sibling. Task 1 closes this defect's cause; this is insurance against the next one.

**Files:**
- Modify: `packages/llama/src/llama/structure.py` (`rank_parses`, ~line 250)
- Test: `packages/llama/tests/test_structure.py`

- [ ] **Step 1: Write the failing test**

```python
def test_rank_parses_prefers_a_complete_parse_over_a_confident_fragment():
    frag = SourcedParse(source="lma:a", parsed=ParsedSetlist(
        items=[SetlistItem(title=f"S{n}", normalized=f"s{n}", set="encore")
               for n in range(8)], confidence="high"))
    full = SourcedParse(source="lma:b", parsed=ParsedSetlist(
        items=[SetlistItem(title=f"T{n}", normalized=f"t{n}", set="1")
               for n in range(34)], confidence="medium"))
    assert rank_parses([frag, full], target_count=34) is full


def test_rank_parses_keeps_todays_order_when_all_are_implausible():
    a = SourcedParse(source="lma:a", parsed=ParsedSetlist(
        items=[SetlistItem(title="A", normalized="a", set="1")], confidence="high"))
    b = SourcedParse(source="lma:b", parsed=ParsedSetlist(
        items=[SetlistItem(title="B", normalized="b", set="1")], confidence="low"))
    assert rank_parses([a, b], target_count=40) is a
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -k rank_parses -q`
Expected: the first FAILS (the confident fragment wins today); the second PASSES.

- [ ] **Step 3: Implement**

```python
    def key(p: SourcedParse):
        multi_set = len({i.set for i in p.parsed.items}) > 1
        # A parse covering less than half the tape cannot be the show's setlist.
        # Sits ABOVE confidence because a truncated parse scores high confidence
        # (it saw a marker) precisely when it is least complete.
        plausible = len(p.parsed.items) >= max(5, target_count // 2)
        return (
            p.source == "setlist.fm",
            plausible,
            _CONF_RANK.get(p.parsed.confidence, 0),
            multi_set,
            -abs(len(p.parsed.items) - target_count),
        )
```

`setlist.fm` stays on top, untouched. When every candidate is implausible the tier is constant and today's ordering decides.

- [ ] **Step 4: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1266 + 2 = 1268 passed. Any pre-existing gather/structure test whose winner changes must be reported, not adjusted away.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "fix(structure): a truncated parse must not outrank a complete one"
```

---

### Task 3: Track-side numeric and duration prefixes (spec §4)

`18 Lost My Driving Wheel` fails to match an item that is present. Measured floor: +96 non-Dead / +164 Dead matched tracks.

**Files:**
- Modify: `packages/llama/src/llama/structure.py` (`align`'s compare path)
- Test: `packages/llama/tests/test_structure.py`

**Four load-bearing constraints — violate any and the change is wrong:**
1. **Matching layer only.** Stored `Track.title` is never modified; it feeds briefings, dj-notes and the manifest.
2. **Miss-path fallback only.** Try the unstripped title first; try the stripped form only when the window match returns None. This is what protects `8 Miles High` — it matches unstripped and never reaches the strip.
3. **Gated on an enumerated tape:** apply only when ≥3 of the tape's cleaned tag titles carry the prefix shape.
4. **Prefix shape:** 1–2 digit index with optional `.`/`)`/`-`, or a bracketed/bare `mm:ss` duration. The 2-digit cap protects `1952 Vincent Black Lightning` a second time.

- [ ] **Step 1: Write the failing tests**

```python
def test_numeric_prefixed_tracks_match_on_an_enumerated_tape():
    c = canon(("1", "Lost My Driving Wheel", True), ("1", "History Lesson", True),
              ("1", "KC Jones", False))
    r = align([tr(1, "18 Lost My Driving Wheel"), tr(2, "08 History Lesson"),
               tr(3, "[05:20] KC Jones")], c)
    assert r.matched == [True, True, True]


def test_numeric_titles_survive_on_a_non_enumerated_tape():
    c = canon(("1", "8 Miles High", True), ("1", "1952 Vincent Black Lightning", False))
    r = align([tr(1, "8 Miles High"), tr(2, "1952 Vincent Black Lightning")], c)
    assert r.matched == [True, True]


def test_a_real_numeric_title_is_not_stripped_even_when_enumerated():
    # "8 Miles High" matches unstripped, so the fallback never fires on it.
    c = canon(("1", "8 Miles High", True), ("1", "Bertha", True),
              ("1", "Sugaree", True), ("1", "Loser", False))
    r = align([tr(1, "8 Miles High"), tr(2, "02 Bertha"), tr(3, "03 Sugaree"),
               tr(4, "04 Loser")], c)
    assert r.matched == [True, True, True, True]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/pytest packages/llama/tests/test_structure.py -k "numeric or enumerated_tape" -q`
Expected: the first FAILS; the other two PASS already (they pin what must not break).

- [ ] **Step 3: Implement**

Add the prefix regex and the tape-level gate near the other `structure.py` helpers, then wire the fallback into `align`'s miss path only — after the existing window match returns None, before the track is recorded as unmatched. Follow the shape of phase 2's fuzz: normalize at compare time, never mutate the `Track`.

- [ ] **Step 4: Run the full suite**

Run: `./.venv/bin/pytest -q`
Expected: 1268 + 3 = 1271 passed.

- [ ] **Step 5: Measure the shipped, gated form**

The +96/+164 floor was measured with an *unconditional* strip on already-missed tracks. The gated form will come in at or under it. **Report actual vs floor and explain any shortfall** — do not report the projection. Verify zero regressions among currently-matched tracks.

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/structure.py packages/llama/tests/test_structure.py
git commit -m "feat(structure): strip track-side numeric prefixes on enumerated tapes"
```

---

### Task 4: Full measurement against the spec's acceptance gates

**Retained by the main session — do not start this task.** Gates 2–8 need judgment about what a changed set label means, and phase 3 established that measurement is where this project's errors concentrate.

The main session runs: the description sweep re-baselined over the full 2095-entry `iacache` (stating both the old 923 and new counts); end-to-end coverage on both corpora against `0.5033` non-Dead / `0.7982` Dead; matched-track deltas against the `+1091` / `+554` projections; both set-label gates; the C→A migration prediction with its falsification clause; and D staying 0 under a **mirror-validated** classifier (`phase4-review-audit/audit_window.py` — `measure2.py` is explicitly disqualified for bucket claims).

---

## Self-review notes

Spec coverage: §1+§2 → Task 1 (one commit, coupling enforced); §3 → Task 2; §4 → Task 3; acceptance criteria → Task 4. 4b is out of scope by the spec and has no task.

**Every code block and every canary number in this plan was executed against the real corpus before the plan was written.** That is what surfaced the two stale spec canaries corrected above, and the raw-vs-normalized songs-lost trap in Task 1 Step 5. Phase 3's post-mortem identified *unexecuted assertion* as the root cause of every error in that phase; a plan is where such assertions pool, so they are discharged here rather than by the implementer.

Test-count expectations (1266 → 1268 → 1271) are a guide; absence of failures is the gate.

---

### Task 1b: The gather-side head-banner guard (spec §1b + §1c)

**Added 2026-08-02 after Task 1 measured a regression.** Task 1's truncation rule recovers real setlists but sometimes recovers a taper banner with them, and places it at the head of the setlist where `align()`'s pointer starts. Measured: **54 shows worse, 53 to zero matched.** The rule is vindicated (`dc2022-06-18` aligns 23/23 once the banner is stripped, vs 0.6190 before), so this task removes the banner rather than the rule.

Read spec §1b and §1c in full before starting. The design is fixed; the constants carry rationale you must not silently change.

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (`_drop_artist_items`, at its existing hoisted call site)
- Modify: `packages/llama/src/llama/setlist.py` (§1c — the probe)
- Test: `packages/llama/tests/test_stage_gather.py`, `packages/llama/tests/test_setlist.py`

**Reference implementation — port it, do not re-derive it.** A measured, 7-iteration prototype lives at `.superpowers/sdd/2026-08-02-setlist-parser-and-variants/scratchpad/phase4-review-audit/banner-guard/dump.py` (`apply_guard`, `meta_norms`, `_RIG`), with its measurement record in `RESULTS.md` beside it. It is a post-parse simulation; your job is the production integration, whose metadata sources are `artist` (gather.py:154), `candidate.venue`/`candidate.city` (:173), and the resolved jerrybase event — not the corpus fields the prototype proxied with. **State that difference in your report.**

- [ ] **Step 1: Write the failing tests, and a mutation for each load-bearing constraint**

Follow the file's existing fixture conventions. Four constraints are load-bearing; each needs a test that **fails when that constraint is removed**:

| constraint | mutation that must break its test |
|---|---|
| head-span only (K=10) | remove the K bound → a late venue-named song is stripped |
| majority-metadata gate | remove it → a lone city-titled song eats the songs before it |
| chatter gap ≤2 | widen to unbounded → a real song between two chatter lines is eaten |
| artist drop stays global | scope it to the head → a mid-setlist artist-name item survives |

**Run each mutation and confirm the test fails.** A test that passes under its own mutation is not a test — this is the standing rule from Task 3, where all three prescribed tests passed under both an eager strip and a disabled gate.

Two domain hazards are spec constraints, and each needs a test: `fades?` must not match **`Not Fade Away`**, and bare `@`/`~`/`#` must not be treated as chatter (they are Dead taper annotation markers).

- [ ] **Step 2: Run the tests to verify they fail**

- [ ] **Step 3: Implement §1b**, then **§1c** (extract the item-emission loop so the probe runs on already-preprocessed lines with no truncation step — the spec rejects "no markers after unescaping" as the same bet at one remove). §1c needs the escaped-markup case as a test (spec gate 2b).

- [ ] **Step 4: Run the full suite**

Expected: prior count + new tests. Absence of failures is the gate. **Any pre-existing gather test whose behavior changes must be reported, not adjusted away** — `resolve_titles`' `len(items) == len(tracks)` gate is downstream of this call site and is exactly what phase 3's hoist ruling was about.

- [ ] **Step 5: Reproduce the v7 profile — this is the acceptance gate**

Spec gate 2a. On the common population, both corpora, `clean_tracks` construction, baseline pair stated:

```
             coverage             matched   worse   to-zero
Dead     0.7990 -> 0.8777          +1468       1     14 -> 1
non-Dead 0.5056 -> 0.8508          +3933       5     39 -> 2
```

**Reproduce or beat it.** The production integration reads different metadata sources than the prototype, so exact reproduction is not guaranteed — **report the delta and explain it; do not tune the constants to hit the number.** Enumerate every worse show with its magnitude. **Gate 0 is absolute: any show reaching zero matched is stop-and-escalate.**

- [ ] **Step 6: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/src/llama/setlist.py packages/llama/tests/
git commit -m "fix(gather): strip head banners using this show's own metadata"
```
