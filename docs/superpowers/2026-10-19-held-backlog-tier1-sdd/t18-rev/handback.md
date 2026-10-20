### Spec Compliance

- ✅ Spec compliant (5c.1, 5c.2, 5c.3, the two `compare` subsections, and rulings M1, B5 and the notes routing), with one test gap on the routing ruling (Important #1 below).
  - 5c.3 / M1: `jerrybase.py:58-66` checks the unfolded exact and fuzzy tiers first (`_match_tiers` with an identity fold behaves exactly like the old code). The fold tier runs only when both come back empty. `test_closer_matching_preserves_a_leading_parenthetical` is byte-identical (diff lines 303-308). The fallback test is at test_jerrybase.py diff 334-346, and mutant (f) is caught.
  - "Zero anchoring changes on shows that already anchored" holds by construction. A show that anchors today found a candidate for every closer in the unfolded tiers, so the fold tier never runs for it and `anchor_breaks` sees the same candidate lists. 5c.2 runs only when `anchored is None` (`gather.py:1269`). `_resolve_positions` and `anchor_breaks` are untouched.
  - 5c.1: the excusal is at `jerrybase.py:120-125`, with no hard flag and no soft note. `filler_tail_closers` uses the Contracts text verbatim (plan line 77). In gather it goes to `op_notes` only (`gather.py:1467`).
  - 5c.2: `anchor_numbered_sets` (`jerrybase.py:169-218`) has the right preconditions: at least one numbered row and one encore row, every encore closer absent, every numbered closer with exactly one candidate, positions strictly increasing. The Contracts text is verbatim (plan line 78). In gather the labels feed the existing anchoring branch: `alignment="jerrybase"`, "set breaks anchored from jerrybase" (+ " (was ...)") goes to the local `notes`, the LLM `elif` is skipped, and the 5c.2 note goes to `op_notes` (`gather.py:1274-1279`).
  - B5: "Casey Jones" replaces "JBG" (test_jerrybase.py diff 362-373).
  - Do-not-retune: structure.py, songs.py and titles.py are not in the diff. `is_filler` is imported, not changed (`jerrybase.py:33`). Checked against the diff's file list.
- ⚠️ Cannot verify from the diff:
  - The spec's 5c.2 wording also allows "encore ... where they match the encore row's songs". The brief and the code leave this out. It is vacuous today: jerrybase stores only the closer, and the precondition requires that closer to be absent. The controller should confirm the omission is intended.
  - `_short_track_arm` and `_second_closer_candidates` read the stored library `show.json` under the cand root, not the replayed tracks. The brief specifies this. If replay changed titles or labels, a row could disagree with the cand flag it is paired with. Checkpoint F readers should know this.

### Strengths
- M1 is implemented cleanly. The `_match_tiers(tracks, closer, fold)` refactor keeps the unfolded tiers byte-equivalent and computes each component once instead of twice. The docstring at `jerrybase.py:61-65` records why the fold is a fallback.
- 5c.2's labelling loop mirrors `anchor_breaks` exactly (`jerrybase.py:200-205` vs `anchor_breaks`' `si` loop), so the numbered portion cannot drift from today's anchoring semantics.
- The mutation work is sound. Two predicted survivors, (c) and (e), were turned into tests that target the gap (`test_5c2_declines_when_the_numbered_closers_are_out_of_order`, `test_5c1_filler_tail_note_goes_to_notes_json_never_to_structure_conflicts`), and the cands[0]/cands[-1] reasoning for (b) is correct.
- The replay rows test (`scripts/test_replay_holds.py` diff 589-616) pins row content, the distinct-show count, and the 420 s boundary in both directions.
- Superset property of `5c.3 second closer candidates`: if neither the closer nor any candidate starts with a parenthetical, the fold is the identity on them, so the unfolded tiers would already have matched. The subsection therefore really is a superset of the shows where the fold created the second candidate.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. `gather.py:1278-1279` — routing of the 5c.2 note to `notes.json` is untested. The only gather-level 5c.2 test (`test_5c2_anchors_the_gd73_tape_when_only_the_encore_row_is_missing`, test_stage_gather.py diff 405-417) ends with an `encore` label, so `numbered_note` is `None`. `grep -rn "numbered sets (encore\|anchor_numbered_sets"` outside test_jerrybase.py finds nothing. A mutant that changes `op_notes.append(numbered_note)` to `notes.append(numbered_note)` would survive and send the note into `structure.conflicts` and the briefing LLM. That breaks Global Constraint "Notes never reach the LLM" (ruling 6) and the orchestrator's notes-routing ruling, and it is the 5c.2 twin of mutant (e).
   - Fix: add a gather test whose deterministic alignment does not label the last track `encore`. For example, monkeypatch `gather_mod.align` or strip the fixture's encore marker so the trailing tracks stay in set 2. Assert the Contracts 5c.2 string is in `res.notes` and not in `res.show.structure.conflicts`, then flip that mutant.

