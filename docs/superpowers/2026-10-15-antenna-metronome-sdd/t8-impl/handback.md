# t8-impl handback
Status: DONE. Commit a35208b "docs: the metronome rollout, rollback and verification; CLAUDE.md and the parent spec as built".
Tests (docs only): before and after, `cd antenna && npm test` = 20 files, 372 passed; `npm run typecheck` rc=0. No difference from the expected 372.
Insert locations (file:line after the edit):
- Step 1: docs/playout-setup.md:215 (sentence appended to step 5); step 7 at :237 (after step 6, which ends "unchanged.").
- Step 2: docs/playout-setup.md:447 (`metronome-down` row after `clock-failed`).
- Step 3: docs/playout-setup.md:496 (section 9 through the end of file; 9.1 follows).
- Step 4: CLAUDE.md:300 (metronome paragraph before "transmitter must stay Python 3.11-compatible"); Commands antenna bullet sentence appended at CLAUDE.md:174.
- Step 5: docs/superpowers/specs/2026-10-09-playout-design.md:512 (paragraph before "### Spend budget"); cost-guard bullet at :556 (after the "...cache hits on `live.m3u8`.)*" bullet).
All anchors were found verbatim. Only the three listed files changed. Insert text is verbatim from the brief.
Concerns: none.
