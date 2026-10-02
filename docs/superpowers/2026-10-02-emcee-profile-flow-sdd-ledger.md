# SDD ledger — plan: .superpowers/emcee-profile-flow-tasks.md
No written spec: bounded design approved in chat 2026-10-02; the task file's design text is the authority. Rulings are provisional against that.
Base: 4b00a4e (main). Baseline suite: 1980 passed.

## Preflight conflict scan
| pair / task | produces → consumes | finding |
|---|---|---|
| T1→T2 | T1 `assignment_for`/`presenter_label`/`PackageStatus.profile` → T2 status views | consistent; T2 depends on T1 names |
| T1→T3 | T1 edits station.scan + cli._scan_broad → T3 adds dot-dir skip to both | same functions, sequential; no conflict |
| T2→T4 | T2 `DJAudioBlock.presenter` → T4 backfill writes it | consistent (T4 must run after T2) |
| T3 vs existing test | `--force` absence pinned by test_force_and_allow_unvoiced_options_no_longer_exist | flag named `--replace-voiced` instead |
| T1 self | tests named vs code named | consistent |
| T2 self | changes default `status` output → existing status tests | brief says migrate them to `--list`, keep assertions |
| T3 self | temp dirs contain manifest.json → emcee scan | brief adds dot-dir skip |
| T4 self | script imports emcee; scripts/ tests in testpaths | consistent |

Ruling: deliver's new flag is `--replace-voiced`, not `--force` (the chat design said `--force`) — `--force` was removed deliberately because it once overrode the held gate, and a test pins its absence; reusing the name invites that misreading — cost if wrong: a rename.
Ruling: under `run --profile/--assigned`, error/unsupported rows with an unknown profile are summarized in one note, not reported per-row — a filtered run shouldn't fail on another profile's broken package — cost if wrong: a broken indie manifest is mentioned only as a count.
Ruling: `deliver --replace-voiced` on a voiced destination replaces it wholesale (clean copy via swap); on an unvoiced/absent destination the flag changes nothing — cost if wrong: stale files in unvoiced overlays persist as today.
Ruling: backfill is a one-off `scripts/` script that imports emcee, not an emcee command — only legacy shows need it — cost if wrong: promote it later.

