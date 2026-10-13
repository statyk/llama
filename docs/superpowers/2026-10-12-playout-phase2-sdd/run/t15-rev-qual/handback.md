VERDICT: NEEDS FIXES

### Findings

#### Critical
None.

#### Important

**I1. A tick that runs no step sends no watchdog ping, so a designed, alerted fail-closed state becomes a watchdog kill and restart every 45 min.** (`packages/transmitter/src/transmitter/service.py`: `tick`'s early `return` after `_read_lead` fails, about line 226; the pings live only in `_step`'s `finally` and in `publish_all`.)
When `publish.json` is unreadable, `tick` returns before any `_step`, by design ("this tick plans, renders and publishes nothing until it is repaired"). The process is alive and looping every 60 s, but it never sends `WATCHDOG=1`. Under the new unit (`WatchdogSec=45min`, `Restart=always`), systemd then kills it with SIGABRT (the default `WatchdogSignal`, so a python core dump each time, via systemd-coredump where it is installed). It restarts after 30 s and is killed again 45 min later, for as long as the file stays broken.
Why it matters:
- This is the one gap in the task's own feature that is unbounded rather than "one show's encode". The task-specific R15 question asked whether any single gap can approach WatchdogSec, and this one exceeds it deterministically.
- The journal reports "Watchdog timeout", which sends the operator chasing a hang (NFS, ffmpeg) that does not exist. The real cause is already in the `publish-state` alert.
- A restart also clears in-memory latches: the `halted` frame-count-drift latch and `HeldTracker`'s count. Before this task a restart was a human act. The drift check re-detects at encode time, before any segment is written, so the latch case limits itself, but it is a semantic shift worth knowing about.

The brief's wording ("after every step") does not cover this path, so this is a gap the plan left open rather than something the plan mandated.
Fix (small): ping once per tick independently of the steps. For example, `self.notify("WATCHDOG=1")` on the early-return path in `tick`, or after `self.tick(...)` in `run`'s loop. Either still goes silent on a genuine hang inside a tick, because the ping comes only after the tick returns. Add a test: a Runner whose `publish.json` is corrupt, run for one tick, must send at least one `WATCHDOG=1`. Today that test would be red.

#### Minor

**M1. R15's bound ("the longest gap is one show's encode") is looser in code than in the ruling.**
- **Render step** (`service.py` tick → `pipeline.render_step(limit=batch_segments)`; config default `batch_segments = 360`): 360 segments × 10.24 s ≈ 61 min of air per render step, with a single ping at the end. A window that crosses a show boundary encodes the next show inside the same step. A show shorter than about an hour, or a cold run start, can therefore put more than one encode in one gap. Because encode time scales with the audio encoded, the worst case is roughly one full show plus about an hour of audio. At the brief's 10–20 min per show that is still under 45 min, but the margin rests on the unmeasured "10–20 min on hugo" figure.
- **Publish step** (`service.row_analysis` → `publish._publish_site`): a lost `cache/` makes one `publish_batch` recompute `analysis_for` for every row in the timeline window, from 24 h back to the horizon. That is about 48 h of shows, each a full ffmpeg analysis over NFS, all before that batch's ping. This can exceed 45 min. It heals itself, because `load_or_analyze` caches each result, so a killed run makes progress. Each kill lands after the segment PUTs and before the horizon PUT, though, so up to 360 segments are re-PUT per kill. That cost is bounded by the daily PUT budget. `row_analysis`'s docstring ("lengthening that one publish tick by minutes") understates this now that a watchdog exists.

Optional fix: pass `notify` into `render_step` and ping after each `encode_show`, and/or ping per `analysis_for` call in `_publish_site`. At minimum, update the unit comment and the `row_analysis` docstring.

**M2. The runner test reaches its count of 4 through a FAILING render step, not the path its comment describes.** (`tests_transmitter/test_systemd.py`, `test_the_runner_says_ready_pings_the_watchdog_after_every_step_and_says_stopping`.)
The Runner is built without a `clock`, so it ticks at the real wall clock. `helpers.make_station`'s epoch is `E = 4e9 s` (year 2096), so `render_step` raises `ValueError: segment index must be >= 0, got -2156447xx`, which is logged and alerted (shown in the log under Checks run).
- The comment "plan, render, publish, and its one batch" implies all four steps succeed. They do not.
- The upside is accidental: this is the only thing that kills mutant M2 (the ping moved from `finally` to the success path). If someone later "fixes" the test by injecting a clock, that mutant would survive silently.

Fix: inject a clock inside the epoch. Add an explicit failing-step case, for example a monkeypatched `pipeline.render_step` that raises, which asserts that the ping still follows. The other Runner tests in `test_service.py` share the wall-clock pattern; that predates this task.

**M3. `STOPPING=1` in `run`'s `finally` is unpinned.** Mutant M5 (STOPPING sent only on normal exit) survives both test files. Low value in practice: under systemd a SIGTERM kills Python without running `finally`, so the `finally` only matters for an exception escaping `tick` or a KeyboardInterrupt. A one-line test with a `tick` that raises would pin it.

**M4. `test_notify_failure_is_logged_not_raised` does not check that anything is logged** (no `caplog` assertion), so the "logged" half of its name is unverified. The `@` → abstract-socket branch of `sdnotify.notify` is untested. It is Linux-only, so a `skipif(sys.platform != "linux")` test would run in the Debian-12 gate.

