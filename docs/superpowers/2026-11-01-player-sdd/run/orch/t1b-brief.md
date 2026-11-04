# Task 1 follow-up: probe "Wait then restart"

Why: iPhone results (/private/tmp/claude-501/-Users-shawn-projects-llama/de0d82af-59e5-4e19-8b40-c0b892640b3f/scratchpad/probe-results-safari-1.md) showed a teardown while offline ends the audio session and iOS freezes the page, so the Retry loop never tested: page alive, element left alone, network back, THEN a scripted restart while locked. The probe must now test exactly that.

Requirement: Add a probe button "Wait then restart" (toggle). While on: never touch the element while the position advances or while offline. Once the position has been stuck at least 30 s, fetch /live.m3u8 with cache:"no-store" and an 8 s timeout every 15 s, logging each result. Only when a fetch returns an HTTP response, do the teardown, src, play() once on the same element, log the play() result and the following events, then keep watching: if ct advances, log RECOVERED; if it stays stuck 30 s, try once more after another successful fetch. Also add a second toggle choosing the restart form: full (teardown as now) or gentle (`audio.load(); audio.play()`, no src removal). Keep the log format.

Rulings:
- Any HTTP response counts, whatever its status; log the status. A rejected or timed-out fetch logs its error and restarts nothing. Do not gate on navigator.onLine; log it.
- AbortController with setTimeout for the 8 s limit. At most one fetch at a time.
- The cadence and stuck check run from the existing interval tick; no tight timer. "Every 15 s" means the first tick at or after 15 s since the last fetch.
- At most two restarts per stall. After that a clear log line and no restarts until the position advances. Advancing ends the stall, resets the count, and logs RECOVERED only if a restart was made in this stall; otherwise a distinct "recovered alone" line.
- The restart happens on the same <audio> element, and its lines carry form, attempt, seconds stuck and vis=.
- Wait then restart and the Retry loop are mutually exclusive, logged. Stop turns Wait off. Pause only turns both off.
- Wait does nothing unless the page wants audio (`wanted`). The form toggle shows its value and persists nothing.
- Existing log line formats stay exact; new lines are greppable: `wait: fetch`, `wait: restart`, `wait: RECOVERED`.
- Only probe.js and probe.html change.
