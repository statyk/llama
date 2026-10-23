### Spec Compliance
- ❌ Issues found:
  - **Ablation view (R1) does not compare `all` with `all-<slice>`.** The brief says R1 is computed "from all vs all-<slice>". `Gate.attributed` (diff L742-760) adds a position whenever it carries a path token **from the `all` arm**: `toks = _tok(_path(r, i)) if arm == "all"`, and `if p == q and not toks: continue`. The ablation call `g.attributed(r, f"all-{s}", "all")` (diff L882) passes `arm="all"`, so every slice's ablation row counts every path-tokened track in the library, including tracks where `all` and `all-<slice>` are identical. See Important 1.
  - **R5 "ships silently" counts shows that did not change** (same root cause), and so does R1's "newly held vs today (path)" show count. The brief defines a changed track as one whose `all` title or source differs from `today`. See Important 2.
  - **Judged and inferred results are pooled**, against the brief ("reported separately, never pooled with judged"). This happens in the removed-fill table and in the "wrong+inferred / tracks" column. See Important 3.
  - **The R2 slice-1 bar is compared against the wrong population** (shows that lose fills instead of shows that are held). See Important 4.
  - **R11 includes shows with no D fill.** It is meant to report consequence (1) of D's denominator effect. See Important 5.
  - Ruling (d): `is_q1_decline` (diff L636-640) tests `declined or notes`. The ruling asks for a non-empty declined list only. It makes no difference on this dump (Minor 1).
- ⚠️ Cannot verify from the diff:
  - The suite counts (4697, then 4706 passed). I did not re-run the suite, per the rubric.
  - The dump re-run itself. I did check what it left behind:
    - `_meta.sha` is `f750d7d`.
    - All 3983 rows have `gate0` and `gate0_as_is` True.
    - All 2983 `alt_bracketed_s.applies` rows carry `remain_both_sides`.
    - All 118 C2 rows have `strict` True and `containment_only` False, so note 6 = 0 holds.
- Global Constraints: I grepped the diff for every protected name. The only hits are an import of `LOOSE_TITLE_RATIO` and a comparison against it (diff L343, L398). Nothing protected is edited.
- Requirement (a) is met. `remain_both_sides` (diff L373) is exactly `gap_span` minus its leading-edge branch. I read `structure.gap_span` L1346-1352 to confirm: `lo-1 ∈ anchors` is false at lo=0, and `hi+1 ∈ anchors` is false at hi+1=n. `containment_only` matches the definition given (diff L396-399). The dump summary uses `gate0_failures` (diff L449-461).
- Requirements (b), (c) and (e) are met. R0 treats None as failing (diff L785). R4 reports both variants (diff L1042-1076). The Notes section has all nine notes and comes after R19, which the test checks.

**Headline numbers I re-checked independently from the raw dump and hand-check rows** (scratch scripts in `~/.llama-harness/piece3/scratch/t14-rev/`):

| Check | Result |
|---|---|
| R0 | 3983/3983 in both views (every row is (True, True)) |
| R2b | 155 chosen-canonical S fills today |
| R5 Q1 | 32 shows, 510 declined tracks (0 rows have `notes` without `declined`) |
| R9 | 7 `agreement` shows (charliehunter-2004-05-22, dalewatson-2009-08-02, eotoband-2007-10-09, fishbone-2011-02-27, both godspeedyoublackemperor 2000-10-30/31, soulive-2012-02-24) |
| R13 | 40 / 38 / 2 |
| R1 removed S fills | 503 = 336 judged right + 118 judged wrong + 26 cant-tell + 15 unjudged + 8 **inferred** wrong |
| Ablation | true per-slice diffs (below) |

On R13: 12 of the 50 U shows fall out because neither reader now yields an admissible list. whitedenim-2013-07-04 also falls out: it is no longer wholly untagged. That is consistent with the Definitions predicate.

