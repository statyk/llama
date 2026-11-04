### Spec Compliance

- ❌ Issues found, two, both small. Everything else in the brief is present and matches.
  - Misunderstood: `antenna/public/index.html:27`. The static "ON THE AIR" stays printed in the off-air state, beside "The station is off the air." Spec "Station states": the cassette says what is happening in plain words. No later task owns it and the span has no id.
  - Missing (part of a requirement): `antenna/public/assets/radio.css:421`. Step 3 asks for safe-area padding, but `.panel { padding: 16px 24px 26px }` at 800 px and up drops it. See Important 2.
- Checked and fine, against the diff:
  - Every id in the interface is in `index.html`. Spec order holds. Only `assets/hls.min.js` (deferred) and the `assets/app.js` module load. `og:*` and the `data:,` icon are right. No sample content in the commit.
  - `indexpage.test.ts` is changed as briefed. `src/` changes only in generated `pages.ts`.
  - Hubs spin only under `.turning` inside `prefers-reduced-motion: no-preference` (`radio.css:150`), and smoke test 3 pins it.
  - `@fontsource` is not in `package.json`, licences are present, `font-display: swap` is set.
  - `testMatch` and `channel: "chrome"` are as briefed. `tsconfig.json` includes neither `e2e/` nor `scripts/`.
- Extra, accepted: `e2e/global-setup.mjs` is off the brief's file list but is the brief's "global setup". The show-page classes go beyond Step 3 but are justified, since Tasks 9 and 10 list no `radio.css` change.
- ⚠️ Cannot verify from the diff:
  - Real iPhone or Safari rendering. Safe-area insets are 0 until Task 11 sets `viewport-fit=cover`.
  - The show-page classes were never exercised by real markup, and the plan names none of them (grep for `bmain`, `bigt`, `jcard` and others in `docs/superpowers/plans/2026-11-01-player.md` finds nothing). Task 9's implementer must be handed the class list from the T6 handback.
  - The "accents render" claim I confirmed only from the screenshots (Béla, Café, curly quotes).

Named-risk checks outside the diff:
- Fixture shape vs `site.py` `build_timeline` and `file_starts`: same keys, `{kind,title,start}` for files, `recent` newest first. Faithful.
- `deploy-assets.mjs` walk: recursive over `public/assets`, and `.woff2`, `.png`, `.txt`, `.css`, `.js` are all typed. New files publish.
- Frozen files: `git diff --stat main..6cab53ae` on `player.js`, `nowplaying.js`, `style.css` is empty. The implementer diffed against `6cc6dae0`, not `main` as briefed; I re-ran it against `main`.
- `.superpowers/` and `*.aac` are both gitignored (`git check-ignore`).
- Torn focus: rendered in the scratchpad from a generated `focus.html`, nothing written to the live tree. See Important 3.

### Strengths

- The CSS is a close, disciplined port. Cassette, ticket and hatch rules carry the mockup's values, and departures are the ones listed.
- `.tickets { minmax(0, 1fr) }` and `overflow-wrap: anywhere` hold up against the worst sample name.
- The harness is real: frame-accurate ADTS cutting, wall-clock playlist, no mocks. Test 4 was tightened from "position > 1" to "position advanced by more than 1 s and not paused", which is the check that proves playback.
- The ffmpeg-missing error names the cause.
- `requests` keeps query strings, which Task 7's allowlist will need.
- `make-art` renders from the page's own cassette, so art cannot drift in design.
- The handback's concerns are honest and useful.

### Issues

#### Critical (Must Fix)

None.

#### Important (Should Fix)

1. `antenna/public/index.html:27`: "ON THE AIR" has no hook, so nothing can change it. It came from the mockup, but the mockup only drew the on-air state. With nothing done, a listener reads "ON THE AIR" directly above "The station is off the air." Fix: give the span an id (e.g. `label-status`) and add it to the Task 7 interface, which hides it in the `offair` state only. It is true in every other state, so the static art can stay as it is: the station is on the air whenever the art is seen, and no `make-art` re-run is needed.

2. `antenna/public/assets/radio.css:421`: a landscape iPhone is 844 px wide, so it hits this rule. Once Task 11 sets `viewport-fit=cover`, panel text runs under the notch and home indicator, while `.page` (`radio.css:388-390`) keeps its insets. Fix: use the same `calc(… + env(safe-area-inset-*))` form as `.page`, or just change the two side values and the bottom value.

3. `antenna/public/assets/radio.css:267` with `:189`: `clip-path` on `.ticket.torn` removes the focus outline. Rendered with two Tab presses: a plain ticket shows the teal ring; a focused torn ticket looks exactly like an unfocused one. Every Just-aired ticket is a link, so keyboard users lose their place across that whole section. Fix: `.ticket.torn:focus-visible { outline-offset: -3px; }` keeps the ring inside the clip. Check that the tear does not cut it awkwardly; the right side will be clipped by the tear, which is acceptable.

