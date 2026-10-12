# task8-fix1 handback — Status: DONE

Commit: 2309c67 (on top of 9fc3c57)

## Follow-up 1
render.py: the post-close() frame-count check is wrapped in `try/except BaseException`, which unlinks
out_path (missing_ok) and re-raises. This covers an AdtsError from frame_offsets, the read itself, and
FrameCountDrift. Error types are unchanged: FrameCountDrift stays FrameCountDrift, and AdtsError
propagates as-is, which makes it a TransmitterError.
Optional verify-before-rename: NOT done, because it would need a hook in AacFileEncoder (out of scope per
the ruling). The SIGKILL window between rename and verify therefore remains. Build_segment's frame_count
check still catches that case loudly as a LayoutError.

## Follow-up 2
The segue test now asserts `t1.samples + t2.samples == 6 * 44_100`.

## TDD
RED: the new test_unverifiable_encode_is_removed (monkeypatches adts.frame_offsets to raise AdtsError)
failed with `AssertionError: assert not out.exists()`; the encode was left at x.aac, as expected. The
new segue assertion passed immediately: the measured sum was already exactly 264600.
GREEN: 9/9 in test_render.

## Tests
- 3.14 / ffmpeg 8.1.1: 155 passed.
- 3.11 venv: 155 passed.
- Debian 12 (ffmpeg version 5.1.9-0+deb12u1, Python 3.11.2): 155 passed, rc 0.
- Full suite: 2304 passed, 7 deselected.

## Files
packages/transmitter/src/transmitter/render.py, packages/transmitter/tests_transmitter/test_render.py
