# Round-2 decisions: simplify (circuit-breaker; operator approved 2026-10-22)

The mechanism is replaced by a whole-structure rule. Apply every item. "Remove" means remove every trace (Goals, Non-goals, Anti-goals, Constraints, sections 1–7, Measurement, Documented limitations, Left to the builder, Open questions). Keep the spec's voice; keep "(My call.)" on author calls; mark operator rulings as such.

## S. The new rule (operator approved, 2026-10-22)

S1. **The taper owns the whole structure or nothing.** The taper takes over a show's structure only when its text asserts a numbered structure of two or three sets (consecutive from set 1), with or without an encore, AND every boundary of that structure is placed (section 3). Then exactly the taper's structure ships: its numbered breaks and, if it marks one, its encore. Otherwise the show is computed exactly as today, every flag included. There is no merge of taper and fallback parts.
S2. **No encore marker:** if the taper marks sets but no encore, the taper's last set runs to the end of the tape (encore songs listed under set 2 ship in set 2: repeating the tape). Safety veto (my call): if the taper's text has no encore marker but some track title on the tape matches `structure._ENCORE_MARKER` (the test `encore_lost` already uses), the taper owns nothing and the show is computed as today.
S3. **Encore-only descriptions do not trigger the rule** (the taper must assert two or more numbered sets). They are computed as today. Add to Non-goals: encore-only descriptions (about 36 of the 262 in-scope shows) are left for a later piece.
S4. **Worded markers only.** The reader recognises:
- numbered sets: the word `Set` followed by 1–3, `one`–`three` or `I`–`III` (word-bounded: `Set Intro`, `Set IV` are not set 1), and ordinal `First Set`/`Second Set`/`Third Set` / `1st`/`2nd`/`3rd Set`; with any decoration around the header (dashes, asterisks, tildes, brackets, parentheses, `=`), alone on the line or followed by `:`/`-` and songs; `Disc N (Set M)`, `Disc N - Set M`, `Disc N / Set M` read as set M;
- the encore: a line starting (after decoration) with `Encore`, `Encores`, `ENC` or `E` followed by `:` (the existing `_ENCORE_LINE` shapes plus `Encores`/`ENC:` and decoration).
Not recognised, so they assert nothing: bare digits (`1:`, `[1]`), bare roman numerals (`I`, `II:`), `S1`/`S2`, `E.`, `(E)`, a trailing `enc`, and inline or parenthetical markers (`(start of Set II)`, `(set II)` mid-line). `Acoustic`/`Electric`/`Early`/`Late Set`, `Early Show`/`Late Show` and act headers stay non-markers.
S5. **Lines that assert nothing or void the structure:**
- a header line naming both a set and the encore (`Disc 3 - Set 2 + Encore`, `Set One & Encore`) asserts nothing;
- a repeated set number (`Disc 3 (Set 2 cont.)`, `Set 2 continued`) is a continuation and asserts nothing;
- the first encore marker starts the encore; later encore lines are continuation;
- a decreasing, restarting or skipping set number, a set number 4 or higher, an empty set (a header followed directly by another header), or any numbered marker after the encore marker means the taper asserts **no** structure (the show is computed as today).
S6. **Notes** are read only when the description has no explicit marker at all (operator's original rule; remove the per-part split and the `railroadearth-2009-01-15` example). Notes lines never become canonical items; notes go through the same reader, guards and placement.
S7. A leading unlabelled block before the first explicit set marker is set 1 only when the first explicit marker is set 2; when the first explicit marker is set 1, lines before it are header text and are ignored.

## P. The reader's output and placement (round-2 definitions)

P1. The reader outputs ordered song items, each with its taper set label (`1`, `2`, `3`, `encore`), produced with `setlist.py`'s existing line handling (`_emit_items`-style: `_NOISE`, `_TRACK_PREFIX`, the enumerated `_NUM_PREFIX`, segue splitting) plus stripping a leading duration/timestamp (`-04:41.50-`). It reuses those helpers without changing them for `parse_setlist`.
P2. Matching: a tape track matches an item when `fuzzy_title_eq` (or a title component of a merged track, by the same test) holds, with gather's family aliases; only tracks whose `title_source` is not in `TAUTOLOGICAL_TITLE_SOURCES` and not `unresolved` count. The same test decides "also occurs on the other side".
P3. A boundary between taper set A and the next set B (the encore counts as the last set) is placed only when: exactly one tape track matches A's last song item (track a) and exactly one matches B's first song item (track b); a < b; every track strictly between them is `is_filler`; neither a nor b is a merged track with components on both sides; and neither A's last nor B's first song title also occurs on the other side of the boundary in the taper's list. Otherwise unplaced, and so the taper owns nothing.
P4. Filler between a and b: if today's (step-1) structure splits that filler run, keep today's split point, with the taper's labels on each side; otherwise the filler goes with B. Labels are always the taper's (1..n, encore).
P5. Remove D4's old wording, D5's "keep today's labels", D6, and "A the last numbered set" phrasing.

## E. Order, LLM skip, flags

E1. Order in §4: (1) deterministic alignment of the winning canonical, then jerrybase anchoring, exactly as today (step-1 structure; the reference for every "was …" note); (2) the reader and placement; (3) if the taper owns the structure, it ships and the `align_structure` LLM is not called; otherwise step 4 onwards is exactly today's path (LLM branch, flags).
E2. Low-confidence flag on a taper-owned show (my call): raised, with no LLM call, only when today's path would have reached the LLM branch (no anchoring and step-1 coverage below `align_coverage_threshold`) AND the coverage of the reader's items aligned (`align()`) against the tape is also below the threshold. Record that coverage.
E3. Remove: per-part ownership, the merge step, the `taper set markers conflict with the aligned structure` flag, the encore-only skip clause, "no source asserts an encore the shipped structure lacks" (replaced by S2's veto), and any discussion of `structure_guard`'s single-set checks needing changes (a taper-owned structure always has at least one numbered break; `structure_guard` runs as today). Remove the "long single set with only an encore break" limitation if it no longer applies.

## F. Provenance

F1. `StructureInfo` gains one permissive boolean field (name builder's choice, e.g. `taper_owned`), absent/false in old dirs. Gather exposes it in-process.
F2. `alignment` becomes `"taper"` when the taper owns the structure AND its breaks differ at song level from the step-1 structure; otherwise it keeps today's value. The "set breaks from the taper's markers (was …)" operator note is written in the same case, citing the step-1 breaks.
F3. `StructureInfo` is created whenever the taper owns the structure, even with no canonical source.
F4. The closer-tripwire skip: as today, it is skipped when the shipped numbered breaks came from jerrybase anchoring; on a taper-owned show it runs, with G2's demotion.

## G. Holds and notes on a taper-owned show

G1. `structure has N sets but jerrybase shows M`: an operator note when the taper's own set count differs from jerrybase's; otherwise computed as today.
G2. A jerrybase closer hard flag for jerrybase set k (mapped by set number; "last numbered" means jerrybase's last): an operator note when the taper's own last song of set k differs from jerrybase's closer of set k; otherwise it stays hard (it then catches llama's placement).
G3. Drop today's "set breaks anchored from jerrybase (was …)" entry from `notes`/`conflicts`, and drop `merge_conflicts` (the `merged track(s) … span a set break` flag), when the taper owns the structure (P3 already excludes merged tracks at taper boundaries).
G4. Notes go to `notes.json` (operator notes), never `conflicts`. Every other flag is untouched.

## H. Harness, reapply, measurement

H1. §7: the relaxation keys on exactly one gather-reported predicate, "the taper owns the structure" (F1), and nothing else. Stored-`llm` + taper-owned → replayable; stored-`llm` + not taper-owned → needs-LLM exactly as today (the Tier 1 mutant keeps holding). Mutation tests both directions, plus one on S2's veto. Every stored-`llm` show this moves is listed for the pre-screen with its segue changes.
H2. Report 3: rows needing the LLM in the candidate are split by candidate ownership; those not taper-owned are provably unchanged by this piece and are counted, not listed. "Before" is the base arm's replay, or the stored structure where the base arm is needs-LLM. Keep the other H2 items (tiers, voiced from the station manifest, unreplayable/slfm-miss section).
H3. Measurement 1 scores at song level; filler-only differences are their own class, not misses. Expected outcomes restated for: encore-only rows (out of scope, today's behaviour), rows whose markers are now unrecognised forms (bare digits, romans, inline: today's behaviour), and the 8 disagreements (taper's structure ships where it owns it; with no taper encore marker the last set runs to the end unless S2's veto applies).
H4. Measurement 5: count raw matches per recognised form over every cached description and notes field; the drop criterion is a non-marker match that **places a boundary or changes ownership** (not any match, since lineage text is neutralised by placement). Sample: every hit on a family artist plus 30 random others per form (all, if fewer).
H5. Add a gate to the start of the work (my call): before building, a read-only prototype of the reader and placement over the 339 yes/partial shows (sort1.json tracks) reports placed / unplaced / owned and how many match the adjudicator target at song level; if fewer than half of the in-scope rows the new rule covers are owned, stop and bring the result to the operator.
H6. Update the Why/evidence yield text: the in-scope population is the 262 minus encore-only rows and rows whose markers are only unrecognised forms; give the estimate as "to be measured by H5" rather than a number.

## N. Negative tests and limitations

N1. Keep the required negative tests, now asserting "no structure asserted": the N: tracklists (giantsand x7, calexico x3, signalpath-2005-06-09), the DSO bare-digit disc numbering (`darkstarorchestra-2005-11-16`, `-2004-04-20`, `-2005-12-03`, `-2004-04-24`), `umphreysmcgee-2004-04-14` and `lotus-2005-10-15` (set+encore disc lines assert nothing, and the later `e:` still starts the encore), `davidnelsonband-2007-09-07` (numbered marker after the encore voids), the `[1]` footnotes (`moe-2002-06-22`, `kinggizzardandthelizardwizard-2025-08-17`), `(E) With Allie Kral` (`railroadearth-2008-08-17`), Antibalas `[1]…[5]`, `E.Ville`, `B. E. Women`, `E. Rutherford, NJ`, `I Know You Rider`, `J`, `Untitled #12`, `1:08:07`, "Set I is Bobby and Jerry playing acoustic" (`gd1981-10-16`), `Set Intro`, `Set IV`. Positive tests: `charliehunter-2001-12-08` is NOT taper-owned (Early/Late Show + encore only), `gratefulshred-2023-11-10`, a `Disc 2 (Set 2)` show, a notes-only show.
N2. Documented limitations (add): explicit single-set statements ("One Set", "no set break") are not read; `is_filler` is a substring test, so a real song matching the filler pattern between a and b can move sides; a `Set Break`/`Donor Rap` track between sets makes the boundary unplaced (falls back); encore-only descriptions and the dropped marker forms keep today's behaviour. Keep the still-valid existing limitations (later fix/redo/triage re-gathers; new gets without hand check).
