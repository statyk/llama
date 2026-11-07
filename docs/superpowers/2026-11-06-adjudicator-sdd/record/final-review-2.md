# final2-review: whole-branch re-review of the post-pilot fixes (ee698e27..0d68a3fc, 12 commits)

**Verdict: ready to merge after one Important fix.** The fix is about 3 lines plus a test. It is on the `--accept`/`[a]` path only and fails closed. No Critical issues.

## Strengths
- The gate's new rules combine fail-closed. I found no combination of coverage veto, placeholder clauses (a)/(b), structure-on-included, the new valid targets and `first_judgements` that auto-applies a placeholder, the wrong recording or an unpredicted structure:
  - include+set_title: the title bar still needs high confidence and an anchor, gate.py:337-351, with `t=None` handled. Clause (b) takes the set_title's title, gate.py:398-419. Apply checks that it landed as `override`, apply.py:225-230.
  - A structure naming an included file is propose-only, gate.py:371-373. A structure naming an excluded file stays malformed.
  - Only a switch exempts a verdict from the coverage veto, gate.py:589. A switch is still held to the switch bar and to `coverage_failures`.
- Every reader of judgements agrees on the first one:
  - gate `_overrule_edit` uses `next()`, gate.py:453.
  - `first_judgements` is used by apply `silenced_flags`/`rehold_flags`, runner `held_proposal` and report `render_proposal`.
  - `_vetoes` iterates all judgements, but repeats agree on verdict, which is all it reads.
- show_unit:
  - The snapshot walks for dirs and files are strict (`_walk` onerror), and a file read error becomes a `LlamaError`. The dir set is captured before `.txn/` exists.
  - `remove_created_dirs` uses rmdir only, deepest first, best-effort, after `put_back`, show_unit.py:172-190 and :233.
  - The restore-time walks stay tolerant, which is the safe direction.
- Ruling (1) is confirmed. config.py:47 sets `"adjudicate": "high"`, and herder/resolve.py:34 maps claude_cli `high` to `opus`. No doc names Sonnet as the adjudicator default. The spec and scripts mention Sonnet only as a pilot arm. config.py:26 ("Sonnet is the workhorse") is pre-existing general tier commentary.
- The docs match the code: packages/llama/CLAUDE.md (adjudicator bullets), the spec's veto, validation and whole-show paragraphs, and prompts/adjudicate.md:75-78 and :126-136. The R4+R5 deferred stale prompt sentence is fixed: adjudicate.md:134-135 now says "unless the same verdict `set_title`s it with a real title".

## Issues

### Critical
None.

### Important
1. **packages/llama/src/llama/adjudicator/apply.py:124-126 (used at :153): `write_edits` silently drops a `breaks_after` entry that names a file the verdict includes.**
   - **What:** `_structure_files_in_play_order` keeps only filenames in the PRE show's `tracks`. R4 made a break on an included file a valid target, but an included file is never in the pre show, so the break is never written to `overrides.json`.
   - **Evidence:** I probed it in the scratch copy: `write_edits(include("x.mp3"), structure(["x.mp3"], "c.mp3"))` writes `set_breaks == []` with `encore_after == "c.mp3"`. `encore_after` is written raw, so only breaks are affected.
   - **Why it matters:** the gate makes such a verdict propose-only (gate.py:371-373), so the operator's only route to it is `--accept`/`[a]`. That route can never succeed:
     - `whole_show_diff` derives labels from `struct.breaks_after`, which includes the break.
     - The re-gathered show has no such break.
     - The set-label check fails and the unit restores.
   - **Severity:** it fails closed, and no data is lost. But a proposal the validator calls valid and the docs say can be accepted is unacceptable in practice. Ruling I1's stated cost ("such verdicts land as proposals") understates this.
   - **Fix:** in `_structure_files_in_play_order`, append the `breaks_after` files that are not current tracks after the ordered current ones. Gather's `resolve_positions` maps filename keys onto the final kept list, and `_sets_from_breaks` uses a set, so order is cosmetic. Add a `write_edits` test for include+structure([included]) and an accept-path apply test where a break on an included file lands.

