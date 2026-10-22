# gb-final: whole-branch review, held-backlog-small-fixes (bfaa837..36473d8)

How I reviewed it: I read the spec, global constraints, final-review notes and deferred minors in full. I read the slice C source (`show_unit.py`, and in `cli.py`: `fix`, `_interactive_resolve`, `_untitled_resolution`, `_redo_show`/`_redo_show_locked`, `redo`/`_redo_batch`, the `_execute` per-show handler, `main_cli`), the slice B/D source diffs and the harness diff. I also checked the code these touch: `drop_stage_artifacts`, `build_package`/`run_package`, `atomic_write_bytes`, `file_lock`, `catalog.resolve_show`/`remove_show`, `grouping._make_candidate`, `cities_compatible` and `gather.metadata_norms`. I read the T8 mutation handback.

- **Suite:** `./.venv/bin/python -m pytest -q` gives 4041 passed, 1 skipped, 8 deselected. `llama.__file__` resolves inside the worktree.
- **Scratch probe:** one read-only probe (`compute_gather` with an operator venue override), run from the scratchpad against the worktree's interpreter. It confirmed Important #1 below.
- **Not touched:** the worktree, `~/.llama` (I only ran a read-only `ls` and `find`) and git state.

## Strengths

- **`show_unit` is small and careful.** The order is right:
  1. Lock.
  2. Check the view against what the caller saw.
  3. Discard any leftover snapshot, and refuse if it cannot be removed.
  4. Take the snapshot. If that fails, discard it and re-raise before any work.
  5. Run the work under a `BaseException` guard: restore, discard, re-raise.

  `index.json` lives outside `files/`, so it can never collide with a show file. Every write-back is atomic. The `.lock` and `.txn/` exclusions are exact, and audio is handled by a filename list, never copied. The survey I ran (read-only `find` over 200 live show dirs) found only small JSON/Markdown outside `package/audio`, so snapshot cost is negligible.
- **Locking is sound.** `_redo_show_locked` is the only form called inside a unit. `process_show` stays lock-free. The only other show-lock takers are `_execute`, deliver, `catalog.remove_show` and reapply, and none of them is reachable inside a unit. Lock order run ⊃ show ⊃ ledger holds. `_redo_show_locked` re-reads `provenance.json` under the lock, which fixes a stale batch-listing entry.
- **Edge cases are handled.** Restore removes `.part` files from atomic writes. It also removes downloads that never finished, and audio files whose new title renamed them. Nothing in the package stage deletes audio, so restore cannot lose kept audio.
- **No prompt runs under the lock.** I traced every triage branch (`[e] [i] [m] [t] [u] [v] [o]`), `fix --suggest-titles` and `fix --untitled`. In each, the prompts run first and the unit holds only the edit and redo. Nothing inside a unit signals success by raising. Unit-time output is either collected into `lines` and printed afterwards (fix), or echoed before the redo's writes (triage).
- **The core billystrings bug is fixed end to end and tested from the real shape.** Every C5 test listed in the spec exists.
- **Mutation evidence is strong.** T8 ran 30 mutants over B and C. All were caught by the predicted test, with shadowing proven for each one.
- **Slice B is minimal and faithful.** It counts exactly as `_make_candidate` does (`if r.venue`, raw strings) and strips only what ships. 1d and `two_venue_signature` still read the original vote. `metadata_norms` still reads `candidate.venue`/`city`. The measurement shows 0 venue or city flags added or removed across 3,983 shows.
- **Slice D is surgical.** The fold is applied on both sides at every call site the spec names. `normalize_song` and `DEFAULT_ALIASES` are byte-identical. No protected constant appears anywhere in the diff.
- **The `_execute` change works and is documented.** Catching `LlamaError` per show (instead of only `IAError`, its subclass) turns a refused-override show into a per-show `other` failure, as C4 asks. CLAUDE.md's failure-records paragraph says so.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

