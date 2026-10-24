# Playout phase 2 verification (runbook §8)

The operator ran the checklist from the artifact `3Jfqrsmwg1akMCgVCLtZhG` ("Phase 2 Verification Run", the §8 list revised 10-17 for the metronome). It ran in three sittings: A1 on 10-22 00:38 EDT; A2–G 10-23 00:45–02:11 EDT; H, then I–K and the final check, 10-23 10:21–22:00 EDT. The per-step results are in the artifact's db collection `results`. Claude analysed them on 10-23 ~22:30 EDT, together with:
- `~/lma-radio-ops/metronome-tail/tail-postdeploy.jsonl` (`wrangler tail antenna`)
- `~/lma-radio-ops/metronome-tail/poll.tsv` (`live.m3u8` every 5 s)
- hugo's user-visible journal for `transmitter@shawn`
- the mtimes in hugo's `~/.transmitter/`
- `state/guard.json`

**Tally:** 27 steps: 22 pass, 1 skip (C1) and 3 fail (A2, J2, K1). On analysis, A2 is benign. J2 found a real latency defect on hugo, and the cloud side passed exactly. K1's first run did not exercise the watchdog (the 2-minute drop-in never reached the running service); the corrected re-run at 23:03 EDT passed.

| Step | Result | Summary |
|---|---|---|
| 0.1–0.3 Setup | pass | The `NTFY_TOKEN` secret is set, but the Worker's ntfy still returns 429 (see "Other observations") |
| A1 `site_url` playlist | pass | `EXT-X-START:TIME-OFFSET=-122.880` and `HOLD-BACK=122.880` are live, and PROGRAM-DATE-TIME is ~2 min ahead |
| A2 guard vs billing | fail → **benign** | R2 matches. Requests: 18k in guard.json vs 16k on the billing page, because the billing page lags (below) |
| B1–B5 off-air | pass | Every layer blocks and restores; the Mac-side `offair.json` write works too |
| C1 join near wall clock | **skip** | Not measurable as written (below) |
| D1 network blip | pass | |
| E1 dashboard toggle undone | pass | |
| F1 lead floor | pass | |
| G1–G3 spend trip and raise | pass | Tripped at $5.50, raised to $7 (02:08–02:09 EDT 10-23), restored |
| H1–H2 blind trip | pass | |
| I1–I3 Rulesets failure | pass | Off-air holds through the soft path while the WAF can't be set |
| J1 delete cron | pass | Deleted 19:55 EDT |
| J2 dead-clock alerts | fail → **cloud PASS, hugo latency defect** | `dead-clock` came 15 min late (below) |
| J3 restore | pass | |
| K1 watchdog and boot | fail → **PASS on re-run** | The boot half passed. The first run tested nothing; the re-run restarted in 2.5 min (below) |
| Final check | pass | offair off, killswitch disabled, $5.00 of $15.00, `budget.json` absent, no alerts |

## A2: the guard counts Worker requests correctly

At the operator's reading (10-23 04:45Z), guard.json said ~18k `workersRequests` and the billing page said 16k. antenna has no routes, so its Worker requests are its cron invocations: one a minute since the period began on 10-11 00:00Z. That is 17,565 fires by 04:45Z, which matches guard.json's figure. The billing page's 16k equals ~11.1 days of fires, so it trailed by about a day. That fits Billable Usage being daily data that is published late. A re-read at 10-24 02:17:54Z gives `workersRequests` 19,559 against 18,858 fires, ~4% over. The surplus is the test deploys, during which an old and a new version both fire cron for a few minutes. In any case the guard's error runs in the safe direction, and it's far inside the 2x the step exists to catch. The R2 numbers matched (operator).

Runbook corrections: the operator could not find a requests graph under Workers & Pages → antenna, so the billing page is the place to read it. Compare it against guard.json's figure from a day earlier, not the current one.

## C1: skipped because the step can't be measured as written

`transmitter status` shows the show on air (`gratefuldead-1977-05-04`, 3+ hours long), not a position inside it. Nothing the operator could see gave the offset in seconds. The operator reported that the iPhone and Chrome were close to each other. The START/HOLD-BACK pair had already been measured on the iPhone with the 10-13 test kit (`~/lma-radio-ops/hls-start-test/`). A proper offset check needs a position readout (hls.js `playingDate` against `Date.now()`, or a now-playing line with a timestamp), which belongs to phase 3's player work.

## J2: the cloud side was exact, but hugo detected the dead clock 15 min late

