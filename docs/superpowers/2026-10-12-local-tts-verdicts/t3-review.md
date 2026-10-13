### Spec Compliance
- ✅ Spec compliant. `config.py` matches the brief's Step 3 code exactly: `HOSTED_BACKENDS` (config.py:~64), `HostedTTSConfig`, `MlxAudioConfig` (url `http://127.0.0.1:8000`, timeout_s 600, model/stt_model None), `VerifyBackend` Literal plus `VerifyConfig.backends = []` via default_factory, the four new `TTSConfig` fields (all default-constructed), and the `_check_keys_and_verify` after-validator (config.py:116). All four required error substrings are there word for word, so Tasks 4/5/9/11/13/14/15 can rely on the names, defaults and messages. All new models inherit `_StrictModel` (global constraint). Step 1's tests were added verbatim, plus the five new markers in `test_default_config_template_mentions_every_section` (test_config.py:~270). The template's `[tts]` portion now matches the brief's "must read" block line for line, including the two rewritten existing comments allowed by the controller ruling (voice_clone's "the house voice clones it" and the legacy model/key paragraph). Everything stays commented, and `test_default_config_template_matches_defaults` still guards that the parsed template equals the defaults.
- ⚠️ Cannot verify from the diff: the full-suite result (2657 passed, 1 skipped, 7 deselected; baseline 2635, +22). I took this from the implementer's report and did not re-run it, per the reviewer instructions. The +22 matches the count of new parametrized cases: 1+1+1+1+4+1+1+1+1+2+2+1+3+1+1 = 22.

### Strengths
- The models were transcribed faithfully. The validator branches give `mlx_audio`, the hosted backends and `fake`/other names separate treatment, so `fake` is never checked, which test fixtures depend on.
- Live-config risk checked: I compared KEY NAMES only (parsed with tomllib, no values printed) between `~/.emcee/config.toml` and `LIVE_CONFIG` (test_config.py:~420). The sets are identical (station.root, llm.scriptwrite.backend, tts.{voice_clone,api_key,chunk,bed_gain_db}, assign.default, assign.profiles.{bluegrass,dead,indie}.{presenter,title}). `test_live_config_loads` therefore covers the real config's shape, and the legacy `[tts] api_key` under the default voxtral house stays valid.
- Error surfacing checked: the validator's `ValueError` becomes a pydantic `ValidationError`, which `load_config` (config.py:~180) wraps as `ConfigError`. The tests assert substrings through `load_config`, not on the model directly, so they cover the real user path.
- Named risk, interaction with `EmceeConfig._lift_llm_tiers` (config.py:158). Checked: it only touches the `llm` key, so it does not interfere with `tts`.
- Named risk, validators bypassed via `model_copy`. Checked: there is no production `TTSConfig(...)` or `model_copy` on TTSConfig in `packages/emcee/src` (grep), so the after-validator cannot be bypassed in production today.
- The strictness test covers all four subtables. The verify name test includes the case-variant `MLX_AUDIO`.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. config.py template, the `[tts]` backend comment (`# hosted Mistral Voxtral TTS (default); or "elevenlabs"; or "fake" for tests`) still omits `mlx_audio`, while the `TTSConfig.backend` field comment now lists it. The brief's must-read block starts below this line, so this is not a spec miss. It is a small doc inconsistency for whichever later task touches the template or README.
2. test_config.py `test_same_key_in_tts_and_house_subtable_names_both` only covers the voxtral house (the default backend). An elevenlabs-house duplicate (`backend = "elevenlabs"` + `[tts.elevenlabs] api_key`) would exercise the `getattr(self, self.backend)` dispatch on its second value. Coverage could be broader. The code is brief-verbatim and correct by reading.
3. config.py `MlxAudioConfig.timeout_s` has no positivity bound, so `0` or a negative value parses and would fail later at request time rather than at load. Same for a whitespace-only `stt_model`, which passes the verify check. Both are brief-verbatim. Bound them in a later task if wanted (`Field(gt=0)`).

### Assessment
**Task quality:** Approved
**Reasoning:** The implementation and tests are a faithful, verbatim realization of the brief, with exact names, defaults and error substrings that downstream tasks consume. The live config's key shape loads unchanged. The three findings are cosmetic or coverage-breadth only.
