Task 3 DONE (commit 162e7e3). Suite: 605 passed, 1 skipped.
Implemented: station.file_set_key_and_sizes + meta keys (total_duration_sec, voiced_profile, sizes); mp3info.mp3_seconds; pieces.estimate_frames/CLIP_FALLBACK_SECONDS/UNVOICED_CLIP_ALLOWANCE_SECONDS; scripts/probe_estimates.py.
TDD note: tests and implementation were written together; RED was not captured separately (honest disclosure). GREEN: 40 passed in the three files, then full suite.
Probe smoke: --help exit 0; ran on tmp fixtures (no cache -> "no eligible package has a cached analysis"; with cached analysis printed est/exact/diff; --time-one printed cold time, cache untouched).
Concerns: aacenc.extra_frames spawns ffmpeg with a tempfile (system temp, not the workspace); ShowAnalysis.meta now includes sizes (cache JSON slightly larger, no test affected).