Timeline (UTC, from the tail and the poller):

| Time | Event |
|---|---|
| 23:55 | The operator deletes the cron trigger in the dashboard (19:55 EDT) |
| 23:56–00:04:08 | Cron keeps firing for 9 more minutes, every renew `applied: accepted`. That is the dashboard propagation delay, which the step warned about |
| 00:19:08 | The lease from the last renew expires (00:04:08 + 15 min) |
| 00:19:11 | The poller's last `MEDIA-SEQUENCE` advance (107694). The playlist stays frozen until 01:01:06 (J3) |
| ~00:20 | The operator's player stops and replays the same segment on restart, as expected |
| ~00:22–00:23 | When `dead-clock` was **due**: the playlist age passes 120 s at ~00:21:11, then the second consecutive stale check |
| 00:34:43 | hugo's first `dead-clock`, "newest segment 937 s old" |
| 00:47:11 | `guard-stale`: last evaluation 00:02:08Z + 45 min, exactly on time |

**The metronome and lease behaved exactly as designed.** The step's "~17–18 min" assumed the trigger stops at once. With the observed 9-minute propagation, the freeze landed at 24 min, just as the lease rule predicts.

**The defect is on hugo.** `DeadClockMonitor.check` runs inside the service's sequential tick, after plan, render and publish (`service.py`). Between 20:15 and 20:34 EDT the journal has no dead-clock line, although alerts log every minute while one is firing. Over the same stretch, hugo's workspace shows a plan step analysing shows from the station root over NFS: `cache/8b32d8df63006c6f0d45.json` was written at 20:24:36, and `cache/670be947806abacdd058.json` with `plan.jsonl` at 20:32:55. The render of that show followed (`render/shows/670be947806abacdd058.aac` at 20:39:19). The dead-clock lines during the render are spaced irregularly (20:34:43, 20:36:47, 20:40:59, 20:42:10). So **dead-clock detection is late by as long as any plan or render step runs**: ~13+ min here, from one fill with two show analyses. `guard-stale` runs in the same call, and so does publish (harmless with a ~20 h lead). A worse fill would mean a longer delay.

Candidate fix (not built): run the monitor on its own timer or thread, independent of the plan/render tick. Alternatively, have analysis and render call back into the monitor the way render already feeds the watchdog. This fits the alert-noise work queued for 10-24 or phase 3.

## K1: the watchdog passes on a corrected re-run, and the boot half passes

- **Boot:** hugo rebooted at 21:10:58 and came up at 21:13:27 EDT. `transmitter@shawn` started at 21:13:28 and is `active (running)` with `WatchdogUSec=45min` and `NRestarts=0`, so the drop-in was reverted. **PASS.**
- **Watchdog: FAIL as run, and the run tested nothing.** The root journal (`sudo journalctl -b -1 -u transmitter@shawn`, read by the operator on 10-23) shows the sequence:

  | Time (EDT) | Event |
  |---|---|
  | 21:03:21 | The last tick's alert line |
  | 21:03:53 | `Sent signal SIGSTOP to main process 70121 (transmitter) on client request` |
  | 21:03:53–21:10:52 | Nothing: no `Watchdog timeout`, no kill, no restart |
  | 21:10:52 | The operator's `revert` and `restart`: Stopping, Deactivated, Started |
  | 21:10:58 | The reboot |

  The 7-minute wait was well past the ~2.5 min the re-run measured. So the `systemctl edit` drop-in (`WatchdogSec=2min`) did not take effect on the already-running service. Its watchdog timer stayed at the 45 minutes it started with, counted from the last ping at about 21:03, and would have fired at about 21:48.
- **Re-run, 23:03 EDT: PASS.** The root journal:

  | Time (EDT) | Event |
  |---|---|
  | 23:03:00 | SIGSTOP to main process 1718 |
  | 23:04:55 | `Watchdog timeout (limit 2min)!`, `Killing process 1718 (transmitter) with signal SIGABRT`, `Main process exited, code=killed, status=6/ABRT`, `Failed with result 'watchdog'` |
  | 23:05:25 | `Scheduled restart job, restart counter is at 1` |
  | 23:05:26 | Started |

  The timeout fired 1 min 55 s after the STOP, because the last ping came a few seconds before it. The SIGABRT killed the stopped process at once: systemd follows its kill signal with SIGCONT, so the 90 s `TimeoutAbortUSec` escalation never came into play. An earlier draft of this doc predicted ~4 min on that basis, which was wrong. The restart came after `RestartSec=30`. Total: **2 min 26 s from the hang to a running service.**