**M5. Type annotations for the notifier differ:** `Runner(notify: Callable[[str], bool])` versus `publish_all(notify: Callable[[str], object] | None)`. Cosmetic.

**M6. Unit file:** `After=remote-fs.target` orders after NFS mounts but does not require them, and the template cannot know the station-root path for `RequiresMountsFor=`. Acceptable for a template; the runbook could mention a drop-in. `ExecStart=/home/%i/.venvs/...` hard-codes the home layout, which is fine because `%h` resolves to `/root` in system units. Neither needs a code change.

### ⚠️ Cannot verify from diff
- The unit's header comment points to "docs/playout-setup.md, section 6". The runbook currently stops at section 5 (phase-1 checklist). Presumably a later docs task adds it; confirm at the whole-branch review.
- The "~10–20 min per show encode on hugo" premise behind `WatchdogSec=45min` is not measured anywhere in this diff.
- That the real `transmitter run` path (`cli.py:224`) does nothing heavy before `READY=1` beyond Station/publisher/monitor construction, within `TimeoutStartSec=2min`. It looked like construction only at a glance; not crawled.
- The Debian-12 run's real AF_UNIX datagram: the implementer reports rc 0. Not re-run here (no Docker use by reviewers).

### Strengths
- `sdnotify.notify` is minimal and correct: a no-op without `NOTIFY_SOCKET`, abstract-socket handling, `OSError` logged and never raised, 3.11-safe imports. An sd_notify failure can never take down the loop.
- Putting the per-step ping in `_step`'s `finally` is the right shape: failing steps (station-root, drift, PublishLocked, generic) still ping.
- In `publish_all`, the per-batch ping comes before `_report_stop`'s alert sends and before the break check. Every batch pings, including the final empty or stopped one, and a long catch-up publish cannot outlast the watchdog.
- Alert channels are bounded (SMTP 20 s / ntfy 10 s timeouts, `CHANNEL_COOLDOWN_S = 300`), and the dead-clock GET has a 10 s socket timeout. Neither can approach 45 min in one gap.
- Alert dedupe is persisted in `alerts.json`, so even the I1 restart loop does not spam the operator.
- The tests pin the main pings against deletion: mutants M1, M3 and M6 all go red (see below). The unit test reads the real committed file.
- Public-repo hygiene: the unit file contains no addresses, IDs or secrets (`%i` placeholders only). No test reaches the network: the datagram test uses a local `/tmp` AF_UNIX socket.

### Checks run
- **R15 ping placement:** read `_step`, `tick`, `run` and `publish_all` in the diff. Checked the blocking calls between pings:
  - `alerts.py` timeouts (lines 72, 89) and `CHANNEL_COOLDOWN_S` (line 38);
  - `deadclock.fetch_text` timeout (line 48);
  - `pipeline.render_step`'s loop (one ping per call; it encodes any show the window enters);
  - config `batch_segments = 360`;
  - `publish.publish_batch`, `_publish_site` and `service.row_analysis` (cache-miss recompute under the flock, before the batch ping);
  - `publish.prune` (after the last batch ping, guard read plus a horizon PUT plus deletes, then the step's ping).

  Found the no-step early return in `tick` (I1).
- **Alert dedupe across restarts** (I1 impact): `alerts.py` docstring and `_state`: persisted to `~/.transmitter/alerts.json`, merged with in-memory.
- **Mutants** in a scratch copy (`git archive 3e79a8a packages/transmitter antenna/templates antenna/public | tar -x`, run from an empty cwd with `PYTHONPATH=<scratch>/packages/transmitter/src:<scratch>/packages/transmitter`, `PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`). Shadowing proven: `transmitter.__file__` and `tests_transmitter.__file__` both resolved inside the scratch tree. Baseline over `test_systemd.py` + `test_service.py`: 32 passed. Each mutant had a named prediction before it ran:

  | Mutant | Change | Predicted | Result |
  |---|---|---|---|
  | M1 | drop `finally` ping in `_step` | runner test red | CAUGHT (1 failed: runner test) |
  | M2 | move the `_step` ping to the success path only | green (no failing-step test) | CAUGHT, unexpectedly. Traced: the runner test's render step fails on the wall-clock-before-epoch ValueError, giving finding M2. |
  | M3 | drop the per-batch ping in `publish_all` | `test_publish_all_feeds...` + runner test red | CAUGHT (2 failed, both) |
  | M5 | `STOPPING=1` only on normal exit | green | SURVIVED (32 passed), giving finding M3 |
  | M6 | Runner passes no notifier to `publish_all` | runner test red | CAUGHT (1 failed) |

  The scratch `service.py` was restored after each mutant. The live worktree was never modified (`git status --short` clean).
- **Focused log run** of the runner test at baseline, `-o log_cli=true`. Output:
  `ERROR transmitter:service.py:206 render step failed ... ValueError: segment index must be >= 0, got -215644778` / `ALERT render: ValueError: ...` / `PASSED`.
  Cause: `helpers.E = 4_000_000_000 * 1_000_000` (year 2096) with the Runner's default real clock.
- **Python 3.11:** the new code uses only `typing.Mapping`, `Callable` and `socket`; no 3.12+ API.
- **Runbook section 6:** `grep "^#" docs/playout-setup.md` lists sections 0–5 only.