### Minor
1. **gate.py:589: nothing pins "only a switch exempts" against a verdict carrying an include.** Mutant m4 (exempt `Include` too) was MISSED by the gate, apply, runner, report and bundle tests. Every coverage test's verdict is an exclude (`_cov` default, test_adjudicator_gate.py:1267-1278). The code is uniform, so this is a test gap, not a bug. Fix: parametrize one `_cov` veto test over an include verdict. This is cheap and worth doing alongside Important 1. It is not blocking.
2. **gate.py:597-616: the coverage veto ignores an operator or accepted `overrides.recording` pin.** select_recording.py:109-118 keeps every sibling in `scores` when pinned. A show pinned to a recording with fewer kept tracks than a sibling therefore makes every later non-switch verdict propose-only, permanently. A switch edit is itself propose-only there (EXISTING, gate.py:502-503). This fails closed and the spec is silent on pins. Shawn should decide whether a pin should exempt the veto. No code before merge.
3. **docs/superpowers/specs/2026-11-06-adjudicator-design.md:367: the spec still says "Shawn decides the model from the results (leans Opus)".** It does not record that ruling (1) was taken (Opus default, Sonnet an option). This is a one-line doc note.

## Declined to judge
- A switch to sibling A while sibling B keeps more is not vetoed. The spec says "a verdict with a switch is left to the auto-switch bar", and `coverage_failures` still requires a gain.
- An include (without a research-song overrule) of a file whose tag is a placeholder gather does not demote can ship that title. This is pre-existing (spec: "an included track's own title ... not predicted"). R3 closed the gap only for research-song overrules, as ruled.
- An included file's set is unchecked when the structure edit does not name it. This is pre-existing, and its label is derived from its landed position anyway.

## Deferred-minor triage (r2-deferred-and-rulings.md)
None has to be fixed before merge.

| Task | Item | Verdict |
|---|---|---|
| R1 | no is_dir asserts | no |
| R1 | `_dirs` swallows errors | resolved by R1b (strict snapshot walk) |
| R1 | put_back ordering comment | no |
| R1 | pre-existing empty dir not recreated | no (unreachable) |
| R1 | nested created-dir test | no |
| R1b | regex slug anchor | no |
| R1b | unreadable FILE raises a bare PermissionError | resolved by R1c (cb0e081c) |
| R1b | message repeats the path / no annotation | no |
| R1c | capture_view bare PermissionError | no (writes nothing) |
| R1c | non-EACCES OSError unpinned | no |
| R1c | Py3.14 `package/audio` 0o600 hole | no (data-safe: restore cannot unlink without search permission); file as follow-up |
| R1c | message repeats the path | no |
| R2 | corrupt selection.json | no (fails closed via the `failed` outcome) |
| R2 | considered vs selection identifier | no |
| R2 | one veto per sibling is noisy | no |
| R2 | NaN skips the duration clause | no (safe direction; the count clause still applies) |
| R2 | non-dict selection.json | no (`failed` outcome) |
| R2 | runner e2e has 0 s on both sides | no |
| R2 | select-time vs adjudication-time basis | no |
| R2 | over-long spec line | no |
| R2b | 1-vs-2 tracks test | no |
| R2b | over-long spec line | no |
| R3 | two prompt sentences | no |
| R3 | `[a]` applies a placeholder-vetoed overrule | no (accept semantics, operator note) |
| R3 | a real "Track 9" keeps the veto | no |
| R3 | veto reason outranks "not judged spurious" | no |
| R3 | `clean_tag_titles` parity | no (the error mode is over-veto or both-real) |
| R3 | included-title check in whole_show_diff | DONE in R4 (apply.py:225-230; mutant m2 CAUGHT) |
| R3 | excluded placeholder set_title test | no |
| R4+R5 | stale prompt sentence at adjudicate.md:134-135 | resolved (text now matches the code) |
| R4+R5 | gate.py `& excluded` | no; keep as is |

## Ruling audit
- Every ruling is consistent with the code and the operator rulings: (1) Opus default, both vetoes, both validator fixes, no stale-show code, `failed` records unchanged, R2 fail-closed, the 60 s tie-break on equal `kept_tracks`, the R3 include gap closed in the gate, and the R4 whole_show_diff check present.
- **Ruling I1 (option a) is right, but its cost is understated.** With a break on an included file, the resulting proposal cannot be accepted until Important 1 is fixed. An encore on an included file (waynehancock edit 13) is accepted correctly.
- The R5 "agree on (verdict, confidence), keep the first" ruling is sound: the gate never reads `why`, and mutant m3 pins the first-wins display.
- The "no prompt change for the coverage veto" ruling is sound (deterministic veto, safe demotion).
- I think no ruling is wrong.

