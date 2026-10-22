# Known findings after rounds 1–3 (7 Opus reviews) and how the spec now handles each

Round 1 items (see the list below in this file's second half) were mostly superseded by the round-2 simplification.

## Round 2 (2 reviews) → simplification (operator-approved)
1. Disc lines naming set + encore made a five-song encore (umphreysmcgee-2004-04-14). -> Such a line asserts nothing; test pinned.
2. Bare `N:` accepted DSO disc numbering; `E.` hit `B. E. Women`, `E. Rutherford`. -> Worded markers only; bare digits/romans/brackets/S1/E./(E)/inline forms are not markers.
3. A taper-placed encore silenced structure_guard's single-set checks (charliehunter-2001-12-08). -> Whole-structure rule: the taper owns only with >=2 numbered sets, so a taper-owned structure always has a numbered break; encore-only descriptions do not trigger.
4. Encore assertion survived a later numbered marker (davidnelsonband-2007-09-07). -> Any numbered marker after the encore voids the structure.
5. Filler kept today's label values (phantom set). -> Today's split point is kept, labels are the taper's.
6. §7 named two predicates as one. -> One gather predicate: "the taper owns the structure".
7. Inline parenthetical forms had no side. -> Not recognised.
8. Reader output and matching undefined. -> Defined (ordered song items via _emit_items-style handling; fuzzy_title_eq; exactly one matching track per side).
9. Measurement 5 drop criterion contradicted reliance on placement. -> Drop criterion is a non-marker match that places a boundary or changes ownership; sample size stated.
10. Low-confidence flag under the skip newly held agreeing anchored shows. -> Raised only when today's path would reach the LLM branch AND the reader's coverage is also below threshold.
11. Skip ignored track-title encore evidence. -> Veto on `_ENCORE_MARKER` in track titles.
12. Merge equality conflicts; per-part ownership; merge_conflicts undefined; encore-only trace. -> Merge removed; merge_conflicts dropped on taper-owned shows.
13. Report 3 needs-LLM flood. -> Split by candidate ownership; non-owned counted, not listed.
14. Notes per-part trigger ambiguity. -> Notes only when the description has no explicit marker at all.

## Round 3 (scenario check, 1 review)
15. Unrecognised encore text (`18. E: Song`, `Encore 1:`, inline `Encore:`) read as "no encore", folding the encore into the last set (~49 shipped shows). -> Markers tested after track-prefix stripping; `Encore 1:`/`1st Encore:` recognised; veto extended to encore-like words in the taper's own text (`\bencores?\b`, `\benc\b`, song lines starting `E.`/`E)`/`E<digit>`/`(E)`).
16. Negative-test list contradicted §2 (DSO 2005-11-16 asserts a structure). -> Reworded per line; 2005-11-16 declines at placement.
17. Bare disc-number lines and set-header timestamps became song items. -> Dropped by the reader.
18. Misdated tape loses jerrybase holds on a taper-owned show. -> Documented limitation; report-2 pre-screen checks dates on shows whose cleared flags were only jerrybase ones.

## Removed by revisions
Filenames/track tags as sources; cross-source disagreement rule; per-part ownership and the merge; the conflict hold flag; the "ships set 2" ruling; any parse_setlist change; structure_guard numbered-only clause; per-form digit/roman/bracket guards.
