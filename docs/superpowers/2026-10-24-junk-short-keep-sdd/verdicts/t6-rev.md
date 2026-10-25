### Spec Compliance

- ✅ Spec compliant. Every Interfaces item in the brief is in the diff, along with all eight named tests and two more.
  - Record fields: `replay.py` lines 66-70 (diff).
  - `--rekey-overrides`, with the re-key before the strip: `scripts/replay_holds.py:249-255` (diff).
  - Row keys `rekeyed`/`rekey_error` (:280-281) and the arm stamp `overrides_rekeyed` (:341).
  - `compare` accepts a re-keyed arm and then writes no apply lists: :407-414 and :432-436.
  - The overrides-validation refusal fires in `_gates`, before anything is written: :379-384.
  - The two probes translate filename values: `taper_probe.py:_to_position/_arm_filenames/_fix_applied` and `title_hygiene_probe.py:567-570`.
- ⚠️ Cannot verify from this diff: spec 4.2 says the harness re-key "imports the migration's own mapping function". The harness imports `override_keys.rekey_raw` (replay_holds.py:164). The controller should confirm that `scripts/rekey_overrides.py` (a later task) calls this same function and has no copy of its own.

### Checks run, one per named risk

- **The live library is never written.** `_shadow_full` writes only `shadow_root/d.name`, and reads `d/overrides.json` and `d/show.json`. `rekey_raw` deep-copies before it maps (override_keys.py:89-111). The test hashes the live file before and after (test_replay_holds.py:616). `compute_legs` does not appear in any +/- line of the diff.
- **The shadow path matches a direct replay.** With `--rekey-overrides` and no strip, every show goes through the shadow. `replay_show` and `compute_legs` read only `show`, `provenance`, `vetting`, `briefing_json` and `overrides` from the show workspace. `research` is read for digests only, which are computed on the real directory. All of these files are in `SHADOW_FILES`, and `state` and `digests` are re-derived from the real directory (:269-277). A rekey arm with no strip therefore differs from a direct replay only in `overrides.json`.
- **Re-key first, then strip, with no second algorithm.** `_rekeyed_data` takes the filenames from `show.json` `tracks[].filename` and calls `rekey_raw`. Only a `legacy` classification is re-keyed. A mixed file is passed through, so the replay refuses it loudly.
- **The refusal texts match what a replay records.** I ran the branch's `run --rekey-overrides` on the test fixture library in scratch, and `_overrides_invalid` was True for all three kinds:
  - legacy: `LlamaError: <slug>: overrides.json uses track-number keys; run the migration`
  - mixed: `LlamaError: <slug>: overrides.json mixes track-number and filename keys (...)`
  - dangling: `LlamaError: <slug>: overrides name files not in the track list: ...`, which the 200-character truncation cuts, but the matched prefix survives.
  - e37f670's `overrides.json unreadable` is matched as well.
  - A successful re-key gave `rekeyed: True` and `unreplayable: None`.
- **No false refusal on the existing evidence.** `~/.llama-harness/piece45/spec/r1/arm_base.jsonl` and `arm_r1.jsonl` contain no `overrides.json unreadable` text, so the new gate will not trip on that evidence.
- **Pairing and digests.** Both arms digest the real directory through `input_digests`, so a re-keyed candidate pairs with an unflagged base. The test asserts that the digest is the legacy file's bytes (test_replay_holds.py:631). `_gates` deliberately does not compare `overrides_rekeyed`. `_delta_kind` (replay_holds.py:1124) checks `stripped` for truthiness, so the `{}` that a rekey-only row now carries does not move a row into "would-hold on a fresh get".
- **The record fields come from the right objects.** Per-track fields come from `g.show.tracks`, `breaks` from `g.show.set_breaks`, and `flags` from `legs.flags`. Every field defaults to `[]`, and the one reader that cares (`_arm_filenames`) handles a base row that lacks them.
- **Probe translation.** `_to_position` maps a filename to `names.index(v) + 1` and leaves an int unchanged. It uses the row's replayed `filenames`, which is the same numbering as the `sets` being graded, so a show shifted by short-kept files falls to "renumbered target (not graded)" instead of being graded off by one. For a row with no `filenames`, the fallback reads `<arm root>/shows/<slug>/show.json` read-only.
- **Protected names.** I grepped the diff for every Global Constraints name. None appears in a +/- line.

