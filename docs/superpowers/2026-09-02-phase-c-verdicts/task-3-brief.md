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
  - near-ambiguous durations → exclusion penalty below `MIN_EXCLUSION_PENALTY` (60 s) declines. **Corrected 2026-09-02:** this bullet originally read "two adjacent 300 s songs both sides, one target track", which is arithmetically impossible — measured, that fixture yields a penalty of **600 s on every row and adopts them all**, so it cannot reach the sub-60 path at all. The mechanism that actually produces a small penalty is a **short adjacent fragment**: e.g. a 25 s donor track beside a 10 s drift gives penalty 20, strictly between 0 and 60, which is what makes the `MIN_EXCLUSION_PENALTY = 0` mutation discriminating;
  - untitled donor track → that row declines, neighbours adopt (per-item pin);
  - donor split (donor 600 s track vs two 300 s target files) → both rows decline with the split reason;
  - hygiene: donor track titled with a metadata norm (`fillmore auditorium`) declines.
- [ ] **Step 2:** verify all fail (`ImportError`).
- [ ] **Step 3:** implement. Constants at module top with the do-not-retune comment citing the evidence doc by its Task 7 name.
- [ ] **Step 4:** full suite green.

**Acceptance (content/mutation):**
- The A2-shaped test's assertion set includes at least three post-deletion titles by exact string; reviewer confirms it fails under the **positional mutation** (replace the DP call with `titles[i] = donor.titles[i]` positional transfer) — the mutation that reproduces the old rung's blindness. Name the failing test and line.
- Named mutation: set `MIN_EXCLUSION_PENALTY = 0`. The near-ambiguous test must fail (it would adopt). If it stays green the test is hollow — rewrite before proceeding.

