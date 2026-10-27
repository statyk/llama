# t5-rerev1: re-review of t5-fix1 (21db2638..f105fb96)

### Finding Verdicts
- **I1 (collapse before `_locate_block` untested): ADDRESSED** — packages/emcee/tests/test_audio.py:1053-1061 (f105fb96). The blocked half now uses a text with mid-sentence wraps ("...in the\nspring of 1974.", "long\njam after Truckin'."), so `_split_sentences` cannot remove the "\n" by splitting; it asserts >1 calls, no "\n" in any provider call, and no "\n" in `ei.value.text`.
  Independent mutation in a scratch copy of f105fb96 (`emcee.__file__` resolved inside the scratch tree; PYTHONDONTWRITEBYTECODE, `-p no:cacheprovider`). Baseline: the test passes. PREDICTION, logged before the run: mutant M1 (collapse kept for `_render`, the original text passed to `_locate_block`) fails this test on the newline asserts. Observed: it failed at `assert all("\n" not in c for c in blocked.calls)`. Under M1 the whole emcee suite gave 1 failed (exactly this test), 1003 passed. Why it holds: under M1 the probe "Tonight ... in the\nspring of 1974." carries "\n", and "long\njam" no longer contains "long jam". Every probe then passes, so a whole_passage SpeechBlocked carrying the original newline text comes back, which the `ei.value.text` assert also catches.
  The implementer's evidence is in order: t5-fix1.log line 3 is the PREDICT line, written before the mutant run on line 4-5, and the mutant matches the finding's. Their result agrees with mine.
- **`_key` unused `monkeypatch` param removed** (test_audio.py:1013): correct. All call sites pass two arguments; nothing breaks.

### New Breakage in the Fix Diff
None. The change touches only the test, and the first half (the `speech.calls == [f"{P1} {P2}"]` send check) is unchanged.

### Out-of-Scope Observations
- Process: per t5-fix1/handback.md ("Restored with git checkout"), the implementer applied the mutant in the LIVE worktree. Mandate 5 forbids that. Porcelain was reported clean afterwards, so there is no lasting damage, but the manager may want to restate the mandate.
- Optional tightening, non-blocking: the test could also assert `"long jam" in ei.value.text` and `not ei.value.whole_passage`. That would pin that location succeeded on the collapsed text, not just that no newline leaked. The current asserts already kill the finding's mutant.

### Verdict: all findings addressed
