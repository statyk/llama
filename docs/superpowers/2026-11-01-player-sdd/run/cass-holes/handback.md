# cass-holes handback
Commits: holes+screw+art (e0029e2f), then stoppedLine constant (see git log -2).
Tests (cd antenna): npm test 519 passed, npm run typecheck clean, npm run smoke 91 passed; run before each commit.
Geometry (cqw of shell width W; shell height 63.54): .trap left 15.5, w 69, h 12.5 (top 51.04, gap to paper 50 = 1.04cqw). Large holes 4.9 dia centres at 25.8/74.2; small 3.4x3.8 r30% at 36/64; hole y centre 59.6 (93.8%); screw 3.2 at 50, y 53.18 (83.7%). Fallback in %/px. Smoke asserts (all widths, fallback test too): 4 holes+1 screw, in .trap, symmetric <=1px, y 90-97%, trap below clabel, small hole >=8px wide. At 320px small hole = 3.4cqw ~ 10.4px (screenshot shows visible).
Screenshots: .superpowers/polish-shots/holes-{320,390,1200}.png. Art regenerated, all four PNGs viewed, holes visible.
stoppedLine: signature kept (stationName still used for no show); text constant; vitest, 7 smoke assertions, spec table + Now playing bullet updated; CLAUDE.md had no such quote. nowLine untouched.
Notes: BSD sed failed once; I killed only my own stale smoke pids.
CORRECTION: the stoppedLine commit (b83be215) was committed with 6 smoke failures (I over-wrote the expected text with an "On Air " prefix; the real text is bare). Fixed in the next commit; full smoke then 91 passed, npm test 519, typecheck clean. Final HEAD is the fix commit; branch is green at HEAD only.
