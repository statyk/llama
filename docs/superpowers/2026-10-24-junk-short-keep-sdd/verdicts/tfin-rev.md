# tfin-rev: final whole-branch review, piece 4 "junk short-keep" (e37f670..a693878)

Reviewer: Opus. Read-only on the live checkout. The only writes were this file, the log, and a scratch copy (`git archive HEAD`) under the session scratchpad, used to try out the two proposed code fixes. Shadowing there was proven with a sentinel; `python -m pytest` only, never a `.venv/bin/*` script.

How I read it, in passes:
1. **Source modules** in the diff: `junk.py`, `override_keys.py`, `models.py`, `gather.py`, `titles.py`, `structure.py`, `replay.py`, `reapply.py`, `show_unit.py`, `audio_reuse.py`, `stages/package.py`, `pipeline.py`, and every hunk of `cli.py`.
2. **`scripts/rekey_overrides.py`**, the whole file (1,549 lines).
3. **The other scripts:**
   - the `replay_holds.py` diff;
   - from `short_keep_probe.py`, `repro` and `voiced-precheck` only.
4. **Tests.** I targeted these and did not read every line: `test_deny_vocabulary_corpus`, the `test_rekey_overrides.py` fixtures, its hermeticity, `monkeypatch.undo` and restore coverage, and the mutation record.

I also checked spec, plan Global Constraints, Review Focus, acceptance.md and the rulings, and deferred-all.md.

Measurements I ran, all read-only against `~/.llama` and `~/.llama-harness`:
- **Full suite at HEAD:** 5372 passed, 1 skipped, 8 deselected. `git status` clean.
- **Lost files:** `cand-c.json` against every library `show.json`: 0 shows lose a stored file.
- **Format choice:** `filter_files(short_keep=False)` against `True`, both formats, over all 31,214 (item × format) pairs in `~/.llama/cache`.
- **Duplicated derivatives:** short-kept derivatives that share an `original` with another kept file, over `cand-c`.

## Strengths

- **The rule is placed where it cannot move the floor.** `_apply_short_rule` runs after the two-pass floor, inside `_keep_and_exclude`, so every `filter_files` caller gets it. `short_keep=False` really is the old filter: the rule is skipped and `orig_tracks` is only hoisted. That is what lets the migration's consistency check (`final_kept(..., short_keep=False)`) mean "today's rule".
  - The normative regexes match the spec text exactly. The corpus test pins all 3,547 rows.
  - The dedupe-before-interior ruling is implemented over a pool keyed exactly as dedupe keys, and is documented.
- **One resolver, one kept-list helper.**
  - `override_keys.resolve_positions` is the only positional reader in gather. My grep found no other `overrides.titles/set_breaks/encore_after` read in src.
  - `gather.final_kept` is shared by gather, `fix`'s staleness check, `--suggest-titles` and the migration. The legacy test is pydantic's own lax-int, checked against the vendored v2.17.0 model.
  - Writers refuse legacy files at `fix` entry, before any prompt. Numbers are translated through `show.json`, with the staleness check gating positional edits.
- **The migration script is careful on the strict surface:**
  - every gate writes nothing;
  - the snapshot is hash-verified on write and on read;
  - each show is re-checked under its lock on exactly the bytes it read (`check_show(overrides_bytes=, show_bytes=)`);
  - a round-trip guard runs on every rewrite;
  - records are durable and an interrupted run is detected;
  - restore empties audio first and never follows symlinks;
  - the process check covers the shell-loop and console-script forms;
  - the per-show apply routes name `--restore` first when anything was migrated.
- **Audio reuse:**
  - It decides from what is on disk, not from `show.json`.
  - It pairs only within one archive item (the Task 13 fix).
  - The aside is single-use and is put back after the snapshot restore.
  - `reapply`'s own undo of audio and manifest is correct: a new file that shares an old name is overwritten by `put_back`.
- **Deliver.**
  - The selector refusal comes before `_setup()`.
  - An unreadable destination refuses, per show in a batch.
  - A changed track list goes through `_replace_destination`.
  - `_read_destination_manifest` is the single reader for both paths.
- **The briefing-reuse gate errs only toward refusing, as the operator ruled.**
- **Mutation coverage:** 20 of 21 mutants caught by the predicted test. Good shadowing discipline.
- **No conflict risk from main.** `git diff e37f670 main` touches nothing under `packages/llama`, `packages/emcee`, `packages/herder` or `scripts/`.

## Issues

### Critical

None.

### Important

