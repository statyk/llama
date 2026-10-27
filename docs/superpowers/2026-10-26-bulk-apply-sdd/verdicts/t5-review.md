# Task 5 review (2ea940c9..f53a3931): station mark writer, deliver over a marked copy, --fixed

### Spec Compliance

- ✅ Spec compliant. I checked every brief interface and the binding plan/spec clauses against the diff:
  - `station_mark.py`: MARK_KEY and COMPARED match the brief verbatim (station_mark.py:44-47). StationRefused(LlamaError) and StationUnreadable(StationRefused) are there, with the text `<slug>: station copy unreadable: <detail>` on one line (:61-62). Also present: read_station_manifest, mark_of, destination_voiced (raises StationUnreadable on a missing dir or manifest, never "unvoiced"), write_mark, clear_mark, put_back (checks the sha first and again before the rename), manifest_differences and emcee_running.
  - The rewrite algorithm matches the pinned order (`_swap_in` :111-129, `_rewrite` :132-153). It reads the raw bytes and dict, adds or removes only MARK_KEY, keeps key order and the trailing newline, and writes a unique `xb` temp in the same directory, flushed with `catalog._flush_to_disk`. It re-reads the bytes right before `os.replace` and on a difference removes the temp and raises StationRefused. After the rename it re-reads and requires the other keys equal and MARK_KEY equal to the written value. On a mismatch it puts back only when the sha still equals its own bytes. It never touches `Manifest`. The residual window is documented in the module docstring.
  - Review Focus 1, before and after the rename: both covered by `test_write_mark_detects_a_concurrent_rewrite` and `test_write_mark_detects_a_rewrite_after_the_rename`. A third test covers the put-back-when-own-bytes branch. Either path raises StationRefused, so the caller sees the show as not marked.
  - deliver:
    - A marked destination always goes through `_replace_destination` (cli.py:2673).
    - `--replace-voiced` on a voiced, marked destination with `manifest_differences == []` raises the exact Contracts string (cli.py:2658-2664, `_EqualMarkedCopy`).
    - An unmarked voiced destination keeps today's route (pin test).
    - `--fixed` keeps a show only when it is not awaiting fix, its record is processed and its station copy is marked (cli.py:2706-2724). It counts in `other_selector`, so it combines with the other selectors and refuses `--replace-voiced` or a name (cli.py:2833).
  - campaign_gate: I compared it line by line with scripts/rekey_overrides.py:352-453. It is a faithful port with the tool as a parameter, and the script is unchanged.
  - Global Constraints: models.py is not in the diff, so `Manifest` gained no field. I grepped the diff for every Untouched name: the only hit is cli.py's `catalog.purge_package_audio` call, an unchanged context line. Nothing imports emcee, and transmitter is untouched.
- Extra beyond the brief, all acceptable:
  - `tool_processes(..., self_script=None)` is an optional keyword, so the brief's signature still works.
  - The `scripts/*.py`-counts-as-tool rule is limited to llama (campaign_gate.py:22). The spec says the emcee check cannot see emcee-importing scripts.
  - `--fixed` keeps a show whose station copy is unreadable, so the batch lists it as refused.
  - `--fixed` with no station prints the existing no-dest string and exits 1.
- ⚠️ Cannot verify from this diff:
  - Task 15 must call `emcee_running()` before each `write_mark`. write_mark does not call it itself (implementer concern 3, consistent with the brief).
  - Task 15 must also handle a non-StationRefused OSError from the write side (Minor 2 below).

### Strengths
- The writer is small and reads straight against the spec. Temp cleanup happens on every exit (`except BaseException`). put_back reuses `_swap_in`, so it has the same pre-rename byte check.
- The tests assert behaviour on real files under tmp_path:
  - bytes, key order, the mtime change and no leftover temp;
  - the write+clear byte round trip on llama-format manifests;
  - all four unreadable shapes across all four entry points, with bytes compared before and after.
