# final-fix1 handback

**Status: DONE**

Worktree `/Users/shawn/projects/llama/.claude/worktrees/playout-phase1`, branch `playout-phase1`, 3a3e034 → **9fdc47a**. Tree clean. Nothing touched under antenna/, the spec, or llama/emcee/herder.

## Commits
- `88fbad1` fix(transmitter): re-encode a lost encode of an unchanged show on air (I1)
- `f3a2e74` fix(transmitter): publish nothing until a fallback is rendered (I2, plus CLAUDE.md and runbook wording)
- `67fed1f` fix(transmitter): drop the cached analysis on a decode/analysis mismatch (Minor 5)
- `f69a4b0` fix(transmitter): fail fast on bad credentials; survive a corrupt publish.json (Minors 9, 12, 13)
- `9fdc47a` docs(playout): as-built plan notes; runbook ordering and checklist items (Minors 3, 4, 6, 7, 8)

## Per finding

**I1** (`pipeline.py` render_step). A row already on air whose encode is missing now goes through the normal re-validation and encode path. If the package is unchanged and still eligible, it is re-encoded, and the existing `encode_show … != r.frames → FrameCountDrift` check guards the frame count. `LayoutError("… already on air … cannot be re-made (<reason>) …")` is raised only when `reason` would be set: package changed, no longer eligible, planned frame count changed, or the encode failed. An on-air row never re-plans and never touches `excluded`/`mismatched`. The per-slug rules from task9-fix2/fix3 are unchanged for rows that are not on air. Tests in `test_pipeline.py`:
- `test_render_step_reencodes_a_lost_encode_of_an_unchanged_show_on_air` (new): it renders everything as a reference, deletes the segment files from `mid_n` on and the on-air show's encode, then renders again. The segments are byte-identical to the reference, the show is encoded exactly once more, and the plan is unchanged.
- `test_render_step_refuses_to_replan_a_show_already_on_air` (rewritten, parametrized `changed|ineligible|render-fails|frames-changed`): each case raises LayoutError, leaves the plan untouched, writes no segment, leaves no encode, and logs no plan-changed line.

**I2** (`publish.py` publish_batch). If `load_fallback_version(ws) is None`, `report.error = NO_FALLBACK` ("no fallback rendered: run `transmitter fallback render` first; …") and the batch returns.
- **Deviation from the suggested placement, with evidence.** The gate sits **before any PUT** (right after the batch is found non-empty), not just before the horizon PUT. The review assumed that "segments already uploaded stay recorded so nothing is re-PUT". That is wrong. `runs` only feeds prune. `publish_next` works from `state.last`, which only advances after a horizon PUT, and segment files are unlinked only after the horizon PUT. So with a horizon-only gate, every tick re-PUTs the same batch (up to 360 PUTs a minute; the 17.5k daily budget would be gone in under an hour). Mutant i2b below shows it: 16 PUTs over two calls, including `seg/etest/100.aac` twice.
- With the gate before any PUT: no PUT, no budget taken (`puts.json` is not even created), no `runs` or high-water change, and the segment files are kept for the first real batch.
- How it surfaces:
  - `run`: `_report_stop` logs `ALERT publish: no fallback rendered …` every tick; no crash, and `publish_all` stops on the error.
  - `transmitter publish`: exits 1 and prints the message.
  - A corrupt `fallback.json` raises inside publish_batch, and `_step` turns it into `ALERT publish` (fails closed).
- **The fallback "deferred" path is confirmed fine.** `upload_fallback` calls `save_fallback_version` *before* its `state.first is None → return False` deferral (fallback.py:113-115). So on a fresh workspace `fallback render` records the version and the first batch carries it. This is pinned by the new `test_cli.py::test_fallback_render_on_a_fresh_workspace_then_run_publishes_with_its_version` (horizon `fallback_version == "v1"`).
- Test changes:
  - `helpers.make_publisher` gains `fallback_version=FALLBACK_VERSION` (saved by default; `None` opts out).
  - `test_publish.py::test_uploads_segments_then_site_then_horizon` now expects that version.
  - `test_fallback.py::test_upload_refuses_state_from_another_epoch_before_any_put` passes `fallback_version=None` (it asserts no version gets recorded).
  - `test_cli.py`: `test_run_once_end_to_end`, `_publish_setup` (all three `_publish_setup` tests) and `_fallback_setup(with_horizon=True)` save a version.
  - `test_service._publisher` saves one, with `fallback=False` to opt out.
