### Finding Verdicts

1. **Important 1, CLAUDE.md content** — ADDRESSED. CLAUDE.md:342 has `npm run smoke`; the player bullet has the layout, frozen files, `sections`, the Cautions literal; :513 says the player is built. Checked against code: no `document.`/`window.` in timeline, recovery, media or notes, each has a test file; the only `setInterval` is app.js:26; root player.js, nowplaying.js and style.css are unchanged since 6cc6dae0; Chrome and ffmpeg match playwright.config.mjs and global-setup.mjs; `CAUTIONS_PREFIX = "## cautions"` (site.py:101, lower-cased at :143) matches brief.py:103 and is pinned by test_site.py:212.

2. **Important 2, footer link** — ADDRESSED. index.html:77 has `target="_blank" rel="noopener"`, smoke asserts both, `build-pages.mjs --check` exits 0.

3. **Important 3, stale setup-doc expectations** — ADDRESSED, each checked against code.
   - Line 645: 122.88 s hold-back, then nativeStallMs 30 s, delay 4-6 s (first probe about 35 s), probeEveryMs 15 s, verdictsNeeded 2 (second probe about 50 s) comes to about 173 s; "about 170 s" is right.
   - Line 647: stallMs 15 s plus delay 4-6 s gives `reconnecting` about 20 s after the position stops; maxBufferLength 130 at player.js. Measured in Chrome with a 20 s `setOffline` on hls.js 1.7.3: `levelLoadError` fatal=false, no recovery action, position resumed by itself, so "shows nothing" holds and hls.js does not die silently on a blip. (The fixture buffer is about 12 s, so that run proves non-fatal and self-resume, not the 130 s.)
   - Lines 275-277: the rule's allowlist (setup doc section 2 step 7) is `/`, `/index.html`, `/offair.html`, `/style.css`, so `/assets/` is blocked as stated.

4. **Important 4, preview rounds** — ADDRESSED in the words the brief asked for: plan:835 and the setup doc name round 3 and removing 1 and 2 from the worktree; the spec's Preview section names no round. `.preview-1.json` and `-2.json` exist here. Note: see Minor B.

5. **Minor 1, render error stops recovery** — code ADDRESSED; the smoke pin NOT ADDRESSED.
   - Code: interval armed before first tick (app.js:26-27), try/catch at app.js:18-22, `zoneLabel` catches at timeline.js:121-130, vitest test stubs Intl. The brief's "longGeneric fallback" is met by falling back to the zone id.
   - Loop order at head: `setInterval` then `tick()`. Correct.
   - **Your check, measured:** with a throw planted at the top of `renderAt` from page load, `player.tick` count went 4 then 10 over about 9 s. With the try/catch removed it stayed 0, with `pageerror` every second.
   - **"Pinned by reading only": the stated reason is wrong.** The handback says a render throw cannot be provoked without a test-only hook. This one does it with no hook, 7 lines: after Play shows `turning`, `page.evaluate` sets `Element.prototype.closest` to throw (`setHeadingHidden` calls it every render) and `audio.playbackRate = 0`, then `expect(#hubs).not.toHaveClass(/turning/)`. Prediction before running: red only on the no-try mutant. Result: green at head, red on the mutant ("window turning" held for 8 s). The shipped scenario at smoke.pw.mjs:126 stays green on that mutant as the implementer said, so its title's "keeps the loop going" claims more than it pins. The brief asked for the pin if it is a few lines; it is.
   - See Minor A for what the try/catch does not cover.

6. **Minor 2, give-up limit undocumented** — ADDRESSED. Setup-doc known limits; matches giveUpMs 600000, `tick` returning `giveup` before any `play()`, `gaveup` text "Lost the stream." (page.js:14) and Try again shown (page.js:147).

7. **Minor 3, Step 2 wait** — ADDRESSED in the setup doc and plan Step 2. `NOTES_CACHE = "public, max-age=3600"` (publish.py:53); the one-liner raises KeyError on an old file.

8. **Item 7, off-air copy** — ADDRESSED. offair.html:24 and pages.ts read "Try again"; `git grep` finds no other use of the old copy.

### New Breakage in the Fix Diff

None from the fix itself. Two Minors, neither a regression:

- **Minor A: a lasting render throw still blocks Play and recovery, by a second route.** page.js:148 `setState` calls `renderAt` unguarded, and player.js calls `show()` ahead of the work: :105 before `attach()`, :175 before `probe()`/`restart()`. Measured with the planted throw:
  - From load: Play gave no source and no audio, state stuck, `pageerror` "planted".
  - Mid-session, then a frozen position: results `["probe"]`, no fetch made, `probing` stays true, so nothing further until give-up. Control with no throw: `["probe","restart"]`, audio back.
  - So `player.tick` runs, as you required, but the finding's title still holds for a persistent throw.
  - Why Minor: no real input reaches it now. `zoneLabel` was the persistent cause. By reading, tapeLog and comingUp filter out unparseable dates, and a bad `start` reaching `airTime` via justAired throws once only, because `rebuild` sets the key (page.js:52) before building rows (:53).
  - Fix tried in scratch: try/catch around page.js:148, five lines. Then from load Play gave audio, and mid-session gave `["probe","restart"]`. It needs no change to app.js.
- **Minor B: the removal of rounds 1 and 2 sits after the step that can delete the worktree.** Plan Step 3 (:830) ends at the finish menu and says "The rest happens from `main`"; the removal is in Step 4.3 (:835). Read in order, the worktree can be gone by then, which is the trap Important 4 described. The final review's recommendation to put it in the finish steps was not carried over. Run the two removals before the finish menu removes anything, or add a clause to Step 3.

### Out-of-Scope Observations

- Scratch slip by me: a stray `cp` targeted `/tmp/x`, which turned out to be an existing directory holding nothing else, so a copy of app.js landed there. I deleted that one file. I cannot rule out that it replaced an earlier `/tmp/x/app.js`. The worktree was not involved: `git status` clean, HEAD ac454f74.
- Spec "Deploy" step 2's "up to about 4 hours" concerns pages going public, not the `curl` check, so it is not a contradiction and I left it.

### Verdict

**Fix round:** Findings remain open: item 5's smoke pin only (Minor). No new Critical or Important breakage. All Important findings are addressed. Recommended in one small commit: the 7-line pin, and the page.js:148 guard (Minor A). Minor B needs an action at finish, or one clause in the plan.

Checks run: all in a `git archive` scratch copy at ac454f74, Playwright against the fake station. Not run: the full suites (the implementer's 519 vitest and 58 smoke are unverified by me beyond the diff) and `deploy-assets.mjs` (not needed). Nothing ran on an iPhone.