### Strengths

- The refusal is placed in `_gates`, before `out.mkdir`, and matches on substring, so the `LlamaError: <slug>:` prefix and the `[:200]` truncation cannot hide a match. It names the shows on each arm separately.
- The digests stay the real file's, which is exactly what keeps a re-keyed candidate comparable while its apply lists are suppressed. The reason is commented in the code (:407-409).
- `rekey_raw` deep-copies, and `_rekeyed_data` returns the original `data` on any exception, so a failed re-key cannot leave a half-mapped file.
- The tests are good. The live-file hash check is real. The refusal test covers all four texts in both arm positions. The re-key-then-strip test asserts both the shadow contents and the filename-valued `stripped`.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)

1. **A failed re-key under a full strip is a measured row that `compare` never surfaces** (`replay_holds.py:249-255`). The brief says "copies the file unchanged". In fact the strip still pops the legacy keys after a failed re-key. With both strip options the shadow then holds no legacy value, so the replay succeeds. I measured this: `outcome: clears`, `rekey_error: "IndexError: track 99 outside 1..6"`, and `stripped` int-valued.
   - The replayed computation is identical to what a successful re-key plus strip would produce, so this is not a mis-measurement.
   - But `compare` neither gates on nor counts `rekey_error`, so a show the migration would refuse looks fine in a fresh-get arm.
   - With a partial strip, or as-is (the 6(a) candidate), it is loud: the legacy refusal makes compare exit 2.
   - Suggestion: add a `rekey errors: N (<slugs>)` line to `summary.txt`, or note this behaviour in the docstring.
2. **`taper_probe._fix_applied` can raise `TypeError`** (`taper_probe.py:739-740`). If a filename-valued `set_breaks` list mixes one file found in `names` with one that is not (for example, a file the new tripwire dropped), `sorted(got)` compares an int with a str. The failure is loud and rare, but it crashes `score`. Suggestion: return False when any translated value is still a str.
3. **The record test's assertions are mostly about shape** (`test_replay.py:120-136`).
   - `short_kept` is all False in the fixture.
   - `segues` and `breaks` are checked only for type and order, not compared with `gathered.show`.
   - A miswired `r.breaks = list(stored.set_breaks)` or `r.short_kept = [False]*n` would pass.
   - The code is a direct copy and I checked it by reading, so this is coverage only. Suggestion: assert `r.breaks` and `r.segues` against the gathered show, and add a fixture with one short-kept track.
4. **`title_hygiene_probe` writes a `stripped_positions` key that nothing reads** (:567-570). The probe compares no override values anywhere (`structure_override`/`title_override` are presence-only), so the brief's "translate before comparing" is met vacuously. The key is harmless as an extra record field. The `rekey` keyword added to `_shadow` (replay_holds.py:213-216) has no caller.
5. **`summary.txt` mentions re-keying only on the apply-lists line.** Unlike `disabled_slices`, it never states which arm was re-keyed. Suggestion: add `overrides re-keyed: base X, cand Y` next to the disabled-slices line.

### Assessment

**Task quality:** Approved

**Reasoning:** The re-key is a measurement-only shadow over the migration's own `rekey_raw`. It never writes the library and stays out of `compute_legs`. I confirmed by an actual run that `compare`'s validation gate matches the real refusal texts the replay produces, and that it fires before any write. The remaining items are a reporting gap for re-key failures under a strip, one rare loud crash in the probe, and test assertions that check shape where they could check values.