- New tests:
  - `test_publish.py::test_no_fallback_rendered_publishes_nothing_and_never_re_puts`: two calls with no PUTs, no budget file, state unchanged, files kept; after `save_fallback_version` the next batch publishes 100..104, each segment PUT once.
  - `test_service.py::test_runner_alerts_and_spends_nothing_until_a_fallback_is_rendered`: one ALERT per tick, zero PUTs, then a clean publish once a version exists.
  - `test_cli.py::test_publish_exits_nonzero_until_a_fallback_is_rendered`.
- Docs:
  - The CLAUDE.md transmitter paragraph is reworded: nothing is published until `fallback render` has run, so every horizon names a fallback. Off-air is inert only if the named fallback is unusable in R2. The WAF kill switch is still the hard stop.
  - `docs/playout-setup.md`: §3 step 4 says to run it before step 5 and describes the ALERT. The §3 step 7 re-epoch wording is updated. §4 step 4 is reworded the same way.

**Minor 3** (plan text only):
- L1825 `prune_margin_minutes … ge=0` is annotated "as built: ge=PRUNE_MARGIN_FLOOR_MINUTES (4), Task 12" (verified at config.py:69-84).
- Task 16 has an as-built note: `MAX_PUTS = 10` hard cap in `putCap`, `d ≠ 10.24` refused (`horizon-refused`), and `LOOP_SECONDS` clamped to 75 s (verified at clock.ts:75-79, 118-120, 167-172).
- The spec is not edited.

**Minor 4** (runbook §3 step 5): do not run `transmitter plan`/`render` by hand while the service runs, because they take no lock against `run`'s plan/render step. `publish`/`status` are safe.

**Minor 5:**
- `render.py` raises the new `AnalysisStale(RenderError)` (errors.py) for "decoded to n samples but was analysed at m". The message still contains "the package changed", so the existing test is untouched.
- `FfmpegEngine.encode_show` catches it, calls the new `analysis.drop_cached(cache_dir, key)` (unlinks `cache/<key>.json`), and re-raises. render_step still treats it as "render failed".
- New `test_render.py::test_a_decode_mismatch_drops_the_cached_analysis` (requires_ffmpeg): it tampers the cached sample count. The encode raises, the cache file and the encode are both gone, the next `analyze` re-measures to the true analysis, and an encode then succeeds at `planned_frames`.

**Minor 6** (runbook §5, new checklist item, worded after reading playlist.ts):
- The reviewer's trigger ("stop `transmitter run` >40 s") **does not work**. Fallback entries appear only for `n` outside `[first, last]` (`windowEntries`). Stopping `run` leaves the 24 h published lead in place, so the clock keeps serving live. The doc says so.
- The realistic trigger is a fresh run's start. On the first start the first horizon is published before its first segment airs, so the window is the fallback loop and then turns live. `EXT-X-DISCONTINUITY-SEQUENCE` drops from `floor(n/len)+1−tags` to 0 once the 6-segment window is pure live (playlist.ts:97-102).
- The item says: attach players when `transmitter status` first shows `published segments …` while `on air` still says not started; keep them playing for at least 70 s past the switch; record whether each player returns to live on its own or needs exactly one reload. It also notes the other trigger: a restart after an outage longer than the lead.

**Minor 7** (runbook §5 player item): start playback first, then enable the kill-switch rule. A page loaded after the rule is enabled shows a dead Play button (player.js, nowplaying.js and assets/hls.min.js are blocked), and that is expected. The WAF rule is unchanged.

**Minor 8** (runbook §3 step 5): the first show's analyse+encode on hugo may take longer than `[planner] start_delay_minutes` (default 10; key verified at config.py:38 and in the template at :140), in which case the first minutes of the first show never air. The fix is to raise it for the first start (e.g. 20–30) and put it back. The default is unchanged.

**Minor 9** (`publish.py` Uploader.put):
- `NON_RETRYABLE = {AccessDenied, InvalidAccessKeyId, NoSuchBucket, SignatureDoesNotMatch}` fails on the first attempt with `PublishError`, with no sleep.
- `budget.take()` still runs before every attempt.
- New parametrized `test_publish.py::test_a_non_retryable_error_fails_fast_after_one_counted_attempt` (4 codes): exactly one PUT, `sleeps == []`, budget count == 1.