**I-1. With `audio_format = "flac"`, a format holding only rule-kept short files now wins the format choice. The whole show then collapses to one short file.**
- **Where:** `packages/llama/src/llama/junk.py:439` (`if fmt_kept:`).
- **Measured** over the cache (31,214 item × format pairs): 2 items flip, both under `flac`, and nothing under `mp3`.
  - `tsp2007-07-28.csb.flac24`: `24bit Flac` with 32 tracks becomes `Flac` with 1 track, `tsp2007-07-28.csb.t34.flac` ("Outro", 61 s).
  - `ymsb2007-04-14.blackfingers.flac24`: 29 tracks becomes 1, `..._set01t01.flac` ("Intro", 71 s).
- **Why it happens.** The item's lone 16-bit `Flac` file is a tagged short file. The rule now keeps it, so `fmt_kept` is non-empty and the preference loop breaks on it.
- **Why it matters.**
  - It is omitting real show content, the error the operator ranks worst.
  - The plan's Global Constraints require `filter_files`' format choice to stay unchanged. The code is byte-identical, but its input moved.
  - Production is `mp3` today, so nothing in the library is affected (0 shows lose a file at `cand-c`). It is a latent defect behind a supported config value. Task 1 deferred concern 1 named it but it was never measured.
- **Fix.** The winner is the first format that keeps at least one file the floor itself passed. Failing that, the first format whose kept list is non-empty. Failing that, today's fallback:
  - the condition becomes `if any(f["name"] not in fmt_short for f in fmt_kept)`;
  - track a `first_nonempty` and use `chosen or first_nonempty or fallback`.
  - `first_nonempty` matters: without it, an item whose first format is all junk and whose second keeps only short files would regress to an empty kept list.
  - With `short_keep=False`, `fmt_short` is empty, so behaviour is identical to v2.17.0 and the migration check is unaffected.
- **Tried in a scratch copy.** The simple form of the condition gave a green llama and scripts suite (3857 passed). The cache scan then showed 0 flips. The library's final kept lists were unchanged by this part of the fix.

**I-2. The rule restores both VBR derivatives of one original, so a short piece airs twice, including on shows the operator had already repaired by hand.**
- **Where:** `packages/llama/src/llama/junk.py:266` (`back = tagged_keep + untagged_keep`).
- **Why it happens.** Some items carry two `VBR MP3` derivatives per original (`X.mp3` and `X_vbr.mp3`). Dedupe keys on (basename, duration), so both survive. Before piece 4 the short arm dropped both copies of a short piece, so an operator who fixed a doubled show by `fix --exclude`-ing every `_vbr` file never had to exclude the short ones. The rule now re-admits both.
- **Measured at `cand-c`:** 8 shows, 15 surplus `_vbr` files. Three of them are not wholly doubled; they were hand-repaired, and every long `_vbr` is operator-excluded:
  - **`stringcheeseincident-1999-12-31`** (packaged, outcome **clean-changed**, so the bulk apply ships it unflagged): Countdown, Mean Mr. Mustard, Polythene Pam, Golden Slumbers and The End each appear twice in a row.
  - `gratefuldead-1970-06-07`: My Dog Has No Nose and the Louie Louie tease, twice each.
  - `gratefuldead-1989-07-19`: d1t06, twice.
  - The other 5 (1966-12-01, 1969-04-21, 1978-12-30, 1990-07-14, 1995-03-18) are already wholly doubled; that is ruling 5's class.
- **Relation to ruling 5.** Ruling 5 put the pre-existing doubled-derivative class outside this branch. These 3 shows are not that: piece 4 creates the duplicates, on shows that are currently correct. The orchestrator classed 1970-06-07 under ruling 5 at Task 15a; I think that is wrong for the hand-repaired shows. I am flagging it, not overruling it. If the operator reads ruling 5 as covering these too, the minimum is to list the 3 shows and their `_vbr` files for `fix --exclude` before the bulk apply.
- **Fix (drop-only, inside the rule).** Re-admit at most one derivative per original:
  - Walk `back` in name order. Drop a derivative whose `original` already has a derivative in `kept`, or one taken earlier in that walk.
  - Name order puts `X.mp3` before `X_vbr.mp3`, which matches the operator's own convention.
  - Tried in a scratch copy: the suite is green. Over the library's final kept lists, exactly the 15 `_vbr` files above drop, in those 8 shows. Nothing else changes and nothing is added.
  - The normative functions are untouched, and `short_keep=False` is unaffected.

### Minor

