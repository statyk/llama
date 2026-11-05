# Final whole-branch review: programs-lineup (b7ec7bda..33198e55)

Reviewer: Opus, read-only. I reviewed in five passes, logged in t14-final-review.log: (1) the emcee lock, retitle, procs and cli; (2) llama deliver and clear-mark, and bulk_apply; (3) transmitter site and publish, and station_probe; (4) the antenna helpers, page and fixtures; (5) the docs and the carry-over triage. I read the source at HEAD rather than every test hunk. I ran no suite. I ran one scratch reproduction: station_probe `cross` against a stale lock, in my scratchpad.

## Carry-over triage

| # | Carry-over | Verdict | Reason |
|---|---|---|---|
| T1a | occurrence_spans revisit (A,B,A) untested | LEAVE | I traced site.py:66-84 by hand and it is correct: B ends at the second A's start. Persisted plan rows are time-ordered, so this case is rare. |
| T1b | lineup bytes stable test compares NOW vs NOW+1 only | LEAVE | The plan mandated this test. The digest gate in publish.py is pinned elsewhere. |
| T1c | lineup lower bound earliest inclusion not pinned | LEAVE | `occurrences()` already owns the window rule and it is tested. |
| T1d | publish.py:240 temp `clock=` unannotated | LEAVE | Superseded: `_publish_site` now loads the clock itself. |
| T1e / T2f | Debian12 gate not run | NOT-OURS | The controller is running the py3.11 gate separately. |
| T2a | lineup-failure test doesn't pin kept notes digests | LEAVE | Low value. The code path is a plain `try/except` that keeps `notes`. |
| T2b | test_publish.py:39-41 lineup compared to itself | LEAVE | Tautological, but the other lineup tests pin real shape and bytes. |
| T2c | unreadable-manifest test lacks show page count==1 | LEAVE | Minor test strength. |
| T2d | PutBudgetExceeded at lineup loses this pass's digests | LEAVE | Same as the timeline today. The next pass re-PUTs. |
| T2e | transmitter CLAUDE.md:22 reflow; inline imports | LEAVE | Cosmetic. |
| T3a | null element in timeline.shows throws | LEAVE | The transmitter never emits one. Consistent with timeline.js. |
| T3b | Tokyo eastward case dropped | LEAVE | The westward move is pinned, and the code does no zone arithmetic that is direction-specific. |
| T3c | exported blockSpan throws when called directly; redundant nonEmpty | LEAVE | All callers validate `start` first (programs.js:45). |
| T3d | fix report gave a summary line only | NOT-OURS | Process. |
| T4a | judgement calls: off-air shows no highlight, long program ellipsized, empty day shows empty list, tomorrow-nominal on-air not highlighted | NOT-OURS | Shawn's eye, at the Task 16 deploy. |
| T4b | tab pattern incomplete: no role=tabpanel or aria-labelledby, no tablist name | SHOULD-FIX | Cheap. Add `aria-label="Days"` to the tablist and `role="tabpanel"` to `#lineup-list` in index.html (then `npm run pages`), and set `aria-labelledby` on render. |
| T4c | lineupDays recomputed every 1 s | LEAVE | About 60 Intl formatters per tick is acceptable. Memoize later if phones show jank. |
| T4d | .block-head restates .kick | LEAVE | Cosmetic. |
| T4e | lineup refetch rides the timeline's 3-minute gate; force doesn't force the lineup | LEAVE | The spec says the lineup is refetched "with the timeline". 30 minutes is fine for a weekly view. |
| T4f | refreshTimeline unread-404-body pattern | LEAVE | Pre-existing, outside this plan. |
| T4g | cross-check lineup.mjs fixture vs site.build_lineup | LEAVE (verified, matches) | I did this check myself. Both produce `{occurrences:[{block, nominal_start, end, title, variety}]}`. `grid.us_to_iso` gives `YYYY-MM-DDTHH:MM:SS.mmmZ`, the same as JS `toISOString()`, so occurrence keys format identically. `variety` is a bool on both sides (`len(profiles) != 1`). The fixture's base timeline shows lack `block`/`nominal_start`/`program`, where the real ones carry nulls. The page treats both the same. |
| T5a | lock clear compare-then-unlink TOCTOU | LEAVE | Operator-only, for a dead writer's lock. The window is microseconds. |
| T5b | plain fsync for the lock | LEAVE | Acceptable. Power loss leaves an empty lock, which counts as held: fail-safe. |
| T5c | SIGINT not masked around acquire/release | LEAVE | Every SIGINT window either unlinks in `acquire`'s BaseException handler or leaves our lock behind. A leftover lock is fail-safe: `emcee lock clear` recovers it. |
| T5d | outer finally's last unblock untested | LEAVE | Defence in depth. |
| T5e | SIG_SETMASK whole mask; handler thread; final _unblock untested | LEAVE | Superseded by round 3 and t5b (only the lock's own signals are unblocked, pinned by test_only_the_lock_signals_are_unblocked). Moot under os._exit. |
| T5f | KeyboardInterrupt inside release-side _block or the handler's release | LEAVE | SIGINT class, fail-safe (stuck lock at worst). |
| T5g | FLAGGED: pthread_sigmask covers the main thread only | LEAVE (resolved) | Closed by t5b's `_critical`/`_deferred`/`_exiting`. I read station_lock.py:205-266. The handler only defers while acquire or release runs, and `_unblock` acts on the deferred signal after the lock is fully held or fully gone. Both parametrized window tests run with a live second thread (`threads="thread"`). The design is identical in the two tools (the diff of the two modules shows only names and docs). |
| T5h | KeyboardInterrupt between acquire return and `held` assignment | LEAVE | SIGINT class, fail-safe. |
| T6a | non-StationLocked acquire error (EACCES/ENOSPC) repeats per package in `emcee run` | LEAVE | Nothing is written, since every package fails before `_process_one`. It is noisy only. It is inconsistent with R13 (bulk_apply stops), so it is worth one line in a later pass. |
| T6b | `emcee voice .` prints an empty slug | LEAVE | Pre-existing. The lock path itself is correct (`.absolute().parent`). |
| T6c | voice --fresh stems validated before the lock, unlinked under it | LEAVE | A clean failure either way. |
| t5b | _unblock comment could name the gap between `_critical=False` and the `_deferred` swap | LEAVE | A handler in that gap sees `_critical` False and exits itself, which is correct. Comment only. |
| T7a | emcee CLAUDE.md:126 / models.py:74 "Task 8's raw writer" | LEAVE (done) | Both now say "the title backfill (emcee retitle)". |
| T7b | test_the_cut checks model_dump title only | LEAVE | Round-trips are covered elsewhere. |
| T8a | write_title any exception stops the run; dry run lists stray temps | LEAVE (done) | Both are implemented in Task 9 (cli.py `_retitle_under_lock`, `_stray_temps`). |
| T8b | fsync assertion not tied to the temp fd; put-back-after-foreign-change untested; 26 warnings | LEAVE | Test strength only. The warnings are the baseline. |
| T8c / T8d | go-live: utime-before-rename over SMB->NFS; one real retitle write before relying on fchmod/utime | NOT-OURS | Task 19/20. |
| T9a | temp-left note not shown; `<n> written` copy; stream mix; Ctrl-C prints no not-attempted list | LEAVE | Cosmetic. A left temp is listed by the next dry run's `stray temp:` lines. |
| T9b | go-live: time `_stray_temps` readdir of 2,786 dirs over SMB | NOT-OURS | Go-live timing (Task 19/20). |
| T9-N1 | restore doc: copy-then-utime on the live file | MUST-FIX (pre-decided; agree) | emcee CLAUDE.md:140-150 tells the operator to put `<slug>.json` back and then utime the live file. A `cp` rewrites the live manifest in place (not atomic), and the file carries a fresh mtime until the utime, which hugo can cache for about 60 s. Rewrite it as: write a temp in the package dir, flush and fsync, `os.utime(tmp, ns=(atime, mtime_ns))`, `os.replace(tmp, manifest)`, then re-check the mtime. Do it with no emcee or llama running, or while holding the station lock. Best is to give a 6-line Python snippet. |
| T9-N2 | restore doc: before-only cause list incomplete; new title not in record.jsonl | MUST-FIX (pre-decided; agree) | Spell out the three outcomes for a before-only slug: (1) file sha256 == before_sha256, so it is the original and there is nothing to do; (2) the file equals the backup with only `dj_audio.title` set, so this run's write landed and is unrecorded; (3) anything else, so someone else wrote it, so leave it. Case (2) cannot be checked, because record.jsonl never records the target title. Add `"title": w.new` to the before line in `_save_backup`'s record (cli.py `_save_backup`/`_retitle_under_lock`) and pin it in test_retitle_cmd. Also list the failed put-back case. |
| T9c | emcee root's parent entry not fsynced if mkdir created the root | LEAVE | First run only, on the local disk. |
| T10 | llama StationLocked str is multi-line | LEAVE (handled) | bulk_apply splits it into stop lines (`_station_locked`) and records the one-line `refused: the station is locked`. deliver and clear-mark print it whole, as intended. |
| T11a | FLAGGED R6: deliver overlay `copytree(dirs_exist_ok=True)` into a live package | LEAVE the code; SHOULD-FIX the docs | This is not a regression. Before this branch SIGTERM had its default disposition and killed the process at the same instant, so R6 leaves the exposure identical: a truncated manifest (the next deliver refuses it) or truncated audio on an unvoiced, unmarked, same-tracklist destination. The lock now keeps emcee out during the copy, so the branch is strictly better. What is false is the documented premise of R6. station_lock.py:24-27 in both tools and emcee CLAUDE.md:44-45 say every station write is an atomic rename. Name llama's deliver overlay copy and its two-rename replace as the exceptions, and say that SIGTERM there behaves like SIGKILL, minus the stuck lock. Making the overlay atomic is a separate decision for Shawn. |
| T11b | R6: replace path interrupted between its two renames | LEAVE code; covered by the T11a doc fix | Pre-existing, with the same reasoning as T11a. |
| T11c | R6: clear-mark exit between clear and add_clear; stray temp never swept | LEAVE | Pre-existing class (SIGKILL had it before). The state is visible by hand. |
| T11d | clear-mark with a missing delivery folder says "cannot create the station lock ... Errno 2" | LEAVE | Accurate, if less friendly. |
| T11e | deliver batch "not attempted" includes unreadable/awaiting slugs already refused | LEAVE | Cosmetic and over-inclusive, which is the safe direction. |
| T11f | no-imports guards miss `import os, emcee` | LEAVE | No such import exists. Hardening only. |
| T11g | llama CLAUDE.md:178 "emcee does not share this locking scheme" | SHOULD-FIX | It now contradicts the station-lock paragraph. Say "this flock scheme". One word. |
| T11h | test_clear_mark span test re-wraps spies | LEAVE | Fragile, but it works. |
| T11i | R6 note: station_lock docstrings claim atomic renames | SHOULD-FIX | Merged with T11a. |
| T12a | unmark --apply locks never-delivered lines too | LEAVE | Accepted by llama-player. Fails safe. |
| T12b | bulk_apply.py:1182 unmark docstring 118 cols | SHOULD-FIX | Re-wrap it in the same wave. Trivial. |
| T12c | bulk_apply.py:1777, :1982 102 cols | LEAVE | Pre-existing. |
| T12d | scripts/CLAUDE.md gained a sentence on create-error stops | LEAVE | Accurate, and consistent with R13. |
| T13a | re-check compares whole seconds vs st_mtime_ns | LEAVE | Equivalent for the integer target. |
| T13b | stale `.lock-race-<tag>` makes cross pass vacuously | SHOULD-FIX (must land before Task 19) | Reproduced. With a stale `d/.lock-race-zz`, `cross --role a --n 5 --tag zz` prints `acquired 0 contended 5 ... double 0` and exits 0. The scripts/CLAUDE.md pass rule ("neither side exiting 1 and at least one exiting 0") then records a cross-host check that never ran. Fix at station_probe.py:200-206: return 3 when `c["acquired"] == 0` too, with a message naming a pre-existing lock. Better still, refuse when `path` exists before `--start-at`. Add a test. |
| T13c | test_race_warns_when_nothing_contended is vacuous | LEAVE | It is a warning only, not an exit-code rule. |
| T13d | cmd_race early return 2 terminates workers without join | LEAVE | Harmless. |
| T13e | plan Task 19 Step 4 wording omits --start-at and the exit-3 rule | NOT-OURS | Task 19 (llama-player). |

## Strengths

- **The station lock is tight and the two tools are true twins.** A `diff` of emcee/llama `station_lock.py` shows only names, the error base class, and llama's single-string `StationLocked` plus `for_package`. The contract matches the spec exactly: `O_CREAT|O_EXCL|O_WRONLY`, mode 0644, the magic line and token, the five holder lines, fsync. Empty or garbage contents count as held, release is token-checked, nothing breaks or expires a lock, and a re-entrant acquire raises. `acquire` cleans up its own file on any BaseException after the create, including a deferred SMB close error.
- **The signal design holds up.** t5b's `_critical`/`_deferred`/`_exiting` closes the off-main-thread delivery gap that the mask alone could not. I walked every window: before the acquire, inside it, between it and the yield, the body, the finally prologue, inside the release, and after it. In each one the handler either defers, or releases and exits, and no caller code runs after the signal. Tests cover both main-only and live-thread runs.
- **The retitle writer is careful.** It refuses anything not in emcee's exact encoding; duplicate keys, `1.50`, `ensure_ascii=False` and a missing trailing newline all fail the `raw != encode(data)` check. Absent and null titles count as equal. It writes the temp, flushes, fsyncs, closes, sets the mtime, re-reads and compares, renames, and re-checks the mtime, in the spec's order. After writing it checks that every other key is unchanged, comparing JSON values by their encoding so `1 == 1.0 == True` can't hide a change. It puts the original back only over its own bytes. Its error messages state exactly what the file now holds. The whole-run drift refusal under the lock, the durable backups written before each write, and the ps gate placed before the lock all match the spec.
- **llama deliver and clear-mark lock in the right place.** The show lock is taken first and the station lock inside it, spanning the destination read through the swap or copy (and the clear, the record and the put-back). The ledger record and the purge come after the release. A held lock stops the batch with a `not attempted:` list. Running the gate check before creating a missing folder (R12) keeps refused deliveries side-effect-free.
- **bulk_apply** turns every failure to take the lock into one `_LockRefused` (R13) and keeps holder lines out of the one-line record. It records `refused: ...`, so a re-run retries the item.
- **The transmitter** reads the title from the manifest at publish time and never from cached meta. The lineup step is best-effort and cannot stop the timeline, and is digest-gated so equal content is never re-PUT. `notes/_lineup.json` cleverly rides the WAF-allowlisted prefix without colliding with any slug. Spans come from the full plan, interstitials included.
- **The antenna side** adds `programs.js` as a new module rather than new exports of a deployed one, and keeps old-`index.html` compatibility (a `.tickets` `#coming-up` stays flat, and with no `#lineup` nothing is fetched). `lineupDays` steps 12 h at a time, which cannot skip or repeat a day across DST, and carries an on-air occurrence from yesterday into Today. All text goes in via `textContent`, and show.html's `$presents` is escaped.

## Issues

### Critical (Must Fix)
None in the code. The two pre-decided doc fixes, T9-N1 and T9-N2 (N2 has a one-line code part: record the target title), are MUST-FIX before finish. They are a runbook for an irreversible surface and are needed before any restore at scale.

### Important (Should Fix)
1. **station_probe `cross` can pass vacuously** (scripts/station_probe.py:200-206, T13b). Reproduced above. This is the only go-live evidence for the cross-host lock property, so it should land before Task 19.
2. **The docs' "every station write is an atomic rename" claim is false for llama deliver** (emcee/llama station_lock.py:24-27, packages/emcee/CLAUDE.md:44-45; T11a/T11i). The code is fine and no worse than before. The written premise of R6 is what's wrong, and a future maintainer will rely on it. Name the overlay copy and the two-rename replace as the exceptions.

### Minor (Nice to Have)
1. llama CLAUDE.md:178 says "does not share this locking scheme"; make it "this flock scheme" (T11g).
2. Lineup tab ARIA: tablist name, `role=tabpanel`, `aria-labelledby` (T4b).
3. bulk_apply.py:1182 docstring over 100 cols (T12b).
4. retitle classification order (retitle.py:118-126): an awaiting-fix show that is also not in emcee's encoding is listed `refused` (exit 1) rather than `skip ... awaiting fix`. Both are safe, since nothing is written. Noting it only so the dry-run counts aren't misread at Task 20. Leave as is.
5. `emcee run` keeps going after a non-StationLocked lock-create error, while bulk_apply stops (R13) (T6a). It writes nothing. Consider aligning in a later pass.

## Recommendations
- Fix wave contents: T9-N1, T9-N2 (doc plus the `title` in the record line, with a test), T13b (exit 3 on acquired==0 or a pre-existing lock, with a test), the T11a/T11i doc correction, T11g, T12b, and optionally T4b (which needs `npm run pages` and smoke).
- Task 20: read the dry-run `refused` list knowing that awaiting-and-non-encoded shows land there (Minor 4).

## Declined to judge
- deliver's `target_dir.mkdir(parents=True)` on a missing station folder, which could create a local `/Volumes/...` dir on an unmounted share. This is pre-existing (copytree created parents before), and R12 already gates it behind the deliver gate.
- Making deliver's overlay or replace atomic: pre-existing, Shawn's call (see T11a).
- Two concurrent `emcee run`s double-voicing: a documented non-goal, and the lock serializes packages, not runs.
- retitle's ps gate refusing on read-only `llama` processes: the spec says any other emcee or llama process.
- Whether the real CDN/WAF serves `/notes/_lineup.json`: a deploy check (Task 16).
- Cross-host O_EXCL atomicity over SMB/NFS: go-live (Task 19).
- 320 px wrapping and hostile-title rendering: I relied on the Task 4 smoke scenarios and did not re-run the browser.
- `lineupDays` per-tick cost on low-end phones: not measured.

## Assessment

**Ready to merge?** With fixes.

**Reasoning:** The strict surfaces (the lock in both tools, the retitle writer, deliver and clear-mark, bulk_apply) match the spec's lock and backfill sections, and I found no correctness bug in them. What blocks finish is the pre-decided restore-runbook fixes N1/N2 (plus recording the target title), and before Task 19 the vacuous-pass fix to the cross probe, all small.
