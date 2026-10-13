### Spec Compliance
- ✅ Spec compliant. The diff matches the brief nearly verbatim in all 9 files:
  - factory: `packages/emcee/src/emcee/tts/__init__.py:14-49`. Every argument is required and the last three are keyword-only with no defaults. It builds only `resolution.backend`, and model, key and key_hint come from the resolution.
  - providers' `key_hint`: `voxtral.py:66,77` and `elevenlabs.py:29,34`.
  - `speech_for` and `ad_hoc_speech`: `process.py:88-156`.
  - conftest: `tests/conftest.py`.
  - test rewrites in test_tts, test_process and test_run_cmd.
- Controller ruling C1, part 1 (docstring) landed. The two "voice or voice_clone" sentences are rewritten (`process.py` diff lines 106-116). They now say `presenter.voice` is passed as `voice` and `presenter.voice_clone` as `clone_ref`, and the house fields are passed the same way. That matches the new body. The brief's Resolution paragraph is appended.
- C1, part 2 (test) landed. `test_pinned_presenter_under_an_mlx_house_resolves_to_its_pin` (`tests/test_resolve.py:526-531`) asserts backend voxtral, model VOX_DEFAULT, presenter "phil", pinned True and key_sources `("[tts.voxtral] api_key",)`.
- Named risk: "a missed call site constructs a backend other than the resolved one." I grepped `packages/emcee/src` for `speech_provider_for`, `speech_for(`, `ad_hoc_speech(`, the three provider constructors, `tts.backend`, `tts.api_key` and `tts.model`:
  - Providers are constructed only inside the factory (`tts/__init__.py:32,37,47`).
  - The factory is called only from `process.py:122,150,153`, and each call passes a `resolve_tts` result and all three keywords.
  - The two `cli.py` callers (`:237` `_process_one` to `speech_for`, `:537` `say` to `ad_hoc_speech`) go through those.
  - `tts.backend`, `tts.model` and `tts.api_key` are read only in `tts/resolve.py:44,70,71`.
  - An mlx_audio resolution reaches `raise SpeechError("unknown TTS backend ...")`, so it fails rather than falling back, which is expected before Task 9.
  - `say` passing no `clone_text` (`cli.py:537`) is expected; that flag is Task 14.
- Named risk: "the new autouse conftest strips keys that emcee live tests need." I grepped emcee tests for `mark.live`: there are no emcee live tests, so nothing is affected.
- ⚠️ Cannot verify from this diff: the strict-surface-2 ordering against the `--fresh` unlink is not touched by this task. The added docstring's claim of "before `_process_one` clears the manifest" does hold: `cli.py:237` comes before the clear, which is documented right after it.

### Strengths
- The factory's required keyword-only signature is pinned by `test_factory_arguments_are_required_keywords`, so an unmigrated positional call fails with TypeError. The implementer's RED run shows exactly that.
- Missing-key tests compare full-string equality, for both the house case (subtable or legacy) and the pinned case (subtable only). They do not use substring matches.
- The `_recorder` double captures the backend and presenter id from the resolution. So the test_process tests check that the resolver was actually consulted, not just that the voice fields were forwarded. The "house clone and transcript never bleed into a presenter" case asserts `clone_text is None` too.
- `ad_hoc_speech --presenter` now goes through `speech_for` instead of duplicating its voice selection. That removes a second copy of the presenter-voice rule, which could otherwise drift.
- The test-double migrations in test_run_cmd use the full new signature rather than `*a, **k`, so they would catch a future signature drift.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **ElevenLabs clone error misreads for `say --clone`** (`tts/__init__.py:40-43`). The message says "a voice_clone resolves to the elevenlabs backend". From `emcee say --clone x.wav` on an elevenlabs house, the operator never set a voice_clone, so the wording points at the wrong cause. This is the wording the brief mandates, and the required substring "voice cloning is not available on elevenlabs" would survive a rewording. A small polish to fold into Task 14 when `say` grows `--clone-text`.
2. **`Presenter.voice_id` is now dead in src** (`presenters.py:63`). Its only remaining callers are tests; the implementer flagged this. Remove it in a cleanup or leave it; it is harmless.
3. **Unreachable fallback** (`tts/__init__.py:30`). The `or "[tts] api_key"` fallback in `key_hint` can only fire when `key_sources` is empty: fake, unknown or mlx backends. None of those builds a hosted provider. It is harmless, but it implies a path that does not exist.
4. **Pin test checks only the backend** (`tests/test_process.py:432-439`). `test_speech_for_honors_a_presenter_pin` asserts only `calls[0][0] == "voxtral"`. Asserting the whole tuple, as its siblings do, would also pin the presenter id and voice. This is a coverage nicety.

Test output: the implementer's full run shows 2691 passed, 1 skipped, 7 deselected and 26 warnings, all of them the baseline fork() warnings. There is no new noise. I re-ran nothing; no doubt arose that the existing runs leave open.

### Assessment
**Task quality:** Approved
**Reasoning:** Every provider construction in emcee's src now goes through one resolution-driven factory with required keyword arguments, and an mlx resolution fails rather than falling back. Both controller rulings landed, and the tests check resolver use and exact error strings, not just mock forwarding.
