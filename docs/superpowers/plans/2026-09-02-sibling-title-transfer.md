# Sibling Title Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the positional exact-count sibling rung with duration-sequence alignment against a tagged sibling of the same performance, guarded so that a wholesale or shifted alignment cannot ship a title silently — and feed the same evidence into the existing `--suggest-titles` operator surface for the untagged shows it exists for.

**Architecture:** One pure alignment module (`siblings.py`) consumed at two trust levels. The **automatic band** (gather) adopts only rows that clear the ratio band (anchor agreement ≥ 0.80 over ≥ 2 anchors) AND guard shape C+ (each fill run bracketed by agreeing anchors per `structure.gap_span`'s rule, count-forced against the donor span), stamping `title_source="sibling-align"`. The **operator band** (0.50–0.80, or any untagged tape) renders through the merged Phase B `--suggest-titles`/triage surface, preferring sibling evidence over the canonical DP. Two corpus-wide defect fixes (`filter_files` dedupe, numeric `is_real_title`) land first behind their own sweeps.

**Tech Stack:** Python 3.12+, Pydantic v2, Typer, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-02-sibling-title-transfer-design.md`

## Global Constraints

- Base: `main` @ `44038ae`. Full suite baseline: **1557 passed, 7 deselected** (`pytest -q`).
- In a worktree, use that worktree's own `.venv` and run `./.venv/bin/pytest` (the repo-root venv imports the main checkout's source).
- `siblings.py` is pure: no I/O, no LLM, no imports from `stages/`. `structure.py` must not import a stage. All fetching stays in `gather`.
- **Do-not-retune constants** (every measurement in the spec was taken at these values; changing any invalidates all of them): `MAX_MERGE=3`, skip cost multiplier 1.0, `MIN_EXCLUSION_PENALTY=60.0`, `MIN_MATCH_FRACTION=0.80`, `AUTO=0.80`, `FLOOR=0.50`, `MIN_ANCHORS=2`. Each carries a comment citing the evidence doc (Task 7).
- `loosely_same_title`'s definition is part of the measured basis of every threshold. Any change to it re-runs Task 7's measurements. Its comment must say so.
- No LLM touchpoint anywhere in this plan. `correspondence.py`'s internals are not modified (its call sites in `cli.py` are).
- **Acceptance is never a shape test.** Every task's acceptance is (a) a content-based check — adopted/proposed title *strings* compared against stated expected strings — or (b) a **named mutation shown failing**: the reviewer applies the stated mutation and names the exact test that goes red, with its failure line. "Tests pass" is a precondition, not an acceptance.
- **Mutations run on a copy outside the worktree, with shadowing proven first**: copy the tree (or `git archive`) to a scratch dir, plant a sentinel edit, confirm the running tests see it, remove it, then mutate. Purge `__pycache__` between mutation runs (a same-second `mv` restore left a valid stale `.pyc` and contaminated three results in the Phase B review — recorded in the ledger; do not rediscover it).
- **From a copied tree, no console script under `.venv/bin/` is safe — use `python -m <tool>`.** Every one of them (`pytest`, `pip`, `llama`, `emcee`) begins with an *absolute shebang* at the ORIGINAL venv's interpreter, so run from a copy they all operate on the original tree. `./.venv/bin/pytest` from a copy silently tests the worktree (measured 2026-09-02: a planted sentinel showed 22 tests passing that should have been red). `./.venv/bin/pip install -e` from a copy is the destructive member of the family: it reinstalls into the WORKTREE's venv and repoints the worktree's `_editable_impl_*.pth` at the copy. `./.venv/bin/python -m pytest` / `-m pip` is the only form that follows the copy; `PYTHONPATH=<copy>/packages/*/src` also shadows safely and is non-destructive. Prove shadowing with a planted sentinel before trusting any result.
- **Never modify the worktree's `.venv`.** Shadow a copy with `PYTHONPATH`, or run the copy's own interpreter. Repointing the worktree's `_editable_impl_*.pth` at a scratch copy *does* achieve shadowing, and it silently poisons every concurrent and subsequent run in the worktree — including other agents' — until someone notices. Measured 2026-09-02: a reviewer left `_editable_impl_llama_radio.pth` and `..._herder.pth` aimed at its own scratch dir, so `./.venv/bin/pytest` in the worktree was importing `llama` and `herder` from outside the worktree. Before trusting any suite result, confirm `llama.__file__` resolves under the tree you meant to test.
- Measurement outputs label every number **SYNTH** (masked well-tagged tapes) or **REAL** (the 8 partly-tagged targets / the 6-show library); no table mixes them.

## Deviation from the spec's first draft, already decided (rev 2 carries it)

The transfer is a separate pass over the resolved `Track` list — after the `overrides.titles` loop, before `adopt_gap_titles` — not a `resolve_titles` parameter. Reasons: `Track` objects make the C+ reuse of `structure.unresolved_runs`/`gap_span` literal instead of a reimplementation, and an operator-forced title can then anchor, the same ratified reasoning as Phase A's placement deviation.

## File Structure

| File | Responsibility |
|---|---|
| `packages/llama/src/llama/junk.py` | Modify: duplicate-listing dedupe in `filter_files` |
| `packages/llama/src/llama/titles.py` | Modify: `is_real_title` numeric widening (scope per Task 2); remove the `sibling` rung + `sibling_titles` param |
| `packages/llama/src/llama/siblings.py` | **Create**: duration DP, rows, ratio band, C+ gate. Pure |
| `packages/llama/src/llama/structure.py` | Modify: add `loosely_same_title` beside the other comparators |
| `packages/llama/src/llama/models.py` | Modify: `title_source` comment (+`sibling-align`, `sibling` marked legacy); `ProposalRow` gains sibling-evidence fields |
| `packages/llama/src/llama/stages/gather.py` | Modify: replace `_sibling_titles` with the donor-load + transfer pass; loosen the fetch gate; decline notes |
| `packages/llama/src/llama/cli.py` | Modify: sibling arm in `_propose_titles_for_show`; run-shaped rendering; three-way anchor display |
| `packages/llama/tests/test_junk.py` | Modify: dedupe tests |
| `packages/llama/tests/test_titles.py` | Modify: numeric-title tests; rung-removal tests |
| `packages/llama/tests/test_siblings.py` | **Create**: DP + guard unit tests |
| `packages/llama/tests/test_stage_gather.py` | Modify: integration + pins |
| `packages/llama/tests/test_cli.py` | Modify: sibling-arm proposal tests |
| `scripts/numeric_title_census.py` | **Create**: Task 2's census |
| `scripts/dedupe_sweep.py` | **Create**: Task 1's corpus sweep |
| `scripts/sibling_blind_arm.py` | **Create**: Task 7's harness (shipped-code blind arm + controls) |
| `docs/superpowers/2026-09-XX-sibling-transfer-evidence.md` | **Create**: Task 7 evidence doc |

---

# Phase 1 — corpus-wide prerequisites (each its own commit, each behind a sweep)

### Task 1: `filter_files` duplicate-listing dedupe

**Files:** modify `packages/llama/src/llama/junk.py`, `packages/llama/tests/test_junk.py`; create `scripts/dedupe_sweep.py`.

**Design notes:** Some archive.org items list every track twice — once at top level, once under an `<identifier>/` directory prefix — identical durations, tags on only one copy (ymsb2005's donor: 56 files for 28 tracks). Collapse inside `filter_files`, after `_keep_and_exclude` for the winning format: key = (basename, `round(duration or 0)`), keep the first copy unless a later duplicate carries a title the kept one lacks (then swap), excluded reason `duplicate-listing`. Play-order derivation runs on the deduped list. This is a behaviour change for every consumer, which is why the sweep gates it and it lands before the rung.

- [ ] **Step 1: failing tests.** In `test_junk.py`: an item listing `d1t01.mp3` at top level (untitled) and `ident/d1t01.mp3` (titled `Alpha`, same length) keeps **one** file and `clean_tag_titles` on the kept set yields `["Alpha"]` (content: the *titled* copy survives, asserted by title string, not by count); the dropped copy appears in `excluded` with reason `duplicate-listing`; two files sharing a basename but with lengths 180 vs 420 are **both** kept (different tracks, not duplicates); a clean item is byte-identical through `filter_files`.
- [ ] **Step 2:** run them, verify they fail on current behaviour (both copies kept).
- [ ] **Step 3:** implement; full suite green.
- [ ] **Step 4: the sweep.** `scripts/dedupe_sweep.py`: walk `~/.llama/cache/md_*.json`, run old and new `filter_files` per item/format, print every item whose kept set changes (identifier, before/after counts, the dropped names). Run it; commit the script; paste the summary into the commit message.

**Acceptance (content/mutation):**
- Sweep output enumerated; **every** changed item is a same-basename/same-duration collapse (spot-check ≥10 by hand, recorded in the PR/commit text); **no library show's kept set changes** except the known duplicate-listing items, named.
- Named mutation: invert the tagged-copy preference (keep the untitled copy). The Step-1 title-content test must fail on `["Alpha"]` vs `[""]` — a count-based test would stay green, which is why the assertion is on the string.

### Task 2: numeric-title census, then the scoped `is_real_title` fix

**Files:** create `scripts/numeric_title_census.py`; modify `packages/llama/src/llama/titles.py`, `packages/llama/tests/test_titles.py`.

**Decision point, named:** the census output decides scope — **global** (`is_real_title` itself accepts an all-digit 4-char title) versus **hygiene-only** (only the sibling/setlist-gap adoption check accepts it; the tag rung unchanged). **STOP after Step 2 and report the numbers to the owner if the census finds any item where the widening would promote year-as-title junk into the tag rung** (any item with ≥2 pure-4-digit tag titles, or any hand-checked sample entry that is a date rather than a song). Zero such items → proceed global without stopping, recording the census numbers in the code comment.

- [ ] **Step 1: census.** Script walks the cache, reports: count of tag titles matching `^\d{4}$` after `clean_tag_title`, per item; distinct values; items where the change moves `title_fraction` across `gather._RECOVER_BELOW` (0.5) or to/from 1.0. Cite-style output like `title_source_census.py`.
- [ ] **Step 2:** run it; record output; apply the decision rule above.
- [ ] **Step 3: failing tests.** `is_real_title("1922") is True`, `is_real_title("2001") is True`, `is_real_title("d1t02") is False`, `is_real_title("01") is False`, `is_real_title("174") is False` (or the hygiene-scoped equivalents if the owner ruled that way). Verify the enumerated-tape gate's existing pinned tests (`test_clean_tag_titles_leaves_an_unnumbered_year_title_alone`, strip-once) still pass untouched.
- [ ] **Step 4:** implement per scope; full suite green.

**Acceptance (content/mutation):**
- Census numbers recorded in the constant's comment (house citation style: script name + date + numbers).
- Named mutation: revert the widening. `test_is_real_title_accepts_a_year_like_numeric_title` (name it exactly that) must fail. Additionally, after Task 5 lands, the TBT expectation in Task 7's six-show table (`1922` adopted) depends on this — noted there, not re-tested here.
- Composition note for the reviewer, from the spec: this erases the merged branch's single demonstrated `--suggest-titles` adoption (`1922` becomes a count-forced `setlist-gap` adoption). Expected; do not "fix".

---

# Phase 2 — the alignment module and its guards (pure)

### Task 3: `siblings.py` — the duration DP and row transfer

**Files:** create `packages/llama/src/llama/siblings.py`, `packages/llama/tests/test_siblings.py`.

**Interfaces (produced):**

```python
@dataclass(frozen=True)
class DonorTape:
    identifier: str
    names: list[str]
    durations: list[float]     # seconds; caller guarantees none missing
    titles: list[str]          # cleaned tag titles, "" when absent

@dataclass(frozen=True)
class SiblingRow:
    track: int                          # 1-based target track
    proposed: str | None                # "A > B" join for a merged pairing
    donor_span: tuple[int, int] | None  # half-open donor track range
    residual_sec: float
    penalty_sec: float                  # exclusion penalty; inf = forced
    verdict: str                        # "adopt" | "decline"
    reason: str = ""

def align_durations(target: list[float], donor: list[float],
                    forbid: tuple | None = None) -> tuple[float, list[tuple]]
def propose_rows(target_durs: list[float], donor: DonorTape, *,
                 metadata_norms: set[str]) -> tuple[list[SiblingRow] | None, dict]
```

**Design notes:** Port the prototype DP exactly (ops: a:b pairing, min==1, max≤`MAX_MERGE`, cost `|Σa−Σb|`; skips at skipped duration; forbid-and-resolve penalty). Whole-tape preconditions in `propose_rows`: complete durations both sides, `MIN_MATCH_FRACTION`. **No whole-donor tag-fraction gate** — an untitled donor track declines its row (`sibling track untitled`), per-item-not-per-donor is the spec's standing principle. Per-row: penalty < 60 s → decline (`weak evidence`); donor song split across target files → decline those rows; hygiene via the same predicate family as `structure._hygienic` (is_real_title / is_junk_title / MAX_TITLE_LEN / no trailing `:` / not in `metadata_norms`) — import from `setlist`/`titles`, do not copy.

- [ ] **Step 1: failing tests.** All content-based, five-or-six-track duration vectors with distinct song-length durations (300/420/510…):
  - a 1:1 alignment adopts the donor's titles, asserted string-by-string;
  - a merged pairing (target file 700 s vs donor 300+400) proposes `"Alpha > Bravo"` exactly;
  - **A2-shaped**: delete the donor's first track → the orphaned target row declines (`no sibling track` reason) and every other row's title is still the correct string (this is the uniform-shift resistance pin — the assertion is on the *titles*, not on counts);
  - **A3-shaped**: delete a donor middle track → same property;
  - near-ambiguous durations (two adjacent 300 s songs both sides, one target track) → penalty below 60 declines;
  - untitled donor track → that row declines, neighbours adopt (per-item pin);
  - donor split (donor 600 s track vs two 300 s target files) → both rows decline with the split reason;
  - hygiene: donor track titled with a metadata norm (`fillmore auditorium`) declines.
- [ ] **Step 2:** verify all fail (`ImportError`).
- [ ] **Step 3:** implement. Constants at module top with the do-not-retune comment citing the evidence doc by its Task 7 name.
- [ ] **Step 4:** full suite green.

**Acceptance (content/mutation):**
- The A2-shaped test's assertion set includes at least three post-deletion titles by exact string; reviewer confirms it fails under the **positional mutation** (replace the DP call with `titles[i] = donor.titles[i]` positional transfer) — the mutation that reproduces the old rung's blindness. Name the failing test and line.
- Named mutation: set `MIN_EXCLUSION_PENALTY = 0`. The near-ambiguous test must fail (it would adopt). If it stays green the test is hollow — rewrite before proceeding.

### Task 4: the guards — `loosely_same_title`, the ratio band, guard shape C+

**Files:** modify `packages/llama/src/llama/structure.py` (comparator only); extend `packages/llama/src/llama/siblings.py`, `packages/llama/tests/test_siblings.py`.

**Interfaces (produced):**

```python
# structure.py, beside fuzzy_title_eq:
def loosely_same_title(a: str, b: str) -> bool
# siblings.py:
@dataclass(frozen=True)
class Disagreement:
    track: int; tape_title: str; proposed: str
@dataclass(frozen=True)
class GuardResult:
    agreement: float | None     # None = no anchors (wholly untagged)
    n_anchors: int
    disagreements: list[Disagreement]
    band: str                   # "auto" | "operator" | "declined" | "no-anchors"
def rate_alignment(rows, tracks) -> GuardResult
def cplus_filter(rows, tracks) -> list[SiblingRow]   # demotes adopts to declines, per run
```

**Design notes:**
- `loosely_same_title`: `fuzzy_norm_title` equality, containment either way, or `SequenceMatcher.ratio() >= 0.80` — the measured comparator, verbatim. Docstring: used by the sibling guard and measurement scorers ONLY; never by `align()`/`normalize_song`; changing it invalidates the band-sweep tables and re-runs Task 7.
- **Anchor** = a track whose `title_source` is independent evidence (`tags`, `sibling-format`, `override`) with a real title, paired by the DP. Agreement = fraction whose own title loosely matches the row's proposal. Bands: `auto` ≥ 0.80 with ≥ 2 anchors; `operator` ≥ 0.50 or < 2 anchors; `declined` < 0.50; `no-anchors` when none exist.
- **C+ by reuse, verbatim:** build `anchors: dict[pos, (min_j, max_j+1)]` from *agreeing* anchors' donor spans; fill runs via `structure.unresolved_runs(tracks)`; bracketing via `structure.gap_span(anchors, lo, hi, len(tracks))` — the real function, so the leading-edge exception and the absent trailing branch are inherited, not re-stated; count-forcing: `span[1]-span[0] == hi-lo+1` (a merge-containing run therefore declines from auto — measured cost, accepted). **Runs decline individually**, reason per run (`tracks 7-9: not bracketed by agreeing anchors` / `donor span holds 4 tracks for a 3-file run`).
- Two spec invariants land as comments AND tests: (1) `cplus_filter` gates the automatic band only — the operator renderer never calls it; (2) count-forcing here is weaker than `adopt_gap_titles`' (donor span endpoints come from the alignment under test — self-referential; justified by measurement, not by the setlist-gap argument). Copy the spec's wording, cite it.

- [ ] **Step 1: failing tests.**
  - comparator: `loosely_same_title("BIODTL", "Beat It On Down The Line")` False is the *known limit* — pin the actual measured behaviour (equality, containment `"Sugaree"`/`"Sugaree (encore)"`, ratio case `"Mister Charlie"`/`"Mr. Charlie"` True); document `("Rain Please Go Away", "Rain go away (?)")` False as the known near-miss with a comment, not a fix;
  - band routing: 9-of-13-agreement fixture → `operator`; 2-of-13 → `declined`; 13-of-13 with 1 anchor → `operator` (MIN_ANCHORS); no tags at all → `no-anchors`;
  - bracketed interior run adopts; **leading-edge** run (run at track 0, right anchor agreeing) adopts; **tail run never auto-adopts** (no track at hi+1 — inherited from `gap_span`);
  - count-forcing: donor span of 4 for a 3-file run declines with the count reason;
  - **per-run independence**: one bracketed + one unbracketed run → exactly the bracketed run's titles adopt (assert both title strings and both reasons);
  - **localised-shift fixture** (the gd1971-08-06 shape, synthetic): correct-and-agreeing head/tail anchors, interior fills whose donor span is shifted by one → `rate_alignment` still says `auto` (8/10 agreement — the ratio is blind, pinned as documentation) but `cplus_filter` adopts **zero** interior titles. This is the regression pin for the class C+ exists for.
- [ ] **Step 2:** verify failures. **Step 3:** implement. **Step 4:** suite green.

**Acceptance (content/mutation):**
- Named mutation A: replace the `gap_span` call with `left is not None or right is not None` (one-sided bracketing). The localised-shift test and the tail-run test must both fail; name them. This proves the reuse is load-bearing, not decorative.
- Named mutation B: delete the count-forcing clause. The count-forcing test AND the localised-shift test must fail (the sweep measured count-forcing catching that case's last wrong title — if the fixture doesn't reproduce that, the fixture is wrong, not the guard).
- Named mutation C: change `MIN_ANCHORS` to 1. The single-anchor routing test must fail.
- Reviewer runs all three on an out-of-worktree copy with shadowing proven (global constraint).

---

# Phase 3 — wiring

### Task 5: gather — replace the sibling rung with the guarded transfer pass

**Files:** modify `packages/llama/src/llama/stages/gather.py`, `packages/llama/src/llama/titles.py`, `packages/llama/src/llama/models.py`, `packages/llama/tests/test_stage_gather.py`, `packages/llama/tests/test_titles.py`.

**Design notes:**
- Delete `_sibling_titles` and `resolve_titles`' `sibling_titles` parameter + `elif` rung (update `test_titles.py` accordingly: the old rung's tests are replaced, not weakened — the replacement pins that a count-equal fully-tagged sibling list no longer transfers positionally).
- New `_sibling_transfer(ia, candidate, identifier, want, tracks, metadata_norms) -> tuple[list[Track], list[str]]` in gather: loads every non-self `candidate.recordings` donor (`filter_files` + `clean_tag_titles` + `length_seconds`; skip donors with incomplete durations), calls `siblings.propose_rows` + `rate_alignment` + `cplus_filter`, picks the winning donor (highest agreement, then lowest DP cost, then identifier), applies `auto`-band C+-surviving rows to `unresolved` tracks with `title_source="sibling-align"`, returns notes for pair-level declines and per-run declines. Runs **after the overrides loop, before `adopt_gap_titles`** (see the Deviation section).
- Fetch gate: `kept and title_fraction(clean_tag_titles(kept)) < 1.0` — drop the count-mismatch/confidence condition.
- `models.py:157` comment: add `sibling-align`, mark `sibling` legacy (still-valid stored value, no migration).
- **Do NOT touch `TAUTOLOGICAL_TITLE_SOURCES` and do not force `matched=None`** for sibling-aligned tracks — they are independent evidence; `align()`'s match on them is a real measurement (spec's title_source section).

- [ ] **Step 1: failing tests** (`FakeProvider` pattern, offline fixtures):
  - an anchored fixture (mixed tags + unresolved, donor sibling in the candidate) adopts into the gap and the adopted titles equal the expected strings; `title_source == "sibling-align"`; `matched` is `align()`'s real verdict (assert it is not forced to None);
  - a fully-tagged show is byte-identical through gather (no donor fetch: the loosened gate's `title_fraction < 1.0` arm);
  - the ymsb2005 untagged fixture (`packages/llama/tests/fixtures/ymsb2005_metadata.json`, on main since Phase B) gets **zero** automatic adoptions — the pin whose inverse Phase B shipped nine times;
  - a below-FLOOR donor produces no adoption and a `sibling alignment declined (anchor agreement N%)` note;
  - a C+-declined run leaves its tracks unresolved and its per-run reason in notes;
  - old-rung removal: a donor with exactly `len(kept)` fully-tagged tracks but shifted content does NOT transfer positionally (assert the target track's title is still its filename, not the donor's shifted title — this is the test the old rung could never pass).
- [ ] **Step 2:** failures verified. **Step 3:** implement. **Step 4:** suite green; run `scripts/title_source_census.py` against the live library and record before/after counts in the commit message.

**Acceptance (content/mutation):**
- Named mutation A: add `"sibling-align"` to `TAUTOLOGICAL_TITLE_SOURCES`. A named test must fail by asserting a sibling-aligned track's coverage contribution (a weak-independent-evidence fixture whose flag state flips when its sibling-aligned matches are discarded). If no existing test catches it, write that test in Step 1 — this is the independence pin.
- Named mutation B: bypass `cplus_filter` in the gather call (adopt everything the ratio band admits). The C+-declined-run test must fail on *title content* (the declined track suddenly carries the donor title).
- The shifted-donor test from Step 1 shown failing against a copy with the OLD rung restored (this is the one backward mutation: prove the replacement actually closed the positional hole).

### Task 6: the operator surface — sibling arm in `--suggest-titles` / triage

**Files:** modify `packages/llama/src/llama/cli.py`, `packages/llama/src/llama/models.py`, `packages/llama/tests/test_cli.py`.

**Design notes:**
- Entry seam: `_propose_titles_for_show` (cli.py:1278). Before the canonical DP, attempt the sibling arm: load donors exactly as gather does (factor the donor-loading helper so the two share it — one definition of "qualifying donor"), run `propose_rows` + `rate_alignment`. If a donor reaches `operator`, `auto`, or `no-anchors` band, build the proposal from sibling rows; `declined` (< FLOOR) or no donor → fall through to the existing canonical DP unchanged. **The renderer never calls `cplus_filter`** — spec invariant 1; put the spec's sentence in a comment at the call site (`applied to the renderer it would show an untagged tape nothing — C+ gates adoption, never display`).
- `ProposalRow` gains optional fields for the sibling arm: `residual_sec: float | None = None`, `note: str = ""` (per-run decline reasons, `sibling track untitled`, the head-rows caution). `evidence` value: `"sibling-align"`. `TitleProposal.evidence_source` likewise.
- Rendering: run-shaped — contiguous proposed runs, and declined runs printed with their reason line, not silent holes. Anchor disagreements render three-ways: `t2 tape: 'Hillcrest Drive' | sibling: 'Count Me Out' | setlist: 'Count Me Out'` (canonical column from the already-built canonical; blank when absent). For a `no-anchors` (untagged) proposal additionally print the donor identifier, the embed-in-canonical coverage figure, and the head-row caution (spec: the one measured miss was a head-banner +1 shift).
- Confirmation path unchanged: same `_propose_and_confirm_titles`, same `overrides.titles` write, same C1 staleness guard, same redo-from-gather. Triage `[t]` inherits with zero extra wiring — add one test proving it.

- [ ] **Step 1: failing tests** (CliRunner, offline):
  - untagged ymsb-shaped fixture with a tagged donor: `fix <show> --suggest-titles` renders a table whose proposed titles equal the expected strings (assert ≥3 exact titles including one merged `"A > B"` row), plus residual column present — and (invariant) rows render despite zero anchors;
  - delmccoury-shaped fixture (13 anchors, 4 disagreeing): proposal renders, three-way disagreement block lists the 4 tracks with all three strings, confirmation writes ONLY the unresolved rows' titles into `overrides.titles` (assert the map's exact contents — anchors are never written);
  - below-FLOOR donor + no usable canonical: existing decline message path unchanged;
  - below-FLOOR donor + usable canonical: falls through to the canonical DP (pin: the proposal's `evidence_source` is not `"sibling-align"`);
  - triage `[t]` on the untagged fixture reaches the same sibling proposal (shared-seam pin);
  - C1 still fires: staged exclusion + `--suggest-titles` refuses before any donor work.
- [ ] **Step 2:** failures verified. **Step 3:** implement. **Step 4:** suite green.

**Acceptance (content/mutation):**
- Named mutation A: make the renderer apply `cplus_filter` to the row set. The untagged-fixture test must fail with an empty/holed table — this is the "later simplification unifies and breaks" hazard the spec names; the reviewer confirms the failing test's name in the report.
- Named mutation B: swap the sibling-arm preference (canonical DP first). The untagged-fixture test must fail on title content (the canonical DP proposes different strings for the reprise rows — that content difference is the entire reason the sibling arm exists).
- Confirmation-write test asserts the exact `overrides.titles` dict — a shape test ("wrote N entries") is explicitly insufficient.

---

# Phase 4 — measurement gates (ship gate for the whole phase)

### Task 7: controls, blind arm, six-show table, re-gather diff — the evidence doc

**Files:** create `scripts/sibling_blind_arm.py`, `docs/superpowers/2026-09-XX-sibling-transfer-evidence.md`; reuse `scripts/regather_diff.py`, `scripts/title_source_census.py`.

**This task is judgment work — run it on Opus, not Sonnet.** It is the ship gate: held to `docs/superpowers/2026-08-03-tail-guard-sanity-check.md` standard, run through the **shipped functions** (`siblings.propose_rows`/`rate_alignment`/`cplus_filter` and the gather pass), never the prototype. Every number labelled SYNTH or REAL; no mixed tables; all rates stated as upper bounds with the ground-truth caveat.

- [ ] **Step 1 — controls, shipped code** (REAL fixtures): probe baseline 23/23 by string; A2/A3 (donor-track deletions) decline exactly the orphaned rows, 0 wrong; rotation control ships zero automatic titles; **prefix-mask arm ships zero automatic titles in every stratum**; the named localised-shift pair (`gd1971-08-06.aud.wolfe…` ← `…mtx.seamons.96668`) ships **0** of the 7 titles the bare ratio ships; a wrong-performance donor lands below FLOOR.
- [ ] **Step 2 — blind arm, both masks** (SYNTH): the cached-alignment harness over the ≥95% population, random AND prefix masks, through shipped gates. Gates: zero wholesale-failure titles in every stratum; per-stratum loose error ≤ the sweep's C+ cells (1.87–1.99% random-mask); **hand-triage every wrong adoption** (variant / non-song boundary / genuine) and compare the genuine class against the tag rung's typo baseline per the M1 standard. A miss on any gate is an escalation to the owner, not a fix loop.
- [ ] **Step 3 — the six-show table** (REAL, hand-checked against the Phase B Section-B table + LMA canonical): ymsb2005 renders 23 correct rows + declines track 1 (operator path); delmccoury in the operator band at 0.69 with its 5 correct fills proposed and 4 disagreements displayed; TBT's `1922` adopted (via setlist-gap post-Task 2 — verify which rung fired and record it); zero wrong titles on any path; **the automatic band's library yield of 0 tracks asserted as the expected result**.
- [ ] **Step 4 — library re-gather diff** (REAL): `regather_diff.py` offline — every currently-resolved track byte-identical; the complete diff = enumerated new adoptions on the 75-track unresolved population, each hand-checked. Spot-check the setlist.fm-won shows with the key active; report per-show arm disagreement as findings.
- [ ] **Step 5 — the doc**: verdict-first, controls stated first, SYNTH/REAL separation, the constants' citations pointed at it, the comparator's re-run obligation restated, and the falsifier list carried over from the spec so the next phase knows what would invalidate this one.

- [ ] **Step 6 — the `_hygienic` exposure, carried from Task 2** (REAL). Task 2's global widening of `is_real_title` also opens `structure._hygienic`, the pipeline's **only silent adopter**: 18 pure-4-digit canonical items (of 181 found in 48,031; the rest absorbed by `_date_norms`) newly clear every clause — `2448` from a flac2448 lineage string, `2026` on a 2025 show, `2020` on a 1994 show, and 15 more, enumerated in `titles.py`'s constant comment. **That 18 is an UPPER BOUND on exposure, not the exposure**: a title only ships if the rung fires, the run is count-forced between anchors, and nothing upstream already resolved it. Required here: (a) measure how many of the 18 actually alter a **shipped** track title in a real re-gather, and lead the risk note with that measured number, carrying 18 as the population it was drawn from; (b) state which figure is measured and which is a bound **in the same sentence**; (c) **if any of the 18 adopt, they are a named regression class in this evidence doc**, not a ledger line — `_hygienic` is the one surface where a wrong title ships with no flag and no operator ever sees it, which is the failure mode this whole line of work exists to prevent.

**Acceptance:** every gate above is a content comparison with the expected value written next to the measured one; **every instrument is proven three independent ways before its numbers are credited** — a schema check, a planted synthetic positive control run through the *committed* script, and an independent oracle sharing no code with the instrument (the standard set by Task 2's census review, which is what caught a first-non-empty-format bug that hid a real item; prefer redundant instruments over merely careful ones, since a careful instrument cannot see its own blind spot); the doc exists in-repo; the do-not-retune comments in `siblings.py` cite it by filename. If any gate fails, the phase does not ship and the failure goes to the owner with the triage attached.

---

## Notes for the executor

- Task order is load-bearing: 1 and 2 land before 3–5 so the rung's measurements run on the fixed filter and the fixed predicate. 5 before 6 so the operator surface shares the donor-loading helper instead of growing a second definition.
- Tasks 1+2 are small and independent → Sonnet implementers. Task 3 and 4 are well-specified ports of measured prototypes → Sonnet, with the mutations as the reviewer's teeth. Task 5 and 6 touch gather/cli seams with invariants → Sonnet implementer, Opus reviewer as usual. Task 7 is Opus (judgment + hand-triage).
- Every reviewer runs the task's named mutations on an out-of-worktree copy with shadowing proven and `__pycache__` purged between runs, and reports each mutation's failing test BY NAME with its assertion line. A mutation that fails to break anything is a finding against the tests, not a pass.
- Commit per task; a green suite between "define the helper" and "rewire the call site" is not evidence the work landed — commit only states where the change is wired and the suite passes.
- Nothing in this plan pushes, merges, or tags. The evidence doc's verdict plus the owner's review of it is the ship gate.
