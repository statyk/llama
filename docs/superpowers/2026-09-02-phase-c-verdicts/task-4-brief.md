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
- **Anchor** = a track whose `title_source` is independent evidence (`tags`, `sibling-format`, `override`) with a real title, paired by the DP. Agreement = fraction whose own title loosely matches the row's proposal. **Bands, evaluated in this ORDER** (a precedence, not a set of predicates — the original wording was a disjunction and answered one case twice): `no-anchors` when there are 0 anchors; `operator` when anchors < `MIN_ANCHORS`, *regardless of agreement* (the ratio is not a measured statistic below 2 anchors, so it may neither license adoption nor justify discarding); then `auto` when agreement ≥ `AUTO`; `operator` when agreement ≥ `FLOOR`; else `declined`. **The overlap the old wording created was exactly two cases**: one anchor that disagrees (ratio 0.0, satisfying both `< 0.50` and `< 2 anchors`) and zero anchors (ratio 0/0, undefined — `rate_alignment` must return `no-anchors` *before* the division, never inherit 0.0 from float semantics, since a wholly untagged tape has zero anchors by construction and is this phase's central case). A ratio between 0 and 1 is arithmetically impossible at one anchor. **Why `operator` and not `declined` for the lone disagreeing anchor:** `declined`'s 68–99% marginal-error basis was measured over ≥ 2 anchors and **does not exist at 1**, so declining there applies a threshold whose justification is absent for that population; 24.1% of disagreeing anchors are tape-wrong (sibling and canonical agreeing against the target's own tag), so one disagreeing anchor is near-zero evidence; and since neither band adopts, `operator` costs a minute of operator attention while `declined` silently discards a possibly-correct alignment for exactly the barely-tagged population this phase serves. Generalises: **a threshold is only valid over the population it was measured on.**
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

