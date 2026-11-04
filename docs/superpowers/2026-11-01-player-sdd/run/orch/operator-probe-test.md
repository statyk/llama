# Early iPhone test (plan Task 1 Step 6)

**What this is.** A throwaway page that plays the real stream with a plain audio element and logs everything the browser does. The real player's design has eight open questions that only a locked iPhone in a car can answer: whether timers run when locked, what events a dropout fires, whether a page may restart audio by itself, whether car Play survives Stop. The answers decide the D1-D6 choices in Tasks 4, 7, 8 and 11.

**The page's buttons.** Start. Stop (teardown): what the real player's Stop does. Pause only. Retry loop: every 30 s tears down and restarts, until pressed again. pushState. An archive.org link. Copy log.

## Set up
1. From the main checkout copy `antenna/.env` to `.claude/worktrees/player/antenna/.env`, or export `CLOUDFLARE_ACCOUNT_ID`.
2. In `.claude/worktrees/player/antenna`: `ANTENNA_BUCKET=lma-radio node scripts/deploy-assets.mjs --preview 1`. Type it exactly: `--preview=1` or a misspelt flag is not refused and uploads the live assets instead (a known minor, fixed in Task 12). This uploads a few objects under `assets/preview/1/`; nothing the live station uses changes.
3. On the iPhone open `https://listen.lma-radio.com/assets/preview/1/assets/preview/probe.html` in Safari.
4. For test 8, Share > Add to Home Screen, then launch from the icon. The first log line should say `standalone=true`.

## Four things to know first
- **Copy the log after every test.** Safari and the home-screen app keep separate logs, so copy from each. If the Copy button can't write the clipboard, a box appears with the text selected: copy it by hand. The log is kept across reloads.
- **Lock-screen or car Pause may do nothing audible,** and Bluetooth off may leave audio on the phone's speaker. That is deliberate: the page only logs those buttons, so that any pause we see is iOS's own doing. Have the phone's volume somewhere safe for test 7.
- **A dropout only counts if the buffer ran out.** The stream buffers about 2 minutes, so stay offline at least 4 minutes. Each test's log needs lines marked `STALL`, or `event waiting`/`event stalled`. No stall in the log means that run doesn't count: repeat it.
- **Stop the Retry loop before test 6** (press it again, or press Stop). Otherwise it restarts audio within 30 s of Pause only.

## Tests
| # | Do | What it checks | What to note by eye |
|---|---|---|---|
| 1 | Start, lock, wait 5 min with music on | Do timers and `timeupdate` keep running while locked, and can the lock-screen title change? | Does the lock-screen title's number and clock change every few seconds? |
| 2 | Start, lock, airplane mode at least 4 min, then off, wait 2 min | The order of events in a dropout; whether `pause` fires; whether iOS recovers alone | Did audio come back with nothing touched? |
| 3 | Start, Retry loop, lock, airplane mode 15 min, then off, wait 2 min | Is a scripted `play()` allowed after a long dropout? | Did audio come back, and how long after airplane mode went off? |
| 4 | Start, lock, airplane mode 15 min, then off | Do timers run in a long stall? This says whether the 10-minute give-up can work on a locked phone | Nothing; leave it locked until the 15 min are up |
| 5 | Start, Stop (teardown), then Play on the lock screen; repeat with the car's Play | Does Play still reach the page after a full teardown? | Is there a Play control at all? Did audio start? |
| 6 | Start, Pause only, then the car's or lock screen's Play | The same with the session kept | Same |
| 7 | In the car, paired: Start, read the display, then Bluetooth off | What the car shows, and what a disconnect fires | Exact text per line of the display. Title is the `#N` line; "artist field" and "album field" name the others. Did audio move to the speaker or stop? |
| 8 | From the home-screen icon: tests 1, 2 and 5, then pushState and swipe back, then Start and tap the archive.org link | Does the app behave like Safari, and does audio survive leaving it? | Did the back swipe stay in the app? Did audio continue during archive.org? How did you get back? |

Tests 3 and 4 are 15 minutes each and could run on a table with the phone locked. A test can be repeated freely.

## Test 9: does a locked page get to restart audio once the network is back?

**Why it exists.** Test 3 turned out not to test this. Its retry tore the audio down while offline, which ended the audio session, and iOS froze the page within seconds. Test 2 showed the opposite when the page leaves the audio alone: the page stays alive through a locked stall, `online` fires, but iOS doesn't resume by itself. So the deciding question is what happens if the page waits for the network and only then restarts. This answers D6: if it works, recovery on a locked iPhone is real; if it doesn't, recovery there ends at Try again.

**New buttons.** "Wait then restart" (on/off): while on, the page never touches the audio during a dropout. Once audio has been stuck 30 s it checks the network every 15-18 s and restarts only after a check gets an answer. "Restart form" (full/gentle) chooses how: full removes the source and sets it again, gentle reloads the same source. It shows the current choice; it resets to full on a reload, so set it each run.

Preview round 2 first: `ANTENNA_BUCKET=lma-radio node scripts/deploy-assets.mjs --preview 2`, and open the same page with `/2/` in place of `/1/`. Reload if it shows no "Wait then restart" button.

| # | Do | What to note |
|---|---|---|
| 9a | Form **full**. Wait then restart ON, Start, lock, airplane mode at least 4 min, off, leave locked 2 min, then unlock | Did audio come back while still locked? Roughly when? |
| 9b | The same with form **gentle** | Same |
| 9c | Whichever of 9a or 9b worked (full if neither), with 15 min offline | Same. This shows whether it still works once the 10-minute give-up would apply |

Turn Wait on before Start, and don't press anything until you unlock. A run counts only if the log shows the stall (`STALL`, `event waiting`) and then `wait: fetch ... status=200`. In the log, `wait: restart ... REJECTED NotAllowedError` means iOS refused it. `REJECTED AbortError` straight after the next restart's teardown is the page's own doing, and `REJECTED NotSupportedError` was the network in test 3: neither is a refusal. `wait: RECOVERED` with `restart_vis=hidden` and `vis=hidden` means the restart worked while locked: that is the only line that answers yes. RECOVERED with `restart_vis=visible` or `vis=visible` happened after you unlocked, and says nothing about a locked phone. `wait: recovered after manual restart` means your own Start or Play did it, which also says nothing. A line reading `wait: recovered alone` means iOS resumed with no help: stay offline longer next time, because short stalls recover by themselves (5 s did). If a phone call or anything else interrupts, repeat the run.

## Report back
For each test, paste:
```
Test <n> (<Safari|home screen|car>, form <full|gentle>), offline <m> min:
What I saw or heard: ...
Log: <pasted>
```