These are the reviewer's own; the deferred-list items are triaged below.

**m-1. Two rules sit in the code with no comment.**
- `junk.py:439`: once I-1 is fixed, the format-choice rule ("decided on floor-passing files") deserves one comment line there.
- `junk.py:266`: the I-2 rule deserves one comment line too.

**m-2. The briefing gate's N1 fix (must-include item 1) has a trap: `’` already joins words without any fold.**
- `replay.py:271` (`_TOKEN = \w+(?:['’]\w+)*`) treats `’` as an interior joiner directly. So "not’listed" glues into one word even with no fold at all.
- The fix must therefore cover `’` and every folded look-alike, not only the `_APOSTROPHES` fold. The simplest refusing-only form: a third normalised copy in which every apostrophe is a separator, and a term fires on any copy.

**m-3. `_deliver_one`'s voiced refusal (`cli.py:2574-2578`) is the text item 4 of the fix wave changes.** That item (Task 16 Minor 6) must word it for the batch only and keep the single-name text, which `test_voiced_destination_still_refuses_without_the_flag` and the existing tests read.

## Deferred-list triage

Verdict is FIX BEFORE MERGE or LEAVE. I gave every remaining "minor (deferred)" a verdict, including the Task 16-18 minors, which orch-r3 had pre-listed in a must-include line the brief has since narrowed.

### orch (Tasks 1-7)

- T1 `_furthur_without_short_tuning` defined twice -> LEAVE: test hygiene.
- T1 `test_floor_unchanged_by_kept_short_files` near-tautological -> LEAVE: brief-mandated pin.
- T1 interior=False sentinel and the spam re-check -> LEAVE: readability only.
- T1 a whitespace-only own title does not fall back to the original's -> LEAVE: as measured.
- T1 concern 1 (a format holding only tagged short files can win) -> **FIX BEFORE MERGE**: measured real, I-1.
- T1 concern 2 (furthur `tmp` / "Tuning Up") -> LEAVE: Task 2's note fires.
- T1 concern 3 (windsor coverage) -> LEAVE: resolved by Task 2's clause.
- T1 pool dedupe may pick a different winning copy -> LEAVE: exotic, and order-only.
- T1 `_doubled` prefix param never non-default -> LEAVE.
- T1 an untagged candidate without a track tag forces filename order -> LEAVE: spec 2.4 mandates it.
- T1 `_listing_key` copies dedupe's key -> LEAVE: the docstring records the coupling.
- T2 test legs identical -> LEAVE.
- T2 the junk note also judges unresolved filenames -> LEAVE: notes only, and `tuning.mp3` does not read as junk anyway.
- T2 test-module import coupling -> LEAVE.
- T3 a duplicate filename maps to its first position -> LEAVE: unreachable; the migration refuses `repeated filename`.
- T3 `rekey_raw` collapses colliding keys -> LEAVE: `check_show`'s duplicate-key refusal runs before any `rekey_raw` (verified).
- T3 the "no track k" check in gather is unreachable -> LEAVE.
- T3 `Positions` is only shallowly frozen -> LEAVE.
- T3 two commits -> LEAVE.
- T4 `_stale` lets IAError escape as a traceback -> LEAVE: nothing is written, and it needs a cache miss plus a network failure.
- T4 `file_of` is a third number-to-filename translation -> LEAVE.
- T4 `_keyed_files` mutable default -> LEAVE: never mutated.
- T4 a test lacks its exit_code assert -> LEAVE.
- T4 exclusion over-refuses in a clear+set+exclude combination -> LEAVE: errs conservative.
- T4 `--suggest-titles` message wording -> LEAVE.
- T5 `_edit_overrides` docstring -> LEAVE: its docstring now names the filename passthrough.
- T5 `cli.py` and/or precedence (~2069) -> LEAVE: it evaluates correctly.
- T5 a dangling filename containing `,` or `=` -> LEAVE: fails safe.
- T5 the triage keyed-exclusion test covers titles only -> LEAVE.
- T6 `compare` never surfaces `rekey_error` -> LEAVE. A failed re-key leaves the legacy file in place; the resolver refuses it, so the row is unreplayable with the legacy text; `_overrides_invalid` then refuses the arm. It is surfaced indirectly.
- T6 `taper_probe._fix_applied` TypeError -> LEAVE: probe only.
- T6 a record test asserts shape, not values -> LEAVE.
- T6 unread vars in `title_hygiene_probe` -> LEAVE.
- T6 `summary.txt` does not name the re-keyed arm -> LEAVE: the apply-lists line does.
- T7 the "shows LOSING a file" counter was not ported -> LEAVE. I measured it by hand at `cand-c`: 0 shows lose a stored file.
- T7 `repro` passes on two empty arms (`short_keep_probe.py:574`) -> **FIX BEFORE MERGE**. It is runbook step 7's gate on strict surface (a), and today it can pass on nothing. Refuse when either arm has zero replayable rows, or when the arms' `root` differ. The rest of that line (the vacuous test assert, the over-strict ancestor `--out`, the override-set rebuild, red only by collection error) -> LEAVE.
- T7 ConfigError traceback -> LEAVE.
- T7 probe tests read the real `~/.llama/config.toml` -> LEAVE: read-only.
- T7 docstring gaps -> LEAVE.
- T7 the ref-dir `--out` guard is unpinned -> LEAVE.

