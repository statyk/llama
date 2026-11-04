# cass-fix handback
Commit: one commit on playout-player (on top of a1de31c6), see `git log -1`. Not merged, not pushed. No production touched.
Files: antenna/public/assets/radio.css, antenna/e2e/smoke.pw.mjs only.

1. J tail: padding-left .12em; margin-left -.12em on .hand, #label-where, #label-date. Nesting does not double: h2 shifts left, #label-where's own -.12em margin lands at the h2 border edge, text stays at its old x. The border-bottom rule would have grown left with the negative margin, so it is now painted as a background (transparent 1px border + gradient, width calc(100% - .12em), right-aligned, border-box origin): rule extents unchanged. Fallback block needs nothing (em units inherit).
   EXTRA: the ink test also exposed a RIGHT clip: the last "8" of "Jan 1 2008" lost 2 px at x=329. Date padding-right .12em -> .2em. The date text moves ~1 px left as a result.
2. Ink test ("the pen's overhang shows...", 390 px, "Jan 1 2008", Jerry Jeff Walker / Jones Hall, Jay OK; clip screenshot of .cass with and without overflow: visible !important on the three; byte-equal). Not flaky; byte comparison kept. Before: FAILS without the fix (CSS reverted to HEAD, first with the old .12em right padding). With only the left fix: still failed, 6 channel values at one x (right edge of the final 8), hence the .2em. With left fix removed but .2em kept: fails again (so the left fix is load-bearing). With both: passes. First attempt used a long venue and failed on the ellipsis (overflow visible disables text-overflow), so the test uses a short venue.
3. Descender row deleted (3 widths). `clipped` comment now says it checks the line box's vertical fit only. Normal-name row kept.
4. Three new tests: off-air keeps .hand.h2 height/top and window/cass rects; 30-char name (class long) loses it going to off air and to a short next name; #label-date padding-right > 0.
5. dateInLine: date.right <= line.right + 0.5.
6. Fallback hub 19% -> 20.6% (one value; percent resolves against the window's content box, 53.3% of cass). Measured fallback spacing 43.2% -> 42.3% at 320/390/1200.

Verification (from antenna/): npm test: 519 passed (unchanged, no vitest additions); npm run typecheck clean; npm run smoke: 91 passed. 90 - 3 (descender row x 3 widths) + 4 new tests = 91.
Close-up: .superpowers/polish-shots/j-390-cass.png (4x, viewed): J tails of artist, venue and date show; rules start where they did. Generated with channel chrome via a scratch script in the scratchpad, not in repo.
Nothing failed to apply cleanly.
