# Scheduler spec review record (2026-10-25)

Review mode Fable. Round 1: breadth Opus + breadth Fable + strict Opus (all
Foundation SOUND; ~37 findings, 0 Critical). Round 2: the breadth pair, informed
(both SOUND; 20 findings, 0 Critical). Round 2's Important findings all hit round
1's mutable-tail "frontier" mechanism (two strikes, self-inflicted share >40%), so
it was replaced by phase 1's append-only plan plus a plan lock rather than patched;
review stopped there. Files: briefs, per-reviewer finding digests (r1-*, r2-opus;
the round-2 Fable review's items are folded into r2-decisions), the known-findings
list given to round 2, and both decision lists the editor applied. The round-1
breadth Opus review is folded into r1-decisions (tag O).
