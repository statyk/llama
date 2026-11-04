### Task 8: The player

**Model hint:** opus.

**Files:**
- Create: `antenna/public/assets/player.js`
- Modify: `antenna/public/assets/app.js`, `antenna/e2e/serve.mjs` as needed
- Test: `antenna/e2e/smoke.pw.mjs`

**Interfaces:**
- Consumes: `recovery.js`, `media.js`, Task 3's `findShow` and `positionMs`, `page.js`'s `setState`, `refreshTimeline` and `currentTimeline`, Task 6's ids, and the decisions in `docs/superpowers/2026-11-01-player-probe.md`.
- Produces: `export const player = { start(), stop(), tick(nowMs), audible, playbackMs() }`.

- [ ] **Step 1: Implement `start`, `stop` and `tick`,** porting `public/player.js`'s hls.js config and comments (`maxBufferLength: 130, backBufferLength: 30`) and `prefersNativeHls` choice. `tick` is called by `app.js`'s loop.
  - Station states go through `setState`; `page.js` holds the text. `start` sets `playing`, `stop` sets `stopped`, and unsupported sets `unsupported`.
  - The first `probe` or `restart` result sets `reconnecting`; `recovery.advancing` sets `playing`. `playing` events and a resolved `play()` never do.
  - `#hubs` has `turning` exactly while `recovery.advancing`.
  - `playbackMs()` returns a finite number or null, as `public/player.js` checks `Number.isFinite`.
  - hls.js: `immediateOffair` and `live === false` go straight to `offair`. Other fatal errors do nothing until `Recovery.tick` says so.
  - Native `error`: `recovery.failed(now)`. `ended`: `offair`. `waiting`: `recovery.noteWaiting()`. `stalled` is not handled.
  - `tick` result `probe`: fetch `/live.m3u8` with `cache: "no-store"` and an 8 s limit via `AbortController` and `setTimeout` (not `AbortSignal.timeout`). `classifyProbe` off-air is `verdict("offair")`; any other HTTP response, whatever its status, is `verdict("reachable")`; a rejected or timed-out fetch is `verdict("unreachable")`. Never read `navigator.onLine`. Act on the verdict at once by running `tick` again, so that a restart follows a fresh answer.
  - The element is not touched between a failure and a `restart` result: a teardown while unreachable ends the audio session and iOS freezes the page.
  - `tick` result `restart`: check `recovery.mayPlay(now)`, tear down with `selfTeardown = true` held until after the queued `pause`, restart on the same `<audio>` in the full form (`src` removed and set, as Stop then Play), `recovery.restarted(now)`. It does not force a timeline fetch.
  - `tick` result `giveup`: stop, then `gaveup`.
  - A `play()` rejection for which `playBlockedNotice` returns text sets `refused`. Any other rejection is left to the stall path.
  - `pause` event: `pauseMeansStop({ selfTeardown, stalled: recovery.stalled, ended: audio.ended })` → stop.
  - Stop cancels any pending retry or probe through a session counter, as `public/player.js` does (Review Focus 5).

- [ ] **Step 2: Media Session.** `navigator.mediaSession.metadata` set from `sessionText` with `ARTWORK`, only when the text changes. `playbackState` follows the player. Handlers `play`, `pause`, `stop`, none for seek or skip. `play` calls `start()` first, then `refreshTimeline(true)`. D2: a car or lock-screen `pause` is a normal Stop. D3: metadata runs from `tick`, with no `timeupdate` fallback.

- [ ] **Step 3: `app.js`.** Import `player.js`. Bind `#play` and `#retry` to `player.start()` and `#stop` to `player.stop()`. The loop becomes `renderAt(positionMs({ playing: player.audible, playbackMs: player.playbackMs(), nowMs }))`, `player.tick(nowMs)` and `refreshTimeline(false)`.

- [ ] **Step 4: Add smoke scenarios,** on the real HLS fixture.

```
Play gives audio (currentTime advances) and #hubs gets turning
Now playing follows the playback position, not the wall clock (the fixture's program-date-time falls in another track)
Stop silences the audio, stops the hubs and shows the stopped line
a stall, then recovery to playing with no key pressed
navigator.mediaSession.metadata.title is the song
/live.m3u8 answering 404 shows "Reconnecting…", then a switch to 403 reaches the off-air notice
Stop during a retry delay: no further /live.m3u8 request after a further 40 s of mocked time (page.clock)
/live.m3u8 unreachable (connections destroyed, setLive("drop")) during a stall: probes only, the element's src is untouched, then reachable again gives a restart within one probe interval
a 10-minute silence shows "Lost the stream." and Try again (page.clock)
over 10 mocked minutes of 404: at most 60 /live.m3u8 requests and at most 4 /timeline.json requests
```

- [ ] **Step 5: Run** `cd antenna && npm test && npm run smoke`. Expected: all pass, and the frozen files are unchanged. Task 12's preview covers the real stream.

- [ ] **Step 6: Commit.** `antenna: the new player with recovery and Media Session`.

---

