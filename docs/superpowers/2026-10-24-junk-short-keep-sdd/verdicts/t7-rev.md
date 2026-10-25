# Task 7 review (t7-rev): scripts/short_keep_probe.py arms|repro — c728356..4de43d2

### Spec Compliance

- ✅ The interfaces match the brief and spec 6(a), (b), (d), (e), 4.3 and 8.1: `arms` writes `arms.md` and `arms.json` with base consistency, reference reproduction, the m3 tallies, the 6(b) classes plus BLOCKS MERGE, the 6(d) title and structure checks, 6(e), and the cleared list; `repro` writes `repro.md` and compares outcome, the 5-tuple per track, breaks and the encore filename.
- ❌ `repro` has no library-root `--out` guard (`scripts/short_keep_probe.py:323-326`). It only refuses an `--out` that overlaps the `--pre` or `--post` file. The brief's Step 3 ("read-only; refuses an `--out` overlapping the config's library root, as `replay_holds._overlaps`") covers the whole script. Global constraints: never write `~/.llama`.
- ⚠️ I could not verify from this diff that `arm_r1.jsonl` built its `flags` the way `replay.Legs.flags` does (gather + vet + carried + brief). The brief says so (`dump.py:224`). If the reference was built otherwise, every show would report `flags differ`, which is loud, not silent. The controller should confirm it when the real candidate first runs.

Port check against `~/.llama-harness/piece45/spec/r1/m3_cmp.py`, side by side:
- These match m3: unchanged (files, titles and flags all equal), changed, files added, the cleared/added/flags-changed/same key, `bucket`, the lost/gained positional definitions (`short_keep_probe.py:207-213` vs m3 `lp`/`gp`), unres-new, and override shift (requires `ov_shows` and `bo != ao`).
- New classes (`low confidence remains`, `long single-set show`, `jerrybase closer`) are split out of m3's `other`, in the brief's order (`:221-234`).
- `nf` is the flags not in the base flags. Because `added` implies the base has no flags, this equals m3's all-flags. Low confidence is matched with `startswith`, not m3's `split(':')` equality. The reference flag is the bare string `low-confidence structure alignment`, so the two agree on this data.
- Deviations:
  - (a) `if not b.get("replayed"): continue` (`:186`) is new. It is inert: all 3983 `arm_base` rows have `replayed: true` (checked).
  - (b) `ov_title` and `ov_struct` are computed for unchanged shows too (`:192-198`, before the unchanged short-circuit). This is stricter than m3, and correct for structure, because "unchanged" never compares breaks.
  - (c) m3's `shows LOSING a file` counter is dropped (Minor, below).
- Shape checks on the real reference: sets are `1..5`/`encore`, segues are bool, `tracks[i].n == i+1` on every row, and the `ov.set_breaks` values are ints. `Show.set_breaks` holds 1-based track numbers, override breaks plus the encore (`stages/gather.py:1714`, `titles.py:543`). So `cf.index(f)+1 in breaks` (`:169`) is the right test, and mutation M3 confirms a test pins it.
- The `BLOCKS MERGE` rule is right (`:241-245`): a class outside the table gets exp 0 and blocks, including `override shift`; `n > 1.25*exp` blocks. Precedence (`:221-234`) follows the brief's order.
- `_base_flags` (`:99-103`) uses the `Legs.flags` order (`replay.py:350,365`: gather + vet + carried + brief) and keeps only `flag_family == "package"` stored flags.
- `repro` exits 1 on each of: a show in one arm only (`:333`), a replayable row lacking fields or with unequal per-track lengths (`:345-349`), any outcome/breaks/encore/track difference, and unreplayable rows that differ. Unreplayable rows with equal reasons are counted equal and listed.

### Strengths
- It is a clean, compact port. The m3 definitions are recognisable line for line, and the deviations are stricter, never looser.
- `_missing_fields` (`:79-85`) checks per-track lengths as well as key presence, so an arm whose lists have different lengths cannot zip down to the shorter one and compare silently. The refusal names the cause ("an arm from older code?").
- The 6(d) structure check reads each break as a base filename and looks it up in the candidate. That is exactly the spec's "falls after the same filename", and it runs on every override show, not only on changed ones.
- `test_reference_reproduction_per_show` uses a base that differs from r1, so it proves the reproduction compares against `arm_r1`, not the base. That is the non-circular check the implementer's synthetic real-data run could not provide.
- The `repro` parametrised cases are well chosen. `break` changes only `breaks`; `segue`, `source` and `outcome` each change only their own field.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **The reference-reproduction check is only pinned on 2 of its 6 fields.** `scripts/short_keep_probe.py:136-144`, test `scripts/test_short_keep_probe.py:~95-101`.
   - Mutation M1, in a scratch copy, deleted the `filenames`, `sets` and `segues` rows and the `flags` row. All 19 tests still pass.
   - So premise 1's check (spec 8.1: "a per-show diff against `r1/arm_r1.jsonl`") could silently stop comparing filenames, which is the very thing piece 4 changes, and no test would notice.
   - Fix: add one candidate per field to `test_reference_reproduction_per_show`, each differing from r1 in only that field (a filename, a set label, a segue, a flag), and assert the exact `"<slug>: <field> differ"` list.

