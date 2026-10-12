# Playout phase 1: verification results (2026-10-11)

These are the first results of the phase-1 checklist (`docs/playout-setup.md` section 5). They were measured on the live station:
- listener host `listen.lma-radio.com`, on a Free zone;
- a dedicated Cloudflare account on Workers Paid;
- transmitter on hugo (Debian 12), reading the station root on the Synology over NFS.

The first show aired at 18:01:43 EDT, epoch `e20261011T055849Z`.

| Item | Result | Observation |
|---|---|---|
| A cron invocation loops ~75 s with only CPU billed | pass | Dashboard: wall time about 57 s average, CPU 7 ms. GraphQL per minute: wall P50 46–66 s, CPU P50 about 5–6 ms, 0 errors. Wall time is below 75 s because each run starts late (next row) and stops at scheduled + 75 s. |
| Scheduled vs actual cron fire times over a day | partial | First 69 invocations: lag median 10.8 s, min 6.9 s, **max 59.2 s**. One minute held two overlapping invocations. The 24 h summary is pending. A lag near 60 s leaves `live.m3u8` unrefreshed for about 45 s, within the 6-segment window. |
| R2 custom-domain cache hits incur no Class B | pass | 50 fetches of one segment: 1 MISS, 49 HIT. Segments carry `max-age=31536000, immutable`. R2 showed about 953 Class B per hour with 2 streams playing. The model predicts about 720/h (`live.m3u8` refresh) plus about 350/h (segments) plus clock reads, listener-independent. |
| A 5 s origin max-age is honoured for `live.m3u8` | pass | Edge age sampled every 2 s over 24 s never exceeded 4 s (2 → 4 → refetch). |
| The ignore-query-string Cache Rule works on this plan | pass | Fresh random `?a=…` values all HIT the same object. "Ignore query string" is available in Cache Rules on Free. |
| `wildcard` rule expressions available on Free | pass | `http.request.uri.path wildcard "/seg/*"` was accepted and enforced (the stream stopped), then the rule was deleted. The custom-rule dashboard offers only Deploy, with no draft. |
| The `*.workers.dev` URL serves no Worker | open | Needs the account's workers.dev subdomain name. |
| Players and PROGRAM-DATE-TIME; stop on ENDLIST and on 403 | pass, with one deviation | **ENDLIST (off-air):** the clock wrote it 10 s after the flag went up. Chrome, Safari and VLC each played the notice and stopped. Back on air 7 s after the flag cleared. **403 (kill switch):** audio stops in every player, but the already-playing page shows **no** off-air notice. Pressing Play then shows it (a fresh start maps the 403 correctly). Accepted for now; phase-2 follow-up. |
| Fallback → live switch (`EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0) | Chrome, Safari pass; VLC needs a restart | Chrome (hls.js) and Safari followed into the first show on their own. VLC went silent at the switch until stopped and restarted. Probable cause: the discontinuity sequence *decreases* (about 2,790 → 0), which RFC 8216 does not allow; VLC played the fallback loop's own discontinuities fine. Phase-2 follow-up. |
| archive.org MP3 derivatives carry LAME/Xing gapless info | pass | gratefuldead-1973-05-26, tracks 26–29 (Truckin' → The Other One → Eyes → China Doll): each has `pad 576 <n>` and `LAME3.99r`. The Truckin' → Other One join was heard as seamless on air. |
| The Email Routing send-email binding is available | pass | Email Routing was enabled with a verified destination. A throwaway Worker with a `send_email` binding deployed (unrestricted) and was deleted. Phase 2 should pin `destination_address`. |
| GraphQL account-scoped queries work with a read-only token, lag by minutes | pass | Token with only Account Analytics: Read. `workersInvocationsAdaptive` and `r2OperationsAdaptiveGroups` lag about 1–2 min. `r2StorageAdaptiveGroups` lags about 45 min, in coarse steps (8,154 objects, 1.37 GB at the time). |
| llama's purge flush over SMB to the Synology | found a bug; fixed in v2.8.1 | `F_FULLFSYNC` on a read-only fd fails with EACCES over smbfs, because an SMB2 FLUSH needs write access. Every deliver to the share kept its library audio. Fix: retry a refused read-only flush on a write-only fd that writes nothing. One show was backfilled. |
| A week of real op counts at ~1 listener | pending | Due 2026-10-18. |

Other findings from bring-up:
- **Cron needs a workers.dev subdomain.** Cron schedules cannot be registered until the account has one (wrangler error 10063). Opening the Workers page once creates it. The runbook now says so.
- **The Free rate-limit rule matches on path only.** It can match on URI Path or Verified Bot, but not host. Its period, mitigation timeout and IP counting are fixed. The runbook now says so.
- **hugo powered itself off at 17:57.** It was an orderly shutdown, logged by logind as "Power key pressed short". The NUC's ITE8708 infrared receiver is a logind power-switch source, so an IR remote may have sent it; the receiver is now blacklisted. Published segments kept the station on air throughout. A transient `systemd-run` unit does not survive a reboot (phase 2's unit does).
- **Render cost.** On the NUC, one show takes about 10 minutes of encoding (ffmpeg native AAC, one core near 100%), plus a loudness-analysis pass. Expect that while the lead builds to 24 h.