Task 1: dispatched implementer (Sonnet), BASE 4b00a4e
Task 1: implementer DONE d16919d (Sonnet; 1992 passed); reviewer dispatched (Opus)
Task 1: minor (deferred): dry-run presenter check is case-insensitive but load_presenter is exact-path — disagree on case-sensitive FS (constraint vs loader gap)
Task 1: minor (deferred): _scan_broad/scan re-read manifest a third time outside try for profile — reuse first dict (carried into Task 2, which touches the same lines)
Task 1: minor (deferred): dry-run label uses manifest_profile while real run uses raw .get chain — `"source": null` / non-str profile edge differs
Task 1: minor (deferred): test polish — dead .replace in test_profile_and_assigned_must_both_hold, no positive both-filters case, `assert voiced.exists()` vacuous, no error-row+known-profile filter test, note line untested under --assigned alone
Task 1: minor (deferred): redundant in-function imports in test_station/test_process
Task 1: minor (deferred): "manifest unreadable" note also fires for parseable v2 manifests without profile (plan-mandated wording)
Task 1: minor (deferred): PackageStatus.state comment omits "error"
Task 1: complete (commits 4b00a4e..d16919d, review clean)
Task 2: dispatched implementer (Sonnet), BASE d16919d
Task 2: implementer DONE_WITH_CONCERNS 5e44242 (Sonnet; 2008 passed; concerns are observations); reviewer dispatched (Opus)
Task 2: minor (deferred): llama DJAudio.presenter field untested (test_the_cut.py:55-67 is the natural spot) — shape-compat unguarded
Task 2: minor (deferred): _scan_broad fallback path's voiced_by/profile untested
Task 2: minor (deferred): readable v2 manifest w/o profile lands in (unknown) not (none); cli.py:137 comment says "unreadable" (matches run's rule)
Task 2: minor (deferred): duplicated counting lambdas w/ noqa E731 (cli.py:149,152) → small helper
Task 2: minor (deferred): cli.py grew ~100 lines of status rendering; move to own module if it grows
Task 2: minor (deferred): --state validated after load_config + full scan
Task 2: minor (deferred): filter matching nothing prints "no packages found" (misleading when station non-empty)
Task 2: minor (deferred): status list/filter tests don't assert exit_code
Task 2: complete (commits d16919d..5e44242, review clean)
Task 3: dispatched implementer (Sonnet), BASE 5e44242
Task 3: implementer DONE b362fe9 (Sonnet; 2016 passed); reviewer dispatched (Opus)
Task 3: minor (deferred): test_status_broad_scan_skips_dot_prefixed_dirs never reaches _scan_broad (measured 0 calls) — _scan_broad dot-skip unpinned
Task 3: minor (deferred): copy-failure test's boom raises before creating tmp — rmtree(tmp) cleanup unpinned; also accepts any nonzero exit
Task 3: minor (deferred): out.rename(old) (cli.py:1977) outside both try blocks — failed rename-aside leaks full hidden temp copy
Task 3: minor (deferred): rmtree(old, ignore_errors=True) silently leaves partial voiced copy; kill mid-swap leaves hidden .old orphan nobody reports
Task 3: minor (deferred): implementer's rollback-on-failed-rename-in untested
Task 3: minor (deferred): --replace-voiced through batch path untested
Task 3: complete (commits 5e44242..b362fe9, review clean)
Task 4: dispatched implementer (Sonnet), BASE b362fe9
Task 4: implementer DONE ac9d60e (Sonnet; 2023 passed; real-station dry run: both legacy shows -> kurt); reviewer dispatched (Opus)
Task 4: review NEEDS FIXES — Important: test_dry_run_writes_nothing reads real ~/.emcee (fails with empty EMCEE_ROOT); CLAUDE.md misstates --assigned (and --profile repeatable). Fix round 1 sent to implementer (Sonnet, resumed); FIX_BASE ac9d60e
Task 4: minor (deferred): regex lookbehind (?<!\w) unpinned by tests
Task 4: minor (deferred): CLAUDE.md status text omits error state, that --profile/--state switch to per-show, --json always per-show, dot-dir skip
Task 4: minor (deferred): failed --apply exits 0 after printing success line; no guard against model_dump dropping a future extra key
Task 4: minor (deferred): valid-JSON non-object manifest / non-int schema_version crashes sweep (AttributeError/TypeError not caught)
Task 4: fix round 1/5 (2 addressed, 0 open; commits ac9d60e..9870323)
Task 4: complete (commits b362fe9..9870323, review clean)
Final review (Opus): With fixes — Important: batch --replace-voiced confirmation doesn't show which voiced destinations get discarded. All deferred minors triaged STAY-DEFERRED; all 4 rulings agreed.
Ruling: final fix wave includes Important 1 plus reviewer's cheap Minors 1-4 (JSON unknown-profile assignment null, no-match notes, CLAUDE.md drift, rename-aside into cleanup try) — all small, same files, one dispatch — cost if wrong: slightly larger fix diff.
Ruling: stale-sibling sweep deletes only `.{name}.deliver-*` (pure copies of llama's package, regenerable) and only WARNS about `.{name}.old-*` (may hold the operator's voiced audio from a killed swap) — never delete paid audio without an explicit request — cost if wrong: an orphan lingers until the operator removes it.
Final fix wave: dispatched (Sonnet), FIX_BASE 9870323
Final fix wave: DONE db293de (Sonnet; 2033 passed); scoped re-review dispatched (Opus)
Final fix wave: re-review (Opus) — 5/5 ADDRESSED, no new breakage. Out-of-scope: cross-workspace concurrent deliver of same slug could fail one deliver (no data loss); batch voiced hint read outside lock (display only).
