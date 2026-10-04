# SDD ledger — plan: docs/superpowers/plans/2026-10-03-tts-content-filter-recovery.md

Spec: docs/superpowers/specs/2026-10-03-tts-content-filter-recovery-design.md
Worktree: .claude/worktrees/content-filter (branch content-filter), base ac51b78. Baseline suite: 2033 passed.
Models: implementers Sonnet; task reviewers Opus; final review Opus.

## Pre-flight scan
| Pair / task | Produces vs consumes | Finding |
|---|---|---|
| T1↔T2 | SpeechBlocked(backend,*,text,categories,whole_passage) + .segment; Fake block | T2 rebuilds SpeechBlocked(blocked.backend, text=, categories=, whole_passage=True): matches T1 signature. OK |
| T1↔T4 | .text/.categories/.segment/.whole_passage | OK |
| T2↔T4 | _synthesize_dj_audio(rendered=), .segment tag, detail() | test_run_cmd fake_synth breaks only once process passes rendered (T4); T4 owns that fix. OK |
| T2↔T3 | scriptwrite imports audio._split_sentences | no cycle (audio does not import scriptwrite). OK |
| T3↔T4 | rephrase_segment(provider, seg, blocked, cats, feedback=), rephrase_problems(orig, rev, manifest) | T4 calls match. OK |
| T1 self | tests vs code | make_preset sleep fix included; MockTransport re-raises handler exceptions. OK |
| T2 self | tests vs code | non-block/force-without-rendered tests pass pre-change (declared regression pins). OK |
| T3 self | tests vs code | template test updated for 2 llm entries. OK |
| T4 self | tests vs code | whole_passage + TaskFailed tests pass pre-change (declared). Guard-fail candidate passes containment (no digit/title). OK |
Scan clean; no rulings needed.

