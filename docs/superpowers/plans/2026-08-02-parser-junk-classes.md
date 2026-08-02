# Parser junk classes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Remove the residual junk item classes the phase-4a work left behind, and recover titles that miss only because a duration is glued to them.

**Why this before phase 4b:** re-running the real `gather` over the live 32-show library with phase-3+4a code held the hold-rate flat at 10/32 but churned it completely — 5 newly cleared (4 Grateful Dead, all jerrybase closer flags) and 5 newly held (all non-Dead). Two of the new holds are caused by junk items in this plan's scope, not by anything in 4b's. Parser junk is still the dominant cause of real holds, and it is far cheaper to fix than the window work.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest. No new dependencies.

## Global constraints

- **No new dependencies.** `songs.normalize_song` / `DEFAULT_ALIASES` untouched. `Track.title` as stored is never modified.
- **Baseline: 1289 passed / 7 deselected** at `1b0a1e2`. Worktree `.claude/worktrees/parser-junk` has its own venv — always `./.venv/bin/pytest`.
- **Run mutations with `PYTHONDONTWRITEBYTECODE=1`**, or build mutants as separate files. `.pyc` invalidation is (mtime, size) at 1-second granularity and a line-reordering mutation restored within the same second silently keeps executing.
- **Capture pytest's exit status without a pipe** (`PIPESTATUS` or a redirect). `pytest | tail && git commit` takes `tail`'s status and is inert.
- **Every load-bearing constraint needs a mutation that makes its test fail, executed.** A test that passes when its constraint is removed is not a test.
- **Fixtures must sit WITHIN the reach of the rule under test.** Three tests in the previous plan passed only because their fixture sat one position outside the rule's range.
- **Cite code by symbol, never by line number.** Line citations rotted twice in one fix wave last phase.
- **Commit after every task.** Do not push, do not merge.

## Measured scope — all figures from both corpora (2052 cached descriptions), items compared against `clean_tracks` titles

```
rule                                     effect                          false positives
A  drop bare durations, any bracket      101 junk items removed          0
B  drop total-time lines                  26 junk items removed          0
C  strip a TRAILING duration from a title 147 items become MATCHES        0 (miss-path only)
                                          across 12 shows
```

**Two candidates were measured and REJECTED — do not re-derive them:**
- **Bare-number drop** (349 items): breaks **8 real matches**. `'333'`, `'1977'`, `'1662'`, `'16'` are genuine song titles that match genuine tracks. Rejected.
- **Punctuation-only drop** (198 items): the dominant case is `'?'` matching a track also titled `'?'` (35×), plus `'??'` and `'? -->'`. That is the taper's *unidentified-track* marker present on both sides — a positionally meaningful correspondence, not a phantom. Dropping it would convert honest correspondences into misses and lower coverage for no gain. Rejected.

---

### Task 1: Drop bare durations in any bracket style, and total-time lines (rules A + B)

`_is_junk_title` currently rejects `(13:33)` and `01:50` but **not** `[1:51]`. Measured live: `yondermountainstringband-2009-04-17` parses to **71 items against 26 tracks**, 28 of them bare `[4:40]`-style durations; the inflation desyncs alignment, set breaks collapse to `[]`, and the show is newly held. `infamousstringdusters-2009-07-18` has 15 such items and is also newly held.

**Files:** modify `packages/llama/src/llama/setlist.py` (`_JUNK_TITLE`); test `packages/llama/tests/test_setlist.py`.

- [ ] **Step 1: Write the failing tests.** Check the file's true length (`wc -l`) before appending.

```python
def test_bracketed_durations_are_not_songs():
    desc = ("Set 1:\nIntro\n[1:51]\nRamblin Boy\n[4:40]\nRiver\n[6:25]\n"
            "Two Hits\n[3:38]\nSharecropper's Son\n")
    titles = [i.title for i in parse_setlist(desc).items]
    assert titles == ["Intro", "Ramblin Boy", "River", "Two Hits",
                      "Sharecropper's Son"]


def test_total_time_lines_are_not_songs():
    desc = ("Set 1:\nBertha\nJack Straw\nSugaree\nRow Jimmy\nBig River\n"
            "Total time = 1:34:29\n")
    assert "Total time = 1:34:29" not in [i.title for i in parse_setlist(desc).items]


def test_real_numeric_titles_survive_the_junk_filter():
    # MEASURED: '333', '1977', '1662', '16' are real songs matching real tracks.
    # A bare-number rule was rejected for breaking 8 real matches; this pins it.
    desc = ("Set 1:\n333\n1977\n1662\n16\nBertha\n")
    assert [i.title for i in parse_setlist(desc).items] == \
        ["333", "1977", "1662", "16", "Bertha"]


def test_unidentified_track_markers_survive():
    # MEASURED: '?' items correspond to '?' TRACKS (35x) — the taper's
    # unidentified-song marker on both sides. Positionally meaningful, not junk.
    desc = ("Set 1:\nBertha\n?\nSugaree\n??\nBig River\n")
    assert [i.title for i in parse_setlist(desc).items] == \
        ["Bertha", "?", "Sugaree", "??", "Big River"]
```

