VERDICT: NEEDS FIXES

Scope: spec compliance of 3e79a8a (Task 15) against task-15-brief.md and ruling R15. The code is a verbatim copy of the brief: all four new or modified artifacts match it byte for byte, and all five service.py edits are present. The one blocking item is plan-mandated. R15 says "the longest gap is one show's encode ... not a long catch-up publish", but that only holds if prune is bounded, and prune has no ping. It runs after the last batch ping, is unbounded after a stop, and saves its progress only when it finishes.

### Findings
#### Critical
None.

#### Important
1. **Plan-mandated: an unbounded, unpinged prune after a long stop can outlast WatchdogSec, and once it does it loops forever** (`packages/transmitter/src/transmitter/service.py:142-156`, `publish_all`; `packages/transmitter/src/transmitter/publish.py:372-443`, `prune`).
   - **Where the pings are.** `publish_all` pings after each batch. It then calls `publish.prune(p, t_us)` with no notifier. The next ping is `_step`'s `finally`, after prune returns.
   - **Why prune is unbounded.** prune sends one sequential `DeleteObject` per segment. That covers every published segment that started more than `prune_margin` ago, up to `state.last`. In steady state the count is about `prune_min_segments` (60). After a stop it is `min(stop length, lead_hours)` worth of segments. At the defaults (`lead_hours = 24`, d = 10.24 s), a stop of 24 h or more leaves about 8,440 sequential DELETEs in one step.
   - **When it reaches 45 min.** 45 min / 8,440 ≈ 320 ms per DELETE. A normal keep-alive link (about 50–150 ms) gives roughly 7–21 min. A degraded link reaches the watchdog. `r2.py`'s `read_timeout = 60` allows up to 60 s per op on a slow-drip connection.
   - **Why it loops.** prune saves `state.first` (the horizon shrink) before it deletes. It saves `state.runs` only at the very end (`publish.py:441-442`). If the watchdog kills it mid-loop, nothing of the delete progress is kept. After `RestartSec=30`, the next tick re-deletes from each run's `lo`. That is the same multi-thousand-DELETE pass, plus whatever became prunable meanwhile, so it is killed again at the same point.
   - **Impact.**
     - No spend: DELETEs are free, and at most one horizon PUT is made per tick.
     - On-air continuity holds, because publish runs before prune in every tick.
     - The service enters a restart loop that never clears and that transmitter itself never alerts. Only the journal shows the watchdog kills.
     - The watchdog was introduced by this task, so this failure mode is new.
   - **This is exactly the catch-up-after-a-stop case.** The brief added the per-batch ping for that case ("so a long catch-up publish (up to `MAX_BATCHES` batches after a stop) is not killed by `WatchdogSec`"), but it stopped at the publish loop.
   - **Fix (small, in this task's spirit).** Pass the notifier through to `prune(p, now_us, notify=None)` and ping every `batch_segments` deletes, mirroring the batch ping. Optionally also persist `state.runs` progress at those points, so a kill for any reason no longer restarts the pass from zero. Add a test in the style of `test_publish_all_feeds_the_watchdog_after_every_batch` that drives a prune of more than `batch_segments` deletes and counts the pings. This needs an orchestrator or operator ruling, since it goes beyond the brief's verbatim code.

#### Minor
1. **R15's "longest gap is one show's encode" is not a bound on the render step either** (`service.py:235-236`; `pipeline.py:207-304`).
   - `render_step` is called with `limit = batch_segments = 360` segments (about 61 min of air). Every row it crosses that lacks an encode is encoded fully inside that one call, with no ping in between. So one step can run two full encodes:
     - (a) a show shorter than about 61 min, followed by the next show;
     - (b) the restore case `render_step` itself documents ("its encode was lost (render/shows cleaned or not restored)"): the on-air show is re-encoded, then the next one.
   - At the R15 figure of about 10–20 min per encode, (b) is 20–40 min, which approaches 45 min. It is rare and operator-triggered, so Minor.
   - Cheapest remedies, either of which works:
     - give `render_step` the notifier and ping after each `encode_show`;
     - or soften the unit comment and R15 wording to "one or two encodes".
2. **No RED capture.** The handback admits the implementation was written before the test was run, so there is no recorded failing run. The tests are the brief's verbatim text and they do pin the behaviour (see Checks). This is a process lapse, not a correctness gap.

### ⚠️ Cannot verify from diff
- **Runbook pointer.** The unit's comment points to "docs/playout-setup.md, section 6", which does not exist yet. The plan assigns it to Task 17 (runbook, deploy, verification; plan lines ~6134-6171), so check it there.
- **Encode duration.** "~10–20 min per show's encode on hugo" is R15's figure, not something measurable here. Both the render-step gap and the safety margin rest on it.
- **R2 DELETE latency from hugo** is unmeasured. Network is off-limits, so the prune numbers above are arithmetic over an assumed per-request latency. One `time` measurement of a prune of about 1,000 segments on hugo would settle Important #1 empirically.
- **Real systemd behaviour.** `systemd-analyze verify`, the actual watchdog kill, and `Restart=always` with the default StartLimit are not exercised. That belongs to the operator at Task 17 (no unit installed or started, per the dispatch).

### Strengths
- **Verbatim fidelity.** Programmatic diffs against the brief show that `test_systemd.py`, `sdnotify.py` and `transmitter@.service` are identical to its code blocks. All four service.py snippets (`__init__`, the `_step` `finally`, the `publish_all` head, `run`) are present verbatim, along with the import change and the docstring tweak.
- **Task 14 is preserved.** Task 14's `monitor` and `held` were kept alongside the new `notify` (the `__init__` keeps `monitor`; `tick` passes `self.held, self.notify`).
- **Pings are where the brief and R15 put them:**
  - `READY=1` before the loop;
  - `WATCHDOG=1` in `_step`'s `finally`, so a failed or alerted step still pings, and the dead-clock step pings too;
  - `WATCHDOG=1` after each batch inside `publish_all`, placed before `_report_stop`, so a batch's alert send does not delay its ping;
  - `STOPPING=1` in a `finally` around the loop.
- **Behaviour elsewhere is unchanged.**
  - `cli.py:224` builds `Runner` without `notify`, so it gets `sdnotify.notify` as intended.
  - Manual `transmitter publish` callers of `publish_all` get `notify=None`, so behaviour is unchanged.
  - Outside systemd every call is a no-op.
- **sdnotify follows the brief's contract.** It returns `bool` and never raises: `OSError` is logged at warning. `@` maps to an abstract socket. `NOTIFY_SOCKET` is read from an injectable `env`.
- **The unit matches every R15 and brief value:** template `User=%i`, `Type=notify`, `NotifyAccess=main`, `WatchdogSec=45min`, `Restart=always`, `RestartSec=30`, `EnvironmentFile=/etc/transmitter/%i.env`, journal output, `WantedBy=multi-user.target`, `After=network-online.target remote-fs.target`. It contains no account details.

### Checks run
- **Risk: deviation from the brief's exact code.**
  - Check: extracted the Task 15 code blocks from `docs/superpowers/plans/2026-10-11-playout-phase2.md` (lines 5733-5960) and `diff`ed them against the committed files. For the service.py snippets, checked by substring that each is present.
  - Result: TEST-VERBATIM, SDNOTIFY-VERBATIM, UNIT-VERBATIM, and all four service.py snippets PRESENT.
- **Risk (R15): where the pings sit within a tick.**
  - Check: read `Runner.tick`, `_step` and `publish_all` in the diff.
  - Result: pings come after plan, render, publish (plus one per batch) and dead-clock. There is none between `_read_lead` calls (local and cheap), none during the inter-tick sleep (≤ 60 s), and none during prune.
- **Risk: the render step encodes more than one show per call.**
  - Check: read `pipeline.render_step` (`pipeline.py:207-304`) and `batch_segments` (`config.py:78`, default 360).
  - Result: Minor #1.
- **Risk: prune after the last batch ping.**
  - Check: read `publish.prune` (`publish.py:372-443`, per-key DELETE with the `state.runs` save at the end), `Uploader.delete` (single attempt), `r2.py:28-31` (`connect_timeout = 10`, `read_timeout = 60`, botocore retries off), and the `lead_hours = 24` and `prune_min_segments = 60` defaults.
  - Result: Important #1.
- **Risk: the publish batch itself, including `_publish_site` and the `analysis_for` fallback.**
  - Check: reasoned from `publish_batch`'s structure and the `Uploader.put` retry (4 attempts, 1/2/4 s backoff).
  - Result: each batch is followed by a ping. One batch is 360 PUTs plus at most a few analyses, so it runs for minutes at most.
- **Risk: alert channel sends.**
  - Check: `alerts.py:38,72,89`: `CHANNEL_COOLDOWN_S = 300`, SMTP timeout 20 s, ntfy timeout 10 s.
  - Result: the implementer's claim of roughly 30 s per alert call (each failing channel costs one timeout per cool-down) is verified.
- **Risk: the dead-clock fetch.**
  - Check: `deadclock.py:48-52`, `urlopen(timeout=10.0)`.
  - Result: a single GET, bounded per socket op, followed by a ping.
- **Risk: the CLI wiring of `notify`.**
  - Check: `cli.py:224`.
  - Result: the default `notify` is used.
- **Tests.** No tests were run. Nothing in the reading raised a doubt that the implementer's reported runs (421 passed on 3.14 and on 3.11, and a Debian-12 gate rc of 0) do not already answer. No mutants were run.
