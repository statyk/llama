### Spec Compliance
- ✅ **Spec compliant.** I judged against the brief as amended by `task-12-operator-decisions.md`. The diff (947aa68..531b75f) carries every Step 1–10 deliverable plus the rulings. The two added script flags, `--rescore` and `--max-s-per-char`, are what decisions 3 and 6 need. The `visible()` skip helper implements the controller's ruling that an empty RUNAWAY_TRANSCRIPTS must skip visibly.
- **Constants match the data and the doc.** I checked them with python against the committed data file, importing the worktree's emcee (`emcee.__file__` resolves inside the worktree).
  - `dataclasses.asdict(CALIBRATED_MODELS[QWEN3_TTS_1_7B_BASE])` equals `recommendation.adopted_guard.calibration`.
  - The derived `recommendation.calibration` is identical except that max/cap_s_per_char is 0.08, the recorded 0.09 deviation (calibration.py:5163-5165 in the diff).
  - verify.py's four thresholds equal `recommendation.thresholds`: 2 / 0.25 / 4 / 0.25. That is also the Whisper `all` derivation, and it matches the doc's adopted table (doc:4828-4835).
- **Step 6 tables are verbatim.** I loaded the test module and compared it to the data file. Every comparison was True.
  - `CLEAN_EDGES` = units 0/26/30 (highest s/char), 1/25/11 (lowest), 0 (shortest, de-duplicated) and 52 (longest).
  - `CLEAN_TRANSCRIPTS` = Whisper's post-rescore top three missing/words (#21, #39, #31) and top three extra/words (#5, #54, #59).
  - `RUNAWAY_TRANSCRIPTS` = both runaway rows' Whisper transcripts.
  - `CHATTERBOX_MORNING_DEW` = ("Here is Morning Dew.", 10.1).
  - The `QWEN_06B_RUNAWAY_TEXT` and `QWEN_06B_RUNAWAY_SECONDS` (320.0) values equal the data's `qwen3tts-0.6b-bf16` row (index 5).
- **Step 3 checks hold in the data at 0.09.**
  - Guard: `adopted_guard.guard_checks.clean_failures` is []. All three runaway rows are non-null ("10.1s, at the 6.8s token cap", "18.2s … 18.2s token cap", "320.0s > long limit 15.2s").
  - Whisper: `verify_checks.clean_failures` is [], both runaways are non-null, and `defects_passing` is [].
  - No ceiling is exceeded in any derivation for either model.
- **Global constraints hold.**
  - MISS_FLOOR is 2 (≥ 2). Every Step 3 ceiling is met.
  - No STT model id appears in `packages/emcee/src` (I grepped for whisper and parakeet).
  - There is no `llama` import in `packages/emcee` or the script.
  - Live test: `test_mlx_live.py` matches the brief verbatim and is `pytestmark = live`.
  - All three commits carry the session_01TNheuMFMvYwCHKaT9xJRS2 trailer (one read-only `git log --format=%(trailers)`, because the diff file omits commit messages).
- **Bundled clip.** I hashed `packages/emcee/src/emcee/data/preflight_en.wav`: its sha256 equals the doc's (74721f21…f8f1ed). It is 16-bit mono 24000 Hz, 2.625 s. It is tracked and not gitignored, so hatchling's `packages = ["src/emcee"]` wheel and `collect_data_files("emcee.data")` both ship it.
- ⚠️ **Cannot verify from the diff:**
  - The rationale the doc attributes to the operator for #2/#3, "(Qwen itself said 'Here's'; it sounded fine)" (doc:4795-4796). The decisions file and the ledger record only "#2, #3, #53 artefact by operator".
  - The doc's "the operator listened to 053–062 and heard no ums" (doc:4987). This is consistent with decision 2's "announcer-voice clone produced no disfluencies", but not stated there as a listen.
  - "6 have exactly 3" comparable words in the corpus (doc:4871). The data file stores only the ≤ 2 count.

