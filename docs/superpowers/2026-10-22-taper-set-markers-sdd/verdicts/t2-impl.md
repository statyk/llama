# t2-impl handback
Status: DONE_WITH_CONCERNS (minor)
Commit: see `git log -1` on held-backlog-taper-markers, subject `feat(taper): exact placement and the ownership decision`.
Implemented in packages/llama/src/llama/taper.py: TaperPlacement, TaperDecision, place_taper_structure, decide_taper (spec s2/s3). Tests appended to packages/llama/tests/test_taper.py (20 new tests incl. both real cases as literals).
RED: copy of HEAD~ code + new tests: `ImportError: cannot import name 'decide_taper'` (collection error). GREEN: test_taper.py 108 passed; full suite 4155 passed, 1 skipped, 8 deselected. setlist.py diff vs main empty.
Judgment calls (declining-biased):
- Filler between a and b must be is_filler AND title_source not unresolved/tautological.
- Today's split inside a..b: if more than one split in the range, decline. Split anywhere in positions a..b-1 is honoured when there is at least one track between a and b.
- "Other side" = all taper items on each side of the boundary (not only adjacent set); merged-track test uses the same match over all items each side.
- Extra declines: fewer than two sets; a boundary's b earlier than the previous boundary's a, or boundaries not strictly increasing ("boundaries out of order").
- Decline format: "unplaced: <A>|<B> <why>".
- Real-case tests: moe uses a minimal tape (Moth, Head, Interstellar Overdrive, Head between set II and encore) -> "between" decline; DSO 2005-11-16 declines on repeated NFA matching 2 tracks.
Concerns: none blocking; the order of checks means a repeated title declines with "matches 2 tracks" before "other side" when the tape also repeats it.