### orch-r1 (Tasks 8, 10-12)

- T8 neighbour, exception swallowing, answers last-wins, window, INSTRUCTIONS, score.md, row C kind, unused line (all 8 items) -> LEAVE: hand-check tooling, whose measurements are already done.
- T8 ⚠ sample coverage -> LEAVE: closed by the ruling 4 check.
- T10 spec stale counts, the vacuous sentence, the call-sign false-positive class, the unless-list cross-reference -> LEAVE here: they belong to Task 23's spec-text batch.
- T10 no pin that a 1 s tagged file is still kept -> **FIX BEFORE MERGE**: a 3-line test on the zero-duration exception's boundary. It guards against over-dropping, which the accuracy rule ranks worse.
- T10 the `wrap\w*` qualifier is untested -> **FIX BEFORE MERGE**: a 1-line test (`KBFH Wrap-Up` drops) on strict surface (c)'s non-performance vocabulary.
- T10 a spam-shaped zero-duration file records `implausibly short` -> LEAVE: drop-only.
- T11 the "tracks differ" return is untested (a mutant survives) -> **FIX BEFORE MERGE**: one assertion on the briefing-reuse gate, which is strict-adjacent.
- T11 the 173-case test passes on old code; unmarked pin -> LEAVE.
- T11 a None break key (break preceded only by short-kept tracks) is untested -> **FIX BEFORE MERGE**: a small test on the same gate.
- T11 stale docstring -> LEAVE: largely updated by 15a.
- T12 mid-file imports, broad except in `plan_reuse`, restore/put_back order, unreadable show.json re-downloads, `build_package` docstring, the two-pass message assert, in-place re-tag, "twice in one unit" text -> LEAVE: all cosmetic or the safe direction.

### orch-r2 (Tasks 13-15a)

- T13 a failed reapply does not restore the manifest; the `--untitled` second pass; manifests read twice; a manifest without an identifier pairs nothing -> LEAVE: each costs a download at worst.
- T13 ⚠ spec 5.4 text -> LEAVE here: Task 23.
- T14 the reuse check measures the clean path only; tally label; double-listing; size-0; the share re-check order; the plan_s pin -> LEAVE: probe, whose numbers are recorded.
- T15a the phrasings minor -> LEAVE: closed by 15b.
- T15a shorthand forms -> LEAVE: the wording arm backstops them.
- T15a the comment -> LEAVE: present at `replay.py` in `briefing_reusable`.
- T15a ⚠ `gratefuldead-1970-06-07` doubled `_vbr` -> **FIX BEFORE MERGE**: measured as a class of 8 shows, I-2. If the operator rules it under ruling 5, list the 3 hand-repaired shows instead.

### orch-r3 (Tasks 15b-18)

- 15b N1, "too (very) short", the measured vocabulary -> must-include (fix wave items 1-3).
- 15b over-matching on instruction prose -> LEAVE: costs a brief call only.
- T16 ⚠ CLAUDE.md line ~72 is stale ("a batch confirmation marks or counts the voiced destinations") -> LEAVE here: Task 23 must fix it.
- T16 a destination with audio but no manifest still merges -> LEAVE: the operator's call. Old files do not air, since emcee and transmitter read manifest tracks only.
- T16 `~` expansion in voiced-precheck -> LEAVE.
- T16 a near-duplicate test -> LEAVE.
- T16 a mid-file import -> LEAVE.
- T16 the batch plan count includes unreadable shows -> LEAVE.
- T16 Minor 6 -> must-include (item 4).
- T16 no test pins that a reordered list replaces -> LEAVE: packaged names carry the index, so a reorder always changes the name list.
- T17 the PROCESS_NOTE position is untested -> LEAVE.
- T18 premise 9 (snapshot speed) -> LEAVE: the operator times it at runbook step 4.
- T18 `<root>` is not flushed after the snapshot directory is created -> **FIX BEFORE MERGE**: one line, `_sync_dir(root)` after `os.rename(tmp, snap / MANIFEST)` (`rekey_overrides.py:667`). The rollback point's durability is the premise of surface (a).
- T18 `find_snapshot` accepts any name -> LEAVE: a stray name fails safe, because the per-show comparison refuses.
- T18 OSError on `.rekey.lock` -> LEAVE.
- T18 symlinked show dir message -> LEAVE.
- T18 duplicate slugs in a manifest -> LEAVE.

