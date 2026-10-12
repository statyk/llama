### Spec Compliance
**Compliant.** The diff matches Task 2 Steps 1-10 line for line. I compared it hunk by hunk against `task-2-brief.md`. `aacenc.py`, `spike.py`, `test-in-debian12.sh` (mode 100755), `test_aacenc.py`, `test_spike.py` and the `.gitignore` `*.aac` line are verbatim. The only departures are the three orchestrator rulings plus one cosmetic change:
- `assert frames` was added at `test_aacenc.py:32` (diff 574).
- `from pathlib import Path  # noqa: F401` was added at `helpers.py:10`.
- No unused imports remain. I checked `spike.py` and `test_spike.py`: `adts`, `segment`, `json` and `np` are all used.
- `helpers.py` merges the `subprocess`/`numpy` imports into the top block instead of appending them mid-file. This is harmless.

Nothing is missing and nothing extra was added. The implementer explained the RED message difference (ImportError vs ModuleNotFoundError): it has the same cause.

**Does the spike exercise what the PASS criteria test?** I checked against the diff and with focused measurements, written to scratch and never into the live tree:
- **Segment boundaries cut by frame count.** `build` (spike.py, diff 370-380) slices one continuous frame list into `SEGMENT_FRAMES` (441) chunks. It pads the tail with silent frames to a whole segment, then calls `segment.assemble(n, frames)`. The test checks every segment's ID3 timestamp equals `grid.segment_timestamp(n)` and that it holds exactly 441 frames. Yes.
- **Phase-continuous segue.** `show_a` carries the phase from `a1` into `a2` at a sample that is not frame-aligned (`int(n*0.30)+337`). Only the outer edges are faded. The generator test is tight enough to catch a phase reset: with `phase=0.0` the jump is about 0.19, against a threshold of 0.0214. I also checked the encoded and decoded stream. The maximum per-sample step within ±0.1 s of the segue is 0.0198, which equals the analytic bound for a 0.25-amplitude 554 Hz sine. The encode adds no click, so anything a listener hears there comes from the player.
- **2 s show gap of pre-encoded silent frames.** `stream = frames_a + [silent]*gap_frames(2.0) + frames_b`, with show B in its own encode. Decoding a 6-minute build gave a gap interior of exactly 0.0. Silence ran 2.041 s from the last sample above 1e-3 to the first: 87 silent frames (2.02 s) plus B's priming frame, minus fades. The splice under test is the production splice: per-show encodes joined by repeated `silent_frame()` frames, which is what `FrameStore` does later in the plan.
- **2^33 wrap inside show B.** `n0 = WRAP_N - int(count*0.6)`, guarded by a `ValueError` if the wrap would land at or before `b_start`. For the operator's 12-minute build the wrap is at 430.08 s and show B runs from 290.06 to about 703 s, so it falls well inside B's continuous tone. `test_wrap_n_is_the_first_wrapped_segment` pins `WRAP_N`.
- **`live.m3u8` ends with `#EXT-X-ENDLIST`.** `live_playlist` appends it once `cur > last`, keeping the final 6-segment window. `serve` sets E so the window is full at start. The test covers the window, the sequence number and ENDLIST.
- **Frame-count model.** This matters for Task 9's `render_show`, which computes `expected = frames_for(padded, extra)` and raises `FrameCountDrift` on a mismatch. On the host (ffmpeg 8.1.1), `extra_frames() == 1` (just the priming frame). I also checked that the model holds on non-silent content, which the shipped tests never exercise because they encode only zeros. `show_a(36)` gave 1552/1552 frames, `show_a(61.3)` 2641/2641 and `show_b(47.7)` 2056/2056. Decoded length equals `count*10.24` exactly. ⚠️ The ffmpeg 5.1 value of `extra` was not recorded, only that it is consistent and that priming is 1024 (see Minor 1).
- The pinned `hls.js@1.7.3` CDN URL returns HTTP 200.