**Minor 12** (`service.py`):
- New `Runner._read_lead`. When publish.json is unreadable or the wrong shape, it logs the traceback and raises `ALERT publish-state: cannot read … this tick plans, renders and publishes nothing until it is repaired`; `tick` then returns early (fails closed: no plan, render, publish or prune).
- The post-publish lead read uses the same wrapper.
- New parametrized `test_service.py::test_an_unreadable_publish_state_alerts_and_fails_the_tick_closed` (truncated JSON → JSONDecodeError; `[1, 2]` → AttributeError): the ALERT fires, there are no bucket calls, no analysis and no plan; after the file is removed the next tick publishes.

**Minor 13:** `row_analysis` docstring added: it uses `time.time()` and `quiet_s=0`, and can run a full ffmpeg analysis under the publish flock when `cache/<key>.json` is missing. That is acceptable because the cache is never GC'd (now also reachable once after Minor 5 drops an entry).

## Test results (final)
- 3.14, full repo at 9fdc47a: `./.venv/bin/python -m pytest -q -p no:cacheprovider` gives **2453 passed, 7 deselected, 26 warnings**. The 26 are the known Python-3.14 fork DeprecationWarnings from llama's tests, the same set the reviewer recorded. `./.venv/bin/python -c "import transmitter; print(transmitter.__file__)"` resolves to `<worktree>/packages/transmitter/src/transmitter/__init__.py`.
- 3.11 at 9fdc47a: `./.venv311/bin/python -m pytest packages/transmitter/tests_transmitter -q -p no:cacheprovider` gives **304 passed** (CPython 3.11.15, resolving inside the worktree).
- Debian 12 at f69a4b0 (last code commit; 9fdc47a is docs only): `packages/transmitter/scripts/test-in-debian12.sh` gives **304 passed in 19.07 s**, ffmpeg 5.1.9-0+deb12u1, Python 3.11.2, rc 0.
- antenna: not touched, so `npm test`/typecheck were not run.

## Mutation check (scratch copies via `git archive HEAD | tar -x` under the session scratchpad)
- Each run used `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<copy>/packages/transmitter/src:<copy>/packages/transmitter <worktree>/.venv/bin/python -m pytest -p no:cacheprovider <copy>/…/tests_transmitter` from an empty cwd, with a fresh copy per mutant.
- Shadowing was proven with a planted `SENTINEL = "copy"` in a sentinel copy's `transmitter/__init__.py`. That was asserted under pytest, and every mutant run also included a test asserting `transmitter.pipeline.__file__` lives in that mutant's copy (it passed each time).
- Predictions were written to the log before running.

| mutant | predicted red | actual red |
|---|---|---|
| i1a: unconditional on-air refusal restored | `test_render_step_reencodes_a_lost_encode_of_an_unchanged_show_on_air` | exactly that (1 failed, 304 passed) |
| i1b: on-air refusal removed (on-air rows re-planned) | `test_render_step_refuses_to_replan_a_show_already_on_air[changed, ineligible, render-fails, frames-changed]` | exactly those 4 |
| i2a: no fallback gate | `test_no_fallback_rendered_publishes_nothing_and_never_re_puts`, `test_runner_alerts_and_spends_nothing_until_a_fallback_is_rendered`, `test_publish_exits_nonzero_until_a_fallback_is_rendered` | exactly those 3 |
| i2b: gate only before the horizon PUT (the review's literal suggestion) | same 3 | exactly those 3; the publish test failed on 16 PUTs including `seg/etest/100.aac` re-PUT on the second call, which proves the re-PUT loop |

## Findings judged wrong (with evidence)
- **I2's "uploaded segments stay recorded so nothing is re-PUT"** is wrong (see I2 above and mutant i2b). The gate was moved before any PUT.
- **Minor 6's trigger** ("stop `transmitter run` for >40 s") does not reach fallback while the 24 h lead is published (`windowEntries`: only `n ∉ [first, last]` is fallback). The checklist uses the fresh-run start instead and says why.

## Concerns / notes
- The plan's Task 9 interface line (plan L4011) still describes the old "LayoutError whenever an on-air row's encode is missing" semantics. I left it, because only Minor 3's plan edits were in scope. A one-line as-built note there would keep the plan consistent.
- Spec :398 (D5, discontinuity `floor(N/len)+1`) is not edited, per instructions; it still needs operator sign-off.
- Process slip: my first launch of the Debian gate sent its output to a stray `.deb.tmp` in the task dir instead of teeing it into the log. I killed it within seconds (stopped its container `45099d0fb7d0`, which I had started), deleted the stray files, and re-ran it teed into `final-fix1.log`. The only files now in the task dir are `dispatched` (pre-existing), `final-fix1.log`, `debian12.rc`, `full314.rc`, `handback.md` and `done`.