- [ ] **Step 2: Run them — the first two must FAIL, the last two must already PASS.** If either of the last two fails now, stop and report: it means a rule this plan rejected is already present.

- [ ] **Step 3: Implement.** Widen `_JUNK_TITLE` to accept any bracket style around a duration, and add a total-time alternative. Do **not** add bare-number or punctuation-only alternatives — both are measured-rejected above.

- [ ] **Step 4: Mutation.** Reverting the bracket widening must fail `test_bracketed_durations_are_not_songs`. Run it.

- [ ] **Step 5: Full suite**, then **Step 6: commit** — `fix(setlist): reject bracketed durations and total-time lines`.

---

### Task 2: Strip a trailing duration from a title (rule C)

`'Althea  [8:40]'` and `'Arguement (4:54)'` miss only because a duration is glued to the title. **147 items become matches across 12 shows**, with zero risk: apply on the **miss path only**, exactly as phase 4a's track-side prefix strip does.

**Files:** modify `packages/llama/src/llama/structure.py` (`align`'s miss path); test `packages/llama/tests/test_structure.py`.

**Four constraints, each needing its own mutation:**
1. **Matching layer only** — the stored `SetlistItem.title` is never modified; it feeds briefings and the manifest.
2. **Miss-path fallback only** — try the unstripped form first. This is what protects a title whose real name ends in something duration-shaped.
3. **Trailing only** — a duration anywhere but the end is not stripped.
4. **Both bracket styles**, `[m:ss]` and `(m:ss)`, and bare `m:ss` at the end.

- [ ] **Step 1: Write the failing tests, plus a mutation per constraint** (see the four above; for constraint 2 the mutation is an eager strip, for 3 a global strip, for 1 an assignment to the stored title).
- [ ] **Step 2: Run them.** Only the new-behaviour test may fail; the constraint tests must fail *under their mutations*, not before.
- [ ] **Step 3: Implement** on the miss path.
- [ ] **Step 4: Measure** — report actual new matches against the **147 / 12 shows** floor, both corpora, stating the baseline pair. Report the delta; do not report the projection.
- [ ] **Step 5: Full suite**, then **Step 6: commit** — `feat(structure): match a title whose duration is glued to it`.

---

### Task 3: Personnel credits reaching the item list

Filed as deferred in phase 4a ("175 still-emitted credit-shaped titles"). Measured here at **1049 credit-shaped items** across both corpora that match no track. `_NOISE`'s credit alternative is **line-level** and its instrument list is incomplete — verified: `'Jason Carter - Fiddle'` and `'Andy Falco - Guitar'` are caught, but **`'Rob Ickes - Dobro'` and `'Sikiru Adepoju - Talking Drum'` are not**.

**This task is measurement-first.** Two mechanisms are plausible and they need different fixes: an incomplete instrument vocabulary, and credits arriving as *split components* of a line that itself did not match `_NOISE`.

- [ ] **Step 1: Attribute before fixing.** For a sample of ≥30 emitted credit-shaped items, report which mechanism produced each. **Do not widen anything until the split is known** — a vocabulary fix and a level fix have different blast radii.
- [ ] **Step 2: Propose the fix with measured gain and false-positive count**, on the same instrument as tasks 1-2, and **report before implementing**. A song legitimately ending in an instrument word (`Drums`, `Fiddle`) is the hazard; `Drums` is a **song** by standing domain ruling and must survive.
- [ ] **Step 3-6:** implement / mutate / suite / commit, once the shape is ruled on.

---

### Task 4: Re-measure

Retained by the main session — do not start.

Coverage and miss buckets on both corpora with a mirror validated to `align()` at 0 divergences; identity (wrong-match) check; gate 0 (**a show leaving the population by falling under the item floor counts as a to-zero event**); and the **hold-rate re-run over the live 32-show library**, offline, against the 10/32 baseline with its 5-cleared / 5-newly-held split.

---

## Self-review notes

Every rule above was prototyped and executed against both corpora before this plan was written; the two rejected candidates were rejected **on measurement, not on taste**, and their pinning tests are in Task 1 so they cannot be silently re-introduced. The library hold-rate figures come from driving the real `run_gather` offline against a throwaway workspace — cached IA metadata, `setlistfm=None`, `align_provider=None`, a sentinel LLM — so no show in `~/.llama` was mutated and no LLM was called.
