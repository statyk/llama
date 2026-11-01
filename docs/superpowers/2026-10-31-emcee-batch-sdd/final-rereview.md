# final-rereview: 6706ca85..e1f67e76

1. ADDRESSED. scripts/backfill_voiced_on.py:113-117: a non-dict block or one already dated returns a skip reason; backfill prints it, counts it and continues (:156-160). Tests at scripts/test_backfill_voiced_on.py:~225-238 cover the cleared and re-voiced cases.
2. ADDRESSED. scripts/backfill_voiced_on.py:32, CLAUDE.md:54, README.md:621. The refusal text matches bulk_apply.py `_unmark_one`.
3. ADDRESSED. README.md:613 clause dropped; pin at packages/emcee/tests/test_voiced_on.py:126.
4. ADDRESSED. packages/emcee/src/emcee/cli.py:279-281.
5. ADDRESSED. packages/emcee/tests/test_keep_script.py:~493.
6. ADDRESSED. process.py:219-221 (clone-only, ahead of the portability check), :223-228 (unknown backend); test_process.py:841 and the refusal table.
7. ADDRESSED. test_process.py:850, :857, :865.
8. ADDRESSED. process.py:166, cli.py `--clone-text` help and say docstring, tts/resolve.py:40; `house_mlx` not renamed.
9. ADDRESSED. cli.py:331-333; the one caller (:314) passes `voiced`.
10. ADDRESSED. scripts/test_backfill_voiced_on.py:241 onward: voiced_before, formatting skip, no trailing newline.
11. ADDRESSED. scriptwrite.py:138. Ran it on the comment's titles: `Mississippi 1/2 Step` and `(23rd/1st)` unsplit, `Danko/Manuel` and ` / ` split, `w/` and `W/` unsplit, `Slow/Fast` still splits. `->`, `-->` and a trailing `->` give the same known set as the old regex. Over the 22,524 unique delivered titles the `w/` change only removes junk parts (55 titles) and the dropped lookbehind splits 3 titles (`Intro #3/Aladdin`, `SP37597/Kashmir/...`), all correct.
12. ADDRESSED. audio.py:437; the render's `json.loads` and `cached.get` raise on corrupt and non-object sidecars, as the docstring says.
13. ADDRESSED. cli.py:713-725, skip keyed on `state == "ready"` under `not force`. No clear or rewrite: skipped packages leave `to_voice`, so `_process_one` never sees them. `counts` is filtered too, so the plan matches what is processed. A failed attempt is `pending` (station.py:280). `--force` bypasses the skip. Probed the case the tests omit, pending with a live block at 0 of M (broadcast.m3u removed): processed, passed.
14. ADDRESSED, with a scope note. scriptwrite.py:139, :150; the whole-title `known.add` at :149 is unchanged, so every whole title is still accepted as itself. The drop runs on every title, including unmerged ones, so two sets move past the brief's wording:
    - `E: Foo` (181 unique titles) now also accepts bare `Foo`. That is the right song.
    - `E: Foo > Bar` no longer accepts the part `E: Foo` (29 unique titles).
    Measured over all 328 scripts on the station: 0 mentions lost and 0 gained, old known set against new. Neither move is breakage. The operator may want to know.

New Critical or Important breakage in the fix diff: none.

Out of scope, one line each:
- Minor: apply_one's `mp.stat`, `read_bytes` and the write are not wrapped, so a manifest vanishing after classification or an SMB OSError still aborts the run (backfill_voiced_on.py:104-105, called at :156). Not in the brief, idempotent on re-run, nothing lost.
- Minor: no committed test for pending with a dj_audio block at 0 of M; only the failed-attempt case is pinned (my probe was throwaway).
- `--drifted` on a ready package with no TTS record at 0 of M now skips, so it never gains a record and is listed again each run. Follows from item 13's rule.
- The false claim from item 6(a) has a house twin: `the house [tts] voice is a preset voice for mlx_audio` under an mlx house with no clip (process.py:228).
- `.split` on ` - ` stays refused as documented; lowercase `e: ` is not dropped.

Not re-run: the suite. Ran one throwaway probe test from the scratchpad; the worktree is unchanged and nothing on the station was written.

Final verdict: 14 of 14 ADDRESSED, no new Critical or Important. Ready to merge on this scope, once the operator has been told about item 2 before the first `--apply`.
