# Round-1 decisions for spec 2026-10-22-taper-set-markers-design.md

Apply every item. "Remove" means remove every trace (sections, Goals, Constraints, Measurement, Left to the builder, Open questions).

## A. Sources (operator ruling 2026-10-22)

A1. The taper's text is the selected recording's **description**, and its **`notes`** metadata field only when the description has no explicit set or encore marker at all (then notes is the one source). Never both for one show, so no cross-source disagreement rule exists.
A2. **Remove filenames and track tags as marker sources** entirely: §1 items 3 and 4, §2's filename and track-tag bullets, §3's "Filename and track-tag boundaries are already per-track", the disagreement bullet in §2 ("If two of the taper's own sources disagree…"), the `moe-2008-01-24`-style concerns. Add one Non-goal line: filename set tokens (`s2t05`, where some tapers use `s3` for the encore and `s0` for pre-show) and set labels in track tags are not read in this piece; they may be added later if the shipped-show report shows they would earn it.
A3. Notes lines never become canonical setlist items. A notes boundary is subject to exactly the same guards and placement test as a description boundary; lineage text such as "Set 1: MSR> C> DAT", "Set 2 is seamless", "Encore: None" asserts nothing because its items match no track (placement requires matches on both sides, D1).
A4. Update the evidence numbers: the 282 split by primary form becomes in-scope description forms + notes; filename-set (7) and track-title-set-label (13) shows are out of scope (fixable by `llama fix`).

## B. The parser stays untouched

B1. `parse_setlist`'s output must stay **byte-identical**. Taper markers are read by a separate, structure-only reader of the chosen recording's description (or notes, per A1), used only to derive and place taper boundaries. Remove the "provenance flag on ParsedSetlist/SetlistItem" option from Left to the builder, and §6's sentence that the vocabulary may improve sibling parses in `rank_parses`. The canonical setlist, `rank_parses`, `blend_segues`, `_corroboration`, the title rungs and `--suggest-titles` see no change from this piece. Rewrite the Non-goal on titles accordingly: titles do not change, by construction, and the harness verifies zero title changes (any title change is a defect).
B2. The structure-only reader may reuse `setlist.py`'s existing regexes and helpers, but must not change their behaviour for `parse_setlist`.

## C. Marker guards (Critical, two reviewers)

C1. Replace the generic "header shape (line start, alone on a line or followed by songs, in a description that otherwise reads as a setlist)" with per-form structural guards, stated as requirements:
- A new marker form may **never act as a truncation point** (the structure-only reader does not truncate; it only reads labels).
- Digit forms (`1:`, `2:`, `[1]`): a header only when the description has no line of that same form numbered 4 or higher, and the numbers used run 1, 2[, 3]. A `N:` followed by a duration digit (`1:08:07`) is not a marker.
- Bracketed forms (`[1]`, `[E]`, `[Set One]`): only alone on the line.
- Bare roman numerals (`I`, `II`, `III`): only alone on the line, or followed only by `:` or `-` and then text. `I Know You Rider` is never a marker.
- `E.`: only followed by whitespace and a capital (never `E.Ville`, `E.T.I`, `E.S.P.`).
- `(E)` and `[N]` followed by prose (a lowercase word, or `With …`) or appearing after the last song are footnote legends, never markers.
- `Set I…` needs a word boundary (`Set Intro`, `Set IV` are not set 1).
C2. Required negative tests on real cases: `giantsand-1991-01-30` (and the other N: tracklists: giantsand 1989-05-10, 1996-02-03, 2001-01-08, 2001-03-04, 2004-10-15, 2005-09-02; calexico 1998-06-14, 2000-07-01, 2003-04-25; signalpath-2005-06-09) assert no break; `moe-2002-06-22` and `kinggizzardandthelizardwizard-2025-08-17` `[1]` footnotes; `railroadearth-2008-08-17` `(E) With Allie Kral`; `antibalasmusic-2003-04-28` `[1]…[5]` track numbers; `E.Ville`; `I Know You Rider`; `J`; `Untitled #12`; `1:08:07`; "Set I is Bobby and Jerry playing acoustic" (`gd1981-10-16`).
C3. Measurement 5 is widened: count, per form (new AND existing forms the reader uses), matches over every cached description and every cached `notes` field; hand-sample; the drop criterion is **any non-marker text read as a marker** (song, track number, footnote, duration, credit, lineage, prose). A form whose sample shows one is dropped or narrowed before merge, never patched around.
C4. Encore forms with collision risk and tiny yield may be dropped by that measurement; the builder must not add a form the evidence did not list.

## D. What the taper asserts and placement