- I ran 7 of my own mutants, each with a predicted test named first, in a scratch copy. All 7 were caught, covering both Review Focus 1 branches and the put-back guard.
- The deliver tests check the whole station tree byte for byte (`tree_bytes`) for shows that must stay untouched, including the voiced, marked, processed show in the `--fixed` batch.
- Targeted run, from the worktree root with `llama.__file__` checked to be inside the worktree: `./.venv/bin/python -m pytest packages/llama/tests/test_station_mark.py packages/llama/tests/test_campaign_gate.py packages/llama/tests/test_deliver_cmd.py -q -p no:cacheprovider` gave 88 passed in 1.64 s with clean output.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **packages/llama/src/llama/station_mark.py:104, `ensure_ascii=False`: bytes change outside the mark on emcee-written manifests.**
   - emcee writes the manifest with `json.dumps(data, indent=2)`, which keeps ASCII escapes (emcee/package_io.py:83). Every voiced station copy with non-ASCII text therefore has `\uXXXX` escapes.
   - I checked this in a scratch dir with an emcee-format manifest containing "Café"/"Señor":
     - after `write_mark`, bytes outside the mark had changed (the escapes became raw UTF-8);
     - after `clear_mark`, the file did not return to emcee's original bytes.
   - Data is not affected: the dicts are equal and the spec's check is at dict level. But it widens marking's byte footprint on voiced copies, the ones most likely to stay marked. It also makes a byte diff against `campaign/station-backup/` noisy.
   - Fix: `ensure_ascii=before.isascii()`. This keeps both writers' bytes: llama's pydantic output is raw UTF-8, and a pure-ASCII file encodes the same either way. Add a round-trip test on an emcee-format fixture.
2. **station_mark.py:111-129 (`_swap_in`): write-side OSErrors escape raw instead of as StationRefused.**
   - Affected calls: `open(tmp, "xb")`, `_flush_to_disk`, `os.replace`. `test_write_mark_temp_is_removed_when_the_flush_fails` (tests/test_station_mark.py:183) pins the raw OSError.
   - Read errors map to StationUnreadable, but a write that fails because the mount dropped or the share went read-only does not. A Task 15 loop catching StationRefused per item would crash the marking batch rather than record the show as not marked.
   - The batch is idempotent and "a killed batch prints no list" is an accepted outcome, so this is not unsafe. Either wrap the OSError in `_swap_in` as StationRefused (retryable, nothing written), or make Task 15's per-item handler catch OSError. Hand this note to Task 15's brief.
3. **packages/llama/src/llama/cli.py:2710: the `_fixed_for_delivery` docstring overstates the lock re-check.**
   - It says "`_deliver_one` re-checks under the show lock", but only the awaiting-fix leg is re-checked. Station-marked and processed are not.
   - Harmless: a copy cleared between selection and delivery is delivered by today's route. Reword the docstring to "re-checks awaiting fix".
4. **cli.py:2658-2664: the equality refusal sits ahead of the gate.**
   - A held, voiced, marked, equal show is told `keep the voicing with: llama clear-mark <slug>`, and clear-mark refuses held shows (implementer concern 7). The text is the Contracts string, and the case needs a held show that is also processed-equal, so it is rare.
   - Option: skip the equality refusal when `deliver_refusals` would refuse, or keep the order and note it in Task 6's brief.
5. **station_mark.py:115: a SIGKILL between temp creation and `os.replace` leaves `.manifest.json.llama-<hex>.tmp` inside the station package dir.** Nothing sweeps it until a re-delivery replaces the directory wholesale. Readers open `manifest.json` by name, so it is harmless. The sweep could be added to `_sweep_swap_leftovers` (or Task 15's resume) at some point.

### Assessment

**Task quality:** Approved

**Reasoning:** The writer follows the pinned algorithm exactly. Both Review Focus 1 branches are caught by tests that pass in the code as built and fail under mutation. Deliver's marked-copy route, the equality refusal and `--fixed` match the spec and the fixed strings, and no untouched surface moved. The five findings are polish or hand-offs to later tasks: the encoding choice and the write-side OSError mapping are worth carrying into Task 15's brief.
