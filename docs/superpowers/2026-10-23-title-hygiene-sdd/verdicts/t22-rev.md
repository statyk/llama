### Spec Compliance
- ❌ Issues found:
  - CLAUDE.md:645, the "Open, awaiting operator rulings" clause advertises a change nobody has ruled on ("count only positions C itself confirmed") and presents behaviour at HEAD as pending. Important #1.
  - CLAUDE.md:645 says C-1 "is measured to fire on darkstarorchestra-2014-07-31 only". The signature fires on 4 shows; it demotes on that one only. Important #2.
- Present and in the right place:
  - The Architecture bullet sits directly after the taper-markers bullet.
  - The Commands bullet sits after the replay_holds compare bullet.
  - Everything the plan requires is there: title_inputs/title_cascade, D, readers (i)/(ii), the slice-1 split, S/Q1, C/C1/C2/C-1, slice 4, slice 5, Q2 plus the replay relaxation, the constants, "dropped: nothing", the ruling-5 cosmetics, and every limitation the brief names.
  - The commit touches only CLAUDE.md and the SDD dir; `git show --stat f28c343 -- packages scripts` is empty. No protected name is edited (docs only).
- ⚠️ Cannot verify from diff:
  - t22's own handback (and this review) are not in `verdicts/`. They were written after the commit. The orchestrator should copy them when it re-syncs the orch-r3 ledger at the finish.
  - Example-show track facts were traced to the SDD handbacks and acceptance.md, not re-measured: newmastersounds #5, MMJ #14, deadandcompany-2016-07-15, elliottsmith-1997-05-15, GY!BE 2000-10-30/31, rosehilldrive `07-8th Wonder`.

### Strengths
Checked against the code at HEAD (f28c343), with quick probes where noted:
- **C-1** matches `lossless_titles.py:233-249`:
  - the signature needs at least 2 delivered real tags that disagree at their own position and agree at ±1;
  - every changed position stays;
  - real, non-filler tags that disagree at their own position are demoted;
  - the note text is `demoted_note`;
  - the override undo is `gather._without_override_positions` (stages/gather.py:1214-1235).
- **C scope.** `in_scope` is `format_titles is None and title_fraction(...) >= _RECOVER_BELOW` (gather.py:1262).
- **Show-level skip and C2 candidates** match (lossless_titles.py:160-189, 206-212).
- **D readers:**
  - Reader (i) checks contiguity, allows a header or disc-change restart, and uses the R16 encore grammar (desc_list.py:193-269).
  - Reader (ii) checks each line separately (desc_list.py:323-382).
  - (i) is preferred (desc_list.py:385-392).
  - A probe confirms Checkpoint A (a): a `1,2,4,5` list is "non-contiguous" in (i) but admitted by (ii).
- **Check 1** scope split and order match `title_hygiene.judge` (title_hygiene.py:109-153).
- **Cleaning order** matches desc_list.py:76-138.
- **`is_junk_tag`** returns True for `2:45 AM`, `09-15-00`, `12.28.99`, `12-28-99` and `2:22`, and False for `J`, `420` and `M80` (probe).
- **Slice 5:**
  - `4:20 Polka`, `8 Cylinders`, `1 Samuel 15:23`, `E: …`, `S2:` and `set1:` are untouched (probe).
  - It runs after every flag, before `Show` (gather.py:2014).
  - `STRIP_SOURCES` matches the list in the bullet.
- **Q2:** `elif today_llm and not cascade.self_filled` (gather.py:1745); `is_self_filled` (title_hygiene.py:462-472).
- **Replay:** `replay.py:333-336` and 540-549. The cascade is also recorded on needs-LLM rows.
- **Taper:** `taper._counts` excludes `TAUTOLOGICAL_TITLE_SOURCES` (taper.py:644), and `test_taper_never_owns_a_self_filled_tape` exists.
- **Sets:** `TAUTOLOGICAL_TITLE_SOURCES` includes `desc-position` (structure.py:1154); `siblings.INDEPENDENT_TITLE_SOURCES` is unchanged (siblings.py:363).
- **Column width:** the 14-character column is at cli.py:1583-1591.
- **Constants** match title_hygiene.py:42-48.
- **Commands claims:**
  - `--strip-title-overrides` strips `TITLE_KEYS = ("titles",)`.
  - `--disable-slices` refuses names outside `ENABLED_SLICES` (replay_holds.py:155-162) and stamps `disabled_slices`.
  - Apply lists are suppressed (replay_holds.py:1350).
  - The probe's subcommands are dump/gate/parity/packets, and its docstring says dump is PRE-WIRING only (title_hygiene_probe.py:22-27, 2048-2066).
- **Measured numbers** match acceptance.md:
  - 7/40 cleared and 14/15 added (:64-67);
  - 0/900 and lotus, met at 1 (:208-224);
  - kinggizzard 12/13 → 10/13, and 6/9 shows (:107; kg-why/handback.md:6-9);
  - "Dropped: nothing" matches Checkpoint A ruling 1.
