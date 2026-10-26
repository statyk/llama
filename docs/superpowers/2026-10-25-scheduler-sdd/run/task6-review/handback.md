### Spec Compliance

✅ **Spec-compliant.** Everything the brief asks for is there: `Piece`, `LengthCache`, `build_pool` and `scan_delivered`, with the controller's additions (live `Show.meta`, `OSError` → `CLIP_FALLBACK_SECONDS`, read-only never analyses or writes). Nothing requested is missing and nothing is misread. There is one small addition beyond the brief (the summed-`duration_sec` fallback, Minor 1). It does not contradict the spec.

- **Piece** (`pieces.py` `Piece`): every field and derived property the brief lists is present. Every property reads the live `self.show.meta`; none reads a cached `ShowAnalysis.meta`. `package` is the slug for a show and None for a clip. `role` is `"show"` for a show, else `meta["role"]`. `profile` is `meta["voiced_profile"]`. `pieces.Piece` does not collide with `layout.Piece`: `pieces` imports `render`, but nothing imports `pieces`.
- **LengthCache**, named risk (a). I read `length()` against `render.planned_frames` and `analysis.load_cached`:
  - An exact count found in the cache is memoised by key, and `mark_exact` wins over everything.
  - The cache is checked before the estimate memo, so an analysis written later by another path upgrades an earlier estimate.
  - `cache_dir=None` does no lookups (tested).
  - The exact count is `render.planned_frames(cached, pause_samples, extra)`. That is the same function `Station.planned_frames` uses (`pipeline.py:114-116`). Matching the pipeline's `pause_samples` and `engine.extra_frames()` depends on the caller (⚠️ Task 11 wiring; the diff cannot show it).
  - Estimates use `_safe_mp3_seconds`. `mp3_seconds` does raise `FileNotFoundError` on a missing file (`mp3info.py:35`), so `test_vanished_clip_counts_the_fallback` really tells the fixed code from the broken one.
- **build_pool**, named risk (b):
  - A clip is analysed only when `lengths` does not already know it exactly, and the result is `mark_exact`ed.
  - A `TransmitterError` drops the clip and returns it with its error.
  - Any other exception type propagates. For example, `write_json` hitting an `OSError` inside `load_or_analyze`. The brief asks for exactly this.
  - `read_only=True` never calls `analyze_clip`, and `LengthCache` never writes, so `cache/` is untouched.
  - `analyze_clip` is enforced with a `ValueError` unless `read_only`.
  - `dir` is `show.dir.name` for shows and `clip_dir` for clips.
- **scan_delivered**, named risk (d):
  - Dot dirs are skipped.
  - An unreadable, non-object, pre-v3 or bool-version manifest is skipped.
  - A package `evaluate` accepts uses its own `Show` (file-set key) and `estimate_frames`.
  - Every other package gets a manifest-only `Show` with key `m-` + `sha256("{mtime_ns}:{size}")[:20]`, and an estimate of total + 240 s. All pieces are `exact=False`.
  - It never decodes (only MP3 headers are read) and never writes.
  - The 240 s allowance also applies to voiced-but-ineligible packages, as the brief says ("unvoiced, or not yet eligible").
- **Manifest-only Show feeding `estimate_frames`**, named risk (e): `estimate_frames` reads `sizes.get(e.path)`, so an empty `sizes` gives `None` (it falls back to `stat`), not a `KeyError`. No crash.
- **Summed-`duration_sec` fallback**, named risk (d): it does not contradict the spec. The spec's "counts an unmeasured track as 0 ... Accepted" describes a `total_duration_sec` that is present but undercounts. The fallback only fires when the field is absent or invalid. It is still inconsistent with the eligible branch of the same function (Minor 1).
- ⚠️ The diff cannot show the following:
  - whether Task 11 builds `LengthCache` with the Station's `pause_samples`/`extra_frames()`;
  - whether the `--library delivered` caller wants cached exact counts for eligible packages. The spec says "exact when its analysis is cached". The brief's `scan_delivered` has no `cache_dir` and always estimates. That follows the brief, but a caller wanting exact counts must re-look them up by `piece.key`.

### Strengths

