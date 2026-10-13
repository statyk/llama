### Spec Compliance
- ✅ Spec compliant. `_process_one` (cli.py:228-282) runs in this order: `pkg.manifest()`, then `resolve_assignment`, then `speech_for` (cli.py:246-248), then `try:` `speech.preflight()`, then the `--fresh` unlink and the `re-rolling` echo, then `rewrite_manifest(..., None, None)`, then `process_package`, with `finally:` a best-effort `close()`. This matches the brief and spec section 2 (spec lines 211-230) word for word. `voice_cmd` keeps stem validation and dedupe (cli.py:481-492) and passes `fresh=stems` (cli.py:495). The protocol method is at provider.py:+61. Voxtral and ElevenLabs have no-op `preflight`. `FakeSpeechProvider(preflight_fail=)` / `preflight_calls` match the brief exactly. The `TaggedProvider` double gained `preflight`. The help text is updated.
- ⚠️ Cannot verify from this diff: the mlx_audio provider's real preflight belongs to a later task. The verification layer's delegation of `preflight()` (spec line 259) is also later work.

### Strengths
- Strict surface 2 holds on both entry paths. `run` (cli.py:404) and `voice` (cli.py:495) are the only two callers of `_process_one`, and both go through the reordered body. `run`'s per-package `except Exception` (cli.py:405-410) makes a preflight failure a per-package error, as the spec requires.
- `close()` runs on every exit path once a provider exists. The `try` now starts right after `speech_for` and covers preflight, the unlink, the clear and `process_package`. If `speech_for` raises there is no provider to close.
- The order test is set up well. The `Spy` checks the clip still exists *at the moment preflight runs*, and `rewrite_manifest` is spied to confirm the clear comes after (test_voice_cmd.py:566-593). The failure tests assert the manifest bytes, the clip bytes, that the LLM was not called (`provider_for` is set to raise and record) and that no `re-rolling` echo appears. That covers every strict-surface-2 artifact.
- Ruling C3 is respected. The no-op test has no unused fixtures and adds `is None` assertions (test_tts.py:+284-290).
- The JUDGMENT CALL comment was trimmed and moved to its new place. It now names preflight as one of the things that must succeed first.

Named risks checked:
1. *Every path into `_process_one`.* I grepped `_process_one` in emcee src: only cli.py:404 (run) and cli.py:495 (voice) call it. Both are covered.
2. *Every test double reaching `_process_one` has `preflight`.* I grepped `def synthesize` across the tests. The only other duplicate-protocol doubles are three in test_audio.py (lines 183, 680, 742). That file only calls `process_package` directly (test_audio.py:35, 256), never `_process_one`, so these doubles never hit the preflight call. `TaggedProvider` (test_run_cmd.py:301) has it. Every other route produces a `FakeSpeechProvider` or a subclass of it.
3. *Provider closed on every exit path.* Read at cli.py:249-282. See Strengths.
4. *`--fresh` validated before, unlinked after.* Validation and dedupe are at cli.py:481-492, before the call. The unlink is at cli.py:+254-257, after preflight. Confirmed.
5. *`speech_for` callers outside `_process_one`* (process.py:147, 155, both inside `ad_hoc_speech`, which serves `emcee say`). They correctly do not preflight, per spec line 225.

### Issues
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. **No test pins close-on-preflight-failure.** cli.py:249-250. If someone moved `speech.preflight()` above the `try:`, no test would fail. That would leak the provider's httpx client and, later, the mlx provider's resources. A fix is a few lines: arm a `FakeSpeechProvider(preflight_fail=True)` subclass that records `close()`, then assert it was closed after `_process_one` raises.
2. **`voice_cmd`'s docstring is slightly stale.** cli.py:460-461 says the manifest is cleared "(once presenter/voice resolution has already succeeded)". It should now say resolution *and the TTS preflight*, to match the `_process_one` docstring and the updated `--fresh` help.
3. **`import pytest` sits mid-module.** test_voice_cmd.py:501, along with three `from emcee...` imports at 503-505, all inside the appended block. The brief said to add it "to test_voice_cmd.py's imports if absent". It works, but module-level imports in the middle of the file are E402-style clutter. Consider moving them to the top import block (lines 11-22).
4. **No `emcee run`-level test of a failed preflight.** Nothing checks that a failed preflight leaves package A untouched and that `run` carries on to package B. The `_process_one` direct test plus `run`'s existing generic `except` make this low-risk. It is a coverage gap only.

The added dry-run test (test_run_cmd.py:+772-793) was ordered by controller ruling and is outside this task's spec. It is correct as written: the pinned row expects the `[voxtral <model>]` suffix and the unpinned row expects none.

### Assessment
**Task quality:** Approved
**Reasoning:** The reorder exactly matches the spec on both callers. The provider is closed on every path after construction, and the strict-surface-2 tests check bytes on disk and that the LLM was not called, not just mocks. The remaining items are a missing close-path test and documentation and import tidiness.
