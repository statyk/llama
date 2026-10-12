# final-rerev1: scoped re-review of the final-review fix wave (3a3e034..9fdc47a)

Reviewer: Opus, read-only. I made no commits and did not touch the tree, index or branch, and I dispatched no subagents. `git status` stayed clean throughout.

Commands I ran:
- 16 targeted tests at HEAD, all passed. These were the I1 re-encode test and its 4 refusal cases, the I2 publish, service and CLI tests, the Minor 9 fail-fast cases plus the retry-with-backoff test, the Minor 12 fail-closed cases, and the Minor 5 render test.
- One scratch reproduction script under the session scratchpad. It imports the worktree's test helpers and writes only to the scratchpad. Its output is in `final-rerev1.log`.

I did not re-run the full suites. The fix report carries 2453 passed on 3.14, 304 on 3.11, and 304 on Debian 12.

## Verdicts on the in-scope findings

| Finding | Verdict |
|---|---|
| I1: render_step wedge when an on-air show's encode is lost | **ADDRESSED** |
| I2: station can go on air with `fallback_version: null` | **ADDRESSED** (the code gate is correct; the doc wording slightly overclaims, see new item N1) |
| Minor 3: plan text drift (PLAN only) | **ADDRESSED** |
| Minor 4: manual plan/render vs a live run | **ADDRESSED** (runbook sentence) |
| Minor 5: analysis cache never invalidated on a decode mismatch | **ADDRESSED** |
| Minor 6: checklist lacks the live/fallback transition | **ADDRESSED** (the changed trigger is correct) |
| Minor 7: kill-switch allowlist vs checklist order | **ADDRESSED** |
| Minor 8: `start_delay_minutes` vs the first encode | **ADDRESSED** (documented) |
| Minor 9: uploader retries non-retryable errors | **ADDRESSED** |
| Minor 12: corrupt publish.json crash-loops `run` | **ADDRESSED** |
| Minor 13: `row_analysis` caveat | **ADDRESSED** (docstring) |

### I1: ADDRESSED. Each check below is against `pipeline.py:235-299`.

- **An on-air row never re-plans.** `on_air = r.start_frame < n*441` is computed before the `reason` cascade. `if reason is not None and on_air: raise LayoutError` sits *before* the `excluded`/`mismatched`/`replan_from` block. So an on-air row reaches `write_plan` only through the success path, which writes no plan at all. When `reason` stays None the encode exists and the loop builds the segment normally. `FrameCountDrift` still re-raises before the on-air check, so a drifted re-encode halts filling and is not re-planned.
- **Per-slug exclusion rules are intact for rows that are not on air.** The `reason`/`exclude`/`mismatched` cascade and the re-plan block are byte-identical to before. The only change for non-on-air rows is that nothing new runs: the early raise used to fire only when `on_air` was true. The task9-fix2/fix3 tests are untouched and pass in the reported full run.
- **Every damaged on-air case still refuses.** The parametrized `test_render_step_refuses_to_replan_a_show_already_on_air` covers four cases:
  - `changed`: the key changes, giving reason "package changed".
  - `ineligible`: `broadcast.m3u` is removed, so the show is missing from the scan.
  - `render-fails`: a RenderError from the engine.
  - `frames-changed`: `extra+1`, caught by `planned != r.frames`.

  Each case asserts LayoutError, an unchanged plan, no segment at `mid_n`, no encode left behind, and no `plan-changed` log. All 4 pass.
- **The re-encode cannot loop in the success case.** `FrameStore.has` is a disk-existence check. After a successful re-encode the file exists, and `_gc_encodes` keeps every key whose `end_frame > next_n*441`, where `next_n` is the render frontier. The only way to need the encode again is to lose a segment file at or above the frontier. That only happens through publish, which deletes files `<= last`, behind the frontier, or through a new run's `_drop_unpublished_segments`, which re-plans. The new test asserts exactly one extra encode.
- **The re-encode cannot cut mid-show.** The plan is unchanged (`read_plan == rows`). `encode_show … != r.frames → FrameCountDrift` guards the frame count. `build_segment` re-checks every overlapping encode's frame count before cutting. With the fake engine the resulting segments are byte-identical to the reference render. One residual worth knowing is in out-of-scope observation O2.

### I2: ADDRESSED.

