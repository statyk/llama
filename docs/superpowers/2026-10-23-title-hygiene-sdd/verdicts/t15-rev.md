### Spec Compliance
- ✅ Spec compliant against the orchestrator's resolution of P1, P2, R16 and (h). There is one ruling-scope question to escalate (Important #1) and one place where P1 and P2 disagree with each other (Minor #1).
- ⚠️ Cannot verify from diff:
  - The commit messages are not in the package, so I can't check that each names its test command. The task produced 3 commits. The brief's Global Constraints say "one commit per task", while the dispatch mandate says to commit incrementally. Treat this as a process note only.
  - The suite count (4717 passed, 1 skipped, 8 deselected) and the RED runs come from the implementer. I did not re-run them, per the rubric. I reasoned each new test against the pre-change code (below), and each one fails there.

Protected names: the diff touches none of the Global Constraints' protected names. `setlist.py` is untouched. `taper._ENCORE_HEADER`, `_SET_HEADERS` and `_DISC_LABEL` are read but not edited. `titles.py`, `structure.py`, `siblings.py` and `gather.py` are not in the diff.

Named risks, one focused check each:
1. **P1 scope.** `title_hygiene.py:181-182`: only `_QUESTION_ONLY` on the cleaned text is neutral, after the independent-source skip. I probed `position_agreement` with a `tags` track. `???` and `E: ?` (cleaning strips `E:`) are neutral. `Unknown`, `Track 03`, `II: ?`, `Set 2: ?` and `2: ?` still disagree. 2b vocabulary and `unknown` are not made neutral, so check 3 is not weakened beyond the ruling.
2. **P2 never touches shipped text.** `_SET_PREFIX` is used only inside `judge`'s slot-placeholder condition (`title_hygiene.py:110-111`): `.sub(..., count=1)` feeds a `match` and nothing else, and `c.text` is unchanged. It only adds a per-track decline (ok → slot placeholder), never an acceptance.
3. **R16 admits only lone encore lines.** `desc_list.py:177`'s pattern is anchored `^…$`. Probes on `read_numbered`:
   - `Encore: Bertha` then a restart: still `non-contiguous at 1`.
   - `Notes:` then a restart: `non-contiguous at 1`.
   - `Encore 2:` needs the flag (pinned at `test_desc_list.py:131-134`).
   - Effect on gather: the new default `encore` kind also adds an `encore` block when numbering continues across a lone `Encore:` line. `block_size_mismatch` folds encore blocks by default (`title_hygiene.py:290-293`; gather never passes `fold_encore=False`), so gather is unaffected. Only R10's alternative count moves (52 → 61, as reported).
4. **(h) leaves adoption untouched.** `lossless_titles.py:207-214`: the strip happens in the final loop over the already-decided `changed`. Every comparison still uses `lossless[i]` unstripped. Probing also shows `fuzzy_norm_title` and `agrees` already ignore these markers (`'Dark Star->'` → `'dark star'`), so stripping earlier could not have changed a decision either. The fallback to the unstripped title on an empty result is present. The pattern is the plan's single `desc_list._TRAIL_MARKERS`, not a fork.
5. **The dump on disk.**
   - `~/.llama-harness/piece3/gate/dump.jsonl` sha256 is `1e7f3054…d791`, matching the report. `_meta.sha` is `89fd787…` (HEAD).
   - Rows: 3983. `gate0` is true on 3983 and `gate0_as_is` is true on 3983.
   - `gate_table.md` sha matches the report, and `untagged_unchecked.txt` is 0 bytes.

### Strengths
- Each change is minimal and sits exactly where the resolution put it. P2's prefix is confined to one boolean test (`title_hygiene.py:110-111`). The R16 default needs no probe change, because `alt_encore_restart` now measures what the broader form adds (`scripts/title_hygiene_probe.py:436-443`).
- The (h) strip reuses the one constant and runs after the adoption decision.
- Each new test fails on the old code, by reasoning against the pre-change code:
  - P1: `test_title_hygiene.py:141-148` (old code returned `disagree` for `???` vs `Mix`).
  - P2: `test_title_hygiene.py:43-49` (old `judge("II: ?")` was not a slot placeholder).
  - R16: `test_desc_list.py:127-143`. Old code made `Encore:` a header only under the flag, so the default gave `non-contiguous at 1`. The moe-2009-02-27 excerpt keeps the taper's `Alnouncements` typo, so it is verbatim.
  - (h): `test_lossless_titles.py:373-382` (old code shipped `Dark Star->`).
