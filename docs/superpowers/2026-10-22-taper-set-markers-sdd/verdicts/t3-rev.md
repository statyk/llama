# t3-rev handback (Task 3 review: scripts/taper_probe.py, 5010a00..e59ab2f)

### Gate numbers trustworthy? — YES
62/186 = 0.333 is a correct measurement of the Tasks 1–2 prototype under the plan's definitions. I rebuilt it with my own bundle parse, cache read and `decide_taper` call and got the same 62. When I use the current library `show.json` tracks (post-adjudication titles) instead of the bundles, the result is 70/186 = 0.376, so the stop verdict holds whichever track source is used. It is a lower bound on what the rule could reach: part of the shortfall is reader defects that Step 7 sends back to Tasks 1–2, and a larger part is marker forms the spec's §1 list does not recognise (see Context).

| slug | what I checked | agrees |
|---|---|---|
| acousticsyndicate-2005-05-29 | bundle table → tracks/today_sets, md description, items, placement at 17/37, target `[17]`/`37` → match | y |
| derektrucksband-2004-04-15 | same; owned, break after 8, encore at 17; match | y |
| darkstarorchestra-2007-05-17 | the only miss: track 17 is tagged `E: I Fought The Law`, the taper puts it in the encore, the adjudicator's `--set-encore 17` puts it in set 2. The probe's encore semantics are right (they make the 33 matches line up); the target is the odd one | y |
| darkstarorchestra-2004-12-04 | filler-only: differs only on the `Crowd` track | y |
| tealeafgreen-2005-01-20 | owned, no target (t_breaks and t_enc both null); listed separately as it should be | y |
| darkstarorchestra-2005-11-16 | unplaced "China Doll matches 0": all 27 bundle tracks `unresolved` (filename as title), so nothing counts, as the spec intends | y |
| railroadearth-2004-08-28 | unplaced: all 35 tracks `unresolved` (the reader also emits a junk `Disc 1:` item, see Context) | y |
| gratefuldead-1990-09-15 | unplaced: the encore track's tag is `One Mors Saturday Night` (a typo), so 0 matches is real | y |
| moe-2005-09-03 | unplaced: the tape tags it `NYC>`, the description says `New York City` | y |
| darkstarorchestra-2008-02-17 / furthur-2010-05-30 | unplaced: the boundary song is not on the tape (DSO is a known partial tape); real | y |
| philleshandfriends-2008-11-18, ratdog-2008-11-16 | "one set": the description's headers are `Disc I 1st Set` and `Set I Disc 1: 74:16`, forms not in spec §1 | y |
| darkstarorchestra-2014-07-31, eotoband-2008-03-24 | "no markers": `Set 1 Disc 1:` and `Disk 1: Set 1`, not in §1 | y |
| garajmahal-2007-06-02, PLF-2001-12-31, moe-2004-01-31 | the encore-like veto comes from the pre-R4 encore-word rule (`encore crowd`, `Phil Encores:`, `(2nd encore)`); R4 collateral 0 is correct | y |
| library tedeschitrucksband-2018-02-09 | tier "encore folded": setlist.fm's encore becomes the taper's set 2, as expected | y |
| library ryanadams-2007-10-14 | stored has 7 encore tracks, the taper has set 2, but the tier says **"labels renamed"** | **n** (tier bug, Important 1) |

