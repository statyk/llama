F (pause→stop swallowed `ended`): ADDRESSED, player.js:86 `if (playing && !audio.ended) stop();`. The comment at :83-84 gives the reason.
- Natural end, measured with the guard as written (micro page): events [playing, pause, ended] as predicted, so offAir() runs again.
- External pause, same page: [playing, pause, stopped]. A mid-play pause still stops, because audio.ended is false then.
- Real page from `git archive f7e3136`, headless system Chrome (hls.js path):
  - ENDLIST: notice "The station is off the air.", 1 live.m3u8 fetch.
  - External audio.pause(): button shows "Play", live.m3u8 fetches stay 1 → 1 over 25 s.
- Probes ran from the scratchpad only; worktree clean at f7e3136. WebKit (the native path itself) not run here.
New breakage: none (one-line guard, nothing else in the diff).
Verdict: Approved