2. **Added-hold class precedence ("first match wins") is untested.** `short_keep_probe.py:221-234`.
   - M2 swapped `positional rung lost` and `new unresolved track`, and all tests pass.
   - M6 relaxed `low confidence remains` from "every new flag" to "any new flag", and all tests pass.
   - `_added_case` (test `:~123-136`) builds only single-cause shows, and it never builds a `positional rung lost` case at all.
   - This matters on the real data: `ratdog-2007-08-12` carries low-confidence, structure, unresolved and research flags and must class as `positional rung lost`. A precedence bug moves counts between classes, and the 1.25x gate may or may not catch it.
   - Fix: add multi-cause shows to the test:
     - a positional-lost show that also has a new unresolved file, expected `positional rung lost`;
     - a show flagged low-confidence plus `unresolved track titles` with no new unresolved file, which must not be `low confidence remains`;
     - one positional-only case.

3. **The library-root `--out` guard is untested in `arms` and missing in `repro`.**
   - `arms` (`:254-261`): mutation M5 removed the library-root entry from the guard, and all tests pass. Only the reference-dir refusal is tested (test `:~214`).
   - `repro` (`:323-326`) has no library-root guard at all (the Spec Compliance ❌ above).
   - Fix: give `repro` an optional `--config` and call the same guard. Add a test for each subcommand that passes `--config` pointing at a tmp config whose `root` is a tmp dir, with `--out` inside it, and assert exit 2 and nothing written.

#### Minor (Nice to Have)

1. `_guard_out` falls back to `DEFAULT_ROOT` when `--config` is omitted (`short_keep_probe.py:256-257`).
   - `replay_holds.run` instead loads `DEFAULT_ROOT/config.toml` and uses its `root` (`replay_holds.py:213-218`), so a non-default `root` set in the default config is guarded there and not here.
   - Fix: use `load_config(cfg or DEFAULT_ROOT / "config.toml").root`.
2. m3's `shows LOSING a file` counter is not ported (`:200-204`; m3 `if set(bf) - set(af)`). In a keep-only change that number should be 0, and the tripwire's new drop reason is exactly what would make it non-zero. The count is cheap to keep.
3. Nothing in the tests tells apart a wrong order of vet and carried flags in `_base_flags` (mutation M4 survives). `test_base_consistency_counts_carried_package_flags` has `vet_flags=[]`. Give it a non-empty `vet_flags`.
4. Every case of `test_repro_compares_tracks_breaks_and_encore` asserts `"differences (" in repro.md`. That heading is always written, even as `differences (0)`, so the assertion is vacuous. Only `rc == 1` does the work. Assert on the specific diff line instead (for example `"s: breaks"`).
5. `repro` passes two empty arms (`{"shows": {}}`) with exit 0 and "0 equal": a check that compared nothing reports success.
   - `arms` refuses an arm that shares no show with the reference; `repro` should likewise refuse when both arms are empty, or when none of the shows is replayable.
6. `repro`'s overlap test refuses an `--out` that is an ancestor of the `--pre` or `--post` file (`:324-326`), for example `--out ~/.llama-harness/piece4` when `pre.json` lives there. This is over-strict, though harmless.
7. `{x for x in base if _has_ov(base[x])}` is rebuilt for every added show (`:224`). Hoist it out of the loop, as m3's `ov_shows` does.
8. TDD: by the implementer's own account, RED was shown only by removing the module, which gives a collection error. That is not evidence that each test fails for its intended reason. Mutations M1, M2, M5 and M6 above show where the tests do not fail on a broken implementation.

Checks run:
- I read `m3_cmp.py` side by side with `compare()`.
- I profiled the reference rows: replayed flags, set labels, segue types, `n` base and `ov` types (`arm_base.jsonl`, `arm_r1.jsonl`).
- I read `replay.ShowReplay`'s fill (`replay.py:533-564`), `Legs.flags` (`:350,365`), `titles.set_breaks` and `_sets_from_breaks`.
- I compared `replay_holds.run`'s guard.
- Mutations ran on a `git archive` copy at `/private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-junk-filter/c03ad18d-bb48-4421-b153-6a96191ad85b/scratchpad/t7mut`, with `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`, one directory per mutant. M3 failing proves the copy, not the worktree, was imported. Results:
  - M0: 19 passed.
  - M1 (drop 4 reproduction fields): 19 passed.
  - M2 (precedence swap): 19 passed.
  - M3 (break off-by-one): FAILED in `test_override_structure_moved_is_reported`.
  - M4 (flag order): 19 passed.
  - M5 (no library guard): 19 passed.
  - M6 (low-confidence all→any): 19 passed.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The port is faithful and the logic is correct on the real reference shapes. But the two checks that gate Checkpoint A, reference reproduction (premise 1) and added-hold class precedence (6(b)), can be broken with no test failing, and `repro` lacks the brief's library-root `--out` refusal. All three fixes are small and test-only, except the `repro` guard.