### Strengths
- **The script is built for recovery.** It saves the data file atomically after every rendered unit (`save` writes a temp file, then `replace`), so `--reuse` resumes partial runs. `--rescore` re-scores saved transcripts without loading a model, which is exactly what option B needed.
- **The analysis matches what the rulings asked for.** STT results are kept per model, the mechanical default is "max recall < 0.5" (the ruling), and false alarms are measured leave-one-out, under the interim thresholds and cross-backend.
- **The evidence doc is unusually honest.**
  - It reports Parakeet's Step 3 failure, the #21 leave-one-out near miss with its mechanism, and that verification caught nothing the guard missed.
  - It puts "SWAP GREW" in bold with raw `vm.swapusage` and swapin/swapout numbers. I checked these against `t12b.log`: 1398.50 → 5508.94 MB, total 3072 → 6144 MB, run 2 4708.94 → 5075.12 MB, and footprint 1938 → 6423 MB with a 12 GB peak. All match.
  - Its "What this does not show" section is specific.
  - Every Step 5 item is present: setup, derivation rules, per-voice table, extremes, both Qwen checks labelled as the brief requires, flagged units with WAV path and classifier, adopted table with the 0.09 deviation and its reason, synthetic cap-margin check, Kokoro provenance and venv install (including the en_core_web_sm step), the footprint and memory-headroom answer, and the live-test result.
  - Every operator decision is attributed: Whisper, Parakeet as comparison only, option B, nothing-heard, the classifications, 0.09, Voxtral disfluency unmeasured, the go-live prerequisite for the four drafts, and the 8765→8781 port substitution.
  - The doc's numbers agree with `analysis` in the data file:
    - per-voice table;
    - histograms {0:37, 1:10, 2:2, 3:4} and {0:9, 1:1};
    - leave-one-out 1/53 (#21), interim 0/53 and 0/10, cross-backend 1/53;
    - STT wall medians 1.22 / 0.31 s;
    - #26 at 0.787 → 0.712 of its long limit, and #25 at 1.251×.
- **`match_words` is tightly bounded.** Every fold consumes the residual words it credits (`found` = n − Σ residual w). No count can go negative, and the exact bag match runs first, so folding can only add credit for heard tokens that were otherwise unmatched.
- **The nothing-heard rule is exactly `if n and not found`** (verify.py:5282), nothing broader. It is placed before the miss check, and its message still contains "words were heard", so the existing assertion at test_verify.py:70 is unaffected.
- **Task 11 tests are untouched.** The `test_verify.py` hunks are the import line (5508-5511) plus new tests only (5533-5579). No existing test was edited.
- **Secrets are clean.**
  - The only key-like strings in the diff are `voxtral_key()`'s env and config lookups.
  - The only long tokens are paths and test names.
  - A boolean-only containment check found the configured key in neither the diff, the data file, the script nor the doc. Nothing was printed.

**Mutation evidence** (scratch `git archive 531b75f` copy, fresh copy per mutant, `PYTHONDONTWRITEBYTECODE=1`, shadowing proven via `emcee.__file__`; ran `test_verify.py` + `test_calibration_measured.py`; the unmutated baseline passed 54):

| mutant | result | caught by |
|---|---|---|
| contraction table removed | caught | 5 tests |
| `if n and not found` → `if not found` (broadened to n == 0) | caught | `test_all_number_sentence_passes` |
| nothing-heard rule removed | caught | `test_nothing_of_a_short_script_heard_fails` |
| pass-2 `found += 2` | caught | `test_a_heard_bigram_matching_a_script_token_counts_as_found` |
| heard token not consumed in pass 1 | caught | `test_folding_never_counts_a_heard_token_twice`, `test_match_words_returns_the_unmatched_words_on_each_side` |
| pass 2 removed | caught | `test_a_heard_bigram_matching_a_script_token_counts_as_found` |
| same-word guard removed (pass 1 or pass 2) | **survived, as predicted** | see Minor 1 |

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **verify.py:5244 and :5252: the same-word guards are not pinned by any test.** These are `(a != b or w[a] >= 2)` and `(a != b or h[a] >= 2)`. Deleting either leaves all 54 tests green (mutants M1/M2 above).
   - Without the guard, a repeated word with one residual copy over-credits. Example: script "bye bye", heard "bye byebye". The exact match takes one "bye"; the pair (bye, bye) then decrements `w["bye"]` to −1 and adds 2, so found = 3 > n = 2.
   - A negative miss count can then offset a genuine miss elsewhere.
   - Fix: add one test, e.g. `found("Bye bye.", "Bye byebye.") == 2`, and its heard-side mirror.
2. **test_verify.py:5533-5579: no negative test that folding is narrow.** Three cases are unpinned:
   - The script pair must be adjacent. For example, script "l b a" heard as "la" must not fold.
   - An unrelated heard token must not be credited.
   - A long script heard as a few contracted tokens must still fail.

   The named risk (folding letting a wrong transcript pass) is low by construction: a fold requires exact concatenation or contraction equality and consumes the token. But the narrowness itself is unpinned.
   - The table also makes "X is"/"X has" fold to "Xs" ("band is" ↔ "bands") and "we are" ↔ "were". These are acoustically identical pairs, so acceptable.
   - Worth one sentence in the doc's contraction paragraph (doc:4815-4818).
3. **test_calibration_measured.py:5322: wrong comment.** It labels unit 26 "highest seconds per character". The data, and the doc's extremes table (doc:4768), show unit 0 is highest (0.084 vs 26's 0.0751). Unit 0's comment names only "the shortest text". Fix: label unit 0 as both shortest and highest, and unit 26 as second-highest.
4. **Evidence doc, Memory headroom (doc:4969-4977) and recommendations (doc:4989): decision 8 is not recorded as an open gate.** Decision 8 says memory is "not a gate unless swap grows", and swap grew. The doc reports the growth plainly but does not say that this makes memory a gate pending the operator, while it still recommends enabling verification at Phil's go-live.
   - The orchestrator ledger shows the gate is already with Shawn, and a llama-9b interim decision ("measured, tight" open item, runbook guidance) is queued for the fix round. Record the outcome in the doc in that round.
5. **Evidence doc: the Kokoro port substitution is not stated as one.** The doc records Kokoro on 8782 (doc:4919) but does not say this replaces the brief's 8766, unlike the explicit 8765→8781 note (doc:4704). This is a nit.
6. **scripts/mlx_audio_calibrate.py:6390: `--rescore` is documented as "with --reuse" but not enforced.** Without `--reuse` it re-scores after a fresh run, which is harmless. This is a nit; it is a one-off script, not the emcee CLI.
7. **Process (phase A handback, self-reported): mandate 2 was broken.** The calibration's stdout went to `$S/calibrate.log` and was appended to `t12.log` afterwards rather than live-teed. Progress lines were echoed at each poll. There is no effect on the code; it is recorded for the ledger.

### Assessment
**Task quality:** Approved

**Reasoning:** Every adopted constant and every literal test table traces exactly to the committed data under the brief's selection rules and the operator's rulings, and the evidence doc's claims check out against both the data and the run log. The matching change is bounded and well tested apart from the unpinned same-word guard (Minor 1). The memory gate (Minor 4) is an operator decision already in flight, not a code defect.