#### Minor (Nice to Have)

- `radio.css:253`: `.sr` is the mockup's name, but `sr` conventionally means screen-reader-only and this one is visible. Task 7 will write the class. Rename it to `.stamp` or `.date` now, while it is cheap.
- `radio.css:248, 265`: "LMA RADIO" and "NO REFUNDS" in `content` join each ticket link's accessible name, on top of the DOM "LMA RADIO PRESENTS". Screen readers will read it as noise. `content: "NO REFUNDS" / ""` silences them where supported.
- `radio.css:382`: `.meta`. Special Elite has no bold and `font-synthesis: none` is set, so the show page's `<b>On the air</b>` and `<b>Taper's lineage</b>` from `show-page.html` render as plain text and those labels lose all emphasis. For Task 9: give `.meta b` the oxblood colour, as `.bstub b` has. Same for the mockup's `.tag` link, which is coloured and underlined there and has no equivalent here.
- `antenna/playwright.config.mjs:7`: a committed config pins `outputDir` to the gitignored SDD scratch folder. Neither the brief nor the plan names it, despite the handback's "as instructed". Harmless, but `test-results/` under a gitignore entry would outlive this run. It is also what makes smoke wipe `shots/` (concern 2).
- `index.html:40, 56`: empty "Tape log" and "Just aired" headings hang with nothing under them; see Part 3. For Task 7: hide the section when its list is empty.
- The handback says ticket columns are "3 at the mockup's width". The mockup's content width is 852 px, which gives 2 columns here; 3 start at a viewport of about 924 px. The choice is still good. The claim is slightly wrong.
- `npm audit` findings after installing Playwright were not investigated. No test-output noise is reported otherwise.

### Part 3: Look

Overall a person comparing the two would approve it. It reads as the approved design, not an approximation.

Against `cassette-tickets.html`, right-hand "Concert ticket":
- Anatomy is right: stub with day, oxblood time, GEN ADM, LMA RADIO; main with teal presents line, serif name, venue, date bottom left, NO REFUNDS bottom right. Just-aired tickets drop NO REFUNDS, as the mockup does.
- Dashed perforation, both notches and the diagonal hatch are all there and visible at 390, 820 and 1200. The tear, fade and desaturation match.
- Palette is exact, with nothing off it.

Against `desktop-layout.html`, layout B:
- Band, cassette left, Now playing above keys, tape log, then rows of tickets. At 800 px and up the tickets drop LMA RADIO and NO REFUNDS and go to 84 px, as B does. Faithful.

Deliberate departures, judged:
- Larger label type (32/19): keep. Caveat runs small and this reads as handwriting on a label.
- 46 px phone keys: keep. Better for a thumb or in a car, with no loss of proportion.
- Regular-weight typed text: acceptable. Hierarchy now comes from size and colour, and Now playing still leads. The exception is `.meta` above.
- 2 columns from 800 to about 924 px: keep. Names read better at 820 than three narrow tickets would.
- Show-page stub 104 px and 26 px name on phone: looks right on paper, unseen in real use. Judge at Task 9.

What a person would object to, in order:
1. "ON THE AIR" in the off-air state (Important 1). Not visible in these shots, but the worst thing on the list.
2. `states-390.png`: empty TAPE LOG and JUST AIRED headings with nothing under them make the no-timeline state look unfinished. The ruled empty label is charming, but stacked empty headings are not. Task 7.
3. `page-320.png`: torn tickets truncate hard, because the tear takes 14% plus padding, e.g. "Camper Van Beetho…", the mockup's own sample name, and "Graffiti's, San Franci…". Worth trying a shallower tear below 360 px (polygon at about 92% and `padding-right` about 10%). Polish, not a blocker.
4. `page-320.png`: a three-line artist name makes the label dominate the cassette. As briefed (wrap), and still tidy. No action needed unless the operator objects at preview.
5. Footer at phone width: the stream URL breaks at its hyphen ("https://listen.lma-/radio.com/…"). Putting `#stream-url` on its own line (`radio.css:291`, `display: block`) keeps it whole at 390. Polish.
6. Notches overpaint the focus ring on plain tickets (visible in the focus render). Trivial.

Inherited from the mockup, not a defect: the right hub sits 8 px off-centre in its tape pack, leaving a dark crescent. A person may notice it at large size in `cassette-og.png`. It matches the approved design, so leave it unless the operator asks.

Art: `cassette-og.png` and `cassette-512.png` are clean, with paper background and an empty ruled label. `icon-180.png` is detailed for its size, but "LMA Radio" and the hubs still read. The ruled lines go faint and it stays recognisable as a cassette. Fine for a home-screen icon.

### Assessment

**Task quality:** Needs fixes

**Reasoning:** The look, harness and structure are solid and the mockups are faithfully ported. Three small fixes are worth making before Task 7 builds on this: a hook for "ON THE AIR", safe-area padding on the wide panel, and a visible focus ring on torn tickets. Each is a line or two.