- **The implementer's claim is correct; I checked it on the code.** `state.last` advances only in the `save_publish_state` *after* the horizon PUT (`publish.py:345-346`), and segment files are unlinked only after it (`:347-348`). With a horizon-only gate, the next tick's `publish_next(rows, state.last)` returns the same `nxt` and rebuilds the same batch from files that are still on disk, so every segment is re-PUT each tick. That is up to 360 PUTs a minute, and the 17.5k daily budget would be gone within the hour. The reviewer's premise ("uploaded segments stay recorded") is wrong: `runs` feeds only prune. Gating before *any* PUT is the right placement, and mutant i2b's 16 PUTs including `seg/etest/100.aac` twice is consistent with this.
- **The gate spends nothing while it holds.** It sits after `if not batch: return report` and before `_extend_runs` and the first `uploader.put`. So it costs no PUT, takes no budget (`puts.json` is never created, as the test asserts), and changes no runs or high-water mark. The only bucket traffic before it is the pre-existing guard GET, at most once per `guard_check_minutes`. That is Class B and is not new. `publish_all` breaks on `r.error`. Prune runs afterwards, but with `state.last` None it returns before any request.
- **The gate does not wedge a legitimate first start.** `upload_fallback` calls `save_fallback_version` after `index.json` returns 200 and *before* the `state.first is None → return False` deferral (`fallback.py:113-115`). So `fallback render` on a fresh workspace records the version, and the first batch carries it. This is pinned by `test_fallback_render_on_a_fresh_workspace_then_run_publishes_with_its_version`. A failed fallback upload never records the version, which fails closed. `fallback render` run while `run` is already going either succeeds or gets `PublishLocked`, and once it succeeds the next tick publishes.
- **It fails closed on a corrupt fallback.json.** `read_json` raises `JSONDecodeError`, and a non-dict value raises `AttributeError` on `.get`. Both propagate out of `publish_batch` with no PUT. In `run`, `_step` turns this into `ALERT publish`. The manual CLI exits non-zero. `{}` and `{"version": null}` read as None and are gated.
- **The doc rewording is accurate on the publish path,** with one overclaim, recorded as N1 below. The WAF kill switch is still named as the hard stop in both CLAUDE.md and runbook §4 step 4. Runbook §3 step 4 ("run this before step 5", plus the ALERT text), §3 step 7 (re-epoch) and §4 step 4 agree with the code and with each other. I found no remaining "inert without a published fallback" or `fallback_version: null` wording elsewhere in CLAUDE.md or the runbook.

### Minor 3: ADDRESSED.

The plan L1825 annotation matches `config.py:84` (`ge=PRUNE_MARGIN_FLOOR_MINUTES`, which computes to 4). The Task 16 as-built note matches `clock.ts`: `MAX_PUTS = 10` at :79, `putCap = min(MAX_PUTS, ceil(loopMs/d)+2)` at :118-119, and the `horizon-refused` and `loop-clamped` events. The spec is not edited, which is correct per the ruling.

### Minor 4: ADDRESSED.

Runbook §3 step 5 says not to run `plan`/`render` by hand while the service runs, and that `publish`/`status` are safe. `publish` is safe because it takes the flock and refuses on overlap.

### Minor 5: ADDRESSED.

- `AnalysisStale(RenderError)` is raised only on the decoded-vs-analysed sample mismatch (`render.py`).
- `FfmpegEngine.encode_show` catches exactly that error, unlinks `cache/<key>.json`, and re-raises.
- `render_step` still sees a TransmitterError, which becomes "render failed".
- `render_show`'s own `except BaseException: enc.abort()` runs first, so no partial encode survives. The test asserts `not out.exists()`.
- There is no loop: the next `analyze` re-measures and re-caches with the current decoder.

For an on-air row, a decoder change that moves a sample count is now caught on the next tick by `planned != r.frames` and refused. That is correct, because re-planning would cut the show.

### Minor 6: ADDRESSED. The changed trigger is correct.