1. **The tie-break leaks into the operator-override arm and changes the shipped city.**
   - **Where:** `packages/llama/src/llama/stages/gather.py:1405` (`tie = venue_tie_break(...)`), together with the override block at about lines 1470-1476.
   - **Spec:** slice B says "Arms that choose the venue themselves (enrichment, swap, 1c, 1d, **operator override**) are unaffected."
   - **What happens:** the tie-break sets both `venue` and `city`. When `overrides.venue` is set and `overrides.city` is not, the override replaces only the venue. The city stays the tie-break's `sel_city`, not the vote's city as before the branch.
   - **Confirmed:** my scratch probe gave `override -> Operator Hall | washington, dc | override`. On base the city would be the vote's `Washington, DC`.
   - **Live case:** `jackiegreene-2010-05-29` (Task 9) goes from `'Angels Camp, California'` to `'angels camp, california'`.
   - **Why it matters:** the city is spoken by the DJ and shown to listeners. Shawn deliberately hand-set this show's venue, and the branch silently re-cases its city on the next re-gather. It is cosmetic but it breaks a named spec invariant, and the fix is one line.
   - **Fix:** `tie = venue_tie_break(candidate, sel) if overrides.venue is None else None` (`overrides` is already in scope). Add a test that fails on HEAD: a tie plus `Overrides(venue=...)` ships the vote city. A city-only override can keep the tie-broken venue, since the operator did not choose the venue there.

### Minor (Nice to Have)

2. **After a "changed by another command" refusal, triage can never succeed on that show.**
   - **Where:** `cli.py`, the `except (LlamaError, HerderError): continue` arms in `_interactive_resolve`.
   - **What happens:** on `ShowChanged`, triage loops back to the same show's prompt with the same session-long `view`. Every later edit to that show refuses again, although the message says "run it again".
   - **When:** only when another process edited the show while a triage prompt was open.
   - **Fix:** on `ShowChanged`, `return _interactive_resolve(config, ia, ledger, entry)`, which re-captures the view, re-resolves and re-prints. Or return and move to the next show.
3. **Failure output does not say the show was restored.**
   - **Where:** fix's error arrives via `main_cli`'s `error: …`. Triage prints `error: …`, and on `[m]`/`[i]` it first echoes "metadata override updated" or the routing note inside the unit.
   - **Why it matters:** an operator who knows the old behaviour (overrides stayed staged after a failed redo) can't tell from the output that nothing stuck. Triage's "updated … error:" sequence reads as if the edit landed.
   - **Fix:** append something like "; the show was left as it was" in the two triage handlers. For `fix`, catch around the unit and add the same suffix before exiting 1.
4. **A track-number `--exclude`/`--unexclude` on a show with no `show.json` refuses without naming the remedy.**
   - **Where:** `_resolve_exclude_tokens` (`cli.py:1497`). It says only "reference the file by name instead".
   - **Spec:** C4 says the remaining refusals "now name the remedy, `llama redo <show> --from gather`".
   - **Fix:** add `refuse_no_show_json`'s suffix. This is arguably within the spec's letter, since filename form works.
5. **A docstring is stale.** `brief.py:121`, in `song_components`, still says "`normalize_song`s each part". It now goes through `_song_norm`, which folds first.
6. **Plan-level: all-or-nothing has a cost. No change is needed now, but Shawn should know.**
   - **What happens:** C2 rolls back everything outside `package/audio` and removes every new audio file. So a unit that pays for a high-tier `brief` (or a `--redo-research` deep_research) and then fails in `package` discards that LLM output and every verified download.
   - **Common trigger:** a delivered show's `package/audio` is empty after deliver's purge, so a `fix`/`triage` edit on it re-downloads the whole tape in `package`, and an archive.org failure late in that re-download is plausible. Each retry then re-pays the brief and restarts the download from zero.
   - **Verdict:** this is exactly what the spec mandates, so it is not an implementation defect. With the 5x plan's tighter meter, it is worth a later refinement, for example keeping md5-verified new audio whose names the restored manifest uses.