Other checks:
- **In-scope set:** I recomputed it independently and got 186 (114 set-header, 66 disc-with-set, 6 inline). The 39 excluded `yes` rows are bare digits, roman numerals, `S1`, Early/Late, and `Set 02`. The reader does not accept `Set 02` either, so the two agree.
- **Aliases:** `GD_SHORTHAND` when `is_family_artist(sj["artist"])`, the same rule as `gather.py:1230`.
- **Meta:** the probe passes `md["metadata"]`, as specified.
- **Bundle parse:** columns are indexed from the end, so `title_source` and `matched` come from the right columns.
- **Target arithmetic:** a break after N means set N+1 starts at track N+1, and the encore starts after track `t_enc`. This matches CLAUDE.md's `encore_after` and the override path. A missing flag reads as absent, which is what the fix would actually ship.
- **R4 switch-off:** the three regexes are used only inside `_encore_like`, and `NO_MATCH.sub` leaves the text unchanged.
- `git diff main -- packages/llama/src/llama/setlist.py` is empty. The diff adds only `scripts/taper_probe.py` and `scripts/test_taper_probe.py`, and edits no protected name (it imports `is_filler` and `_split_songs`, read-only).
- `./.venv/bin/python -m pytest scripts/test_taper_probe.py -q`: 6 passed.

### Spec Compliance — ✅ with one reporting gap
- ✅ In-scope set fixed before the reader runs, using the plan's regex (`taper_probe.py:66-97`).
- ✅ Gate over every yes/partial row. Ownership = owned / in-scope, with skipped rows kept in the denominator (none were skipped). Target match counts exact matches only; filler-only, renum and no-target rows are reported apart (`:299-349`).
- ✅ `today_sets` must be parallel to the tracks, else the row is skipped (`:157-160`).
- ✅ R4-alone collateral via a probe-local patch (`:163-183`). Ambiguous cases resolve to the taper owning less.
- ✅ Library pass skips shows with an override (`set_breaks: []` counts as one) (`:354-399`).
- ✅ `forms` covers every recognised form plus the void, cross-check and veto rules, with all family-artist hits and 30 seeded others per form (`:438-570`).
- ✅ `--out` refused when it overlaps `--root` or `--bundles` (exit 2).
- ❌ The library tiers misreport the very kinds the spec says decide whether the reader is defective ("encore folded or sets merged"). See Important 1 and 2 (`:234-252`).
- ⚠️ Cannot verify: whether every `forms_samples.txt` match is a true marker. That is Step 7's reviewer.

### Strengths
- The probe reproduces exactly and runs in seconds. It prints `llama.__file__` and is careful about read-only access.
- The bundle parser fixes sort1.py's `' | '`-in-title column bug.
- Every judgment call is documented and leans toward the taper owning less. The headline number is conservative: skipped rows stay in the denominator and filler-only differences are kept out of the numerator.
- The implementer's own flags ("junk items", "classifier vs reader disagreement") pointed at the real issues.

### Issues
**Critical:** none.

**Important**
1. `taper_probe.py:243-244`. The run-equality test for "labels renamed" runs before the encore checks, so an encore relabelled as a numbered set (or the reverse) is filed as "labels renamed". All 3 rows in that tier are really encore changes:
   - `ryanadams-2007-10-14`: a 7-track encore folded into set 2.
   - `joerussosalmostdead-2016-02-10` and `joerussosalmostdead-2022-04-30`: the stored set 3 becomes the taper's encore.
   As a result "encore folded" undercounts by 1 and "encore added" by 2, and the Checkpoint A reviewer will not see these cases. Fix: compare encore presence first, or call it "labels renamed" only when the encore positions are equal on non-filler tracks.
2. `taper_probe.py:250-251`. "sets merged or split" lumps the spec's defect signal (merged) with the expected effect (split): 4 merged, 13 split. The merged ones are `assemblyofdust-2004-12-31`, `mymorningjacket-2018-03-05`, `ryanadams-2008-01-19` and `tedeschitrucksband-2020-02-21`. The 10-of-17 random sample can leave merges out. Two more merges hide in other tiers: `smashingpumpkins-1998-05-19` (encore folded, 3 sets → 2) and `tedeschitrucksband-2019-11-15` (encore added, 4 sets → 2). Fix: split the tier into "sets merged" and "sets split", and list every merge, or flag a numbered-set decrease inside every tier.

