# Known findings after round 1 (4 Opus reviews: 2 breadth, 2 strict) and how the spec now handles each

1. New marker forms collide with N: tracklists, [N] footnotes, (E) legends, E.Ville, "I Know You Rider", durations; a new marker could truncate the setlist (Critical x2). -> Per-form structural guards; the structure-only reader never truncates; required negative tests on named real shows; corpus measurement over descriptions and notes with "any non-marker read as a marker" as the drop criterion.
2. Changing parse_setlist moves canonical items, confidence, rank_parses winner, corroboration, setlist-gap counts, suggest-titles. -> parse_setlist stays byte-identical; a separate structure-only reader of the chosen recording; zero title changes is an acceptance check.
3. Two taper sources disagreeing dropped one boundary while the taper still owned the rest; filename s3-as-encore and s0 pre-show. -> Filenames and track tags removed as sources (operator ruling); notes is read only when the description has no marker, so one source per show.
4. Lineage text in notes ("Set 1: MSR> C> DAT", "Encore: None"). -> Notes boundaries need matched songs on both sides (placement), never become canonical items, and are in the corpus measurement.
5. Break per marker, not per change; continuation/decreasing/restarting labels; "Set IV"/"Set Intro". -> A break is a change of explicit set number; numbers must run 1..n consecutively and strictly increase; any violation means no numbered assertion; word boundary on Set I.
6. Partial-tape "ships set 2" contradicted §2 and trips ordinal guards. -> Removed; taper-owned labels are always 1..n.
7. Placement vacuous with no match on one side; greedy align order clause can't fail; repeated titles across a boundary; merged tracks; tautological tracks in the gap. -> Placement needs independent matches for A's last song and B's first song with only filler between; merged-across and repeated-title boundaries are unplaced; tautological/unresolved tracks in the gap make it unplaced.
8. Filler default moved intro/tuning labels on agreeing shows (report flood). -> Filler keeps today's labels when today's break lies in the filler run.
9. Monotone conflict between taper and fallback was a note. -> Now a hold flag.
10. Low-coverage skip had no fit check; "ships no encore" circular with the LLM step; order unspecified. -> Explicit order (deterministic+anchoring, taper, decision, LLM if needed, merge); skip only when every boundary taper-owned and no source asserts an encore the structure lacks; low-confidence flag still raised (no LLM) when the taper parse's own coverage is below threshold.
11. alignment:"taper" for any part erased llm/jerrybase provenance and flooded structure-changed lists. -> Separate taper-ownership field; alignment becomes "taper" only when the taper owns the numbered breaks and they differ from today's; tripwire skip keys on mechanism + ownership.
12. Closer/set-count demotion also silenced the only check on llama's placement. -> Demoted only when the taper's own text disagrees with jerrybase (count, or closer song).
13. Numbered-only guard clause newly held shipped shows. -> Removed; documented limitation.
14. Stale anchoring note reached the briefing; merge_conflicts against pre-taper breaks. -> Dropped/recomputed when the taper owns the numbered breaks.
15. §7 relaxation read as "no LLM call" (deletes the Tier 1 pin); wrong rationale. -> Keyed on the gather-reported all-taper-owned boolean; rationale corrected; mutation tests both directions; moved shows listed with segue changes.
16. Report 3: base drift misattributed, unreplayable rows absent, voiced not derivable, label-only flood, no independent check. -> Before = base arm replay; tiers; voiced from station manifest read-only; unreplayable/slfm-miss section; Opus pre-screen before merge.
17. Override-ignoring mode unscoped. -> Strips only set_breaks/encore_after; script-side scratch transform stamped in the arm, never a compute_legs parameter.
18. Composition point named run_gather. -> compute_gather.
19. Labelled non-ordinal sets explicit or not. -> Ordinals explicit; Acoustic/Electric/Early/Late not.
20. StructureInfo absent with no canonical. -> Created whenever any part is taper-owned.
21. Partial tapes (~10 named) held only by structure flags could clear. -> Named; pre-screen checks completeness.
22. Evidence counts (375 vs 320, 19 other, 312 of 394 already overridden, 82 held); 8 disagreements' expected outcomes. -> Corrected and restated per show.
23. Later fix/triage/redo on shipped shows and new gets pick up the rule unseen. -> Documented limitations.

## Removed by later revisions
- Filename set tokens and track-tag labels as marker sources.
- The cross-source disagreement rule.
- The partial-tape "ships set 2" ruling.
- The provenance-flag-on-ParsedSetlist option and any parse_setlist change.
- The monotone-conflict note (now a hold).
- §5's numbered-breaks-only structure_guard clause.
