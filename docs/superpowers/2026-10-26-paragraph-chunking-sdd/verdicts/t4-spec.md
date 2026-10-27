# Task 4 spec-compliance review (8fa473df..6623bae5)

### Spec Compliance
- ✅ Spec compliant.
  - `Chunking` frozen dataclass (ceiling, room_tone), defined above `TTSConfig` (config.py diff hunk @@ -83), so the eager-annotation guard holds.
  - `chunk_chars: StrictInt = Field(default=250, ge=50, le=1000)` and `room_tone: bool = True`; `TTSConfig.chunking(*, enabled)` returns `Chunking(chunk_chars, room_tone)` or `None`. Matches the brief's interface and the spec's "strict integer, 50 to 1000, default 250" / "bool, default true".
  - Required keyword-only `chunking` with no default on `render_speech_mp3`, `_render`, `_segment_pcm`, `_synthesize_dj_audio` (`Chunking | None`) and `_chunked_pcm`, `_synthesize_chunked` (`Chunking`, never None). No `chunk` parameter remains in the chain.
  - Production callers, both explicit: process.py:307 `chunking=config.tts.chunking(enabled=config.tts.chunk)`; cli.py:733 (say) `chunking=config.tts.chunking(enabled=chunk)`, so `--chunk/--no-chunk` is unchanged and say takes chunk_chars/room_tone from config (spec "Settled at the builder check").
  - Behaviour preserved: `_chunked_pcm` body is unchanged apart from its signature (it still splits per `_split_sentences` and ignores ceiling/room_tone). The cache key is `chunk={chunking is not None}` (prints `True`/`False` exactly as before), and `loud_key` gates on `chunking is not None or bed is not None`. That is byte-identical for both the unchunked and the chunked keys, and the existing `test_cache_key_*` assertions (unchanged) pin it.
  - Template: `# chunk_chars = 250` and `# room_tone = true` sit commented after `# chunk = false` with the wording the brief asks for. `"chunk_chars"` and `"room_tone"` were added to the `test_default_config_template_mentions_every_section` markers (spec Acceptance). The `[tts] chunk` field comment no longer says "sentence-by-sentence".
  - Tests: `test_chunk_chars_defaults_and_bounds`, the parametrized rejection test `[49, 1001, "250", 250.0, 250.5, True]`, the TOML load-error test through `load_config` → `ConfigError`, `test_tts_chunking_helper` and `test_chunking_has_no_default` (KEYWORD_ONLY, `Parameter.empty`, no `chunk`) are all present as briefed. `helpers.py` gains `CHUNKED` and `SENTENCES` with the specified values.
  - No existing test assertion changed. I checked every test hunk: only call arguments changed (`chunk=True`→`chunking=CHUNKED`, `chunk=False`/omitted→`chunking=None`, direct `_chunked_pcm`/`_synthesize_chunked` calls→`CHUNKED`), plus the two fake signatures (test_recording.py:51, test_run_cmd.py:313) renamed `chunk=False`→`chunking=None` as the brief directs.
- ⚠️ Cannot verify from diff: none blocking. The implementer's 992-passed run (log line 15) is the evidence for the eager-annotation guard (`test_annotations_resolve_eagerly.py`) and the whole suite; I did not re-run it.

Named-risk checks run (outside the diff):
1. Risk: a production or script caller still passes `chunk=`, or calls a changed function without `chunking`. Check: `git grep` at HEAD for every changed function name and for `chunk=` across packages/ and scripts/. Result: there are exactly two production callers, process.py:306 and cli.py:732, and both pass `chunking` explicitly. The remaining `chunk=` hits are `TTSConfig(chunk=...)`/`_config(chunk=...)` config construction and the `_expected_key(chunk=...)` test helper, which are correct and untouched.
2. Risk: the brief lists test_say_cmd.py as a caller, but the diff never touches it (a Missing finding under the batched-files rule). Check: grep. test_say_cmd.py mentions `render_speech_mp3` only in its module docstring (line 4), and has no direct call, no monkeypatch with a `chunk` kwarg and no `chunk=`. Its CLI-level tests go through cli.py's now-explicit call. So no hunk was needed, and this is not a Missing finding.
3. Mutation evidence (binding rubric). Check: $D/t4-impl/t4-impl.log. Predictions are logged before each run (lines 16, 22). The first two runs were correctly declared invalid because BSD sed never applied the mutant (line 31), and both were redone. A gave exactly `test_chunking_has_no_default` (1 failed). B gave the predicted `["250"]` plus `[250.0]` and the TOML load-error test (3 failed). Each observed result plausibly follows from its edit: plain `int` lax-coerces "250" and 250.0. Accepted.

### Strengths
- The change is a tight mechanical refactor. The cache-key expression keeps the exact `chunk=True/False` text, so no existing clip is invalidated, and the unchanged `test_cache_key_*` tests prove it.
- `test_chunking_has_no_default` pins the spec's "no default anywhere" directly (kind, default and absence of `chunk`) over all four public and middle functions.
- The implementer was candid about the invalid sed runs and did not count them.

### Issues (spec only)
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
1. Process: the handback says the RED run from Step 2 was skipped (implementation came before the failing tests were run). Mutations A and B show the key tests bite, but nothing ever saw `test_tts_chunking_helper` or `test_chunk_chars_defaults_and_bounds` fail. Both are trivially correct by reading, so no action is needed beyond noting the deviation.
2. test_config.py `test_chunk_chars_bad_value_in_config_toml_is_a_load_error` covers only the string case through the loader. The spec names a string, a float and an out-of-range value as load errors. The float and out-of-range cases are covered at the model level (`ValidationError`) and go through the same `load_config` wrapping, so this is coverage breadth only. Parametrizing the TOML test over `'"250"'`, `250.0` and `1001` would pin all three spec cases end to end.
3. `room_tone: bool` uses pydantic's lax bool, so a TOML string such as `"yes"` would be accepted. The spec states no strictness for room_tone and the sibling `chunk: bool` behaves the same, so this is not a deviation. It is noted only so the omission is deliberate.

### Assessment
**Spec compliance:** Approved