**Minor**
3. `test_taper_probe.py:679-688`. The decide_taper monkeypatch proves nothing, because `in_scope` never calls the reader. Running `gate_rows` with a patched reader that returns a fixed decision, and asserting the `in_scope` flags are unchanged, would actually test "fixed before the reader runs".
4. `taper_probe.py:588-591`. The `--out` guard covers `--bundles` but not the rest of `~/.llama-harness/t3`, where the verdicts live. `--out ~/.llama-harness/t3/x` is accepted.
5. `breaks_of` (`:188`) is used only by the tests.
6. `forms_outputs` uses `h not in fam` (`:563`), which is O(n·m). It runs in 24 s, so this is cosmetic.
7. One correction to the implementer's handback, not a code issue. Trailing annotation symbols (`^`, `@`, `~`, `$`, `*`, `#`) are NOT why rows decline: `fuzzy_norm_title` strips them (tested: `One More Saturday Night^`, `Loner@`, `Funtime~`, `Immigrant Song^` all match). Those declines are on the tape side. Footnote digits (`Six Days on the Road1`) and parentheticals (`Darkstar (v1)`, `Sugaree (Chris vocals)`) do defeat the match.

### Context for Checkpoint A (what the 124 non-owned in-scope rows are)
- **14 unplaced rows have zero countable tracks** (all `unresolved` or the tautological `setlist`). The spec intends this.
- **Most of the 38 "one set" / "no markers" rows are marker forms outside spec §1:**
  - Set and Disc combined: `Set 1 Disc 1`, `Set I Disc I`, `Disc I 1st Set` (3 PLF/TTB rows), `Disk 1: Set 1`, `Disc 1, Set 1`, `DISC 1 SET ONE`, `Disc/Set1`, `disc 01 [Set I]`, `DISC 01:SET I :`, `Set 1/Disc 1:`, `set 1 - disc 1`, `CD1 Set 1`.
  - A duration or clock time after the header: `SET ONE (50:28)`, `Set One (9:30PM - 10:46PM):` (4 JRAD rows), `Disc 1 - Set 1 (61:20):`, `Set I (66:41)`.
  - A description with only an encore marker becomes the source, so the set markers in its notes are never read (`railroadearth-2009-01-15`).
  - The plan says Task 3 may only drop or narrow a form. Adding any of these is a spec change for the operator.
- **About 12 boundary items are reader-cleaning defects** (Tasks 1–2, per Step 7):
  - track prefixes the reader does not strip: `s2t01: Ripple`, `08: Ripple`;
  - disc text left after a set header on the same line: `Disc 2:`, `-Disk 2`, `Disc 1:`;
  - junk or non-song items: `=====`, `?`, `?(@15:57) 24:48`, `(Electric)`, `Set Break`, `Track 5`, `Phil reads Edgar Allen Poe…`;
  - footnote digits and annotation parentheticals (as in Minor 7).
- **The rest are genuine tape mismatches:** abbreviations, tag typos, partial tapes, songs matching 2–3 tracks, a non-filler track between the boundary songs.
- **Arithmetic:** fixing every cleaning defect gives about 74/186 ≈ 0.40. Getting to 0.5 also needs most of the form variants, which means a spec change.

### Assessment
**Task quality:** Needs fixes. Only the library tiers (Important 1–2) need a fix before Step 7's reviewer reads `library_summary.txt`. The gate numbers and the stop verdict are sound.
**Reasoning:** The yield gate is a faithful, independently reproduced measurement, and 0.333 holds (0.376 with current library tracks). The library tier classifier hides encore folds and merges inside "labels renamed" and a mixed merged/split tier, which are exactly the signals the checkpoint review is meant to check.

Scratch scripts (read-only): /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/5c4f03eb-6157-439a-a1f1-688e02807eae/scratchpad/t3-rev/spot.py, /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/5c4f03eb-6157-439a-a1f1-688e02807eae/scratchpad/t3-rev/classify.py, /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-taper-markers/5c4f03eb-6157-439a-a1f1-688e02807eae/scratchpad/t3-rev/desc.py