- `windowEntries` (`playlist.ts:33-40`) marks an entry as fallback only when `n ∉ [first, last]`. Stopping `run` leaves the published horizon, about 24 h ahead by default (`lead_hours = 24.0`), so `cur` stays inside `[first, last]` and the clock keeps serving live. The reviewer's trigger therefore does nothing until the lead drains.
- On a first start, the first horizon has `first = run start = now + start_delay` (`continuing` is false, so `first = nxt`). Until then, `cur < first` gives fallback entries. This is followed by a mixed window, then a pure-live one, where `fi = -1` makes `discSeq = 0` (`:97-102`).
- 70 s exceeds the 6 × 10.24 = 61.4 s window.
- The `transmitter status` wording the item relies on exists: `on air (between shows, or not started)` and `published segments a..b; lead …` at `service.py:238,245`.
- The "outage longer than the lead" alternative is also right: `cur > last + grace` gives fallback, then a recovery starts a new run with a new `first`.

### Minor 7: ADDRESSED.

The checklist now says to start playback first and then enable the rule. It explains that the kill-switch expression (runbook §2 step 7: only `/`, `/index.html`, `/offair.html`, `/style.css`) blocks `player.js`, `nowplaying.js` and `assets/hls.min.js`, so a dead Play button on a freshly loaded page is expected. The WAF rule itself is unchanged, which matches the ruling.

### Minor 8: ADDRESSED.

The runbook §3 step 5 "First start" note is accurate: `start_delay_minutes` defaults to 10.0 (`config.py:38`, template :140), and it affects only fresh runs. The default is unchanged, which matches the review's "document or raise" option.

### Minor 9: ADDRESSED.

- `budget.take()` is still the first statement of every loop iteration, so it runs before every attempt, including the fail-fast one. The test asserts count == 1 and no sleeps.
- Only `_error_code(exc) ∈ {AccessDenied, InvalidAccessKeyId, NoSuchBucket, SignatureDoesNotMatch}` raises early.
- Any other exception, and a non-200 status, still falls through to the backoff, as before. `test_retry_with_backoff_and_every_attempt_counts_against_the_budget` still passes (3 attempts, sleeps `[1.0, 2.0]`, count 3).
- Callers are unchanged: the segment loop records `report.error`, and the site step logs it and continues to the horizon PUT, which fails fast too. With bad credentials that is about 2 counted PUTs per tick instead of 8, and the alert still fires.

### Minor 12: ADDRESSED.

- `Runner._read_lead` wraps `lead_us`. Its broad `Exception` covers `JSONDecodeError`, `AttributeError` and `OSError`. It logs, raises `ALERT publish-state`, and returns `(False, None)`.
- `tick` returns before any `_step`, so there is no plan, render, publish or prune, and therefore no bucket call. The test asserts `bucket.log == []`, `engine.analyzed == []`, and no `plan.jsonl`.
- The post-publish read uses the same wrapper, and `filling` is left unchanged when it fails.
- After repair, the next tick publishes. Nothing escapes `tick`, so there is no crash loop.

### Minor 13: ADDRESSED.

The `row_analysis` docstring states `time.time()`, `quiet_s=0`, the full analysis that can run under the publish flock, and the reachability: after `cache/` is deleted, or once after a Minor 5 drop.

## New issues in the fix diff

**N1 (Minor; doc overclaim, pre-existing code path).**
- **The claim.** The new CLAUDE.md sentence "Every horizon therefore names a fallback" and runbook §4 step 4's "transmitter never publishes a horizon without one … so every `state/horizon.json` names a version" are not strictly true.
- **Why it fails.** `prune` (`publish.py:392-394`) still rewrites the horizon with `load_fallback_version(p.ws)`, which is ungated. If `fallback.json` is lost after the station has published (an operator deletes it, or restores `~/.transmitter` without it), the next prune PUTs `fallback_version: null` and makes off-air inert.
- **Reproduced in scratch.** I published 100..139 with a version, unlinked `fallback.json`, and ran prune at segment 200. The result was `horizon fallback_version = None` (log: `final-rerev1.log`).
- **Why it is only Minor.**
  - The fix diff did not introduce the code path; it only introduced the absolute wording.
  - Reaching it needs local state loss.
  - In that state `publish_batch` alerts `no fallback rendered` every tick, and re-running `fallback render` rewrites the horizon with a version (`fallback.py:123-124`).
  - The WAF kill switch is unaffected.
  - Spend is unaffected: prune's rewrite is one PUT per `prune_min_segments`, as before.
- **Fix options.** Either one line in `prune` (if `load_fallback_version` is None, set `report.stopped = "no-fallback"` and return before the horizon PUT; deletes must wait for the horizon to shrink anyway), or soften the two sentences to "every horizon publish/prune writes names the recorded fallback; if `fallback.json` is lost, re-run `fallback render`".