## Progress
Task 1: ⚠️ items resolved by controller — full-repo run 2046 passed includes test_no_llama_imports; no llama import in diff.
Task 1: minor (deferred): voxtral._guardrail_block not defensive when `categories` is a non-dict or `guardrails` a non-iterable → AttributeError/TypeError escapes as a traceback (shape observed once; cheap isinstance guards)
Task 1: minor (deferred): mid-file `from emcee.tts.provider import SpeechBlocked` in test_voxtral.py/test_tts.py (plan-mandated placement); move to top imports
Task 1: minor (deferred): fake.py docstring line ~100 cols
Task 1: minor (deferred): SpeechBlocked args[0] differs from str(e); not picklable (nothing pickles/reads args)
Task 1: complete (commits ac51b78..10f0269, review clean)
Task 2: ⚠️ items accepted — suite counts from report; RED captured by temporarily reverting audio.py (fails against old code; test-first ordering not shown). Tree verified clean.
Task 2: minor (deferred): sidecar test should also assert "set2-intro.mp3" not in sidecar (pins persist-after-write ordering)
Task 2: minor (deferred): no test for bed+unchunked locate using fmt="wav" (fake ignores fmt)
Task 2: minor (deferred): no test that a non-block SpeechError raised DURING locating propagates
Task 2: minor (deferred): audio.py:280 docstring "force re-renders everything" now overstates (qualified at 294-298)
Task 2: minor (deferred): plan-mandated mid-file test imports (test_audio.py, test_say_cmd.py)
Task 2: complete (commits 10f0269..30a5206, review clean)
Task 3: ⚠️ items (lazy provider, problems-as-guard handling, unchanged-consumes-attempt in the loop, revised: detail line) are Task 4's — carried into Task 4's review.
Task 3: minor (deferred): stale comment test_config.py:253-254 ("the only llm entry present")
Task 3: minor (deferred): no test for case-insensitive title match or punctuation-ending title (Truckin')
Task 3: minor (deferred): rephrase.md says "refused sentence"; under chunking .text is a chunk (maybe several sentences) — "refused passage" fits both
Task 3: minor (deferred): generic GD track titles (Drums, Space, Jam) used as ordinary words → false "names a track" reject, costs an attempt (fails closed; accepted residual — FINAL REVIEW: judge whether GD-heavy usage makes this worth a narrowing)
Task 3: minor (deferred): plan-mandated mid-file test import (test_scriptwrite.py)
Task 3: complete (commits 30a5206..0eee4b4, review clean)
Task 4: Ruling: plan predicted test_rephrase_llm_failure_leaves_manifest_untouched passes pre-change; it failed RED (unrepaired SpeechBlocked) and passes GREEN — plan's expectation was wrong, the test is correct as a pin — costs nothing if wrong
Task 4: ⚠️ resolved by controller — whole_passage message ("[tts] chunk = true") pinned by Task 2's test_render_block_only_in_context_is_whole_passage; Task 1 pins __str__.
Task 4: minor (deferred): test_unchanged_rephrase_consumes_an_attempt doesn't pin budget charge ([SEG2, SEG2] → EmceeError w/ "unchanged" would)
Task 4: minor (deferred): detail() blocked:/revised: lines untested (capsys); rephrase provider built-once not asserted (requested.count == 1)
Task 4: minor (deferred): unchanged check on script text, not speech-normalized text — a normalize-erased edit is re-sent and re-blocked (bounded by budget)
Task 4: minor (deferred): plan-mandated mid-file test imports; _repair takes 8 params incl. 3 mutable state containers
Task 4: complete (commits 0eee4b4..0e96a93, review clean)
Final review: With fixes — 2 Important (generic GD titles false-reject; rephrase LLM failure loses block context), 5 Minor folded; dispatching ONE fix wave (final-fixes.md), base 0e96a93
Task 5 step 1: live check PASSED — rephrase cleared Voxtral on attempt 1, rephrase_problems [] , 10/10 sentences ok; recorded in spec. Ruling: plan's Task 5 script used speech_for's return as a provider (it returns (speech, bed)) — fixed in the scratch script only; plan text left as historical — costs nothing if wrong. Step 2 (re-voice real package) awaits user go-ahead.
Final fix wave: f1d8056; scoped re-review: 1,2,3,5,6,7,8 ADDRESSED; 9 addressed w/ wording nit; 4 NOT ADDRESSED (test can't fail — sentences <20 chars merge into one chunk).
Final: Ruling: residual — fold applied to text but not titles, so a curly-apostrophe/dash manifest title (Truckin’) no longer matches → newly named track slips the containment check (regression from the fix wave) — load-bearing for strict surface 2's containment; per process no second fix wave, so SURFACED TO USER with a recommended 2-line fix (`_fold(title)` in both _names calls) + curly-title test — costs if wrong: a newly named curly-quoted track goes to air unflagged (same class as the accepted out-of-show residual).
Final: Ruling: residual — item 4's typography test cannot fail; surfaced to user alongside the above (4-sentence ≥20-char test shape known) — costs if wrong: _fold could be removed without a red test.
Final: parked — audio.py:276 parenthetical "a repaired block re-voices from the cache" is backwards (other clips are reused) — Ruling: wording only, fold into the same follow-up — costs nothing.
Final: parked — provider_for("rephrase") construction sits outside the HerderError wrap (bad [llm.rephrase] config fails without block context) — Ruling: out of item 2's scope, Minor — costs a less helpful error on misconfig.
Residual fix round (user-approved 2026-10-04): residual-fixes.md, base ea71b56. Show re-voice deferred by user until loudness-normalization lands.
Residual fix round: 1111d77 — scoped re-review: items 1-3 ADDRESSED, no new issues (title folding verified incl. dash titles; typography test proven to fail with _fold neutralized). Full suite 2081 passed.
Final: parked — titles ending in an apostrophe (Truckin’) are not flagged when the revision drops the apostrophe ("Truckin") — Ruling: pre-existing, out of scope, small gap; same class as the accepted out-of-show residual — costs: that spelling could go to air unflagged.
Branch review: CLEAN after residual round.

---

## Appendix A — final-review fix list

### Final-review fix wave — content-filter branch (base 0e96a93)

Apply ALL of the following in one pass, with tests. Spec (binding):
docs/superpowers/specs/2026-10-03-tts-content-filter-recovery-design.md

## Important

1. **Generic track titles falsely trip the containment check** — `packages/emcee/src/emcee/scriptwrite.py` `rephrase_problems` (~lines 300-303).
   On a manifest with Jam/Drums/Space tracks (on nearly every Grateful Dead show from 1978 on), the measured Voxtral-passing rewording "…tape flip on this source cuts into the end of that jam." is rejected as "names a track … Jam". Exempt a small module-level frozenset of generic segment/filler titles from the "no newly named track" rule, compared case-insensitively on the stripped title:
   `_GENERIC_TITLES = frozenset({"drums", "space", "jam", "tuning", "intro", "crowd", "banter"})`
   with a one-line comment: these name parts of the show, not songs, and are the natural vocabulary for rewording. Tests (test_scriptwrite.py):
   - "jam" newly used as an ordinary word with a `Jam` track → no problem;
   - "…less space before the drums" with `Drums`/`Space` tracks → no problem;
   - a real song title is still flagged (existing Morning Dew test stays);
   - case-insensitive: a lowercase "morning dew" newly in the revision IS flagged;
   - punctuation-ending title: with a track `Truckin'`, a revision newly saying "Truckin' leads off" IS flagged.

2. **A failed rephrase LLM call loses the block context** — `packages/emcee/src/emcee/process.py` `_repair`, the `rephrase_segment(...)` call (~line 204).
   A `TaskFailed`/`RateLimited`/any `herder.HerderError` currently surfaces only as "LLM task 'rephrase' failed after 3 attempts", missing spec Goal 3. Wrap the call:
   ```python
   try:
       revised = rephrase_segment(...)
   except HerderError as e:
       raise EmceeError(
           f"content filter blocked a sentence in {seg}{cats}; the rephrase task failed: {e}",
           details=[f'blocked: "{blocked.text}"',
                    f"re-run `emcee voice {pkg_dir}` for a fresh script"],
       ) from e
   ```
   (`from herder import HerderError`.) Update `test_rephrase_llm_failure_leaves_manifest_untouched` in test_process.py to expect `EmceeError` whose message contains "set2-intro" and "rephrase task failed", whose `__cause__` is a `TaskFailed`, and whose details contain the blocked sentence; the manifest-bytes-unchanged assertion stays.

## Minor (fold in)

3. **`_guardrail_block` crashes on unexpected shapes** — `packages/emcee/src/emcee/tts/voxtral.py` (~39-47). If `guardrails` is not a list, treat it as empty; if a moderator's `categories` is not a dict, skip it. Result stays a `SpeechBlocked` (categories possibly `[]`). Tests in test_voxtral.py: `"guardrails": 1` and `"categories": ["sexual"]` bodies → `SpeechBlocked` with `categories == []`.

4. **Typography/whitespace noise counts as an edit** — `scriptwrite.py` `rephrase_problems` and the unchanged check in `process.py` `_repair`. Add one small helper in scriptwrite.py, e.g. `_fold(text)`: collapse runs of whitespace to one space, map curly single/double quotes to straight (’‘ → ', “” → "), and en/em dashes to "-". Use it (a) on each sentence before the SequenceMatcher diff, (b) on both texts before the title match, and (c) in process.py's unchanged check in place of the bare whitespace collapse (import it). Tests: a revision identical except curly quotes + a double space in an untouched sentence → `rephrase_problems == []`; `_repair`'s unchanged detection treats a typography-only change as unchanged (cover via a process test or a direct unit test of the helper plus the existing unchanged test — your choice, keep it small).

5. **CLAUDE.md** (the WORKTREE copy: /Users/shawn/projects/llama/.claude/worktrees/content-filter/CLAUDE.md): move the content-filter passage so it comes AFTER the sentence beginning "Everything else in a package is llama-owned and read-only from emcee's side." (it currently splits that sentence from the one it follows), and add one clause noting the `[llm.rephrase]` config key, which does not inherit scriptwrite's backend.

6. **Chunked repair through `process_package` is untested** although production runs `[tts] chunk = true`. Add to test_process.py a test using `EmceeConfig(root=..., tts=TTSConfig(chunk=True))` (TTSConfig is already imported there) and `force=True`: the repair succeeds; capture output with `capsys` and assert the `rephrased`, `blocked:` and `revised:` lines appear; assert the rephrase provider was requested exactly once (`requested.count("rephrase") == 1`, `_arm` already returns `requested`). A reference probe that already passes lives at /private/tmp/claude-501/-Users-shawn-projects-llama/3c18eff6-aae4-425b-9e1d-dad9bc809a99/scratchpad/test_chunked_probe.py (read it; do not copy its file into the repo verbatim — write the test in test_process.py's style).

7. **`packages/emcee/src/emcee/prompts/rephrase.md`** says "refused sentence" (~lines 13 and 25): with chunking on, the refused text can be a chunk of several short sentences. Say "refused passage" in both places (keep the rest).

8. **Stale comment** `packages/emcee/tests/test_config.py:253-254` ("the only llm entry present") — update to match the two-entry assert.

9. **Stale docstring** `packages/emcee/src/emcee/audio.py` ~280: "force re-renders everything" — qualify it (force re-renders every clip once per call; see `rendered` below).

## Out of scope (do NOT do)
Mid-file test imports, `_repair` parameter refactor, SpeechBlocked args/pickling, Retry-After handling, anything not listed above.

## Appendix B — residual fix list

### Residual fix round — content-filter branch (base ea71b56)

User-approved follow-up to the final-review fix wave (f1d8056). Apply ALL of the following; nothing else.

1. **Fold titles too (regression from f1d8056)** — `packages/emcee/src/emcee/scriptwrite.py`, `rephrase_problems` (~lines 310-320).
   `original`/`revised` are folded with `_fold` (curly quotes → straight, en/em dash → "-", whitespace collapsed) before the title match, but `_names(title, …)` still searches for the RAW title, so a manifest title containing a curly apostrophe or a dash (e.g. `Truckin’`) can never match and a newly named such track slips through.
   Fix: search for `_fold(title)` in both `_names` calls (the generic-title exemption check stays on `title.strip().lower()`).
   Tests (test_scriptwrite.py):
   - track `Truckin’` (curly U+2019), revision newly saying "Truckin’ leads off early." → flagged ("names a track the original did not: Truckin’");
   - track `Truckin’` (curly), revision newly saying the straight-quote "Truckin' leads off early." → flagged too;
   - each must FAIL before the fix (record it).

2. **Make the typography-noise test able to fail** — `packages/emcee/tests/test_scriptwrite.py`, `test_rephrase_problems_typography_noise_is_not_an_edit` (~557-561).
   Its sentences are all < 20 chars, so `_split_sentences` merges them into one chunk and the multi-passage rule can never fire; it passes even with `_fold` made a no-op. Rewrite it with a 4-sentence segment, every sentence >= 20 characters:
   - sentence 1 differs ONLY by typography: a straight `'` turned into a curly `’` plus an internal double space;
   - sentence 2 identical;
   - sentence 3 is the real reword;
   - sentence 4 identical.
   Assert `rephrase_problems(orig, rev, manifest) == []`. Prove it can fail: temporarily make `_fold` an identity function (or monkeypatch `emcee.scriptwrite._fold` to `lambda t: t` in a scratch run — NOT committed) and confirm the test then reports "changed more than one passage"; record that output in the report, then restore.

3. **Docstring wording** — `packages/emcee/src/emcee/audio.py` ~276: the parenthetical "a repaired block re-voices from the cache" is backwards (the repaired segment is newly synthesized; it's the OTHER clips from earlier in the call that are reused). Replace with: "a repair round reuses the clips it already made".

Out of scope: everything else (in particular the `provider_for("rephrase")` placement in process.py, mid-file test imports, any refactor).
