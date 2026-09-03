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