### Strengths
- The spike isolates the right variable. The offline decode of the assembled stream is click-free at the segue, the segment cuts and the gap, so any artefact a human hears is attributable to player/container handling. That is exactly what the checkpoint is meant to decide.
- It uses the production `grid`/`adts`/`segment`/`aacenc` modules rather than a mock path. The build is deterministic in its segment bytes (the implementer re-ran it twice), and the operator offsets come from `meta.json`, so they cannot drift from what was built.
- `AacFileEncoder` writes stdout to a temp file and stderr to an anonymous file, so it cannot deadlock on a pipe. `mkstemp` in the target dir plus `os.replace` matches the atomic-write constraint. `abort()` and the failed-close path remove the temp file, and both tests assert the directory ends up clean.
- `extra_frames()` measures the model instead of assuming it. `test_extra_frames_is_the_same_for_every_padded_length` (3/441/1000 frames) and the priming impulse test are the right pins, and both passed on Debian 12 / ffmpeg 5.1.9 / Python 3.11.2.
- Nothing needs Python 3.12 or later. The Debian runner correctly forwards `"$@"` through `sh -euc '...' sh "$@"`.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **Checkpoint procedure, not code: the ENDLIST criterion only checks what the listener hears, while the spend control depends on the player stopping its requests.** Step 11 point 5 says "every player stops cleanly, with no error loop". Spend is the strict surface, and the property the clock relies on is that a player *stops requesting* `live.m3u8` after ENDLIST. A player that goes quiet but keeps polling would pass point 5 by ear. The spike already produces the evidence: `serve` keeps `SimpleHTTPRequestHandler`'s default per-request stderr log (`log_message` is not overridden). I recommend the orchestrator add one line to the operator's checklist: "after ENDLIST, confirm in the `serve` terminal that `GET /live.m3u8` requests stop within about one target duration (per player)". Record that per player in the ledger. No code change is needed, and this does not block approval of the task code.

#### Minor (Nice to Have)
1. **The `extra_frames()` value on ffmpeg 5.1 was never recorded** (handback, "I did not record the numeric value"). The `aacenc.py` docstring (diff 70-71) says "1 on ffmpeg 8.1; the Debian 12 run checks 5.1", but the check only asserts consistency. Plan line 4626 computes `base = ... + ENCODER_PRIMING_SAMPLES`, which assumes the leading extra frame is the priming frame. Recording the 5.1 number (one `python -c` in the container) would remove the ⚠️. Task 9's `FrameCountDrift` guard limits the risk.
2. **Plan-mandated: `AacFileEncoder.__exit__` (diff 142-144) does nothing on a clean exit.** A `with` block that forgets `close()` leaves an ffmpeg child blocked on stdin and a `.k.aac.*.tmp` file in the target dir. The only planned caller (`render_show`, plan line 3949) uses an explicit `try/close/except BaseException: abort`, so this is a footgun rather than a live bug. Possible fix: on a clean exit, call `abort()` if the encoder is not closed.
3. **`AacFileEncoder.close()` is not idempotent and can leak its temp file.** A second `close()` raises `FileNotFoundError` from `os.replace`. If `os.replace` itself fails, `_closed` is already True, so a following `abort()` is a no-op and the `.tmp` file stays. Also, `write()` wraps only `BrokenPipeError`, not other `OSError`s, in `EncodeError`. All of these are edge cases.
4. **The shipped tests check the frame-count model only on digital silence.** A one-line assertion in `build` (frames from `encode_pcm` == `frames_for(len(padded), extra_frames())` for shows A and B) would pin it on real content for free. I measured that it holds on 8.1.
5. **Small test gaps.**
   - `test_build_...` asserts `wrap_at_s > show_b_at_s` but not that the wrap is before the end of show B, i.e. not inside the trailing silent pad. That is impossible with the current `0.6` factor, but the test does not pin it.
   - `test_live_playlist_window_and_endlist` does not test the `cur == last` (no ENDLIST yet) and `cur == last+1` (first ENDLIST) edges.
6. **Debian runner over-copies** (`test-in-debian12.sh:12-13`). `--exclude=./.venv` does not match `./.venv311`, which is 72 MB (the implementer flagged this), and `./.superpowers/` (ledger plus the ~11 MB spike output) is copied too. The fix is `--exclude='./.venv*' --exclude=./.superpowers`.
7. **The printed offsets are in PCM time.** Decoded VOD time is about 23 ms (one priming frame) later at the segue and inside each show. The `serve` banner says the live playlist "starts at the beginning", but players join about 3 segments behind the live edge, roughly 20-30 s in. Neither matters for seek-and-listen, and the segue is still reached in live.

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation is verbatim to the brief plus the three rulings. Measurement confirms the spike actually exercises frame-count segment cuts, a click-free segue, an exactly-silent 2.04 s gap from repeated silent frames, a wrap inside show B and a live ENDLIST, with the frame-count model holding on real content. The one Important item is an addition to the operator's Step 11 checklist (watch for `live.m3u8` polling stopping), not a code fix.