### orch-r4 (Tasks 19-21)

- T19 Minors 1-2 -> must-include (items 5-6).
- T19 `_interrupted` swallows exceptions -> LEAVE: the record is informational. Restore works from the snapshot's slugs, not from the record.
- T19 `_summary` counts husks -> LEAVE.
- T19 up-front tracebacks -> LEAVE: nothing is written.
- T19 `monkeypatch.undo()` -> LEAVE. Read: both tests re-stub `_ps_lines`/`llama_versions`, and `_apply` always passes `--config`, so the undone `DEFAULT_ROOT` is never read.
- T20 Minor 1 -> must-include (item 7).
- T20 `--restore` accepts any directory -> **FIX BEFORE MERGE, narrowed**. Refuse when `rekey-applied.json` exists and names a different snapshot, so a migrated library is never rolled back to an older snapshot by a mistyped path. That would silently discard every edit between the two snapshots, on surface (a). The cheap form is just that check plus a test. Requiring `<root>/rekey-snapshot-*` -> LEAVE.
- T20 the re-voiced-in-place listing -> LEAVE: it is the operator's question at Checkpoint C.
- T20 mid-file import -> LEAVE.
- T20 convoluted assertions -> LEAVE.
- T20 three untested refuse-and-stop branches in restore -> **FIX BEFORE MERGE**: tests only, on the library-wide rollback path. The three are a directory where the snapshot holds a file (`:1216-1218`), the `_check_inside` refusal (`:1196-1204`) and the rename collision (`:1365`).
- T20 empty directories are removed by restore -> LEAVE.
- T21 duplicated unreadable-destination handling -> LEAVE. Read: both paths already go through the one `_read_destination_manifest` (`cli.py:2471`, called at `:2569` and from `_destination_is_voiced`); only the `dj_audio` test expression repeats.

## Declined to judge

- The exact coverage of the briefing gate's vocabulary, beyond must-include items 1-3 and m-2: measured over five fix rounds by others; I did not re-measure the corpus.
- The acceptance tallies (1,531 / 2,639 / 20 / 34) and the hand-check score: I trusted acceptance.md. I re-checked only "no show loses a file" and the format-flip scan.
- Spec and plan text, and CLAUDE.md: Task 23's batch, not code.
- `short_keep_probe.py` beyond `repro`/`voiced-precheck`, and `taper_probe.py`/`title_hygiene_probe.py`: measurement tooling with no library writes; skimmed only.
- The bulk apply (reapply extended to packaged and delivered shows): named as an open gap, not built here.
- transmitter and antenna: not in this diff.
- The `_vbr` long-track doubling of the 20 shows: ruling 5's follow-up, outside I-2's narrower scope.

## The fix wave (one dispatch)

1. **I-1, format choice** (`junk.py:439`). The winner is the first format whose kept set holds a file outside `fmt_short`, else the first non-empty one, else today's fallback.
   - Tests: a fixture shaped like `tsp2007-07-28.csb.flac24`, with 1 `Flac` file (tagged "Outro", 61 s) and 33 `24bit Flac` files. With `want=("Flac","24bit Flac")` it chooses `24bit Flac` with the full set. A second fixture where `Flac` is all non-short junk and `24bit Flac` keeps only short tagged files chooses `24bit Flac` (non-empty).
   - Acceptance: `short_keep=False` output unchanged, so the vendored v2.17.0 oracle tests stay green. Re-run the cache scan (0 flips) and record it.