D1. Replace §2's "numbered break is asserted at each explicit numbered-set marker that has taper items before it" with: a numbered break is a **change of explicit set number**. A leading unlabelled block before the first explicit number counts as set 1 when the first explicit number is 2. The taper asserts a numbered structure only if its set numbers run consecutively from 1 (1, 2[, 3]) and strictly increase, with no numbered marker after its encore marker. A repeated label (continuation headers, `Disc 3 (Set 2 cont.)`) asserts nothing. Any decreasing, restarting, skipping or post-encore number means the taper asserts **no** numbered structure (the encore assertion is judged on its own).
D2. Remove the "ships set 2" partial-tape ruling and its note. Taper-owned labels are then always 1..n.
D3. Labelled sets: ordinal labels (`First Set`, `Second Set`, `Third Set`) are explicit numbered markers. `Acoustic Set`, `Electric Set`, `Early Set`, `Late Set` and similar are **not** explicit for this rule (they may be two shows or unnumbered); `Early Show`/`Late Show` and act headers stay non-markers.
D4. Placement (rewrite §3's test): a boundary between taper set A and the next taper set B is placed after track t only when ALL hold:
- the tape has a matched track for A's **last song item** and one for B's **first song item** (an independent match: title_source not in `TAUTOLOGICAL_TITLE_SOURCES`, not `unresolved`); with track a for A's last and b for B's first, a < b;
- every track strictly between a and b is filler (`is_filler`); a tautological, unresolved or song-like track between them makes it unplaced;
- no track at a or b is a merged track whose components match items on both sides;
- neither A's last song nor B's first song title also occurs on the other side of the boundary within the taper's list (`Jam`, `Drums`, `Space`, reprises): such a boundary is unplaced.
Otherwise the boundary is unplaced. Matching uses `fuzzy_norm_title`/title components and gather's family aliases, as today (no new fuzzy rule).
D5. Filler between a and b: if today's (fallback) structure puts its break inside that filler run, keep today's labels for those filler tracks; otherwise filler goes with the set it introduces (B). Purpose: agreeing song-level boundaries do not move filler labels.
D6. The encore boundary placement uses the same test (A = last numbered set, B = encore).

## E. Precedence, order and merging

E1. State the order in §4 explicitly: (1) deterministic alignment of the winning canonical, then jerrybase anchoring, exactly as today; this is "today's structure" and the reference for every "was …" note; (2) taper derivation and placement; (3) the ownership decision; (4) the `align_structure` LLM path only if the §4.5 skip does not apply, evaluated exactly as today on the non-taper path; (5) the merge.
E2. Ownership stays all-or-nothing per part (numbered breaks; encore boundary) as in the current §4.3, with D1 and D4 feeding it.
E3. Replace "the taper-owned part ships, the conflicting fallback boundary is dropped, and an operator note records it" with: if the taper-owned part and the fallback part cannot combine monotonically, the show is held with a new flag `taper set markers conflict with the aligned structure` (the safe direction). Remove the note-on-conflict.
E4. §4.5 skip rewritten: the LLM realignment is skipped only when every shipped boundary is taper-owned AND no source asserts an encore the shipped structure lacks (neither an unplaced taper encore marker nor a canonical encore item). Even then the `low-confidence structure alignment` flag is raised, with no LLM call, when the coverage of the taper's own parse against the tape is below `align_coverage_threshold`. Record that coverage.
E5. Fix §6: the composition point is `compute_gather` (which the harness and `reapply` call), not `run_gather`.

## F. Provenance record

F1. Add a permissive `StructureInfo` field (name builder's choice, e.g. `taper_owned: list[str]`, values `numbered`, `encore`, empty or absent for old dirs) that records which parts the taper owns. Gather also exposes this ownership to its callers in-process.
F2. `alignment` keeps naming the mechanism of the numbered breaks: it becomes `"taper"` only when the taper owns the numbered breaks AND the taper's numbered breaks differ at song level from today's structure (the "was …" condition). Otherwise it keeps today's value (`deterministic`, `jerrybase`, `llm`). An encore-only taper ownership never changes `alignment`.
F3. Create `StructureInfo` whenever any part is taper-owned, even with no canonical source.
F4. The closer-tripwire skip keys on "the numbered breaks came from jerrybase anchoring" (ownership + mechanism), not on the `alignment` string alone.

## G. Holds and notes

G1. Demote `structure has N sets but jerrybase shows M` to an operator note only when the taper owns the numbered breaks AND the taper's own numbered set count differs from jerrybase's (the taper text disagrees with jerrybase). If the taper's text agrees with jerrybase's count, the flag is computed as today on the shipped structure.
G2. Demote a jerrybase closer hard flag to an operator note only when the taper owns the break that ends that set AND the taper's own last song of that set differs from jerrybase's closer (text disagreement). If the taper's text names the same closer, the hard flag stays (it then catches llama's placement, not the taper's text).
G3. Remove §5's "count numbered breaks only" clause for `structure_guard` entirely; the guard runs as today on the merged structure. Add a documented limitation: a long single set whose only break is an encore boundary is not flagged, as today.
G4. When the taper owns the numbered breaks, drop today's "set breaks anchored from jerrybase (was …)" entry from `notes`/`conflicts` (it would reach the briefing contradicting the shipped labels), and compute `merge_conflicts` (the `merged track(s) … span a set break` flag) against the shipped breaks.
G5. Keep: notes go to operator notes (`notes.json`), never `conflicts`.

## H. Harness and `reapply`

H1. §7 rewritten. The condition is the gather-reported boolean "every shipped boundary is taper-owned" (E4's condition, from F1's in-process ownership), never "the gather made no LLM call" and never the `alignment` string. Rationale corrected: the stored LLM structure was never an input to the replay; the rule exists because deterministic re-gathers wrongly replaced LLM structures (Tier 1 spec, 15 of 84 prototype clears, at least 4 wrong at a set boundary). Relaxing it is justified only where the shipped structure is wholly the taper's, placed by D4's exact test. Tests in both directions: a stored-`llm` show whose candidate is all-taper is replayable; a stored-`llm` show whose candidate is deterministic, anchored, or only partly taper-owned stays needs-LLM (the Tier 1 mutant keeps holding). Every stored-`llm` show this moves is listed for the pre-screen, with its segue changes.
H2. Report 3 (shipped shows whose structure changes):
- "before" is the **base arm's replay**, with the stored value alongside, so old-code drift is not attributed to this piece;
- rows are tiered: songs moved between sets / filler labels only / provenance only;
- voiced status is read read-only from the station root's manifest `dj_audio` (as `deliver`'s voiced check does); llama's `derive_state` has no voiced state;
- a section lists shipped shows unreplayable in either arm and `slfm_miss` rows, so no shipped show the rule could touch is silently absent;
- stored-`llm` shipped shows still needing the LLM in the candidate are listed with `after: needs LLM`.
H3. Report 3 gets an **Opus pre-screen before merge** (all rows with songs moved; a stratified sample of the rest by marker form), like report 2.
H4. The override-ignoring mode for Measurement 1 strips only `overrides.set_breaks`/`encore_after` (keeping excludes, includes, titles: the adjudicator's targets are in post-exclusion numbering), runs as a script-side scratch transform stamped in the arm, and is never a `compute_legs` parameter (so it can never feed a `--from-list` apply). It is a required harness task.
H5. Structure-changed accounting: because F2 keeps `alignment` unchanged when the taper merely agrees, `_structure_changed` needs no change; say so. If the builder finds a remaining label-only flood, it reports, it does not change `_structure_changed`'s rule (a reapply gate).

## I. Evidence and scope text

I1. Correct numbers: 375 verdicts were `fix`, 320 of them with a structure flag; the 282 breakdown includes 19 `other`; and **312 of the 394 already carry an operator structure override and are not held; 82 remain held**. Say plainly that the payoff is mostly future gathers and shipped shows that carry the defect unflagged (e.g. `gratefulshred-2023-11-10`: "Dancin' in the Streets" ships in set 1 while its own `S2T02` filename puts it in set 2 — note that under A2 this specific case is filename-driven; pick a description-driven example if one is at hand, else keep it as illustration of the class).
I2. The 8 disagreements: restate per show — all are `partial`; for `derektrucksband-2005-01-09`, `darkstarorchestra-2007-05-08`, `thedead-2009-04-29` the disputed boundary is an encore the taper did not label, so the fallback's encore ships; `gratefuldead-1970-05-15-spans` stays held by `tape spans`. Measurement 1 scores them by those expectations.
I3. Name the ~10 partial-tape shows whose verdicts carry `partial-tape` (citizencope-2007-12-29, gratefuldead-1970-02-11-spans, campervanbeethoven-2003-01-18, gratefuldead-1970-06-06, soulcoughing-1998-10-25, gratefuldead-1981-12-31, derektrucksband-2004-04-15, darkstarorchestra-2008-02-17, darkstarorchestra-2004-04-17, waynehancock-2004-04-08); the report-2 pre-screen checks every newly cleared show for completeness against the adjudicator's `partial-tape` tag.
I4. Documented limitations (one line each): after release, any later `fix`/`triage`/`redo --from gather` of a shipped show re-gathers under the new rule and may change its breaks without a listing; new `llama get` gathers run the rule with no hand check (the pre-merge pre-screens of reports 2 and 3 are the check); a long single set with only an encore break is not flagged (G3); a taper whose set boundary lands next to a title repeated across it falls back (D4).
I5. Remove the Open questions line's "taper wins where it marks, others fill the rest" phrasing only if it now contradicts anything; add the 2026-10-22 ruling: description first, notes only when the description has no markers; filenames and tags out of this piece.
