VERDICT: Ready to merge: With fixes

# Final whole-branch review — playout phase 1 (ff14e07..3a3e034, 44 commits, 19 tasks)

Reviewer: Fable (single reviewer, no subagents dispatched; the review was done in nine
passes, logged in `final-review.log`). Read-only: no commits, no mutation of the tree,
no wrangler, no network. The only commands run were the two full pytest suites (worktree
and main) to settle the warnings question; `./.venv/bin/python -c "import transmitter"`
and `./.venv311/bin/python -c ...` both resolve inside the worktree.

The "fixes" in the verdict are small and none is on the spend surface: one continuity
trap in `render_step` (Important 1), one operator-ordering gap that leaves both off-air
levers inert (Important 2 — this is also my answer to open item (b)), and doc drift.
Nothing found can multiply PUTs, serve uncached, or make the station unstoppable beyond
what the spec already accepts for phase 1 (the WAF kill switch is the hard stop).

## Strengths (specific)

- **The clock's spend bound is input-independent.** `antenna/src/clock.ts:75-79,118-120,167-172`:
  `MAX_PUTS = 10` is a hard constant, the horizon is refused unless `d === 10.24`, and
  `loopMs` is clamped to 75 s before the cap is computed. A corrupt or hostile
  `state/horizon.json` cannot turn the clock into a PUT loop. The tests pin this with
  adversarial inputs (`d = 0.01`, `LOOP_SECONDS=900`, skewed fire time), not just the
  happy path.
- **The high-water mark closes a real gap the plan had.** `publish.py:308-313` persists the
  candidate `last` before the horizon PUT; `pipeline.plan_step` recovers on
  `listed_bound()`; `prune` and `upload_fallback` both refuse to rewrite the horizon below
  it. `test_publish.py:97-174` simulate the crash with a `BaseException` raised *after* the
  fake bucket stored the object — a genuine "the 200 never reached us" test, not a mock
  that asserts nothing.
- **No List call can slip in unnoticed.** `helpers.FakeBucket.__getattr__` raises on any
  S3 method the publisher is not supposed to use (`list_objects*`, `delete_objects`).
  Prune deletes per key by computed range; every PUT attempt (including retries) takes
  from the daily budget *before* the request (`publish.py:95`).
- **Guard fails closed and re-reads on a clock step-back** (`publish.py:126-137`), and the
  unreadable-guard case is tested for both publish and prune.
- **Frame-line arithmetic is consistent end to end.** `extra_frames()` and
  `ENCODER_PRIMING_SAMPLES` were measured equal (1 frame / 1024 samples) on ffmpeg 5.1.9
  and 8.1.1 (task2-fix1), `render_show` verifies the encoder's count against
  `planned_frames` and deletes an unverifiable encode, `FrameStore.build_segment`
  re-checks every overlapping encode's count before cutting, and `site.file_starts` adds
  the same priming constant. The Debian-12 gate ran on every ffmpeg-touching task.
- **Operator-facing docs match the code.** I checked every quantitative claim in
  `docs/playout-setup.md` and the new CLAUDE.md paragraph against the source (MAX_PUTS,
  d refusal, loop clamp, prune floor = 4, `HELD_ALERT_AFTER = 3`, PublishLocked
  behaviour, fallback-before-first-publish in the re-epoch procedure, cache headers per
  key class). All hold.
- Tests parse segments back (`segment.parse`, `payloads`) rather than asserting on
  mocks; the gapless segue test decodes the real ADTS output and measures RMS across the
  join; the one-package-station wedge and the per-slug second-mismatch rule are pinned.
- Python 3.11: no 3.12+ API in src or tests (grepped for `itertools.batched`, `Path.walk`,
  PEP 695, `datetime.UTC`, `typing.override`, `except*`); 289 passed on CPython 3.11.15
  and on Debian 12 in Docker.

## Issues

### Critical

None.

### Important