### Strengths
- `HandCheck.judge` (diff L539-556) follows the brief.
  - "Judged" means the candidate equals the new title by `fuzzy_norm_title` after `clean_one`. `right-partial` counts as right.
  - Otherwise the result is inferred from a non-null `correct_title` via `agrees`, else unjudged.
  - Hand-check classes are respected.
- Verdict groups are kept in their own columns (diff L492-508). Neutral and cant-tell are never folded into good or bad. Every show verdict in the real hand-check rows is a known value, so nothing falls through to cant-tell by default.
- Removed fills are scored separately, on the title they removed (diff L754-755, L762-772). They are not mixed in as shipped titles of the wrong kind. That was one of the named risks, and it is handled.
- R4 and R14-R17 and the notes read `alt_*` fields and records only. Note 3a's `?` sample confirms check 1 lets `?` through, which is expected: `?` is a per-track slot-placeholder decline, not a hygiene decline.
- R0 reports both views separately. As a sanity check, the held approximation on arm `none` matches today's flags on every show (0 mismatches).
- The tests run on a real fake dump through `main([...])` and cover rulings (b) and (d) and the order of the headings.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The ablation rows of R1 are mis-scored. These are the operator's keep/drop input.**
   - **Where:** `scripts/title_hygiene_probe.py`, `Gate.attributed` (diff L751-752) and the ablation loop (diff L879-887).
   - **What's wrong:** every slice's ablation row reports 1221-1235 tracks, which is every path-tokened track. The true `all` ≠ `all-<slice>` fills are much smaller:

     | Slice | Counted | True diffs | True score |
     |---|---|---|---|
     | slice1 | 1235 | 171 | 107 judged right, **1** judged wrong, 35/4 inferred, 24 unjudged |
     | slice2 | 1235 | 483 | 390 judged right, 0 wrong |
     | slice3 | 1221 | 254 | — |
     | slice4 | 1221 | **22** | 2 judged right, **0** judged wrong |
     | slice5 | 1221 | 422 | — |

   - **How the table misreads:**
     - slice1 shows "6 judged wrong, 3.5%". Five of those six are S fills that are identical in `all` and `all-slice1`.
     - slice4 shows "1 wrong of 5, 20.0%". That wrong track is not a slice-4 fill; it is another path's track on a show with A_rev rows.
     - The implementer's concern "slice 4's 1 wrong of 5 judged" is therefore an artifact of this bug. Under the operator's 2026-10-23 framing (drop a small-yield slice in favour of an adjudicator), this row would push toward a wrong ruling.
   - **Fix:** in the ablation, keep only positions where `_titles(r, f"all-{s}")[i] != _titles(r, "all")[i]`. For example, give `attributed` a `use_paths` flag, or iterate `changed_positions`. Add a test where `all-<slice>` is a copy of `all` and assert that the ablation counts 0 tracks. The current fixture already deep-copies the arms, so the assertion is all that is missing.

2. **R5's per-slice "ships silently" and R1's "newly held vs today (path)" show counts include unchanged shows.**
   - **Where:** diff L1101-1103 and L892-896.
   - **What's wrong:** both use `attributed(r, "today")`, which picks up S fills identical to today.
   - **Effect:** slice1 reports 92 changed shows, 41 unheld today. Counting only shows with a slice-1-attributed track that actually differs from today gives **48 changed, 15 unheld**. The other slices are unaffected (34/63/16/27 all have real changes).
   - **Fix:** the same as item 1. "Changed" must mean the title or source differs from `today`, per the brief.

3. **Judged and inferred results are pooled.**
   - **Where:** `score_removed` (diff L762-772) and `score_cells` (diff L737, L740).
   - **What's wrong:**
     - `score_removed` throws `kind` away, so the headline "was wrong (benefit) 126" is 118 judged plus 8 inferred.
     - The column "wrong+inferred / tracks" pools them by construction.
   - **Why it matters:** the brief requires inferred results to be "reported separately, never pooled with judged". Pooling them is one of the named risks.
   - **Fix:** split the removed table into judged right / wrong / cant-tell, inferred right / wrong, and unjudged. Drop the pooled column. If kept, it must never sit beside the ≤2% preview.

