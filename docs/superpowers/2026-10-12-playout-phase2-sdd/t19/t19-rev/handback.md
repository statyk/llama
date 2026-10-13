# t19-rev handback (range 8e59555..9720344)

SPEC: APPROVED
QUALITY: APPROVED

No Critical or Important findings. Five Minor findings (four are doc wording, one is a narrowing in the code), all optional.

## Verification done
- Re-ran from the worktree: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` gave 459 passed, 1 skipped. `cd antenna && npm test` passed the pages.ts freshness check, then 14 files / 236 tests. Worktree clean, nothing committed or edited.
- Mutation tests in a scratch copy (`git archive 9720344`, PYTHONPATH shadowing proven by a planted `T19_SENTINEL` that resolved to the scratch file, PYTHONDONTWRITEBYTECODE=1, `-p no:cacheprovider`):
  - **M1** removed the new `except ValueError` arm. I predicted exactly `test_the_guard_cache_reads_offair_like_the_worker[{not json-True]` and `[-True]` would go red with `None is True`. They did: 2 failed, 38 passed. CAUGHT, as predicted.
  - **M2** made the generic arm `offair = True`, so every read error would count as off the air. I predicted only `test_the_guard_cache_records_evaluation_time_and_offair_but_gating_stays_on_tripped_only` would go red (line 348). It did: 1 failed, 39 passed. CAUGHT, as predicted. This means the failed-GET → None behaviour is pinned.
- I checked every quantitative claim against the source (code wins). All match:
  - wrangler.jsonc: PLAYLIST_WINDOW 16, LOOKAHEAD 12, HOLD_BACK 12, GUARD_EVAL_SECONDS 900, BLIND_AFTER_SECONDS 21600, MONTHLY_BUDGET_USD 15, BILLING_ANNIVERSARY_DAY 11.
  - clock.ts: MAX_LOOKAHEAD 16; holdBack clamped to window−1; MAX_PUTS 10; MAX_LOOP_MS 75 s; guardMs measured; alerts flushed in `finally` after the last write; `blocked === null` writes nothing.
  - playlist.ts: tags emitted only when holdBack·d ≥ 3·TARGETDURATION; holdBack clamped to entries−1; `(12·10240/1000).toFixed(3)` = 122.880.
  - offairSequence = `max(0, indexAt(max(seqMs, now))) + lookahead + 1`, with seqMs = scheduledTime + loopMs.
  - pricing.ts: TRIP_ACTUAL 0.9, TRIP_PROJECTED 1.0. meter.ts: RECENT_MS 3 h, LAG_MS 5 min.
  - waf.ts: exactly one rule by description, and the action must be `block`.
  - alerts.ts: `EmailMessage` from `cloudflare:email`, text/plain.
  - player.js: `maxBufferLength: 130` and `backBufferLength: 30`, with no liveSyncDuration.
  - nowplaying.js: stallMs 15000, probeEveryMs 10000, verdictsNeeded 2; 403 or ENDLIST are the verdicts; `networkDetails.status` 403 maps to off-air.
  - config.py: dead_clock_seconds 120 (ge=31), guard_stale_minutes 45; deadclock STALE_CHECKS 2.
  - systemd unit: Type=notify, WatchdogSec=45min, EnvironmentFile=/etc/transmitter/%i.env. alerts.py reads SMTP_USERNAME/SMTP_PASSWORD/NTFY_TOKEN and writes ~/.transmitter/alerts.json.
  - `npm test` = `build-pages.mjs --check && vitest run`; the wrangler-config test rejects account_id, zone_id and any `@domain`.
  - The cron numbers (15.1/76.7/117.4 s, 846 invocations, ~13.6 h) match the phase-1 verification doc. The docs are consistent with playout-setup.md section 4 step 6, section 7 (VLC) and the secret list, and with the plan's A4 amended block and A1/A2/A3/A5.
- Brief and plan coverage: Task 19 Step 1 items 1–4 and Step 2 (A1, A2, A3, A5, and A4 as built, with the cron lag) are all present. The brief's extras are present: hold-back/lookahead with "keep L = R" and "a lookahead alone adds no runway", the SYSTEM unit `sudo systemctl … transmitter@<user>` with no `--user`, and the SDD-record pointer.
- Public-repo scan of the added lines found no address, ID, token or key (the only `@` is `transmitter@<user>`).
- F9 code: the `except ValueError` arm comes before `except Exception`, which is correct ordering. `JSONDecodeError` and `UnicodeDecodeError` (raised by `json.loads(bytes)`) both land in it. botocore's read and transport errors fall to the generic arm and give None: ResponseStreamingError, ReadTimeoutError, IncompleteReadError, ConnectionClosedError, EndpointConnectionError and ClientError are all non-ValueError (checked on botocore 1.43.112, and StreamingBody.read wraps urllib3 errors). `blocked`, `error`, the return value and the cache shape are unchanged.

## Minor

1. **publish.py:161-163, how wide the catch is.** `except ValueError` also catches the few botocore/urllib3 classes that do subclass ValueError (`UnknownEndpointError`, `InvalidRegionError`, `LocationParseError`, …). So "Botocore read errors are not ValueErrors" holds for read errors but not for every botocore error.
   - Failure scenario: a bad endpoint or region config would record `offair: True`, which suppresses dead-clock alerting, instead of `None`. In practice the guard.json read fails first, so `blocked=True` with an error and publish stops loudly. The impact is negligible.
   - Suggested fix (optional): narrow the catch so the comment is true by construction:
     `except (json.JSONDecodeError, UnicodeDecodeError):` with the comment `# Present but unparsable: the Worker (guard.ts) reads such bytes as off the air. A failed read is not caught here (-> None below).`

2. **CLAUDE.md:139, "both write `state/` directly".** Bare `transmitter budget` only reads. R7 also has both commands bypassing the publish lock.
   - Replace `(both write \`state/\` directly, bypassing the guard and the PUT budget)` with `(\`offair\` and \`budget --raise-to\` write \`state/\` directly, bypassing the publish lock, the guard and the PUT budget)`.

3. **CLAUDE.md:272, "evaluating when `guard.json` is 15 min old".** The code (latch.ts `shouldEvaluate`) keys on the last attempt's `evaluated_at` being ≥ 15 min old, or a raise newer than that attempt. It does not key on the file's age; guard.json is rewritten for other reasons too.
   - Replace `evaluating when \`guard.json\` is 15 min old through` with `evaluating when its last attempt is 15 min old (or at once after a raise) through`.

4. **Spec :452, "superseding A2's ~45 s".** This has no referent in the spec. The A2 as-built note (Player section, after this note) never states ~45 s; that figure lives only in the plan.
   - Replace `out (~2.5 min, superseding A2's ~45 s; spend is unaffected).` with `out (~2.5 min, against the plan's ~45 s estimate for A2; spend is unaffected).`

5. **Spec :436-449, the A4 note omits one changed playlist rule.** The grace hold and the fallback switch now key on the window's end, `cur + lookahead`, not `cur` (playlist.ts `windowEntries`, and the comment at playlist.ts:18). The spec's grace rule above still reads `0 < cur − horizon.last ≤ 3`. Separately, "~123 s from the listed end" is the nominal value; iOS measured 113–120 s (plan A4).
   - After `airing (cap 16),` insert `with the grace hold and the fallback switch applied to that end (cur + lookahead),`.
   - Optionally change `start ~123 s from the listed end` to `start ~123 s from the listed end (113–120 s measured on iOS)`.

## CLAUDE.md density
These are acceptable, so I suggest no trims. Nearly every added clause is one the plan's Step 1 or the brief explicitly required (secret list, VLC limitation, "MAX_PUTS unchanged", SDD pointer). The paragraph matches the file's existing register, and it does not repeat text already in the file. The hold-back sentence is two sentences, as the brief asked. If a trim is wanted, the cheapest is to drop "The spend bounds above (`MAX_PUTS = 10` etc.) are unchanged." The antenna paragraph directly above already states those bounds as current.