- **SDD record:**
  - The orch/orch-r1/orch-r2 ledgers and all five checkpoint/minors files are byte-identical to their sources (`cmp`). orch-r3's copy is a byte prefix of the live ledger, as the README says.
  - Every $D task dir that has a handback.md has an identical `verdicts/<task>.md`, except t22 itself (above). No verdict lacks a task dir.
  - 89 files, 767,892 bytes, all `.md`. None is over 256 KB and no source tree was copied.
  - The README follows the piece-2 model, including "Dropped from the record".
  - The commit body states docs only and no suite run, and carries the exact trailers.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **CLAUDE.md:645, the "Open, awaiting operator rulings (each is one clause; edit that clause alone when ruled)" passage: it advertises a proposal and frames behaviour at HEAD as pending.**
   - The text "(C-1) a possible narrowing of what counts toward the shift signature (count only positions C itself confirmed)" names a change that has not been ruled on. The "edit that clause alone when ruled" instruction is process text, not a description of the code.
   - **Why it matters:** CLAUDE.md is what later sessions trust about the code. A sentence advertising an unruled change can be read as the plan of record. This review's brief names exactly this as a finding.
   - **Fix:** describe HEAD only, keeping each clause separately editable.
     - (a) A C-1 limitation clause: "the signature is symmetric: it cannot tell delivered tags shifted against a right reference from a reference shifted against right tags; a synthetic case (fixwave-rr Important #1) ships wrong titles unflagged; no library show is known to carry it."
     - (b) The C2-and-coverage clause as written, minus the "awaiting" framing.
     - Both can sit under Accepted limitations, or under a "Known open limitations" lead.
     - Drop the proposal parenthetical and the edit instruction.
2. **CLAUDE.md:645 says C-1 "is measured to fire on `darkstarorchestra-2014-07-31` only (fresh-get view; …)". That is wrong as stated.**
   - The signature holds on 4 shows: darkstarorchestra-2014-07-31, lettuce-2002-07-13, tedeschitrucksband-2019-02-15 and tedeschitrucksband-2020-01-15. Sources: $D/fixwave/handback.md, "Re-measure of the four signature shows"; acceptance.md:193, "the 4 C-1 signature shows".
   - C-1 demotes only on DSO-2014, fresh-get view, #3 (acceptance.md:254, :274). On the as-is view #3 is an operator override, which C-1 never demotes.
   - **Why it matters:** anyone weighing the pending narrowing, or reasoning about C-1's reach, gets the wrong population.
   - **Fix:** "demotes on `darkstarorchestra-2014-07-31` only (fresh-get view, #3; on the as-is view #3 is an operator override); the signature also holds on lettuce-2002-07-13 and two tedeschitrucksband shows, where every unconfirmed tag already agrees at its own position, so nothing is demoted".

#### Minor (Nice to Have)
3. **CLAUDE.md:645, C1 "adopted when it agrees … or else when `MIN_ANCHORS` comparison stems agree".** This reads as per target. In the code, if ANY target fails (a), (b) and (c), C1 fills nothing on the show (lossless_titles.py:196-203; plan Global Constraints, "if any target fails all three, C1 fills nothing"). Add "; one target failing all three declines every C1 fill on the show".
4. **CLAUDE.md:645, C-1 "(`unresolved`; the hold, D or the gated S rung then decides)".** Every later rung can fill a demoted position: sibling-align, setlist-gap, 2a, slice 4, D and deferred S. setlist-gap is exactly how the fixwave-rr reproduction ships 5 wrong titles. Say "every later rung (sibling-align, setlist-gap, 2a, slice 4, D, deferred S) sees it as unresolved".
5. **CLAUDE.md:645, "Never taken: a bracketed lossless tag".** The veto is for a WHOLLY `[...]` tag only (`_BRACKETED.fullmatch`, lossless_titles.py:67, 110). `Foo [live]` is taken. Say "a wholly `[...]` lossless tag".
6. **CLAUDE.md:645, slice 4 "the core (at least `STEM_SUBSTRING_MIN` = 2 characters) is not a substring of the file stem".** This reads as a length requirement. In the code the stem test applies only when the core has at least 2 characters (title_hygiene.py:657), so a one-letter `J` skips it. Reword: "a core of at least 2 characters must not be a substring of the file stem".
7. **CLAUDE.md:645, "the untagged residual (…; sample 0 of 34)".** The spec's "0 of the 34" counts untagged-check firings on right shows (spec lines 245, 258), not residual failures. The residual's evidence is "the sample had 0 such failures" (spec, class U) and gate R12 (8 residual shows, 0 bad). Cite one of those.
8. **CLAUDE.md:645, "Harness: … (below, Commands)".** `## Commands` (line 16) is ABOVE the Architecture section (line 430). Say "above".
9. **CLAUDE.md:645, "0 of 900 automatically filled or replaced tracks".** The pooled 900 includes 355 slice-5 strips and 3 changed-no-path tracks (acceptance.md:208-216). Say "0 of 900 changed tracks (fills, replacements and slice-5 strips)".
10. **CLAUDE.md:645, bullet length.** It is 13,454 bytes against the taper bullet's 4,067, and CLAUDE.md loads into every session. Consider trimming detail that the spec and plan already hold: the S-plan mode list, the full check-1 vocabulary and the cleaning list. Most of the content was brief-mandated, so this is optional.
11. **docs/superpowers/2026-10-23-title-hygiene-sdd/README.md:5, "every other reviewer was Opus".** The Checkpoint B hand-check checkers cpb-k01..k13 and u4check were Sonnet (orch-r2 ledger:53, 57, 59, 105; orch-r1 ledger:32). The spec/plan reviews also had a Fable seat. The phrasing came from the brief, but adding "hand-check checkers: Sonnet" would make it accurate.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** Most of the bullet's claims check out against code and acceptance.md, and the SDD record is clean and byte-faithful. Two accuracy defects should be fixed before every later session reads them as fact: the pending-ruling clause advertises an unruled proposal, and C-1's "fires on DSO-2014 only" is wrong (it demotes there only; the signature is on 4 shows).
