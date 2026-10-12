### Spec Compliance

- ❌ Issues found (one; everything else in the brief + rulings R1-R3 is implemented):
  - fallback.py:104-119 `upload_fallback` rewrites `state/horizon.json` without `check_epoch(state, p.epoch)`, which both sibling horizon writers run (publish.py:247 `publish_batch`, publish.py:350 `prune`). Inherited from the brief's listing, which omits it too. Details under Important.
- ✅ R1 (high-water rule): fallback.py:111-117 skips the horizon PUT when `high_water > last`. It still uploads the segments, notice and index.json, records the version (fallback.py:108), never saves state and never moves high_water. Both branches are tested (test_fallback.py:83-104). This matches publish.py:290/354. A crash in prune between its horizon PUT and its save is benign here: deletes follow the save (publish.py:376-381), so an older `first` still names existing keys.
- ✅ R2: fallback.py:65-66 runs `require_station_format` on every encoded frame. test_fallback.py:33-47 checks that each segment and the notice, with and without a notice, tile exactly into 441 whole station-format frames (`frame_offsets[-1] == len(body)`, `frame_length == len(f)`).
- ✅ R3: the tests use `make_publisher`, whose epoch is helpers.py:145 `E = 4_000_000_000 * 1_000_000`. No unused plan imports; `id3`/`load_publish_state` are used.
- ✅ Ordering: index.json goes up last among the fallback objects (fallback.py:105-107). The version is recorded only after index.json returns 200, so `publish_batch` (publish.py:313) never carries a version whose objects are missing. The horizon comes last, with the exact put order asserted (test_fallback.py:72-74). The guard is checked before any PUT (fallback.py:102-103; test :113-119).
- ✅ Cache-Control: segments, notice and index.json all use `IMMUTABLE`; the horizon uses `STATE_CACHE` (fallback.py:105-107, 118-119).
- ⚠️ Cannot verify from diff: the Debian-12 gate (Python 3.11 / ffmpeg 5.1.9) is the implementer's claim. Its output is not in the handback beyond the counts.

### Strengths
- R1 is implemented the way the publisher implements it, and the log explains the deferral (fallback.py:111-117). Tests pin both `high_water > last` and `high_water == last`.
- The frame-count invariant fails closed with `EncodeError` (fallback.py:62-64) instead of shipping a short or long segment.
- The content-addressed version covers every segment and the notice, and the test pins determinism plus notice sensitivity (test_fallback.py:50-53).
- Silent/absent notice: the zero PCM bypasses `_gained` (fallback.py:80-81). Silence elsewhere is unity gain via `gain_db(i_lufs=None)` (analysis.py:57).

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
- fallback.py:109-119: the horizon is rewritten without the epoch check.
  - Failure: `load_or_create_epoch` (workspace.py:138) mints a new epoch whenever epoch.json is gone, which is the deliberate re-epoch operation. Publish state still carries the old epoch's `first/last`. `upload_fallback` then PUTs a horizon with the new `epoch_id`/`epoch` and the old `first/last` (`horizon_doc`, publish.py:176-179).
  - Impact: R2 lists `seg/<new>/100..200`, which do not exist, and the clock serves them, so players stall. This replaces a live horizon that still pointed at real segments. The constraints name "never list a segment that does not exist" as a stakes item. `publish_batch` and `prune` both refuse this case via `check_epoch`.
  - Fix: after `load_publish_state`, call `check_epoch(state, p.epoch)` before any PUT, so the command refuses like its siblings. Add a test with `PublishState(epoch_id="eold", first=100, last=200)` asserting PublishError and `bucket.puts() == []`. Expected red before the fix: that new test.

#### Minor (Nice to Have)
- test_fallback.py:75: only index.json's Cache-Control is asserted.
  - A mutant that put segments/notice under `STATE_CACHE`, or the horizon under `IMMUTABLE`, would survive. Not run; this is inferred from the assertions present. Constraints call for exact Cache-Control on fallback objects.
  - Fix: assert `CacheControl` for every `fallback/` key and `STATE_CACHE` for the horizon.
- fallback.py:98-119: `upload_fallback` returns None, so its caller (Task 14 CLI) cannot report whether the horizon was refreshed or deferred except through the log. Consider returning a bool or a small report. Optional, since the brief fixed the signature.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** Rendering, frame invariants and R1/R2/R3 are correct and well tested. The one horizon writer that skips `check_epoch` can, after a re-epoch, publish a horizon that lists segments that do not exist. That is a one-line fix with a one-test pin.

Checks run (no tests or mutants executed; the reading was unambiguous):
- Read publish.py `publish_batch`/`prune`/`check_epoch`/`horizon_doc`/`Uploader`/`guard_blocks_publishing` for the R1, epoch and ordering risks.
- Read state.py `PublishState`/`save_fallback_version` for atomicity and the high_water fields.
- Read workspace.py `load_or_create_epoch` to see how the epoch-mismatch case is reached.
- Read analysis.py `gain_db` and audio.py `LoudnessMeter.finish` for the silent-input risk.
- Read helpers.py:145 for R3's E.