1. **`render_step` wedges filling permanently when a show already on air has lost its
   encode, with no documented way out.** `packages/transmitter/src/transmitter/pipeline.py:223-227`
   raises `LayoutError("… is already on air … refusing to re-plan into a mid-show cut")`
   whenever `store.has(r.key)` is false for a row whose `start_frame < n·441`. The
   `Runner` catches it as an ordinary step error, so every tick alerts and renders
   nothing; the lead drains to fallback in ~24 h. The refusal is more conservative than
   needed: when the package is unchanged (`show.key == r.key`) re-encoding reproduces the
   planned frame count by construction — the `encode_show … != r.frames → FrameCountDrift`
   check three lines below already proves it — so the only cases that *must* refuse are
   "package changed / no longer eligible / encode failed". Triggers are operator-side
   (cleaning `render/`, restoring `~/.transmitter` without `render/shows`), so likelihood
   is low, but the failure mode is an alert every minute pointing at nothing actionable.
   Fix: for an on-air row, attempt the re-encode path (same `else:` branch) and raise the
   LayoutError only if `reason` would be set; add a test that deletes the encode of an
   on-air row and asserts the next segment is written from a fresh encode. Alternative if
   you prefer not to touch the loop: document in the runbook that the recovery is
   `rm plan.jsonl` (plan_step then starts a fresh run at `listed_bound()+1`, one cut at a
   segment boundary ~lead hours later).

2. **Nothing prevents the station going on air with `fallback_version: null`, which makes
   BOTH off-air levers inert** (`clock.ts:180-191`, `playlist.ts:76,81`). The runbook orders
   `fallback render` before `run` (section 3 steps 4-5) and the re-epoch procedure says
   "before the first publish", but the code never enforces it: `publish_batch` happily
   PUTs a horizon with `fallback_version: None` (`publish.py:314-316`). In that state the
   operator flag does nothing, a stale horizon does nothing, and the "N < first" window
   after a recovery lists nothing (`buildPlaylist` returns null: players stall on the
   previous playlist, which is the continuity half of open item (b)). Spend effect: none
   directly; continuity/stoppability effect: the only stop is the WAF rule, and the
   runbook says so — but a one-line gate removes the whole class. Fix: in
   `publish_batch`, before the horizon PUT, `if load_fallback_version(p.ws) is None:
   report.error = "no fallback rendered: run `transmitter fallback render` first"; return
   report` (segments already uploaded stay recorded in `runs`; nothing is listed until the
   fallback exists). `prune` needs no change (it only runs with `state.last` set).
   Tests: `helpers.make_publisher` saves a fallback version; one new test in
   `test_publish.py` asserting no horizon PUT and the error; `test_cli.py::test_run_once_end_to_end`
   and the two `_publish_setup` tests need `save_fallback_version`. See (b) below for the
   clock-side half.

### Minor

3. **Doc drift, plan/spec vs code** (deferred list): plan L1825 says `prune_margin_minutes
   … ge=0`; code floors it at `PRUNE_MARGIN_FLOOR_MINUTES = 4` (`config.py:58-73`). Plan
   Task 16 describes the formula-only PUT cap; code has the hard `MAX_PUTS=10`, `d`
   refusal and 75 s clamp. Spec :398 says pure-fallback discontinuity sequence is
   `floor(N/len)`; code is `floor(N/len)+1` (`playlist.ts:87-101`) — the RFC 8216 §6.2.2
   argument in the ledger is correct (the clamp renumbered segments inside the first `len`
   segments of an epoch, and the regression test at `playlist.test.ts:101-122` pins the
   fix). All three need one-line edits to the plan/spec text, not code; the spec edit
   wants the operator's sign-off since it is the binding document.

