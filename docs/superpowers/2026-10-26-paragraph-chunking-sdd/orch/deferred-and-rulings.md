Task 1: minor (deferred): implementer's Mutation A was degenerate (literal block move = rule deleted); reviewer ran a faithful order mutant → only the outro test fails, so ordering IS pinned
Task 1: minor (deferred): no test pins the `U.S. B.B.` chain behaviour (works on HEAD)
Task 1: minor (deferred): `_split_sentences` docstring does not list dotted abbreviations
Task 1: minor (deferred): inline `re.sub(r"^[^A-Za-z0-9]+")` vs module-level compiled pattern convention
Task 2: minor (deferred): test_plan_chunks_no_paragraphs_packs_plain_sentences compares plan_chunks to itself (plan-mandated literal); packing pinned elsewhere
Task 2: minor (deferred): step-2 inner _greedy is an equivalent mutant (step 3 alone gives the same result)
Task 2: minor (deferred): lone CR "\r\r" is not a paragraph break (out of spec scope; no \r reaches provider)
Task 2: minor (deferred): handback typo ("8 Task1 tests?")
Task 2: ⚠️ carried to Task 5: whitespace-only text → plan_chunks [""]; check caller makes no empty provider call (Review Focus 2)
Tasks 1-2: minor (deferred): chain `U.S. B.B.` untested (also t1-rev) — folded into fix round 1
Tasks 1-2: minor (deferred): no test for 2+ consecutive tiny middle chunks — folded into fix round 1
Tasks 1-2: minor (deferred): no_paragraphs test near-tautological; regex rebuilt per part; t2 handback lacks mutation command line
Task 3: minor (deferred): test_pool_excludes_… "no zero run ≥24" assertion cannot fail on its fixture (holes inside the crossfade window); rule still pinned by the RMS line; move holes to f[200:230]
Task 3: minor (deferred): defensive extras beyond brief (odd byte passthrough, n<=xf guard, max(1,…), unreachable len(pool) guard)
Task 3: minor (deferred): tests and impl written together (RED shown by moving module aside)
Tasks 1-2: minor (deferred): parametrized abbreviation suffix "Blues for the crowd." is exactly _MIN_FRAGMENT_LEN; raising the constant by 1 would make the test vacuous — lengthen the suffix
Task 3: minor (deferred, RECOMMEND FIX BEFORE MERGE): room_tone.py:85 `astype("<i2")` truncates toward zero (loudness.py uses np.rint); makes exact zeros in crossfades (10% zeros at RMS~2 floor). Fix while ROOM_TONE_VERSION v1 is unshipped.
Task 3: minor (deferred): two unreachable guards (len(frames), len(pool)) — drop or comment as defensive
Task 3: minor (deferred): odd-byte passthrough and degenerate-rate early return untested/undocumented
Task 3: minor (deferred): test_odd_length_pcm doesn't assert edge runs filled (add longest-zero-run check)
Task 3: minor (deferred): linear crossfades on noise dip ~3 dB mid-crossfade (~67 Hz); harness-mandated; flag for listening check
Task 4: minor (deferred): no RED run (tests written after impl); mutations A/B carry it
Task 4: minor (deferred): TOML load-error test covers only the string case; parametrize "250"/250.0/1001
Task 4: minor (deferred): room_tone is a loose bool (matches chunk: bool; spec asks no strictness)
Task 4: minor (deferred): render_speech_mp3 / _synthesize_dj_audio docstring wording (Task 5/8 rewrite these)
Task 4: minor (deferred): test stand-in fakes accept chunking=None with a default (brief-mandated rename)
Ruling: carry Task 4 quality minor 4 (end-to-end forwarding test of non-default chunk_chars via process_package and say) into Task 5's dispatch — Task 5 is where the settings first change behaviour, so that is where the test can fail; costs one or two extra tests if wrong.
- 09:30 Task 5: implementer dispatched (Sonnet, t5-impl, a8642476a567f2774), BASE 6623bae5; carries T2 ⚠️ (no empty provider call) and T4 forwarding test
Ruling: Task 5 R2 — keep today's behaviour (whole-empty text → one empty call, as before this branch) and keep its test. Review Focus 2's text and example ("a script ending ...\n\n  \n") are about whitespace-only PARAGRAPHS inside a script, which make no call (pinned by test_chunked_trailing_blank_paragraph_makes_no_empty_call); plan Task 2 itself mandates plan_chunks("  ") == [""]; inventing a skip/raise for a wholly empty segment changes the unchunked-equivalent behaviour and the MP3 path for no listening benefit. Cost if wrong: an empty DJ segment still makes one empty provider call, exactly as today.
Task 5: minor (deferred to Task 8 doc pass): stale "Sentence-by-sentence" docstring on _synthesize_chunked; _synthesize_dj_audio key description lacks chunks=/tone=; loop vars still named sentences/sentence
Task 5: minor (deferred): forwarding test for process_package added after code (no RED); mutations B/E carry it
Task 5: minor (deferred): collapse test could also assert "long jam" in ei.value.text and not whole_passage
Task 5: minor (deferred → Task 8): _synthesize_dj_audio cache-key docstring lacks chunks digest / tone
Task 5: minor (deferred): forwarding test fixture paths built from dict repr; clever lambda recorder
Task 5: minor (deferred): mid-module aliased import `Chunking as _Chunking` and in-function imports in test_audio.py
Task 5: minor (deferred): room-tone recorder checks only seed (not pcm length/channels)
Task 6: minor (deferred): narrows test uses CHUNKED (room_tone=True) not brief's Chunking(250, False); no behavioural difference
Task 6: minor (deferred): reblocked-twice test could check the quoted sentence in the feedback field specifically
Task 6: minor (deferred): mutants B/C/E run with -x (first failure only, each the predicted test)
Task 6: ⚠️ (spec reviewer, not blocking): narrowing takes pass through QualitySpeech/[tts.verify] wrapper; untested (spec does not require)
Ruling: start Task 7's implementer while Task 6's read-only quality review runs (reviewer works from a scratch copy; T7 files are disjoint from audio.py). If T6 needs a fix round, it waits for T7's implementer to finish, so there is never more than one writer. Cost if wrong: a T6 fix rebases onto T7's commit; no conflict expected (disjoint files).
Task 7: minor (deferred): prompt test depends on "never a raw line break" staying on one line (a rewrap breaks it)
Task 6: minor (deferred): fallback is silent (no detail() line) — optional visibility
Task 6: minor (deferred): later takes not checked against first take's rate/channels/width (pre-existing; cheap guard)
Task 6: minor (deferred): redundant `_split_sentences` import at test_audio.py:1086; one-caller `_bed` helper
Task 6: minor (deferred): coverage — SpeechError during narrowing propagates; fallback with room_tone=True; bed fallback PCM length
Task 7: minor (deferred): prompt test brittle to rewrap — compare whitespace-collapsed copy
Task 7: minor (deferred): no test pins unescape-before-strip in rephrase_segment
Task 7: minor (deferred): only \n unescaped (not \r, \t) — spec scope
Ruling: Task 8 dispatch also carries the deferred wording items from Tasks 4-6 (stale "sentence" docstrings on _synthesize_chunked/_chunked_pcm/render_speech_mp3/_synthesize_dj_audio, the cache-key formula docstring missing chunks=/tone=, and the `raise  # each chunk is already its own request` comment) — they are exactly Task 8's wording scope; comments/docstrings only, no code or variable renames in the strict path. Cost if wrong: a slightly larger Task 8 diff.
Ruling: report the transmitter failure to emcee now as a stop-point notice, and continue the in-progress Task 8 review cycle (read-only reviewers, docs-only diff) — the failure is independent of every file this branch touches and reproduces on the base commit. Cost if wrong: emcee wanted a full halt; the extra work is two read-only doc reviews.
Task 8: minor (deferred, cheap): _synthesize_dj_audio docstring says key always carries tone=; code adds it only when room_tone is on
Task 8: minor (deferred): quality.py "the chunk when chunked" omits narrowing takes as their own verified units
Task 8: minor (deferred): Rich eats `[tts]` in say --help strings (pre-existing pattern in cli.py; escape as \[tts])
Task 8: minor (deferred, follow-up): pre-existing file-wide rich-markup swallowing of `[tts]` in cli.py help (~8 option helps)
Ruling: fold the cheap Task 8 wording minors into fix round 1 (all docs, same files): _synthesize_dj_audio docstring line 420 reflow + accuracy (chunks=/tone= are separate key parts; tone= only when room_tone on; point at _render_key), quality.py narrowing wording, ragged say-docstring line, README mlx-memory "(measured with sentence-sized chunks)" qualifier. Cost if wrong: a few extra doc lines in the fix diff.