2. **I-2, one derivative per original among the rule's keeps** (`junk.py:266`, drop-only).
   - Test: `X.mp3`/`X_vbr.mp3` short twins, both tagged; the long `_vbr` twins in `kept` or not. Only `X.mp3` is re-admitted, and `ordering["short_kept"]` lacks `X_vbr.mp3`.
   - Acceptance: re-measure the library's final kept lists. Exactly the 15 `_vbr` files in the 8 shows of I-2 leave, nothing else changes, and `test_deny_vocabulary_corpus` stays green. Unless the operator rules it under ruling 5; then list `stringcheeseincident-1999-12-31`, `gratefuldead-1970-06-07` and `gratefuldead-1989-07-19` for `fix --exclude` before the bulk apply.
3. **(must) 15b N1**: the apostrophe glue, including `’`, which `_TOKEN` already joins (m-2).
   - Tests: `is not‘listed’`, `not’listed`, `isn´t listed` refuse; `isn't listed` still refuses.
   - Prefer a third normalised copy with every apostrophe a separator, so the change refuses only.
4. **(must) 15b**: `too <≤2 words> short` and `implausibl[ey] <≤2 words> short`, on the normalised text.
   - Tests: "too very short", "implausibly, very short" refuse.
5. **(must) 15b measured vocabulary**: `lacks`, `not recorded`, `cut from the recording`, and data-subject `lists/contains no <piece>`.
   - Each term gets its corpus count from `t15b-rr5/handback.md` over `~/.llama-harness/piece4/ckb/15a/dump.jsonl` in the test docstring or comment, and a test using the corpus wording (e.g. `the show data lists no encore`, `billystrings-2017-08-29`).
6. **(must) Task 16 Minor 6**: the per-show voiced refusal printed inside a batch gets batch wording: "re-deliver it by name with --replace-voiced", not "pass --replace-voiced". The single-name text is unchanged.
   - Test: a batch with one voiced destination prints the batch wording and no `(pass --replace-voiced`.
7. **(must) Task 19 Minor 1**: pin the `first: --restore` line on the up-front refusal path after an interrupted run.
   - Test: interrupt `--apply` after one show is rewritten, make another show refuse, re-run; the output contains `first: run --restore`.
8. **(must) Task 19 Minor 2**: pin `check_show`'s byte arguments under the lock.
   - Test: spy on `rk.check_show` from `_rekey_show`, asserting non-None `overrides_bytes` and `show_bytes` equal to the files' bytes.
9. **(must) Task 20 Minor 1**: a station or runs listing failure in `--restore` is repeated before `next:` (and/or a distinct exit code).
   - Test: an unlistable `delivery_path` gives the warning twice, the second just before `next:`.
10. **T7, `repro`** (`short_keep_probe.py:574`): refuse (exit 1) when either arm has zero replayable rows, or when the arms' `root` differ.
    - Tests: two empty arms exit 1; arms from different roots exit 1.
11. **T18**: `_sync_dir(root)` after the snapshot manifest rename (`rekey_overrides.py:667`).
    - Test: spy on `_sync_dir` and assert it is called with `root` after the manifest exists.
12. **T20, restore against the wrong snapshot**: `--restore` refuses, writing nothing, when `<root>/rekey-applied.json` exists and its `snapshot` is not the given directory's name.
    - Test: two snapshots, apply from the newer, restore with the older: refused, and the library is byte-identical.
13. **T20, restore's untested branches**: tests for a directory where the snapshot holds a file, the `_check_inside` refusal, and the rename collision. Each asserts the stop message and that nothing after it was touched.
14. **T10 pins**: a 1 s tagged short file (reasons exactly `["implausibly short"]`) is kept; `KBFH Wrap-Up` drops as non-performance.
15. **T11 pins**: `briefing_reusable` returns `"tracks differ"` when a non-short track's filename differs; a None break key (break preceded only by short-kept tracks) is compared, both the equal case and the moved case.

After the wave: full suite green (`./.venv/bin/python -m pytest -q`). Then re-run `cand` and `arms` at the new HEAD for Checkpoint C. Expected: only the I-2 shows change, plus briefing fields if the gate moved.

## Assessment

**Ready to merge: with fixes.** The strict surfaces hold as built: the migration, the deliver changes, the tripwire and the junk test, plus the reuse and briefing gates. I found no Critical defect. Two Important defects are real and measured, both in the filter's interplay with item structure:
- I-1: with `flac`, the format choice can collapse a show to one short file;
- I-2: duplicated `_vbr` short pieces, which would ship `stringcheeseincident-1999-12-31` with its Abbey Road medley doubled.

Both are small, drop-only or choice-only, and do not change `short_keep=False`. Fix them in the one fix wave together with the must-include items and the cheap pins above.
