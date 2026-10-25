### Spec Compliance

- ✅ Spec compliant with the brief and the controller rulings, one Important reservation on how the tool fails (below). Checked:
  - `reuse-check` subcommand with `--cand`, `--sample 20`, `--seed 47`, `--config` and `--out`: scripts/short_keep_probe.py (the `rc = sub.add_parser("reuse-check")` hunk) and the dispatch-dict hunk.
  - Delivered unvoiced means a readable station `manifest.json` whose `dj_audio` is null or absent (`_delivered_unvoiced`). The candidate counts as changed when its kept filenames differ from the stored `show.json` filenames (`if list(row["filenames"]) == [...]: continue`). Both follow the rulings.
  - The sample is `random.Random(seed)` over the sorted changed slugs (`sample = sorted(changed); random.Random(args.seed).shuffle(sample)`). That follows the ruling.
  - `plan_reuse` is called with `<delivery_path>/<slug>`, the same station dir the real call sites pass (packages/llama/src/llama/cli.py:2711, reapply.py:150).
  - The per-file check copies `reuse_into` exactly (packages/llama/src/llama/audio_reuse.py, `reuse_into`): `length_seconds(meta length)`, then `is_file`, then `read_duration`, then `abs(real-exp) > DURATION_TOLERANCE_S`. This is the same expected-length source `build_package` uses (stages/package.py:76).
  - The byte sum covers ALL changed shows: metadata `size` of every candidate file not in `plan.station`. Because `_pair` is all-or-nothing, that is exactly the new files plus every file of an unpaired show, as the brief says.
  - Wall time uses `time.monotonic()` around `plan_reuse` plus the duration reads, as the ruling says.
  - `--out` is refused when it overlaps the library root, `delivery_path` or the candidate arm (`_guard_out(...)`).
  - Nothing is copied. The only `audio_reuse` call is `plan_reuse`, which only reads.
- ✅ Global constraints: the diff touches none of the protected names. `DURATION_TOLERANCE_S` is imported and read, never redefined.
- ⚠️ Identifier mismatch, checked. `build_package` pairs nothing when `reuse.identifier != show.identifier` (stages/package.py:63-66), and the tool does not model that. This is benign only because replay re-gathers under the stored identifier (replay.py:342), so a candidate row cannot change the item. The controller should confirm the candidate arm comes from `replay_holds` (no re-selection).
- ⚠️ The measurement covers the clean path only: `show.json` is still the pre-regather one when re-packaging runs, which is how plan_reuse is meant to be used. A held re-gather followed by `fix --overrule` (Review Focus 6) runs `plan_reuse` against the NEW `show.json`, so the station copy pairs nothing and everything re-downloads. The tool does not count that cost. It falls outside the brief, but whoever reads premise 6's number should know.

### Strengths

- The duration check is a line-for-line mirror of `reuse_into`, including its precondition order. The per-file fallback reasons are specific and testable, for example `length 130.0s vs metadata 100.0s` or `not paired`.
- Read-only by construction. It uses `CacheOnlyIA` (cache reads only, scripts' replay.py:39-60), `plan_reuse` (reads only) and `read_duration`, with no writer imported. `test_reuse_check_never_writes` hashes both trees, plants a library `package/audio` file to tempt the aside, and asserts `.audio-aside` is absent.
- `test_uncovered_bytes_sum` exercises every population boundary in one fixture: paired, foreign item, not delivered, voiced and unchanged. The asserted 570 can only come from the right inclusion set.
- The `--out` guard reuses `_guard_out` and adds `delivery_path`, which on the live config is the SMB station share `/Volumes/media/lma-radio/delivered/`.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)

1. **An unreachable station share reports "0 uncovered bytes" and exits 0.** scripts/short_keep_probe.py, `_delivered_unvoiced` (`except (OSError, ValueError): return False`) together with the loop's `if not _delivered_unvoiced(station): continue`.
   - What's wrong: `delivery_path` on the live config is an SMB mount. If the share is not mounted, or a read fails mid-scan, every show silently counts as "not delivered". Premise 6's figure then becomes 0, the best possible result, with exit 0.
   - Check I ran: a scratch config whose `delivery_path` does not exist, and a candidate row that changes a show's track list. Output: `changed delivered unvoiced shows: 0`, `uncovered bytes: 0`, `rc 0`. The evidence is in the t14-rev log.
   - Other silent exclusions bias the number the same way:
     - an unreadable `show.json` (`except Exception: continue`);
     - unreplayable candidate rows (`_unreplayable(row) ... continue`);
     - a metadata cache miss (`_file_meta`: `except Exception: return {}`, so every size counts as 0);
     - a missing or unparsable `size` (`_size` returns 0).
   - Why it matters: this is the affordability premise, and the tool's failure mode reads as a pass.
   - Fix:
     - Refuse when `station_root` is not an existing directory.
     - Tally each exclusion class into `reuse_check.md`: station dir present but manifest unreadable, `show.json` unreadable, unreplayable row, metadata miss, files with no size. A reader can then see what the number does not include.
     - Add a test for the missing-root refusal.

#### Minor (Nice to Have)

1. scripts/short_keep_probe.py, `reuse_check`'s first line (`cfg = load_config(args.config or ...)`). This runs before `_guard_out` checks that the config exists, and `load_config` returns `Config()` for a missing path (config.py:177-178). So a mistyped `--config` is refused as "the config has no delivery_path" instead of `no such config: ...`. Fix: call `_guard_out` first, or check existence first.
2. The byte sum is structural only. Paired files that would fail the duration check also re-download but are not counted. The report says so in the header line's definition, and that definition matches the brief. Optionally, add the sampled fallback bytes, or a fallback rate, next to the sum.
3. `plan_reuse` runs twice per sampled show, and the timed second call reads station manifests the first call already read. Over SMB that slightly understates premise 8's wall time. Timing the first call, or dropping the second, fixes it cheaply.
4. Library-side audio (a delivered show whose purge was skipped) is ignored. This errs toward overestimating the uncovered bytes, the safe direction, but the report header should say so.
5. Test gaps:
   - The `station file missing` and `no metadata length` branches have no test.
   - `--sample`/`--seed` selection is never asserted. `test_uncovered_bytes_sum` passes `--sample 1` but does not check that exactly one show is sampled, or which one.
   - Wall time is asserted only as the substring `"wall"`. A regex such as `wall \d+\.\d{3}s` would pin the format.
6. Import order: `from llama.workspace import ...` sits between the other `llama.*` imports and `from llama.replay import ...`. Cosmetic.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The pairing, duration check, population and sampling follow the brief and the rulings, and the tool is genuinely read-only. Its failure mode is the problem: an unmounted share, or a silently excluded show, yields a clean "0 uncovered bytes, exit 0". A measurement premise must refuse in that case, or at least report what it left out.
