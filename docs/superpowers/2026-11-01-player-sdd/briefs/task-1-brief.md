### Task 1: Asset deploy and the early iPhone test

**Model hint:** opus (the probe's design decides what the operator can learn).

This task ends in a human checkpoint. Nothing later may start until its results are recorded, because Tasks 4, 7, 8 and 11 depend on them.

**Files:**
- Modify: `antenna/scripts/deploy-assets.mjs`, `.gitignore`
- Create: `antenna/public/assets/preview/probe.html`, `probe.js`
- Create: `docs/superpowers/2026-11-01-player-probe.md`

**Interfaces:**
- Produces: `node scripts/deploy-assets.mjs [--dry-run]`, `--preview <n>`, `--remove-preview <n>`. Later tasks add files under `public/assets/` with no script change.

- [ ] **Step 1: Make `ASSETS` walk `public/assets/`.** Keep the five existing entries exactly. Add every file under `public/assets/` except `preview/`, keyed `assets/<relative path>`, `max-age=3600`. Content types: `.js`, `.css`, `.html` as existing; `.woff2` `font/woff2`; `.png` `image/png`; `.webmanifest` `application/manifest+json`; `.txt` `text/plain; charset=utf-8`. Unknown extension: exit 1 naming the file.

- [ ] **Step 2: Add `--preview <n>`.** It uploads, all with `public, max-age=60`:
  - `assets/preview/<n>/index.html` from `public/index.html`, and everything under `public/assets/` (including `preview/`) to `assets/preview/<n>/assets/...`;
  - `node_modules/hls.js/dist/hls.min.js` to `assets/preview/<n>/assets/hls.min.js`;
  - `assets/preview/<n>/assets/radio.webmanifest`, once `radio.webmanifest` exists, rewritten with `start_url` `/assets/preview/<n>/index.html` and `scope` `/assets/preview/<n>/`;
  - `assets/preview/<n>/probe.webmanifest`, generated while the probe exists: `display: standalone`, `start_url` `/assets/preview/<n>/assets/preview/probe.html`, `scope` `/assets/preview/<n>/`.

  HTML under `public/` refers to its own assets relatively (`assets/radio.css`) and to data root-absolutely (`/live.m3u8`), which is why this copy works. An upload writes its key list to `antenna/.preview-<n>.json`, gitignored (`antenna/.preview-*.json`); `--dry-run` writes none. `--remove-preview <n>` runs `wrangler r2 object delete ... --remote` over that list, then deletes it. A missing list exits 1 naming the file.

- [ ] **Step 3: Verify.** `ANTENNA_BUCKET=x node scripts/deploy-assets.mjs --dry-run` lists the five old keys and nothing under `preview/`; `--preview 1 --dry-run` lists keys under `assets/preview/1/` with `max-age=60`.

- [ ] **Step 4: Build the probe page.** One page, no styling work, large buttons, usable on a phone:
  - **Start**: sets `audio.src = "/live.m3u8"` on one `<audio>` and calls `play()`.
  - **Stop (teardown)**: `pause()`, remove `src`, `load()`, as `player.js` does.
  - **Pause only**: `audio.pause()`.
  - **Retry loop**: repeats teardown, `audio.src = "/live.m3u8"` and `play()` every 30 s, logging each result, across a dropout and the reconnect, until pressed again.
  - Media Session metadata with a counter in the title, updated by three independent sources labelled in the title: a 5 s `setInterval`, `timeupdate` every 5 s, and on `play`. Handlers `play`, `pause`, `stop` log and, for `play`, restart.
  - A log on the page of timestamped `play, playing, pause, waiting, stalled, error, ended, suspend, abort`, `visibilitychange`, `pagehide`, `pageshow`, `online`, `offline`, and a line per interval tick with the gap since the last tick. Persist it to `localStorage` so it survives, with a **Copy log** button.
  - An `<a target="_blank" href="https://archive.org/details/etree">` and a `history.pushState` button, to check audio and the back swipe.
  - A `<link rel="manifest" href="/assets/preview/<n>/probe.webmanifest">` (the page reads `<n>` from `location` and inserts the link). `--preview` writes that file (Step 2).

- [ ] **Step 5: Commit** `deploy-assets.mjs` and the probe. Message: `antenna: asset walker, preview rounds and the early iPhone probe`.

- [ ] **Step 6: HUMAN CHECKPOINT.** Stop and report to the parent. `antenna/.env` isn't in the worktree, so the operator first copies it from the main checkout or exports `CLOUDFLARE_ACCOUNT_ID`. The operator then runs `ANTENNA_BUCKET=lma-radio node scripts/deploy-assets.mjs --preview 1` and opens `https://listen.lma-radio.com/assets/preview/1/assets/preview/probe.html`, in Safari and from the home screen, and in the car. Write the operator's instructions so each step says what it checks. The buffer holds about 2 minutes, so a dropout test needs at least 4 minutes offline and a stall confirmed in the log; if the log shows no stall, that test run doesn't count.

  | # | Do | Answers |
  |---|---|---|
  | 1 | Start, lock, wait 5 min with music on | Do timers and `timeupdate` run while locked; does the lock screen title change |
  | 2 | Start, lock, airplane mode at least 4 min, then off | Event order in a dropout; does `pause` fire; does iOS recover alone |
  | 3 | Retry loop across a 15-minute locked dropout, network back during the loop | Is scripted `play()` allowed after a dropout |
  | 4 | Airplane mode 15 min, locked | Do timers run in a long stall; is the 10-minute limit enforceable |
  | 5 | Stop (teardown), then lock-screen or car Play | Does Play still reach the page after teardown |
  | 6 | Pause only, then car Play | Same with the session kept |
  | 7 | In the car: Start, read the display, Bluetooth off | What the car shows; what a disconnect fires |
  | 8 | From the home screen: tests 1, 2 (airplane mode at least 4 min), 5, plus pushState back swipe and the archive link | Does the app behave like Safari; does audio survive opening archive.org |

- [ ] **Step 7: Record results** in `docs/superpowers/2026-11-01-player-probe.md`, with the pasted logs, and commit. Then write down these decisions there, each with its evidence:
  - **D1 pause rule:** does a `pause` during a dropout need the stall condition (Task 4)?
  - **D2 session:** does a car or lock-screen `pause` tear down, or only pause and `stopLoad()` (Task 8)?
  - **D3 ticks:** do timers survive locking, or must metadata and the age-based timeline refresh run from `timeupdate` (Tasks 7 and 8)?
  - **D4 freeze:** do timers run during a locked stall? If not, recovery on a locked iPhone only happens on thaw, and the give-up check before `play()` is the safety (Task 4 still holds; Task 12's check changes).
  - **D5 home screen:** does the app match Safari? If not, stop and take it to the operator before Task 11.
  - **D6 restart:** read from test 3. If scripted `play()` is refused, recovery on iPhone ends at Try again, as the spec allows; say so in the go-live notes.

  Also record that a backwards playlist step can't be produced here: that case stays unverified and is left to the road.

  Then `--remove-preview 1`.

---

