### Spec Compliance (SPEC role) — ✅ Spec compliant ; ⚠️ Cannot verify from diff: whether `_venue_changes` runs only after compare's show-set/arm-mismatch exit-2 gate (it indexes `base["shows"][slug]` for every cand slug) — it sits beside `_exposure`, which makes the same assumption, so it inherits the existing guarantee.

### Strengths
- Every brief rule is implemented as written: `OUTPUT_FILES` gains `venue_changes.txt` (replay_holds.py:184); `_venue_changes(base, cand) -> (lines, n, m)` (replay_holds.py:383-406); written in `compare` right after `packaged_exposure.txt` (~:778); summary line `venue_changes.txt: {n} show(s), {m} with a flag change` right after the `packaged_exposure.txt` line (~:818).
- Row format matches the brief exactly: `{slug}  [{state}]` + `  DELIVERED` on cand `state == "delivered"`, `  venue: {_j(bv)} -> {_j(cv)}`, `  city: ...`, `  flags: unchanged` / `  flags CHANGED: added [...]; removed [...]` over `_all_flags`, slug order (sorted), unreplayable-in-either-arm skipped and counted in a header line.
- Both brief tests are present verbatim (test_replay_holds.py:+786-821) and assert what the brief says; implementer reports RED (2 failed) then GREEN (55 file / 3988 suite).
- Spec item B covered: both strings, delivered marker, flag changes on listed rows.

**Named risk — one-arm diff (base null = stored).** Focused check: `llama/replay.py:182` `_pair(old, new)` returns `None` iff `old == new`, and `ShowReplay` defaults `venue`/`city` to `None` (replay.py:405-406). So a non-null diff always has `old != new`. `_shipped` (replay_holds.py:373-380) returns own `new` when own has a diff, else the other arm's `old` (the stored value), else `None`. Cases:
  - base null, cand {S→X}: bv=S, cv=X, X≠S ⇒ listed with the right strings (this is test 1's shape).
  - base {S→X}, cand null: bv=X, cv=S ⇒ listed, correct direction.
  - both {S→X}: bv=cv=X ⇒ not listed (venue arm of test 2).
  - both null: None==None ⇒ not listed.
  No show whose two arms ship the same value can be listed. Stored `old` is the same in both arms because compare refuses arms whose input digests differ.

### Issues
#### Critical
None.
#### Important
None.
#### Minor
1. scripts/test_replay_holds.py:+803 — test 2 is named "ignores an identical diff" but the show is still listed (its city changes), so nothing asserts that a show whose ONLY diffs are identical in both arms is left out (the `continue` at replay_holds.py:391). Fix: add a case where both arms carry the same venue diff and no city change, and assert `0 show(s)` / `(none)`.
2. No test for the base-diff/cand-null direction or for the unreplayable skip + header count (`skipped N unreplayable show(s)`). The brief did not ask for them, so this is coverage, not a missing requirement. The header counts every unreplayable show, changed or not; the implementer disclosed this and the brief's wording ("counted in a header line") allows it.
3. Spec B says venue/city flag changes are defects while other flag changes on those rows are expected (slice D). The report lists all flag changes together and does not mark venue/city families separately. The brief's rule (one `flags CHANGED` line over `_all_flags`) mandates this, so it is compliant, but the operator has to pick out `venue mismatch`/city flags by eye.

### Assessment
**Task quality:** Approved
**Reasoning:** Every brief rule and spec item B requirement is in the diff, and both mandated tests are present. The named one-arm-diff risk holds up: `_pair` never emits an equal pair, so `_shipped` compares the stored value against the shipped one and never lists a show whose two arms ship the same value. The only gaps are Minor test-coverage items.