4. **R2 compares the slice-1 bar with the wrong population.**
   - **Where:** diff L949-964.
   - **What's wrong:** R2 prints "good shows that lose S fills: … other 7 (the bar allows 2)". The Acceptance-4 bar is "slice 1 **holds** no more than 2 hand-checked-good S shows". Of those 7, only 3 are newly held: gomez-2008-07-05, lotus-2010-06-10 and steepcanyonrangers-2004-05-21 (per `samples/r2_s_good_lost.txt`). The other 4 were already held or remain unheld.
   - **Why it matters:** the implementer's handback carries "7 > 2" forward as a bar failure. The bar does fail either way (3 > 2), but by a different margin.
   - **Fix:** report the bar on newly held, non-Q1, good S shows. Keep "lose S fills" as a separate, labelled line.

5. **R11 attributes non-D coverage changes to D.**
   - **Where:** diff L1210-1236.
   - **What's wrong:** R11 takes every show with today's low-confidence flag that is now self-filled or covered. 32 of its 52 shows have **no D fill**: their coverage rose through C1/C2 (e.g. darkstarorchestra-2012-10-13, lettuce-2002-07-13), slice 4 (thenewdeal-2006-12-13) or `+5` strips (seven moe shows, ratdog-2008-04-11).
   - **Why it matters:** the section title and the spec item are about consequence (1), "newly unflagged by D-filled tracks leaving coverage's denominator". As written, the table reads as 52 D-caused unflaggings.
   - **Fix:** restrict the denominator-size table to shows with D fills (20), or split it into D and non-D columns.

#### Minor (Nice to Have)
1. `is_q1_decline` (diff L640) uses `declined or notes`, but ruling (d) asks for a non-empty declined list. It has no effect here: 0 rows have notes without declines, and the count is 32 either way. Drop `or notes`, and add a case with notes but no declines to `test_q1_declines_need_a_non_empty_decline`.
2. R4 "good shows it would hold" (diff L1066-1067) includes shows that are already held in `all`. derektrucksband-2004-11-20 is held, and so is beneventorusso-2005-08-27 (both-sides variant). The true counts are 2 (gap_span) and 3 (both-sides), against the reported 3 and 5. Intersect with `not g.held(r)`, as "holds added" already does.
3. R1's path view counts the 59 S fills that are identical to today (judgement call 1, labelled in the table). So "S 8.8%" is S's residual (it still ships 5 wrong of 57), not wrong titles that slice 1 adds. Add one line to the table saying so; otherwise the operator may read it as slice-1 damage.
4. The code reaches into a private function across modules: `title_hygiene._short_core` (diff L398-399). The test file has a mid-file `import copy  # noqa: E402` (diff L62). `build_gate` calls the row builders as tuple expressions (diff L1552-1553). These are polish.
5. Note 4's `LEAD_NUM_RE` also matches dates (`12.28.99`, 3 of its 4 hits). This is acknowledged and the hits are listed, but say so in the note text itself.
6. No test pins the ablation semantics, the "changed" semantics or the judged/inferred split of removed fills. Each of Important 1-3 would have been caught by a fake dump where `all-<slice>` equals `all`, or by a removed track judged only by inference.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The dump fix is correct and every alternative row reads the dump, but R1's ablation rows (slice1 3.5% instead of about 0.9%, slice4 20% instead of 0 wrong), R5's slice-1 ships-silently count (41 instead of 15), the pooled judged/inferred results, R2's bar population and R11's attribution would each steer a Checkpoint A ruling. All five come from three small fixes: compare against the reference for "changed", keep `kind` in the scoring, and count newly held / D-filled shows. After the fixes, the gate should be re-run before Step 6.
