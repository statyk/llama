# polish-impl handback

Both changes are done and committed on `playout-player`. Nothing was merged, pushed or deployed.

## Commits
- 68b3b301 antenna: a Show notes link for the show on air
- 25028832 antenna: the cassette keeps a real cassette's proportions

## Test results (from antenna/, on the final tree)
- `npm test`: 519 passed (baseline 519); pages.ts is fresh
- `npm run typecheck`: clean
- `npm run smoke`: 76 passed (baseline 60: 7 for the notes link, 9 for the shape)
- Six mutants in a scratch copy were all caught. The ones that changed behaviour:
  - square aspect ratio: 10 tests failed
  - no line clamp: the 3 "past two lines" tests failed
  - venue wrapping: 6 tests failed
  - old `ticketLinks` selector: the panel test failed
  - never unhiding the link: 4 tests failed
  - writing the link every tick: the "left alone" test failed
  - Two predictions were off, though each mutant was still caught. I predicted 9 for venue wrapping, but a one-line artist leaves room for it, so 6 failed. I predicted 1 for never unhiding, but the link starts hidden in the HTML, so 4 failed.

## Change 1
`#now-notes` sits in `.playing` under `#now`. `renderAt` sets its slug and href through `showHref` only when the slug changes. It is hidden, with its href removed, when nothing is on air or the state is off air. The selector in `ticketLinks` is extended, with no second listener. "Follows when the on-air show changes" is tested with `page.clock.fastForward`.

## Change 2
`.cass` uses `aspect-ratio: 100.4 / 63.8` and every child is absolutely placed, so content cannot grow it. Everything is sized in cqw, so the drawing scales as one piece: ratio 1.574 at all three widths.

The paper covers most of the shell, its top corners cut for the screws. The window sits in the paper's lower-middle and the trapezoid at the bottom edge. Artist takes at most 2 lines then an ellipsis; venue and date take 1 line each with an ellipsis.

I added a third fixture to the shape test, a name past two lines, because the required long-band fixture fits in two lines and would not exercise the clamp. The shape test also checks that no label line reaches the window.

## Screenshots
/Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/polish-shots/: normal-320.png, normal-390.png, normal-1200.png, long-320.png, long-390.png, long-1200.png, plus a -cass.png close-up of each. I viewed normal-390, normal-1200 and long-320-cass; they read as a real cassette. The other nine shots were taken but not viewed. The long fixture also uses a long venue.

## For the operator
- Desktop: the column stays at 340 px, as in the approved layout B, so the cassette is 340 x 216. It is now shorter than the deck beside it, which leaves empty band below it at 1200 px. Widening the `.band` column to about 420 px would fill that, but I left it because it changes the approved layout.
- No width cap: the widest cassette is 428 px (page 460 less padding), which is not absurd.
- Artist type is smaller on a phone: about 24 px at 320 wide, was 32 px, so that two lines fit.
- The window is smaller than the mockup: 56% of the width, 37 px high at 320 wide. Its hubs shrank with it.
- Container units need iOS 16+ or Chrome 105+. On older browsers the cassette's sizes and positions are dropped and it will look broken. No fallback was added.
- The PNGs are unchanged, so the icon and link-preview art still show the old, squarer cassette. `scripts/make-art.mjs` was not run or changed.
- CLAUDE.md is unchanged: its player bullet names no page structure this affects.

## Unfinished
Nothing. Not run on a real iPhone or in Safari; the smoke tests use Chrome only.
