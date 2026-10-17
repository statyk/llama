# Metronome verification day (plan Task 9, step 5)

Analysed 2026-10-16 ~20:50 EDT. The switch has been `METRONOME="on"` since ~10:05 EDT on 2026-10-15 (version `43efbc92`). The two deliberate no-change redeploys produced versions `bbc9586c` and `2f294aee`.

Captures (both nohup, on the operator's Mac):
- `~/lma-radio-ops/metronome-tail/tail.jsonl`: `wrangler tail antenna`, 10-15 10:02 → 10-16 20:45 EDT, 14,582 events. It lost the tail connection about 15 times; the largest loss was 10-16 08:25–11:23 (177 cron minutes, one 10,680 s alarm gap). In total 182 cron minutes are missing, and 10,832 of about 12,100 alarms were captured. Every tail alarm gap over 21 s apart from the deploy-free 10.25 s ones sits on a missing-cron stretch, and the poller shows no matching freeze, so these gaps are capture loss, not chain breaks.
- `~/lma-radio-ops/metronome-tail/poll.tsv`: `live.m3u8` fetched every 5 s through the public hostname, 24,985 rows. It covers the whole window apart from 8 fetch timeouts.

Analyser scripts are in the session scratchpad (not kept). The numbers below are reproducible from the two capture files by following the plan's step-5 recipe.

## Results by item

1. **Write times.** 10,832 alarm events, all `outcome: ok`, at 6 per minute (the median minute). 15 renews wrote (`wrote: true`). Cron fallback writes: **0**, since every clock line had `puts: 0`.
2. **Freezes** (runs of fetches showing the same `MEDIA-SEQUENCE`, after the flip). There were 12,132 runs: median 10.0 s, and 168 over 20 s, which is normal phase jitter against a 5 s poll. 4 runs were over 30 s and **1 was over 45 s**; none was over 60 s. The 1 run over 45 s was 10-15 16:11:39, 47.8 s. Within it, the last successful fetch with an unchanged sequence was at +15 s, and the next 33 s were poller **fetch timeouts**. The tail disconnected over the same stretch (16:03–17:00), so this was client-side network loss and is not attributable to the playlist. There were 8 fetch errors, all TimeoutError, all 10-15 16:08–17:00. No freeze over 45 s with successful fetches on both sides. No `metronome-down`, and no silent chain break.
3. **Alarm lateness** (`eventTimestamp − scheduledTime`):

   | Window | Alarms | Median | p99 | Max |
   |---|---|---|---|---|
   | All | 10,832 | 0 ms | 1 ms | 51 ms |
   | Weekday daytime :00–:02 and :30–:32 (10:00–18:00) | 474 | 0 ms | 1 ms | 13 ms |

   0 alarms were `canceled`. One `metronome-late` line appeared (10-16 17:25:57, `lateMs` 7358). The event itself was delivered 16 ms after its scheduled time, but the handler ran 8.2 s of wall time, so the delay was inside the handler (the PUT path), not in alarm delivery. The poller shows a 20.5 s run there, which is harmless.
4. **PUT rate.** Alarms ran at 60/10.24 ≈ 5.86 per minute (≈ 8,440 per day), plus 15 renew writes over 34 h. A renew skips its PUT when the bytes are identical. Within "one per boundary plus one per renew". **PASS.**
5. **Fallbacks and stalls.** Fallbacks: **0** (`metronome.fallback` null on all 1,899 post-flip clock lines). `stalls` was 0 on every renew. `stalledMs`: median 5.1 s, p99 10.2 s, max 28.9 s, with 3 over 15 s, all in the R2 PUT-timeout episodes under "Other observations". Every renew was `applied: accepted`.
6. **The two deploys.** Both chains survived with no stall:

   | New version | First cron on new version | DO's last alarm on old version | First alarm on new version | Gap |
   |---|---|---|---|---|
   | `bbc9586c` | 12:57:43 | 13:02:17.025 | 13:02:27.278 | 10.25 s |
   | `2f294aee` | 14:34:43 | 14:39:03.105 | 14:39:13.357 | 10.25 s |

   The DO keeps running the old code for about 4.5 min after a deploy, and the first new-code alarm is about 13 ms late.
7. **Meters.** `state/guard.json` (evaluated 10-17 00:32Z) has `last_error` null, `actual_usd` = `projected_usd` = $5 (budget $15), and these DO meters:

   | Meter | Period to date | Projected for the month | Allowance |
   |---|---|---|---|
   | `doRequests` | 14,174 | 260,550 | 1M |
   | `doDurationGbS` | 1,590 | 27,079 (6.8%) | 400k |
   | `doRowsWritten` | 64,360 | 1.19M | 50M |

   Cross-check: 34.45 h since the flip gives 12,111 boundaries plus 2,067 renews = **14,178** expected requests, against 14,174 metered. That is ≈ 5.3 rows written per tick, inside the expected 4–6.

   **Dashboard comparison (operator, 2026-10-17): close enough.** guard.json evaluated 10-17 20:31:43Z reads `doRequests` 22,416, `doDurationGbS` 2,478.92 and `doRowsWritten` 102,064 for the period to date. The operator's dashboard read was taken against a reading of 2,467.96 GB-s, about 15 min earlier. The operator judged the numbers close. The dashboard shows duration only abbreviated, as "2k". That is consistent with 2,468 GB-s if the dashboard truncates rather than rounds, so the check bounds duration only loosely: it rules out the 2x misread the check exists to catch, and nothing finer.
8. **Anomaly lines:**

   | Line | Count |
   |---|---|
   | `metronome-duplicate` | 13 (see item 9) |
   | `metronome-put-failed` (alarm side) | 5: four "timed out after 5000 ms", one "Network connection lost." |
   | `metronome-late` | 1 |
   | `metronome-expired`, `-hold`, `-lease-invalid`, `-lease-superseded`, `-cap`, `-alarm-cap`, `-null-build`, `-alarm-error`, `-rearm-failed`, `offair-without-fallback` | 0 each |

   Every cron event carried a clock line.
9. **Duplicates: FAILS AS WRITTEN, benign in effect.** 13 `metronome-duplicate` lines appeared, every one on a **fresh** `scheduledTime`. No `scheduledTime` repeated anywhere in the capture, so no real redelivery was observed. Every one has the same shape:
   - The renew RPC lands 1–25 ms before a boundary B, while B's alarm is already in flight. `getAlarm()` therefore reads null.
   - The renew writes, reporting `wrote: true` with `stalledMs` ≈ 10.22 s because B's alarm has not yet been recorded as good, and it arms B+1.
   - B's alarm handler then runs, sees B+1 pending, and logs a duplicate (`pending` = B+1 in all 13). It does the idempotent write without re-arming.

   The chain never broke, and the alarm events continue every 10.24 s. Alarms arrived every ~10 s, never about once a minute. Spec reading 9 assumes that "a pending alarm" means a redelivery; on the real runtime it is mostly this renew-and-alarm race. The engine's own comment ("unless setAlarm ran since") anticipates exactly this case. The redelivery path itself was **not exercised** in 34 h.

## Other observations

- **R2 PUT timeouts on 10-16 00:41–00:43:** several consecutive alarms ran 10.24 s of wall time against the 5 s PUT bound, with 3 `put-failed` lines. The poller saw a 40 s freeze, then the sequence **went backwards once**: 41737 at 04:42:32Z, 41736 at 04:42:42Z. This is consistent with a timed-out PUT landing in R2 after a newer one. A different edge-cache copy cannot be ruled out from this data. RFC 8216 forbids a live playlist's `MEDIA-SEQUENCE` from decreasing; it happened once in 34 h and self-healed on the next write.

  **Accepted, not fixed (operator ruling 2026-10-16: audio continuity outranks momentary playlist correctness).** The obvious fix, conditional PUTs that refuse an out-of-order write, would refuse more writes exactly when R2 is slow. That would lengthen the playlist freezes that measurably drop iPhone audio (over ~45–60 s), in exchange for removing a step that is very likely inaudible. Research by reading sources, not by testing, found no audible effect:
  - **hls.js:** a lower `endSN` reads as updated but not advanced. Fragments merge by sequence number, and there is no flush, seek or error. The unchanged-playlist error counter resets.
  - **AVPlayer:** Apple's documented failures need a sequence number whose URI changed (-12312) or an unchanged playlist (-12888). This step is neither: it is the same window shifted back one, with every number mapping to the same segment URI.
  - **VLC:** probably drops segments below its current one. Low confidence.

  Players hold ~123 s, and the bad playlist lasts one reload. The variant that would matter is a late write that changes the sequence-to-URI mapping, which for this stream means a write landing across an epoch change; that has not been observed. The definitive check, still owed, is Apple's `mediastreamvalidator` or replaying the regressed playlist on an iPhone with `~/lma-radio-ops/hls-start-test/`.
- After the flip, cron lag dropped to median 1.0 s, p90 8.1 s, max 48 s (16 over 25 s), against a median of 16.9 s and a max of 143 s on 10-13. Cron no longer writes for 75 s per run, so invocations no longer overlap.
- The off-deploy version `29b99363` fired cron twice a minute during the deploy overlap (10:02–10:04). The flip version fired once a minute for the whole window, with no minute fired twice.

## Pass criteria (spec, Rollout step 4)

| Criterion | Verdict |
|---|---|
| No freeze over 45 s outside a `metronome-down`, at most 1–2 silent chain breaks | **PASS**: 0 attributable freezes, 0 chain breaks |
| Meters agree with the dashboard | **PASS**: internally consistent to 0.03%; the operator's dashboard read (10-17) agrees, duration only to the dashboard's "2k" precision |
| PUTs within ~one per boundary plus one per renew | **PASS** |
| Duplicate check (item 9) holds | **FAILS AS WRITTEN**: 13 duplicates on fresh `scheduledTime`s, all a benign renew-and-alarm race; no redelivery observed. The logging fix (`794fb9b`/`94268a7`) was deployed 2026-10-17 17:58:26Z as version `2a275ac5`. Re-check, 18:03–22:58Z (4 h 55 m, 1,986 alarms; a fresh `wrangler tail`): **0** `metronome-duplicate` lines against ~2 expected at the old rate, 0 `metronome-target-invalid`, 0 `metronome-down`, 0 non-ok outcomes. The one alarm gap over 11 s (311 s) was a tail reconnect; the poller's longest playlist stall in the window was 20 s, which is its sampling granularity. **Fix holds** |

The operator decides between accepting item 9 as benign, with a possible follow-up to stop the renew race being logged as a duplicate, and a fix. Nothing here argues for a rollback.