I found no other breakage. There are no 3.12+ APIs in the diff, and no llama or emcee imports.

## What I checked (one focused check per named risk)

1. I1, re-plan: traced the control flow from the `on_air` computation through the raise to the re-plan block. The raise always precedes `excluded`/`mismatched`/`write_plan`.
2. I1, exclusion rules for rows that are not on air: diffed the cascade (unchanged) and confirmed the old early-raise was `on_air`-only.
3. I1, refusal cases: ran the 4 parametrized refusal tests and read their assertions.
4. I1, loop: checked `FrameStore.has` (`layout.py:114`) and the keep rule in `_gc_encodes`.
5. I1, mid-show cut: checked the unchanged plan, `FrameCountDrift`, and the `build_segment` frame re-check (`layout.py:147-151`), and ran the re-encode test.
6. I2, re-PUT claim: traced where `state.last` and the segment unlinks happen relative to the horizon PUT (`publish.py:345-348`) and how `publish_next` uses `state.last`.
7. I2, first start: checked the ordering of `upload_fallback`'s save versus its deferral and ran the CLI first-start test.
8. I2, no spend while held: checked the gate's position relative to `_extend_runs` and the first put, and the test's assertion that `puts.json` is absent; prune returns early with `last` None.
9. I2, corrupt fallback.json: checked `read_json` (`workspace.py:47-51`), which raises, the `.get` on non-dicts, and that `_step` catches it.
10. I2 docs: checked CLAUDE.md :240-252 and runbook §3 steps 4, 5 and 7 and §4 step 4 against the code, and grepped both for leftover null/inert wording. This produced N1.
11. Minor 6: checked `windowEntries`, `buildPlaylist`'s `discSeq`, the `status_lines` strings, and the `lead_hours` default.
12. Minor 9: checked the order of `budget.take()` within the loop and ran both the fail-fast and the backoff tests.
13. Minor 12: checked the early return in `tick` and ran the parametrized fail-closed test (no bucket calls).
14. Minor 3: checked `config.py:84` and `clock.ts:79,118-119,160,169`.
15. Minor 5: checked that `AnalysisStale` is raised only on the sample mismatch, the drop, the re-raise, and `enc.abort()` ordering, and ran the test.

## Out-of-scope observations (to defer; not blockers)

- **O1 (prune gate, the code half of N1).** If the operator prefers keeping the wording, gate prune's horizon rewrite on a recorded fallback version. Phase 2's dead-clock check should also notice `fallback_version: null`, which the final review already recommends.
- **O2 (I1 residuals).** These are CPU/continuity only, with no spend.
  - (a) For an on-air row whose encode *persistently fails* (a corrupt file on NFS), every tick now attempts a full re-encode before refusing. Before the fix it refused instantly. This is the deferred T9-a "no negative memo" class, now reachable for on-air rows: minutes of CPU and NFS per tick until the lead drains.
  - (b) For the residual refusals there is still no runbook line. In fact the station self-heals once the lead drains: `render_step` reports recovery pending, `plan_step` cuts the plan at the frontier, and a new run starts. The cut is deferred about a lead's length and bridged by the fallback loop. One runbook sentence on the `… already on air … cannot be re-made` alert would close the "nothing actionable" complaint for these cases.
  - (c) A re-encode of an unchanged package under a changed `[render]` loudness target, or a different ffmpeg build, splices two encodes at a segment boundary mid-show. The planned frames are equal, so it is a level or encoder-delta step, not a cut.
- **O3.** The plan's Task 9 interface line (about L4011) still describes the old "LayoutError whenever an on-air row's encode is missing" behaviour, as the implementer flagged. It needs a one-line as-built note.
- **O4.** A `fallback.json` holding a non-null but bogus version (`""`, a number) passes the gate. Only transmitter writes this file, so this is negligible.

Fix wave: Approved

Reasoning: All eleven in-scope findings are addressed, and both of the implementer's departures check out on the code. Gating before any PUT is necessary to avoid a re-PUT-every-tick loop, and the fresh-run-start trigger is the only one that actually reaches fallback while a lead is published. The one new item (N1) is a doc overclaim over a pre-existing prune path reachable only by losing `fallback.json`. It does not touch spend or the WAF stop, and is cheap to fold in or defer.