- **Corrected runbook procedure** (as used in the re-run; publishing pauses ~3 min, no effect on air):
  1. `sudo systemctl edit transmitter@shawn` (add `[Service]` and `WatchdogSec=2min`).
  2. `sudo systemctl restart transmitter@shawn` and wait ~1 min for a tick.
  3. `sudo systemctl kill -s STOP transmitter@shawn; date`.
  4. Watch `sudo journalctl -u transmitter@shawn -f`. `sudo` is needed: without it the PID-1 lines are hidden, and transmitter logs nothing at startup. Expect `Watchdog timeout (limit 2min)!` within 2 min of the STOP, an immediate SIGABRT kill, and a restart 30 s later.
  5. `sudo systemctl revert transmitter@shawn && sudo systemctl restart transmitter@shawn`.

  A caveat for step 1: with a 2-minute limit, a plan step that is analysing shows (~17 min in J2) would itself trip the watchdog. If a restart comes before the STOP, check whether a plan step was running.
- **A related finding:** render and publish feed the watchdog from inside long steps (`pipeline.py:273`, `service.py:148`), but the plan step does not. J2's plan step ran ~17 min without a ping, inside the 45-minute limit. A fill that analyses several new shows over NFS could pass 45 min and be killed. That would heal itself (analyses are cached as each one finishes, so the restarted plan resumes), but it would be a spurious restart. Belongs with the J2 fix (monitor off the tick).

**Stalling during K (operator, ~21:07–21:14 EDT):** the server side was fine. The poller saw no `MEDIA-SEQUENCE` run over 25 s from J3 onward (01:01:06Z on). A SIGSTOPped transmitter only pauses publishing, and the published lead was ~22 h. So this was client-side, most likely the player left in a bad state by J's 42-minute freeze: it has no auto-retry (deferred to the post-phase-3 player polish). Worth a recheck on a fresh page load if it recurs.

## L1: cron lag over 24 h (pre-metronome)

From the 10-13 01:19 → 10-14 01:19 EDT antenna tail: 1,432 fires.

| Measure | Median | p90 | p99 | Max | Over 25 s | Over 75 s |
|---|---|---|---|---|---|---|
| Lag | 16.9 s | 51.2 s | 99.8 s | 143.1 s | 473 | 39 |
| Lag + guard | | | | | 501 | 41 |

`guardMs` had a median of 1.2 s and a max of 5.2 s. The resulting playlist freezes: 118 over 45 s, 52 over 60 s, 30 over 75 s and 13 over 90 s. That is what led to the Durable Object metronome. Since the flip (10-15), cron lag no longer drives the playlist (median 1.0 s; see `2026-10-16-metronome-verification.md`).

## L2: op counts against the allowances

From `state/guard.json` evaluated 10-24 02:17:54Z, 13.10 days into the period that began 10-11:

| Meter | Period to date | Per week | Projected month | Share of allowance |
|---|---|---|---|---|
| `workersRequests` | 19,559 | 10,455 | 46,300 | 0.5% of 10M |
| `r2ClassA` | 220,495 | 117,860 | 521,950 | **52.2% of 1M** |
| `r2ClassB` | 232,867 | 124,473 | 551,237 | 5.5% of 10M |
| `r2StorageGbMonth` | 0.634 | | | 6.3% of 10 GB |
| `doRequests` | 83,480 | 44,622 | 197,612 | 19.8% of 1M |
| `doDurationGbS` | 9,300 | 4,971 | 22,016 | 5.5% of 400k |
| `doRowsWritten` | 380,453 | 203,361 | 900,599 | 1.8% of 50M |

Class A is the meter to watch. At ~16.9k a day it equals two writes per 10.24 s boundary (8,438 boundaries a day: hugo's segment PUT plus the metronome's playlist PUT), plus prune and horizon traffic. It is steady and projects to about half the free tier. `unknown_action_types` is empty. Actual and projected spend are both $5.00, the base charge.

## Other observations

- **B2 runbook fix:** `curl -s $H/ | grep -i 'off the air'` always matches, because the notice is a hidden div in the normal player page (operator). Test for something only the off-air `index.html` carries instead.
- **The Worker's ntfy still fails** even with `NTFY_TOKEN` set (429, see the playout memory). Email is antenna's only working channel. hugo's alerts push normally. The fix, the hugo relay, is queued.
- **The J1 cron delete took 9 min to stop firing.** That's within the documented "up to 15 min" for dashboard trigger changes.
