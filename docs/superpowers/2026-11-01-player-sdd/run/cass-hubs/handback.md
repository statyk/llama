# cass-hubs handback

Done. The cassette is re-laid out and committed on playout-player, not merged or pushed. Nothing was written to production. The frozen files, antenna/.env and antenna/.preview-*.json are untouched.

## Commits (on aacf9d84)
- 2086ca7e antenna: lay the cassette out like a real one (radio.css, index.html, page.js, src/pages.ts, smoke.pw.mjs, spec)
- a1de31c6 antenna: regenerate the cassette pictures from the new layout (four PNGs)
Tree clean at a1de31c6.

## Test results (from antenna/, on a1de31c6)
- `npm test`: 519 passed, 26 files. Pages check passes.
- `npm run typecheck`: exit 0.
- `npm run smoke`: 90 passed. Was 76. The 9 old shape tests became 23:
  - 12 layout tests: 4 names at 3 widths, all with a long venue
  - 3 "44 characters fit once stepped down"
  - 3 "too long ends in an ellipsis, one line, title attribute"
  - 3 no-cqw fallback
  - 1 size-class steps at 26/27/34/35
  - 1 written only on change, and a short name loses the step

Mutation checks ran in a scratch copy (/private/tmp/claude-501/-Users-shawn-projects-llama/de0d82af-59e5-4e19-8b40-c0b892640b3f/scratchpad/cass-mut), running only the cassette smoke tests. 10 of 11 mutants failed tests, all with the expected kind of failure:
- hub y, hub spacing, tight line height (descender clipping), no `long` class, no title, always write
- fallback window, venue line not below the window, date allowed to shrink, line wrapping

The survivor was `#label-date { flex: 1 1 0 }`. It gives the date half the line, which still shows it whole, so it is not a defect. The stronger mutant (date shrinks, venue grows) was caught by dateUncut.

## Measured geometry (% of shell; the same at 320, 390, 1200 because everything is cqw)
| Width | Shell px |
|---|---|
| 320 | 288 |
| 390 | 358 |
| 1200 | 340 |

- Hub centres: 47.2% down, 42.3% of width apart, centred at 50.0%. Target 44-50 and 40-45; photo 47 and 42.
- Window: 58.0% wide, 27.1% tall, 33.7% to 60.7% down, centred, rounded rectangle. Photo 60, 27, 34-60.
- Paper: 6.9% to 78.7% down, side margin 5%.
- Artist line ends at 31.4%, above the window.
- Venue/date line runs 64.5% to 76.2%, below the window.
- With the long venue, date width is 60.7 px at 320 and uncut. scrollWidth equals viewport width at all three widths.

## Smallest text at 320 px
- Venue and date: 15.0 px
- Artist: 21.9 px normal, 17.9 px `long` (27-34 chars), 14.4 px `longer` (35+ chars, then ellipsis)
- `.ln` (LMA RADIO / ON THE AIR): 9.2 px, unchanged by this work

## Screenshots
In /Users/shawn/projects/llama/.claude/worktrees/player/.superpowers/polish-shots/:
- {normal,long,descender,longest}-{320,390,1200}.png and -cass.png close-ups
- fallback-{320,390}-cass.png

normal-320.png, normal-390-cass.png, long-320-cass.png, long-1200.png, descender-320-cass.png, longest-320-cass.png and fallback-320-cass.png were viewed beside skm.jpg. It reads as a real cassette and descenders are not clipped. The other shots were taken and measured but not viewed.

## Art
Regenerated with `node scripts/make-art.mjs`. cassette-512, cassette-og, icon-180 and icon-192 were all viewed: centred, whole, and showing the new layout.

## What changed besides the brief
- Hub drawing is unchanged but grew from 9.6 to 11 cqw to suit the taller window. Tape packs are re-centred on the hubs.
- `.hand` line heights went up so Caveat descenders are not clipped. A test now checks the text's content area stays inside its box.
- The date has .12em right padding because the pen stroke's overhang clipped the last digit.
- DOM: `#label-where` and `#label-date` are now spans inside one `.hand.h2`. `.hand.h3` is gone.
- `title` is set on every artist write, including the station name.
- Fallback block rewritten in percent and px, with clip-path, border radii, packs and hubs. It is tested by serving radio.css with cqw invalidated in Chrome, not in a real old browser.

## Decisions for the operator
1. With nothing on air (and so in all four pictures) the line below the window is a blank ruled line. It reads as an unwritten label; I left it. Say if the art should carry something there.
2. A long venue ellipsises from the end, so the city is lost first. At 320 about 26 characters show before the date.
3. `.ln` stays 9.2 px at 320. That is below the 11 px aim, which the brief set for the venue line only.
4. Size steps go by character count (thresholds 26 and 34), not measured width. An all-caps name of up to 34 characters may hit the ellipsis at the `long` size. Not measured.
5. No independent reviewer has looked at this. Only the mutation checks and my own viewing back it.