- `_safe_mp3_seconds` is a small, well-scoped wrapper, injected through the existing `clip_seconds` seam rather than by changing `estimate_frames`' default.
- `scan_delivered` calls `station.evaluate` first, so the two library paths share one notion of eligibility and one key. The test pins `key == evaluate(...).key` and the `m-` prefix being absent.
- The tests catch real mistakes. Reading each one, a plausible wrong implementation fails it:
  - `analyze_clip=lambda c: 1/0` fails if read-only ever analyses, and fails if an already-known clip is re-analysed;
  - the `pkg` dir name differs from the `"s"` slug;
  - the clip that has vanished really is missing on disk;
  - the 3600 + 240 frame count is exact.
- The focused run is clean: 17 passed in 0.10 s, with no warnings or noise.
- `_date_parts` refuses malformed dates instead of half-parsing them.

### Issues

#### Critical
None.

#### Important
None.

#### Minor

1. **The summed-duration fallback is inconsistent and untested.**
   - Where: `pieces.py`, `_manifest_show`, the `total = sum(t["duration_sec"] ...)` branch.
   - What: when `total_duration_sec` is missing or invalid, a manifest-only Show sums the tracks' `duration_sec` and stores that sum as `meta["total_duration_sec"]`. The eligible branch of the same `scan_delivered` counts a missing total as 0 (`estimate_frames`; `test_missing_total_duration_counts_zero`). `station.evaluate` stores `None` there.
   - Effect: in one rehearsal, two packages that both lack the field are estimated by different rules, and a fabricated value sits in the meta key that the live scan reserves for the manifest's own number.
   - Why it is only Minor: a v3 manifest written by llama always carries the field, so the branch is practically dead.
   - No test covers it. My probe confirmed it fires (manifest total `null` gives `meta["total_duration_sec"] == 180.0`).
   - Fix: either count 0 (or keep `None` in meta and use 0 for the estimate), matching `estimate_frames` and the spec's undercount stance; or keep the fallback, use it on both branches, and test it.

2. **A malformed v3 manifest crashes the whole scan.**
   - Where: `pieces.py`, `scan_delivered` and `_manifest_show`; the `except (OSError, ValueError)` clause.
   - What: the scan crashes outright on a v3 manifest whose `show` or `source` is not an object (`AttributeError`), or whose `set_intros` holds a list value (`TypeError: unhashable`). Probe output: `show-str CRASH AttributeError`, `source-str CRASH AttributeError`, `intro-list CRASH TypeError`.
   - Why it is only Minor: `station.evaluate` already crashes the same way on `show: "x"` for a voiced package (probed), so this matches existing tolerance. llama writes manifests through pydantic. The command is a read-only rehearsal.
   - Fix (optional): add `isinstance(..., dict)` guards matching the ones already used for `dj_audio`, or widen the per-package `except` to `(OSError, ValueError, TypeError, AttributeError)` so one bad package is skipped rather than ending the scan.

3. **Test gaps on the brief's own surface.**
   - Where: `test_pieces.py`.
   - The `m-` key is checked only for its prefix and length (22). A key built from the manifest's content, or from size alone, would pass. Fix: assert the key equals `"m-" + sha256(f"{st.st_mtime_ns}:{st.st_size}")[:20]`.
   - The voiced-but-ineligible branch is untested. That covers clip entries from `set_intros`/`outro`, the `voiced_profile` taken from `dj_audio.profile`, and the allowance on top.
   - `Piece.date`/`year`/`month_day` are not tested on an odd date (`"1977"`, `"1977-5-8"`, `"1977-05-08T..."`).
   - Fix: add a test for each of these.

4. **Entry order in a manifest-only Show is not broadcast order.**
   - Where: `pieces.py`, `_manifest_show`.
   - What: entries are all intros, then all tracks, then the outro. A real `broadcast.m3u` puts each set's intro before its own set. Nothing uses these entries for frames today, since the allowance path ignores them.
   - Risk: if a later caller ever passed such a Show to `estimate_frames` or a layout, it would count the joins wrongly and stat clips without sizes.
   - Fix: a one-line docstring note that these entries are descriptive only, or omit the clip entries.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation follows the brief and the controller's additions on every named risk.
- Exact counts come only from a cached or freshly done analysis, through the same `render.planned_frames` the pipeline uses.
- Read-only paths never analyse and never write.
- Clip analysis failures of type `TransmitterError` are returned, not raised.
- Unvoiced and ineligible packages get the spec'd `m-` key and the 240 s allowance.

The open points are Minor. They are an inconsistency in a practically dead branch, a crash class `evaluate` already has, test gaps, and a descriptive-only entry order. None of them can put an estimate into a written plan row or a write into a read-only path.