#### Minor (Nice to Have)
1. `jerrybase.py:142-158` — `_filler_excused` re-implements `closer_contradictions`' loop: the `breaks` set, `last_index`, the single-candidate test, the not-at-a-break test and the filler test. The two must agree; today only `test_5c1_closer_followed_only_by_filler...` pins that they do.
   - Fix: have `closer_contradictions` compute the excused list through one private helper that returns `(hard, soft, excused)`. The public signature stays the same.
   - Similarly, `scripts/replay_holds.py:542-546` re-walks the set tail that `_followed_only_by_filler` walks (`jerrybase.py:134-138`). A shared `_set_tail(tracks, i)` would remove the copy.
2. `jerrybase.py:207-211`, concern (1) — the trailing-run encore labelling departs from the brief's per-track wording. Verdict: acceptable, and better than the brief.
   - It labels a subset of the tracks the per-track rule would, so it still never invents an encore.
   - It rules out "encore" followed by a set-N track, and it starts at `last + 1`, so the final numbered set is never consumed.
   - The `stay` count (`:212`) stays consistent with the labels.
   - Record it in the ledger as an accepted deviation.
3. Concern (2), more holds — accepted; it follows from the spec. Spec 5c.3 says "on both the closer and the track side", and the brief puts the fold in `_closer_candidates`, which `closer_contradictions` also uses. A closer that had no candidate (soft note) and now has one folded candidate away from a break becomes a hard flag. That flag is the tripwire working with better matching, not a defect.
   - Measured reach: in `jerrybase._load()` only 2 of 564 distinct closers start with a parenthetical: "(I Can't Get No) Satisfaction" ×29 and "(I'm A) Road Runner" ×14.
   - Checkpoint F's `flags.txt` should show any such additions under `structure`. The controller should tell the operator to look there, because neither 5c subsection lists them.
4. `jerrybase.py:81-82`, concern (3) — the fold strips a parenthetical only at the start of the whole title, so a merged track's last component is not folded. Accepted as a narrow gap.
   - The jerrybase data has a bare "Satisfaction" closer ×21. A tape track "Jam > (I Can't Get No) Satisfaction" therefore still misses that closer. I checked: `title_components` gives `['jam', 'i cant get no satisfaction']`, and `fuzzy_title_eq('i cant get no satisfaction', 'satisfaction')` is False.
   - The opposite direction works: a closer "(I Can't Get No) Satisfaction" against a tape "Jam > Satisfaction" folds the closer and matches.
   - Literal to the brief. A later tier can fold per component.
5. test_stage_gather.py diff 430, concern (4) — the monkeypatched `jerrybase.is_filler` is acceptable. The test checks routing. The real predicate is exercised unpatched by `test_5c1_closer_followed_only_by_filler...` with "Tuning"/"Crowd". The patch targets jerrybase's own imported name, so `structure.is_filler` is untouched for the alignment and coverage code.

Checks run:
- Crash risk: can the fold produce an empty title that crashes `[-1]` or matches everything?
  - `title_components('')` and `title_components('()')` return `['']`, so `[-1]` does not crash.
  - `fuzzy_title_eq('', 'satisfaction')` is False.
  - No jerrybase closer folds to empty (scanned all 564 distinct closers), so a wholly parenthetical track such as "(tuning)", which folds to "", cannot exact-match a closer.
  - No crash and no catch-all match.
- Interpreter: `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves inside the worktree, so these checks ran against the code under review.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The 5c logic is correct and the "already-anchored shows never change" guarantee holds by construction under M1. However, the 5c.2 note's notes.json-only routing, a binding ruling and a global LLM-isolation constraint, has no test that can fail. One small gather test plus that mutant closes it; the Minor items can be deferred.
