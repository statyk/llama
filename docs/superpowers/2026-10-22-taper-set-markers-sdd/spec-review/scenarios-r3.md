# Fixed scenarios for the simplified rule (whole-structure ownership)

For each: what the spec says happens, and whether that is safe (today's behaviour or the taper's own structure, never a structure nobody asserted, never a newly cleared wrong show).

1. Description `Set 1: … Set 2: … Encore: …`, setlist.fm one unlabelled set, all boundaries place → taper structure ships, hold clears.
2. Same, but the set-2 opener is followed on tape by an unlisted `Set Break` track before it → unplaced → today.
3. `Set One … Set Two …` with no encore marker; tape's last two tracks are titled `Encore: X`, `Y` → S2 veto → today.
4. Same with no encore-marked track titles, setlist.fm has an encore → taper's set 2 runs to the end (encore songs in set 2).
5. `1: Song / 2: Song / … / 14: Song` (giantsand) → no worded marker → nothing asserted → today.
6. DSO `1: … 2: … Set 2: … 3: … E: …` → only `Set 2:` and `E:` are markers; leading block before `Set 2` is set 1 (S7); does it place? If it places, taper ships 2 sets + encore where `1:`/`2:`/`3:` were discs. Check this against jerrybase (2 sets) and the true structure.
7. `Disc 3 - Set 2 + Encore` then `e:` later (umphreysmcgee-2004-04-14) → disc line asserts nothing; `e:` starts the encore; result?
8. `set 1 … 08. encore: Box Of Rain (set 2) / disc 2 / set 2 …` (davidnelsonband-2007-09-07) → numbered after encore → nothing → today.
9. Early Show / Late Show + `Encore` lines only (charliehunter-2001-12-08) → no numbered markers → today.
10. PLF show: `Set I … Set II … Encore`, jerrybase one-set row with closer = last song of the show → taper owns; set-count flag (taper 2 vs jerrybase 1) → note; jerrybase set-1 closer ≠ taper set-1 last song → note; show clears. Is the jerrybase closer (last song of the show) at a break in the taper structure? (It is the end of the show, not a break → tripwire would fire as hard? check G2 mapping.)
11. A Dead show where taper and jerrybase agree; llama's placement of set 1→2 is one track off due to a merged closer → P3 declines (merged with both sides) → today.
12. Repeated `Jam` closing set 1 and opening set 2 → P3 declines → today.
13. Notes only: description has no marker; notes `Set 1: MSR> C> DAT / Set 2 & 3: MSC> DAT> CD` → set+... `Set 2 & 3` line? numbering 1, then "2 & 3" ambiguous; items `MSR> C> DAT` match no track → unplaced → today.
14. Stored `llm` shipped show, description `Set 1/Set 2/Encore`, all place → taper-owned → replayable; structure listed in report 3 with segue changes. Stored `llm`, not taper-owned → needs-LLM as today.
15. A show with an operator `set_breaks` override → override wins; the rule never runs.
16. A taper structure with three numbered sets where jerrybase has two → set-count note; ships three sets.
17. Sets numbered `Set 1`, `Set 3` (skip) → nothing → today.
18. `Set 1` header only, no `Set 2` → fewer than two numbered sets → today.
19. Low coverage: step-1 coverage 0.4, no anchoring, taper boundaries place, reader coverage 0.5 → taper ships with `low-confidence structure alignment` (still held) and no LLM call.
20. Same with reader coverage 0.9 → taper ships, no flag, no LLM call; clears.
21. Filler run (`tuning`, `crowd`) between set 1's last song and set 2's first; today splits inside the run at a different point than default → keep today's split point with taper labels.
22. Future `llama get` of a new show of shape 1 → taper ships live; no hand check (documented).
23. Taper `Set 2` first explicit marker with an unlabelled block before it → block is set 1; if that block is actually a band/venue header (no songs that match) → set 1's last song is header text → no unique track match → unplaced → today.
24. Encore with several encore lines (`Encore 1:`, `Encore 2:`) → first starts encore, later continuation.
