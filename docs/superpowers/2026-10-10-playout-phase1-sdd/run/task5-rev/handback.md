### Spec Compliance

Compliant. `station.py`, `test_station.py` and the `helpers.py` additions match the Task 5 brief line for line. The only deviation is `Callable` imported from `collections.abc` instead of `typing`, which is harmless. Orchestrator rulings are honoured: the existing `from pathlib import Path` in helpers.py is untouched, and there are no unused imports.

Plan review focus #1, checked against the diff:
- **NFS down on hugo.** `require_root` refuses a directory without `.station-root` with `StationRootError(... marker ...)` and never returns an empty library. `scan` calls it first (station.py `scan`, the first statement). It is pinned by `test_empty_root_without_marker_is_refused`, which goes through `scan` rather than `require_root`, so the wiring is pinned too.
- **Read-only.** Nothing in `station.py` writes, renames or unlinks anything.
- **`dj-audio/*.tmp` ignored.** Checked against emcee's real writer: `packages/emcee/src/emcee/workspace.py:23` names temp files `mkstemp(prefix=path.name + ".", suffix=".tmp")`, so `endswith(".tmp")` matches exactly. The test uses a name of that form with a fresh mtime, so it is a real behavioural test.
- **Vanishing file.** It becomes `Ineligible("changing: …")` on the quiet-period stat path and the `file_set_key` hash path. The read of `broadcast.m3u` is not covered (Important #1).

Eligibility checked against what emcee actually writes (named risk: transmitter's re-implementation drifting from emcee):
- `emcee/station.py:readiness` has the same four legs with the same reason wording.
- `emcee/audio.py:interleave_broadcast` writes `audio/<filename>` and `dj_audio` paths with their own `dj-audio/` prefix.
- `DJAudioBlock` has exactly `set_intros` and `outro`, plus `presenter`.

So `_clips`/`titles` key by the same strings that appear in `broadcast.m3u`, and every `dj-audio/` m3u entry from a real emcee package gets classified as a clip. emcee's `segments.json` sidecar lives in `dj-audio/` and is watched, which is correct: it updates as clips render.

### Strengths
- The root guard is tight and its error messages tell the operator what to check (NFS mount, marker).
- `_inside` resolves both sides. It rejects absolute paths, `..` traversal, and symlinks inside the package that point outside it. That last case is stricter than the tests demand, which is good.
- Version, notes, clip, track and m3u failures are all collected as reasons rather than stopping at the first, so `status` output will be useful.
- `file_set_key` runs only after every other check passes, and its `OSError` is caught.
- `scan` skips dot entries (llama's swap siblings, AppleDouble files) and directories without a manifest, and the test pins both.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **The `broadcast.m3u` read in `evaluate` is outside any try. A package that vanishes mid-scan can still crash the whole scan.** (Plan-mandated: the brief's code is verbatim.) In station.py `evaluate`, `if not m3u.exists(): … else: rels = read_m3u(m3u)` has no `OSError` guard. The manifest read earlier is guarded, so this is the one unguarded read.
   - **Trigger:** llama `rm`, or `deliver --replace-voiced` swapping the destination directory away between `m3u.exists()` and `read_text`. That raises `FileNotFoundError` out of `evaluate` and then out of `scan`, so it fails every show's evaluation for that tick, not just the changing one. That is the exact contract the review focus states: "a file vanishing mid-scan is Ineligible with a `changing: …` reason, never a crash".
   - **Severity:** the window is narrow, and the next tick retries.
   - **Fix (two lines):** `try: rels = read_m3u(m3u)` / `except (OSError, UnicodeDecodeError) as exc: return Ineligible(slug, (f"changing: {exc}",))`. `UnicodeDecodeError` is a `ValueError` and is also uncaught today; emcee always writes UTF-8, so only corruption triggers it.

#### Minor (Nice to Have)
1. **Python 3.11 (hugo) `Path.exists()` still raises `OSError` for errors other than ENOENT/ENOTDIR/EBADF/ELOOP.** That includes EACCES, ESTALE (a stale NFS handle) and EIO. 3.14 swallows all of them, so the dev suite cannot show the difference. The many `.exists()` calls in `evaluate` and `scan` therefore raise raw `OSError`, not `StationRootError` and not `Ineligible`, when the NFS share goes stale mid-scan. Also on 3.11, `_inside` → `Path.resolve()` raises `RuntimeError` on a symlink loop in an m3u entry. Consider wrapping the body of `evaluate` with `except (OSError, RuntimeError)` → `changing:`, or having callers map `OSError` from `scan` to a station-root failure. Whatever later tasks do with an exception out of `scan` decides how much this matters.
2. **Malformed-but-valid JSON can raise `AttributeError`.** `manifest.get("show") or {}` and `source` assume dicts, and `_clips` assumes `dj_audio` values are strings. A non-dict `show`/`source` raises `AttributeError` at the end of `evaluate`. emcee/llama write these, so the risk is low; `isinstance` guards would make "never a crash" total.
3. **Coverage gaps (the behaviour is correct as written):**
   - No test for a symlink inside the package pointing outside it, which `_inside` handles.
   - No test for the `changing:` path from `file_set_key` (the hash `OSError`); only the quiet-period stat path is exercised.
   - No test that a `dj-audio/` m3u entry not named in `dj_audio` falls back to kind `"track"`. That fallback would put speech into the music loudness measurement and the gapless track→track join. It cannot happen with emcee's writer; worth a comment, or an Ineligible reason ("m3u clip not in dj_audio"), rather than a silent reclassification.
4. **Inconsistent import source (style only).** `station.py` imports `Iterable` from `typing` while helpers.py uses `collections.abc`.

### Assessment
**Task quality:** Needs fixes
**Reasoning:** The implementation matches the brief exactly and gets the NFS guard, the `.tmp` filter and the emcee-shape correspondence right. One plan-mandated gap remains: the unguarded `broadcast.m3u` read breaks the stated "vanishing file is Ineligible, never a crash" contract and needs a two-line guard. The Minor items can be batched.
