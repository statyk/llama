Ruling: preflight scan done at the interface level (File Structure + self-review type table), not by re-reading all 4,199 plan lines — the plan already passed two independent review rounds (16f0e72) and the 7-day meter is 89%; cost if wrong: an intra-task inconsistency surfaces in the task review loop instead of here.
Task 1: minor (deferred): normalize_artist has no Unicode normalization — NFD input ("Béla" decomposed) yields "be la fleck"; spec silent; candidate NFKC before casefold (spec-level call)
Task 1: minor (deferred): ArtistRule populate_by_name=True accepts `from_` as a TOML key (brief-mandated)
Task 1: minor (deferred): redundant extra="forbid" on ArtistRule (config.py:150)
Task 1: minor (deferred): mid-module import test_config.py:499 (brief-mandated)
Task 1: minor (deferred): comment alignment test_artists.py:32
Task 2: Ruling: fold write_moves into atomic_write_bytes(..., fsync=True) — the spec/constraint require temp+fsync+replace, not a second copy of the helper, and workspace.py/package_io.py explicitly forbid duplicating it; cost if wrong: one small helper signature change to revert
Task 2: minor (deferred): no parent-dir fsync after os.replace (atomic, not fully durable on power loss)
Task 2: minor (deferred): identical-profile record_move does not refresh a renamed package name (spec "unchanged")
Task 2: minor (deferred): lock release on exception paths / after clear_move unpinned by tests
Task 2: minor (deferred): no RED evidence captured for T2
Task 2: minor (deferred): workspace.py module docstring lists only presenters/package_io as users of the atomic writers (out of date)
Task 3: minor (deferred): test_accessors_are_total does not exercise manifest_voiced_profile on garbage nor a non-string dj_audio.profile
Task 3: minor (deferred): Effective invariant (rule None unless source=="artist") is docstring-only
Task 4: minor (deferred): `emcee run --profile` help (cli.py:322) still says "delivered for this llama profile" — selection is effective now; check T8/T9 fix it
Task 4: minor (deferred): scan reads each package manifest three times (Package has no cache)
Task 4: minor (deferred, FINAL-REVIEW MUST TRIAGE — strict surface 2): _scan_broad post-manifest error rows' identity() unpinned; mutant forcing voiced_source=None SURVIVED (831 passed). Fix: one case in test_a_missing_moves_file_with_move_voiced_packages_fails with a move-voiced + malformed-track package
Task 4: minor (deferred, FINAL-REVIEW MUST TRIAGE — strict surface 2): _scan_broad's first except arm (pkg.manifest() raises on valid-JSON-but-bad manifest) emits a row with no voiced_source, so require_present cannot count it; identity(_raw_manifest(...)) would close it
Task 4: minor (deferred): identity() omits `voiced`, so error rows carry voiced_by but voiced=False — carried to T5/T7 dispatch as a heads-up
Task 4: minor (deferred): status --state bogus with a bad moves.json reports the moves error first (strict-first; noted)
Task 4: cannot-verify items resolved by plan ownership: voice loads moves (T5), --json delivered_profile/profile_source/tts + "(from …)" (T8), stale note (T7/T8), move_problem error rows (T7). Intermediate T4→T5 state re-voices rule-moved packages every run — no real-station run until T5 lands (none planned)
- 2026-10-16T14:52:27-0400 PARENT RULING (llama-ed): final-review fix wave MUST include (a) a test pinning the surviving T4 _scan_broad mutant; (b) close the arm: a JSON-readable but structurally wrong manifest whose raw dj_audio.profile_source == "move" counts toward the missing-moves.json check (unreadable JSON stays a documented limit); (c) fold unicodedata NFC into normalize_artist (T1 minor). Not optional.
Task 5: minor (deferred): models.py module docstring still says emcee blocks are "shape-identical" to llama's DJAudio (check T9 updates it)
Task 5: minor (deferred): voice --fresh help text silent on moves/artist rules
Task 5: minor (deferred): bed computed twice (speech_for_voicing's bed discarded at cli.py:226; process.py:312 recomputes) — plan-mandated return type
Task 5: minor (deferred): SpeechProvider Protocol does not declare voice/model though TTSRecord depends on them
Task 5: minor (deferred): pre-existing llama fork() DeprecationWarnings in full-suite output
Task 5: minor (deferred, runbook candidate): _process_one clears dj_audio before process_package, so a failed re-voice of a move-voiced package loses its "move" record and the missing-moves.json guard no longer counts it (two independent failures; within spec's acknowledged limit)
Task 5: cannot-verify: run-side error row for an invalid move target — owned by Task 7 (verify there)
Task 6: minor (deferred, FINAL-REVIEW SHOULD TRIAGE — strict surface 2): writer/reader mismatch — with [assign.profiles.""] configured, `emcee move X ""` writes "profile": "" which load_moves rejects; reported as success exit 0, then every command hard-fails. Fix: record_move validates before write (or Assign forbids empty profile names)
Task 6: minor (deferred): --list marks a stale --delivered exemption to an unassigned profile "[no assign entry]" on a missing row (re-implements target_problem; untested)
Task 6: minor (deferred): unchanged move does not refresh renamed package name (dup of T2 minor)
Task 6: minor (deferred): broad except Exception around post-write assess (cli.py) — narrow to (EmceeError, OSError)
Task 6: minor (deferred): usage-error test checks only exit code
Task 7: minor (deferred): --yes and new exit codes documented only in CLI help (T9 docs should cover README/CLAUDE.md)
Task 7: Ruling: fix it, and fix the class — forbid_spend also records each attempt so a swallowed spend is still visible; the EOF and declined tests assert no attempts, no "error:", no "voiced:" — strict surface 1 is the plan's top stake and its only EOF test must be able to fail; cost if wrong: a helper change touching T4-T7 tests
Task 7: minor (deferred): _stdin_is_tty raises AttributeError when sys.stdin is None (fails closed, with a traceback)
Task 7: minor (deferred): -y alias and bare-Enter default decline untested
Task 7: minor (deferred): test_run_cmd.py:437 weakened stderr=="" to "error:" not in stderr (brief-mandated)
Task 7: minor (deferred): --assigned/--profile filter silently drops a package whose move targets an unassigned profile (no error row unless unfiltered); pre-existing filter semantics
Task 7: minor (deferred): EOF/Ctrl-C exits 1 "Aborted." — exit-code docstring does not mention it
Task 7: minor (deferred, final review): other forbid_spend callers (test_recording, test_profile_readiness, test_move_cmd) ignore the returned attempts list — check for broad-catch blindness there
Task 8: minor (deferred): unused `from pathlib import Path` in test_status_profiles.py:4 (plan-mandated)
Task 8: minor (deferred): no test of unsupported/error row's profile cell under a rule/move
- 2026-10-16T16:35:45-0400 GATE (b) independently confirmed by llama-ed. Go for Task 9 + final review + fix wave. PARENT RULING: T6 empty-profile write (record_move validates before write) joins the mandatory final-wave items.
Ruling: Task 9 dispatch also carries two doc-only fixes from deferred minors (emcee models.py "shape-identical" docstring → "shape-compatible"; CLAUDE.md resolve_assignment "keyed off manifest source.profile" → effective profile) — they sit in T9's files and are cheaper there than in the final wave; cost if wrong: one extra docstring line in T9's diff
Orch note (final wave): CLAUDE.md:109 still says emcee run `--profile` "limits it to those llama profiles' packages" — selection is by effective profile (same staleness as T4's cli.py:322 help minor)
Task 9: Ruling: the fix round also corrects CLAUDE.md:108 "only problem is missing track audio" (code skips ANY pending package with missing tracks) — it is the same defect class (a doc claim the code contradicts), not polish; cost if wrong: one extra sentence edit
Task 9: minor (deferred): runbook bullet "until emcee voice <show> succeeds" — next emcee run also retries
Task 9: minor (deferred): emcee models.py:4-5 stacked parentheticals
Task 9: minor (deferred): CLAUDE.md long unwrapped inserted lines (cosmetic)
Task 9: minor (deferred): CLAUDE.md:104 "its own six models" count stale (pre-existing)
Task 9: minor (deferred): cli.py:436-438 run docstring still says "whose only problem is missing track audio" (shows in emcee run --help)
Task 9: minor (deferred): docs/station-brief.md:78-81 presenter chosen by source.profile — no mention of moves/rules