- The measured effects check out against the checkpoint-a copy:
  - gomez-2008-07-05 drops off R2's newly-held good list, so the R2 bar of 2 is met.
  - ericmcfadden-2005-10-06 t12 becomes a per-track decline.
  - The C1 trailing-marker sample falls from 22 items to 0.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **R16 admits 4 of the 7 count-matched lists the operator expected. This needs escalation, not a code fix.**
   - Where: `desc_list.py:177` (`_ENCORE_ONLY_LINE`).
   - The ruling reads: "(`Encore:`, `Encore`, `E:`, `Enc:` alone on its line) is ALLOWED … Checkpoint B hand-checks the **7** count-matched lists this admits." That 7 was measured with the broader `taper._ENCORE_HEADER` form.
   - The narrow lone-line form follows the orchestrator's resolution and the ruling's literal parenthetical, but admits only 4 count-matched lists: furthur-2010-02-06, moe-2009-02-27, moe-2009-04-04 and thedead-2009-05-02. It also admits 5 non-count-matched ones: discobiscuits-2006-02-04, gratefuldead-1980-05-10, moe-2009-01-30, robynhitchcock-2009-03-21 and soundtribesector9-2008-07-23. I confirmed all 9 read `admitted` by default in the new dump.
   - Three count-matched lists stay blocked. Their encore lines read:
     - assemblyofdust-2004-12-31: `Encore 1:` and `Encore 2:`
     - mogwai-2006-04-25: `(encore)`
     - railroadearth-2005-08-20: `Encore: Disc 3: `
   - maxcreek-2009-01-31 (`Encore - Disc 4/end of disc 1:`) is also still blocked, but is not count-matched.
   - Why it matters: the operator's acceptance assumed 7. Whether the parenthetical is exhaustive or only examples is an operator call. The current reading is the conservative one.
   - Fix: the orchestrator reports the 7 → 4 difference and the three line shapes to the operator, and keeps the narrow form unless the operator rules otherwise.
2. **The gate no longer lists the lists R16 admits, which is Checkpoint B's hand-check population.**
   - Where: `scripts/title_hygiene_probe.py:1530-1540`, and `gate_table.md` R16 ("Lists blocked only by an Encore-header restart: 4 show(s)").
   - The row now lists the shows the ruling did NOT admit. Its title and wording describe the pre-ruling situation, and the 9 newly admitted shows appear in no gate row or sample. They can be recovered only by diffing against `checkpoint-a/samples/r16_encore_restart.txt`, which is how I got the list in #1.
   - Why it matters: the ruling makes Checkpoint B hand-check them, and a stale heading invites misreading.
   - Fix: either the orchestrator records the 9 (4 count-matched) names from #1 for Checkpoint B and relabels R16 in its record as "what the broader encore form would add", or the probe adds that heading plus a sample of lists the default admits through an `encore` boundary from a restart. The first is enough for this task.

#### Minor (Nice to Have)
1. **P1 and P2 define "slot placeholder" differently.**
   - Where: `title_hygiene.py:110-111` vs `:181-182`.
   - `judge` treats `II: ?` as a slot placeholder (P2), but `position_agreement` tests `_QUESTION_ONLY` on the cleaned text without the P2 prefix strip. So `II: ?`, `Set 2: ?` and `2: ?` against an independent tag are a check-3 `disagree` (probed), which is a show-level decline.
   - Read together, the operator's P1 ("a slot-placeholder entry … is NEUTRAL") and P2 ("`II: ?` is a per-track slot-placeholder decline") suggest it should be neutral. The orchestrator's resolution scoped P2 to "the `?`-only test", which is ambiguous here.
   - Measured population is empty: 0 set-prefixed `?` entries across the 1236 admissible lists used in the new dump.
   - Fix (optional): a module helper `_question_only(text)` that applies the one-prefix strip, used at both sites, plus a test. This also removes the two divergent copies of the test.
2. **No test pins the edges of P1 and R16 (named risks 1 and 3).**
   - Where: `test_title_hygiene.py`, `test_desc_list.py`.
   - A mutant that widened P1's neutral to `is_placeholder`/`_UNKNOWN` would not be caught: no check-3 test asserts that `Unknown` or a 2b tag (`Track 03`) entry still disagrees.
   - No test asserts that a restart after `Encore: Bertha` (encore line with a song) stays `non-contiguous`.
   - Fix: add two one-line asserts.
3. **The (h) decline note still prints the marker.** `lossless_titles.py` (C1 decline note, the `c1_notes` line above the diff's hunk) prints `lossless[first]` unstripped, e.g. `(track 4 'Dark Star->')`. That is consistent with "the C note uses the stripped title" only for the change note. Notes only, no shipped effect.
4. **(h) test case.** `test_lossless_titles.py:373-382` uses constructed `_dl(*names)` rather than the darkstarorchestra-2012-10-13 description excerpt. The comment cites the slug, but the brief's real-case rule asks for the verbatim excerpt. Low value either way.
5. **Extra blank line.** `test_lossless_titles.py` ends with a trailing blank line (W391), the diff's final `+` line.

### Assessment
**Task quality:** Approved
**Reasoning:** All four rulings are implemented as the orchestrator resolved them. Each is pinned by a test that fails on the old code, the protected names are untouched, and gate 0 is 3983/3983 on both views on disk. The two Important items are for the orchestrator to escalate or record, not to send back as code fixes: R16 admits 4 of the operator's expected 7 count-matched lists, and Checkpoint B's R16 population is no longer listed by the gate.