## Deferred-minor triage

- **T9 jackiegreene operator-override city:** **MUST-FIX-BEFORE-MERGE**. Same as Important #1: it breaks a named spec invariant, I confirmed it, and the fix is one line plus one test.
- **T9 `venue_changes.txt` 'null -> null':** STAY-DEFERRED. An informational report; apply uses `predicted_list.json`.
- **T9 incomplete hand-check lists:** STAY-DEFERRED. It is a process artifact. Point Shawn at the full lists in `$D/t9-review/handback.md`.
- **T9 drift row gratefuldead-1966-03-12:** STAY-DEFERRED. It is identical in both arms, so not this branch.
- **T1 CLAUDE.md:778 long line:** STAY-DEFERRED (cosmetic; the notes say T1's was already fixed).
- **T1 test_structure mid-file imports:** STAY-DEFERRED. It matches local style.
- **T2 no pin for a tie in the final-else / 1c arms:** STAY-DEFERRED. I confirmed by reading that the code leaves those arms untouched, and B9-B11 mutants pin the neighbouring arms.
- **T2 gather.py:958 `sel` annotation:** STAY-DEFERRED (cosmetic).
- **T2 gather.py:955 `sel` unannotated (duplicate):** STAY-DEFERRED (duplicate).
- **T2 step-1 predicate written twice:** STAY-DEFERRED. A small duplication, and mutants B9/B10 pin both copies.
- **T2 test_stage_gather mid-file imports:** STAY-DEFERRED (style).
- **T2 lambda idiom in a test:** STAY-DEFERRED (style).
- **T2 vacuous venue assert in the incompatible-city test:** STAY-DEFERRED. The city half catches B2, and the mutation run confirmed it.
- **T2 step-1 test relies on a vendored CSV row:** STAY-DEFERRED. The CSV is vendored and refreshed deliberately.
- **T2 CLAUDE.md:623 ~600-character line:** STAY-DEFERRED (cosmetic).
- **T3 identical-only skip path untested:** STAY-DEFERRED (report tooling).
- **T3 base-diff/cand-null direction and unreplayable header untested:** STAY-DEFERRED (report tooling).
- **T3 venue/city flag changes not separated:** STAY-DEFERRED. The layout was brief-mandated, and the measurement shows 0 such changes.
- **T3 unreplayable shows counted, not named:** STAY-DEFERRED (plan-mandated).
- **T3 null -> null rendering:** STAY-DEFERRED (duplicate of the T9 item).
- **T3 untested skip counter etc.:** STAY-DEFERRED (report tooling).
- **T3 row omits outcome:** STAY-DEFERRED (informational).
- **T4 symlinks dereferenced:** STAY-DEFERRED. The library has none: the 200-show sample found only regular files.
- **T4 a unit on an already-removed show leaves a .lock husk:** STAY-DEFERRED. Every CLI path resolves the show first, so it is reachable only through a race, and the spec documents that.
- **T4 restore rewrites unchanged files:** STAY-DEFERRED. The only effect is `llama show` stage ages. File modes are unchanged, since every artifact is already 0600 via mkstemp.
- **T4 c9d770c commit message test line:** STAY-DEFERRED. It is history and cannot be fixed without a rewrite.
- **T4 refusal test patches shutil.rmtree process-wide:** STAY-DEFERRED (test hygiene).
- **T4 docstring limitation 3 omits the leftover refusal:** STAY-DEFERRED. A one-line doc nit; worth folding into the Important #1 fix commit.
- **T5 removed-show check after discard and snapshot:** STAY-DEFERRED. Harmless: the snapshot is of an empty dir and restore is a no-op.
- **T5 leftover-txn redo test cannot distinguish deleted from restored:** STAY-DEFERRED. It is pinned in `test_show_unit` (C8 mutant).
- **T5 CLAUDE.md:65 'see llama fix below':** STAY-DEFERRED. Already resolved at HEAD, which reads "(one unit, above)".
- **T5 batch FAILED line prints the slug twice:** STAY-DEFERRED (cosmetic).
- **T5 batch restore test does not assert bready's write committed:** STAY-DEFERRED (test breadth).
- **T5 duplicated provenance message:** STAY-DEFERRED (cosmetic).
- **T5 test import polish:** STAY-DEFERRED (style).
- **T6 CLAUDE.md 'One unit' label placement:** STAY-DEFERRED. Already resolved at HEAD by f616ea5: the label now sits on the fix entry.
- **T6 no-show.json test breadth:** STAY-DEFERRED. The routing is a single predicate and both sides are tested.
- **T6 `test_no_run…` not marked (pin):** STAY-DEFERRED (labelling).
- **T6 lone `--overrule` waits on the lock and snapshots:** STAY-DEFERRED. An acceptable owner-visible behaviour change.
- **T6 edit lines print after the redo's progress:** STAY-DEFERRED (plan-mandated).
- **T6 fix is ~305 lines:** STAY-DEFERRED (refactor later).
- **T6 CLAUDE.md fix entry leaves the redo item as a fragment:** STAY-DEFERRED (cosmetic).
- **T7 triage tail passes a fresh `_resolve_show` entry:** STAY-DEFERRED. Harmless, since it runs under the lock.
- **T7 removed-show triage test asserts only 'error: ':** STAY-DEFERRED (test tightness).
- **T7 no partway-failure test for [u]/[e]/[i]/[t]:** STAY-DEFERRED. 36473d8 added the [u] test, and [e], [i] and [t] share the tested [m] unit block.
- **T7 per-turn re-resolve ~1 s:** STAY-DEFERRED. An owner-visible UX cost, plan-mandated; a one-directory entry builder is the follow-up.
- **T7 noqa E731 lambdas:** STAY-DEFERRED (style).
- **T7 'metadata override updated' echoed, then rolled back:** STAY-DEFERRED, but see Minor #3 for the better remedy.
- **T7 removed-show message 'no show matches':** STAY-DEFERRED. It is accurate, and the in-unit path does print "the show was removed".
- **T7 no ordering pin for capture-before-re-resolve:** STAY-DEFERRED. The window exists only under concurrency.

## Declined to judge

- **The ledger, run dirs and item cache are not rolled back by a failed unit.** The spec C2 excludes them explicitly.
- **SIGTERM/SIGHUP (terminal closed) runs no restore, so a stale `.txn/` is deleted by the next unit.** This is the spec's documented "killed outright" limitation.
- **`fix` or `redo` wait silently on the show lock behind a long `get`, with no "waiting" message.** The spec says nothing on this, and `redo` already behaved this way.
- **Should the 154 delivered shows' venue changes ever reach air?** Owner ruling: they are not revisited.
- **The 13 base-drift rows in Task 9.** Ruled not this branch.
- **The C2 all-or-nothing cost (Minor #6).** Raised as a note about the plan, not judged as a defect, since the spec mandates it.
- **Untouched packages.** emcee, transmitter and antenna are unchanged on this branch, so I did not review them.

## Recommendations

1. Fix Important #1 with a failing-first test, then merge. Consider folding in Minors #2-#5 and the T4 docstring line, since each is a line or two.
2. Before running `reapply --from-list`, re-run the harness compare. The current `predicted_list.json` came from the `--no-repro-gate` measurement run and is not for apply. Check that `jackiegreene-2010-05-29` no longer appears in `venue_changes.txt`.
3. Tell Shawn about the C2 cost (Minor #6) as a candidate follow-up, given the tighter 5x usage meter.

## Assessment

**Ready to merge?** With fixes

**Reasoning:** Slice C meets its strict-surface guarantees. Every path I traced either restores byte-identically or is a limitation the spec documents. The locking is correct and well tested, and B, D and the harness are faithful to the spec. The one should-fix is a confirmed, one-line slice B deviation: an operator's venue override no longer protects the show's city.