4. **Manual `transmitter plan` / `render` take no lock against a live `run`**
   (`cli.py:64-84`; the flock covers only publish/prune/fallback per the constraints).
   Two processes can both re-plan from the frontier in `render_step` and write
   `plan.jsonl` last-writer-wins; the deterministic planner makes the usual outcome
   identical, and `path.exists()` skips make a duplicate segment harmless, but a segment
   written by the loser from a stale plan is possible. Fix now: one sentence in the
   runbook ("do not run `plan`/`render` by hand while the service runs; `publish` is
   safe"); fix later: a non-waiting `render.lock` shared by `plan`, `render` and the
   runner's fill step.

5. **Analysis cache is never invalidated on a decode mismatch.** `render.py:97-99` raises
   `RenderError("… decoded to n samples but was analysed at m — the package changed")`,
   `render_step` excludes the show, and the cache entry (`analysis.py:110-116`, keyed by
   file set only, not ffmpeg version) stays. A decoder change that alters trimmed sample
   counts would fail every show every tick, with a message blaming the packages, until
   someone deletes `cache/`. Fix: on that specific RenderError unlink
   `cache/<key>.json` so the next tick re-analyses; or fold the ffmpeg version string into
   the cache filename.

6. **The phase-1 verification checklist never exercises the live↔fallback↔live
   transitions with real players** (`docs/playout-setup.md:186-190` covers ENDLIST and
   403 only). The deliberate restart of `EXT-X-DISCONTINUITY-SEQUENCE` to 0 when the
   window returns to pure live (`playlist.ts:94-96`, "spec-accepted glitch") is the one
   playlist behaviour that cannot be verified offline, and hls.js/Safari tolerance of a
   decreasing sequence is not something I can assert. Add a checklist item: stop
   `transmitter run` for >40 s with players attached (fallback loop audible, discontinuity
   at the switch), restart it, confirm each player returns to live (or needs exactly one
   reload).

7. **Kill-switch verification vs allowlist.** The kill-switch rule (`docs/playout-setup.md:72`)
   allows `/`, `/index.html`, `/offair.html`, `/style.css` but not `player.js`,
   `nowplaying.js` or `assets/hls.min.js`; a page loaded *after* the switch is enabled
   has a dead Play button rather than the off-air notice the checklist (line 189-190)
   describes. The checklist's order (play first, then enable) works; say so explicitly,
   or allowlist the three JS files in the kill-switch rule (they are static and cheap).

8. **`start_delay_minutes = 10` may be shorter than hugo's first analyse+encode of a 3 h
   show** (two full decodes over NFS plus ebur128, then up to 360 PUTs). It is not a
   recovery — tick 2 finds everything published — but the first minutes of the first
   show are simply never aired, and the clock writes nothing until the first horizon
   exists (`clock.ts:166`). Document ("raise `start_delay_minutes` if the first show starts
   mid-song") or default to 15-20.

9. **Uploader retries non-retryable errors.** `publish.py:103-107` catches every exception
   and retries 4× with backoff, so a wrong bucket name or revoked key costs 4 PUT
   attempts and ~7 s per tick, every tick, with an alert each time (5,760 budget units a
   day — bounded, never trips the 17.5k budget). Classifying `AccessDenied`,
   `InvalidAccessKeyId`, `NoSuchBucket`, `SignatureDoesNotMatch` as fail-fast would cut
   that to 1/tick. Spend effect is small and bounded; the alert makes it visible.

10. **Off-air costs one PUT per invocation (~1,440/day, ~43k/month Class A)** because
    `offairPlaylist`'s MEDIA-SEQUENCE advances per invocation and `lastBody` is
    per-invocation (`clock.ts:175,193`). Likewise the forced immediate write
    (`clock.ts:204`) duplicates the previous invocation's last boundary write ~once a
    minute in the live case. Both are spec-literal ("write immediately", "skip bytes
    identical to the last write" within an invocation) and inside the spec's own 360k/month
    estimate. If Class A ever matters, seed `lastBody` from a GET of `live.m3u8` through
    the binding (Class B, 43k/month) and skip the forced write when identical — saves
    ~100k Class A/month. No action for phase 1.

11. **`plan_step` scans the whole NFS root every tick while filling even when the plan is
    already covered** (`pipeline.py:125` runs before the early return at `:156-157`):
    ~256 packages × (manifest read + N stats) per minute during a fill. Not spend; keep
    as is (the refusal-on-missing-marker semantics depend on it), but expect it in
    NFS traffic graphs.

12. **A corrupt `publish.json` crash-loops `run` without an ALERT line**: `Runner.lead_us`
    (`service.py:154-156`) runs outside `_step`, so a `JSONDecodeError` escapes `tick`,
    `main_cli` prints a traceback, systemd restarts it every 30 s. Writes are fsynced
    and atomic so this needs disk-level damage. Wrap `tick` body or treat an unreadable
    publish.json as a fail-closed alert.

13. **`row_analysis` (service.py:56-69)** uses `time.time()` with `quiet_s=0` and can run a
    full ffmpeg analysis inside `_publish_site` while the publish flock is held. Reachable
    only when `cache/<key>.json` is missing for a planned row (the cache is never GC'd),
    i.e. after an operator deleted `cache/`; then one show's analysis (~minutes) extends
    one publish tick. Acceptable; note it in the module docstring.

14. Cosmetic/deferred-OK: `station.evaluate` labels a `dj-audio/` m3u entry not named in
    `dj_audio` as kind `track` (it would join the music loudness set and skip the clip
    pause) — emcee never writes such an entry; `site.py:147` archive URL scheme unchecked
    (trusted llama input); `.gitignore` gains a global `*.aac` (nothing tracked matches).

## Deferred-items triage (every item from `final-review-deferred.md`)

Legend: **FIX** = must fix before merge; **defer** = fine to defer (file it); **none** = no action.

| # | Item | Triage |
|---|---|---|
| D1 | `row_analysis` uses `time.time()`; can run ffmpeg analysis under the publish flock | defer — Minor 13; reachable only after a cache wipe |
| D2 | Manual `plan`/`render` take no lock against a live `run` | defer, but add the runbook sentence now — Minor 4 |
| D3 | Plan/spec say `prune_margin_minutes ge=0`; code floors at 4 | FIX (doc only) — Minor 3 |
| D4 | Plan/spec Task 16 describe formula-only PUT cap; code has MAX_PUTS=10, d refusal, 75 s clamp | FIX (doc only) — Minor 3 |
| D5 | SPEC DEVIATION: pure-fallback discontinuity sequence floor(N/len)+1 | FIX (spec wording, operator sign-off) — code is right per RFC 8216 §6.2.2; the regression test pins it |
| D6 | Epoch change restarts MEDIA-SEQUENCE; players must reload | none — runbook §3 step 7 and the `runClock` docstring both state it |
| D7 | fed0df4 committed with one failing test, fixed by 04b6df6 | none — HEAD green on 3.14/3.11/Debian 12 and `npm test` 37/37; history not worth rewriting |
| D8 | 26 pytest warnings at HEAD | none — settled by running the full suite on this branch (2438 passed, 26 warnings) and on main at ff14e07 (2149 passed, 26 warnings): identical set, all `DeprecationWarning: multi-threaded … fork()` from Python 3.14's `multiprocessing/popen_fork.py` in llama's concurrency tests; nothing new on the branch, and llama/emcee/herder are byte-identical to main |
| D9 | Wrangler dry-run never run | none here — already in runbook §4 step 2; keep it in the checklist |
| T1-a | `adts.parse_header` ignores raw_data_blocks; CRC unchecked | defer — ffmpeg's `aac` encoder emits one block, no CRC; `require_station_format` is a sanity check not a validator |
| T1-b | `id3.parse_timestamp_tag` raises IndexError on a truncated tag | defer — only `segment.parse` (tests, spike) calls it |
| T1-c | `segment_key` accepts negative n | none — `segment_timestamp` refuses n<0 first on every real path |
| T1-d | `adts.build_frame` masks out-of-range fields | defer — test/contingency helper only |
| T1-e | `grid.us_to_iso` truncates to ms | none — the epoch is whole seconds; segment starts are exact in ms |
| T1-f | Task 1 test gaps; ADTS comment says ffmpeg 8.1 | defer — comment should mention 5.1.9 measurement too (cosmetic) |
| T1-g | `typing.Sequence` style nit | none |
| T2-a | AacFileEncoder `__exit__` no-op on clean exit; close() not idempotent; .tmp leak if os.replace fails | defer — `_gc_encodes` sweeps stale `.tmp` after an hour; render_show's try/except aborts on every failure |
| T2-b | frame-count model pinned only on silence | none — reviewer measured tones; `test_render_show_frame_count_gain_and_gapless_segue` pins it on real music |
| T2-c | build test doesn't pin wrap<end; live test skips ENDLIST edges | none — operator checkpoint covered live wrap in every player |
| T2-d | printed offsets ~23 ms early; banner loose | none — spike tool |
| T3-a | `atomic_write_bytes` no fsync | none — fixed in Task 7 (`workspace.py:28-29`) |
| T3-b | corrupt state JSON / config OSError surface as tracebacks | defer — Minor 12 for the one that crash-loops `run` |
| T3-c | `prune_margin_minutes ge=0` | none — fixed in Task 12 (floor 4) |
| T3-d | `load_or_create_epoch` not exclusive | none — fixed in Task 11 (`epoch.lock`) |
| T3-e | template test can't catch a missing knob; config mode 0600; init race | none — test_config pins template == defaults; the rest cosmetic |
| T5-a | non-dict show/source/dj_audio → AttributeError | none — `_evaluate` guards `dj_audio` with isinstance and `show`/`source` with `or {}`; a non-dict `show` would still raise `.get` — defer, llama never writes one |
| T5-b | dj-audio entry not in `dj_audio` becomes "track" | defer — Minor 14 |
| T5-c | `typing.Iterable` vs collections.abc | none |
| T5-d | persistent EACCES labelled "changing:" | none |
| T7-a | silence-path tests thin | defer |
| T7-b | gapless test checks lengths; resampler transient at 48 kHz segue joins untested | defer — the RMS-across-the-join assertion in test_render covers 44.1 kHz; 48 kHz sources are rare on the LMA MP3 derivatives |
| T7-c | cache key ignores ffmpeg version; no subprocess timeouts (NFS hang) | defer — Minor 5 for the cache; the NFS-hang case is phase 2's lead-floor alert in the clock, by design |
| T7-d | test comment −14.8 claim; OSError from read_json; fsync per segment write | none/defer — fsync per 160 KB segment is cheap at ~1/10 s |
| T4-a | `build_segment` doesn't validate rows / n>=0 | none — `read_plan` validates; `render_step` only passes n ≥ publish_next |
| T4-b | FrameStore memory ~170 MB × keep=2 | none — hugo has the RAM; documented in the class docstring |
| T4-c | no tests for LRU eviction etc. | defer |
| T6-a | PlanError "no eligible packages" when all skipped; rows added then discarded | none — `test_plan_step_recovery_with_nothing_eligible_touches_nothing` pins the invariant that matters |
| T8-a | changed package detected only after full decode+encode | none — by design; `render_show` catches it |
| T9-a | no negative memo for persistently failing shows | defer — CPU/log only (each tick re-tries one failing show per re-plan) |
| T9-b | PlanError on re-plan untested; doomed encode redone each tick | defer |
| T9-c | stale `.N.aac.*.tmp` in `render/seg/` never GC'd; helpers imports pipeline at top | defer — `atomic_write_bytes` unlinks its temp on failure; only a kill -9 mid-write leaks one small file |
| T10-a | site.py archive link scheme unchecked | none — Minor 14 |
| T11-a | `(last,hw]` local seg files leak when a new run starts above hw | defer — ≤ one batch (~58 MB) on disk, once |
| T11-b | `render_step` uses plain `last` not `listed_bound()` | none — unreachable: files ≤ hw are only deleted after the save that sets last=hw |
| T11-c | listed+1 floor inert in the recovery branch | none — defensive; comment is accurate |
| T12-a | prune's hw deferral also blocks old-run deletes below `first` | defer — deletes are free; one reconcile batch later they happen |
| T12-b | test_config redundancy; comment "listed (6+3)·d after" → "at most" | none (cosmetic) |
| T14-a | `publish_all` break-condition mutant survives | none |
| T15-a | wrangler types @types/node hint; 3 extraneous npm packages | none |
| T18-a | runbook "always $TRANSMITTER_ROOT/config.toml" ignores `--config` | none — runbook never uses `--config` |
| T19-a | "What this is" parenthetical antecedent; ~95-col line | none (cosmetic) |
| M2 | Spec's "128 kbps CBR" not achievable with native `aac` (ABR-ish, silence → tiny frames) | none beyond a spec note — nothing in the design depends on constant frame size; the grid counts frames, not bytes, and storage is *lower* than the 57.6 MB/h estimate |
| M4 | Plan-mandated duplication (lock+guard preamble ×3, seg-seconds ×3, clip-pause ×3, ffmpeg stderr ×2, playlist header ×2) | defer — the three `publish_lock`+`guard_blocks_publishing`+`load_publish_state`+`check_epoch` preambles (`publish.py:244-250,347-353`, `fallback.py:106-108`) are the one worth folding into a `_open_publish(p, now_us)` context manager so a future writer cannot forget the guard; the rest is cosmetic. Not a merge blocker: each copy is tested on its own path |
| Task 9 parked ruling (one-package wedge) | none — fixed by task9-fix2/fix3 and pinned (`test_one_package_station_*`, `test_a_lone_show_mismatching_twice_*`) |

## (b) Off-air without a published fallback — recommendation

**Both options are cheap on spend; neither can run up a bill.** Null (today): the clock
writes nothing; players keep polling the stale `live.m3u8` at its 5 s max-age, so the
edge refetches from R2 about once per 5 s per tier (≤ ~17k Class B/day, inside 10M free)
and the segments they already have are cache hits; hls.js and Safari stall rather than
stop, VLC retries. ENDLIST-only: one PUT per invocation (MEDIA-SEQUENCE advances; ~43k
Class A/month, same as off-air *with* a notice today); players that honour it stop and
polling ends. On continuity both are dead air by definition; the difference is whether
the listener gets the off-air notice or an indefinite stall, and whether the operator's
lever visibly did anything.

**Recommendation: ENDLIST-only, plus the transmitter gate in Important 2 so the branch
is almost never reached.** Reasoning: (1) the point of the flag is to stop; writing
nothing is the one outcome that *cannot* be distinguished from a dead clock by a listener,
an operator reading the player, or a dead-clock alert in phase 2; (2) a zero-segment
playlist with `#EXT-X-ENDLIST` is RFC-valid and the `MEDIA-SEQUENCE` rule is already
handled by `offairSeqMs`; (3) player.js already treats `ended`/`error`/`live === false` as
off-air, so Safari and VLC stop with the right notice. The one honest caveat: hls.js
reports an empty media playlist as a non-fatal `LEVEL_EMPTY_ERROR` and may keep
reloading it; player.js would need `if (data.details === "levelEmptyError") offAir(...)`
(one line, `player.js:59-63`) to stop cleanly there. Even without that line, ENDLIST-only
is no worse than null for hls.js and strictly better for everything else.

What each option touches:
- **Keep null** (no change): nothing; the `offair-without-fallback` error, runbook §4
  step 4 and the CLAUDE.md sentence already document it.
- **ENDLIST-only**: `antenna/src/playlist.ts` — new `endlistOnly(g, seqMs)` (header +
  `MEDIA-SEQUENCE` + `ENDLIST`, no segments) returned from `buildPlaylist` when
  `isOffair && fb === null`; `clock.ts:180-191` keeps the structured error but no longer
  gates on `body === null` for this case; `player.js:59-63` the hls.js empty-level line;
  tests: `playlist.test.ts:154-158` (the `offair: true, fallback: null` expectation flips),
  `clock.test.ts:121-147` (puts become 1 per invocation, error still logged once), one
  new assertion that the body has no URI lines; docs: runbook §4 step 4 and the CLAUDE.md
  "INERT" sentence become "ENDLIST without a notice".
- **Transmitter gate** (recommended with either option): `publish.py` before the horizon
  PUT, `helpers.make_publisher`, one new test, three `test_cli` setups — see Important 2.

If the operator prefers the spec's literal "notice + ENDLIST" semantics and would rather
not add a no-notice branch at all, the gate alone (Important 2) gets most of the value:
with it, the only way to reach the null branch is deleting fallback objects from R2 by
hand.

## Recommendations (beyond the issues)

- Fold the three publish-lock/guard/state/epoch preambles into one context manager
  (M4) before phase 2 adds `offair`/`budget` writers — four copies is where the guard
  gets forgotten.
- Add the fallback transition to the phase-1 checklist (Minor 6) and record the hls.js
  behaviour on the pure-live sequence restart; if any player needs a reload there,
  consider carrying the live discontinuity count forward instead of restarting at 0.
- Phase 2's dead-clock check should also notice `fallback_version: null` in the horizon
  it fetches, as a belt to Important 2's braces.
- When phase 2 ships alert dedupe, the per-tick `ALERT publish: PUT … failed` from a
  misconfigured bucket (Minor 9) is the first thing it should collapse.

## Declined to judge

- Phase 2-4 functionality (cost guard, WAF reconciliation, alert channels,
  `transmitter offair|budget`, scheduler, embed.html, index.html rewrite at show
  boundaries, Media Session): spec-scoped out of phase 1; the seams exist
  (`guardStep`, `alerts.alert`, `anchors: []`).
- The Playwright smoke test: plan-listed deliberate deferral.
- Correctness of the Cloudflare dashboard steps (cache rule semantics on Free, `wildcard`
  availability, Budget alert mechanics, Smart Tiered Cache): no network allowed and they
  are the phase-1 verification checklist's job, not the code's.
- hls.js's exact behaviour on a decreasing `EXT-X-DISCONTINUITY-SEQUENCE` at the
  fallback→live return and on an empty ENDLIST playlist: not verifiable offline; turned
  into checklist items (Minor 6, (b)) rather than judged.
- `transmitter.spike` internals: dev-only tool, exempt from the atomic-write constraint
  by the plan, not on any production path (the CLI never imports it).
- `npx wrangler deploy --dry-run` and the real asset deploy: banned for this review; in
  the runbook.
- LMA licensing / ToS exposure and the Paid-plan decision: spec context, not code.
- The 24 h `offair_after` default (fallback loop can play for up to 24 h after the lead
  runs out before ENDLIST): spec-chosen value; a product decision, not a defect.
- Whether `antenna/worker-configuration.d.ts` is current: generated file, excluded from
  the diff by the brief; `Env` carries `BUCKET: R2Bucket` and the five vars, which is
  all `index.ts` needs.

## Assessment

A careful, well-tested slice whose spend paths are genuinely bounded on both sides and
whose one novel invariant (the high-water mark) is pinned by crash-shaped tests; the two
Important items are a continuity trap with no documented exit and an ordering gap that
leaves the off-air lever inert, both cheap to close, and nothing found changes the
operator's spend exposure.