## Pilot replay at HEAD 0d68a3fc
- **Safety:** I read the source first. `replay_gate.py` reads only `<scratchpad>/pilot` and `<scratchpad>/replayroot`, which are real copies (no symlinks). Metadata comes from a cache-only fake IA, where a miss raises, so there is no network. Its only output is stdout. `build_bundle` is read-only.
- **How it ran:** from an empty cwd, with `-B`/`PYTHONDONTWRITEBYTECODE`, and with `gate.__file__` in the worktree. OLD gate = `git show ee698e27:.../gate.py` (the pilot's gate). I ran the original `replay_gate.py` and the r45 variant `replay45.py`, which also gates the formerly malformed records. Full output is in final2-review.log.

Key rows:
```
opus | infamousstringdusters-2010-10-15 | True | True | False | [] | ["edit 0 overrule: research-song overrule while 4 shipped title(s) are placeholders (e.g. ...d01t03.mp3: 'Track 3')", ...]
opus | buttholesurfers / joerussosalmostdead / littlefeat / moe / soundtribesector9 / themotet | True | True | True | [] | []
sonnet | buttholesurfers / joerussosalmostdead / littlefeat / moe / themotet | True | True | True | [] | []
sonnet | gratefuldead-1971-12-01 | True | True | False | ['considered recording gd71-12-01.aud.minches-vernon.24765.sbeok.shnf keeps more (23 tracks, 7363 s) than the current (11 tracks, 3937 s); no switch_recording edit'] | []
sonnet | yondermountainstringband-2009-07-11 | True | True | False | ['considered recording ymsb2009-07-11.u89i_16bit keeps more (18 tracks, 5292 s) than the current (6 tracks, 1715 s); ...', '... u89i_24bit ...'] | []
opus/sonnet | waynehancock-2004-04-08 | False | False | False | [] | ['edit 13 structure: structure names a file this verdict includes; its position is not predicted']   (new malformed=[])
sonnet | discobiscuits-2002-10-02 | False | False | False | [] | []   (new malformed=[]; edit 0 switch fails: show is station-marked)
OLD-GATE MISMATCHES: none
```
Result: every expectation matches.
- NOT auto: sonnet Yonder, sonnet GD 1971-12-01, opus stringdusters.
- The other 11 are auto.
- The old gate reproduces every record.
- waynehancock (both arms) and sonnet discobiscuits are valid and not auto.

## Suite
`./.venv/bin/pytest -q -p no:cacheprovider` at HEAD: **7592 passed, 1 skipped, 8 deselected, 26 warnings in 102.61s**.

## Cross-task mutant audit
- **Setup:** scratch copy via `git archive 0d68a3fc`. Run as `<worktree>/.venv/bin/python -m pytest` from an empty cwd, with `PYTHONPATH` set to the copy's llama/herder src. Shadowing was proven with a planted `SENTINEL_F2` (gate and apply resolved inside the copy; the sentinel was removed before mutating), and each run printed `gate.__file__` inside its mutant dir. Each mutant used `PYTHONDONTWRITEBYTECODE=1` and its own `PYTHONPYCACHEPREFIX`.
- **Tests run:** gate, apply, runner, report and bundle tests (466). The baseline m0 (no-op) gave 466 passed.
- The expected red tests were logged before any flip.

| mutant | interaction | expected red | result |
|---|---|---|---|
| m1: clause (b) skips an included file the verdict set_titles | R3 x R4 | test_a_placeholder_set_title_on_the_included_file_triggers_clause_b | CAUGHT (exactly it) |
| m2: whole_show_diff skips included files before the title check (pre-R4 order) | R4 x R3 (apply backs clause b) | test_whole_show_diff_checks_the_set_title_of_an_included_file; test_apply_include_lands_but_its_set_title_does_not_restores[*] | CAUGHT (those 3, plus the 2 included-structure-label tests) |
| m3: first_judgements keeps the LAST repeat | R5 x runner/report | test_validate_agreeing_repeated_judgements_collapse_to_the_first[*] | CAUGHT ([why-only]) |
| m4: coverage veto also exempts a verdict carrying an include | R2 x R4 | predicted MISSED | MISSED (Minor 1) |

## Assessment
**Ready to merge: with fixes.** Fix Important 1 (apply.py:124-126) and its test before merge. Minor 1 is a cheap test to add alongside it. Minors 2 and 3 are for Shawn's information or a one-line doc note.
