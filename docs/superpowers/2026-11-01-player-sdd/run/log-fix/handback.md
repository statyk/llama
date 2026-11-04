# log-fix report
Commit: 87d2d73d on playout-player (not merged/pushed). Items 1-8 in one commit; shots (item 9) are gitignored.
Results: npm test 524 passed (was 523, +1 tapeLog start:null case); npm run typecheck clean; npm run smoke 107 passed (was 104: -1 padding test, +4 new: off-air log, synthetic bold, focus to list, button keeps focus).
Item 1: font-synthesis: weight on .log li.now. Chrome's fake bold does NOT change advance width (width equal 48.25 bold vs 400), so the "wider" check is impossible in Chrome; the smoke test compares ink (element screenshots): bold != 400, synthesis:none == 400. In the shots the now row's bold is only slightly visible, looks acceptable, no redesign; WebKit not checked.
Item 2: renderLog(atMs, show) uses a shared onAirShow(); off air -> 0 rows, no aria-current, heading and button hidden (test).
Item 3: list gets tabindex=-1; focus moves to it only when the focused button hides (test, plus a test that it stays on the button otherwise).
Item 4: tapeLog skips tracks whose start does not parse (vitest, start:null).
Item 5: no-shift now measures #now-show top at 320 px with a 44-char artist. Mutant (scratch copy, stoppedLine restored to `${artist} is on the air. Press Play.`), predicted red on that expect: RED, expected 446.27 received 401.27 (line moved up 45px as #now unwrapped). Live tree unaffected.
Item 6: padding test deleted. Item 7: aria-expanded written only on change. Item 8: spec line narrowed; says long song title may wrap once playing.
Item 9: six shots retaken in .superpowers/polish-shots/log-{320,390,1200}-{collapsed,expanded}.png (long artist+venue+city) and viewed. Nothing broken. Notes: at 320 the #now-show line wraps to 4 lines, ending with an orphan "1 2008"; cassette label bottom truncates the venue with an ellipsis (by design); collapsed window shows Tape 11-15 with now marker on 13.
Nothing applied unclean. Shot script lived in scratchpad (shots.mjs), nothing extra in log-fix dir besides log-fix.log.
