# Playout phase 4: the player — design

**Date:** 2026-11-01
**Scope:** `antenna/public/`, `antenna/templates/`, `antenna/scripts/`, the
clock's `index.html` step in `antenna/src/`, and `packages/transmitter`'s show
page rendering (`site.py`). llama, emcee and herder are untouched.
**Parent:** `docs/superpowers/specs/2026-10-09-playout-design.md` ("Full
antenna", "antenna", "Player"). This document replaces the parent's phase 4
where they differ. The parent still governs the clock, the guard and publishing.
**Review mode:** Opus (operator, 2026-11-01).
**Mockups:** `docs/superpowers/2026-11-01-player-mockups/` (open in a browser;
each is an HTML fragment with its own styles, content from the live station).
In `cassette-tickets.html` the approved ticket is the right-hand "Concert
ticket"; in `desktop-layout.html` the approved layout is B.

## Intent

The current page is a placeholder. The station is about to be shared with other
people, so it needs a page that looks like something and explains itself, and it
needs to work in the car. This rebuilds the listener-facing pages from scratch.

Success: a stranger who opens a shared link understands what this is, sees what
is on and what's next, presses Play, and gets a page they'd want to leave open.
The operator can drive with it, read the show and song on the car display, and
not have to touch it when the signal drops.

## Stakes

Nothing here can lose data or take the station off the air: the stream is
produced elsewhere and a bad page is rolled back by redeploying. The risk is
spend and public embarrassment.

**Strict surfaces:**
- **Spend.** Nothing billed per listener, the parent's rule. Every new listener
  request must be a static object served from the edge cache. A reconnect loop
  must not be able to turn one listener into a request storm. The clock's added
  work is bounded (see "Link previews").
- **Untrusted text.** Titles, venues, lineage and briefings come from
  archive.org uploaders and an LLM. All of it reaches the page as text: escaped
  on the server, `textContent` in the browser, never as HTML.

Everything else is judged proportionately.

## Goals

- A vintage page built around a cassette, with concert-ticket stubs.
- What's playing now, with the show and the song.
- Recently played tracks and shows; upcoming shows (never upcoming tracks).
- Every show leads to its archive.org item, through its show page.
- Show and song on the phone's lock screen and the car display when paired.
- Link previews good enough to share.
- The player recovers from dropouts by itself.

## Non-goals

- The embeddable player (`embed.html`): deferred by the operator.
- An about page, and a schedule further out than the published data (about a
  day either way).
- A per-show picture. One fixed cassette picture for now.
- Any new scheduler or render behaviour.

## Anti-goals

- Looking like the Internet Archive, or implying any connection to it. "Archive"
  is a mood (tapes, labels, stubs), not their branding.
- Rainbow stripes or psychedelic colour. The palette is the mockups': cream paper,
  tape brown, oxblood, a muted teal.
- Any listener request that a Worker serves or that bypasses the cache.

## The main page

Layout: phone is one column in the order below; on a computer the tape sits in a
band across the top, with rows of tickets beneath (layout B). The operator
judges against the mockups; exact sizes are the builder's.

- **Header:** "LMA Radio" and the line "Live concert tapes from the Live Music
  Archive, around the clock."
- **Cassette:** the show on air, hand-lettered on its label: artist, venue and
  city, concert date. The hubs turn only while audio is playing, and not at all
  under `prefers-reduced-motion`. With nothing on air the label carries the
  station name.
- **Play and Stop keys,** styled as tape-deck keys. Play is the large one. Both
  are real buttons. Radio semantics are unchanged: Play always joins live.
- **Now playing:** the song title, or the DJ segment during a clip.
- **Tape log:** recent songs in the current show with their air times, newest
  first. DJ clips are left out.
- **Coming up:** the remaining shows in the timeline, as concert tickets (see
  the mockup): the stub carries the listener's day and air time and "GEN ADM";
  the main part carries "LMA RADIO PRESENTS", the artist, the venue and city, the
  concert date. Perforated line, notches and paper texture are what make it read
  as a ticket, so they stay.
- **Just aired:** past shows from the timeline as torn, faded tickets, newest
  first.
- **Every ticket** links to that show's page.
- **Time zone:** all times are the listener's, and the page says which zone in
  words near the schedule ("Times shown in Eastern Time"), from the browser.
- **Footer:** the Live Music Archive credit and "Non-commercial; no ads", and the
  stream URL for VLC and apps, kept small.

The page shows all of this before Play is pressed. That changes the parent's rule
that `timeline.json` is fetched only while playing: it is now fetched on load and
refreshed about every 3 minutes while the page is visible or audio is playing
(a locked phone in the car is "hidden" and still needs it), and also fetched when
Play is pressed from the lock screen or car. Stopped and hidden, it never fetches.
It is a cached static object (`max-age=30`), so this stays within the spend rule.

Position in the timeline: while playing, the playback position (as now); while
stopped, the wall clock.

Long lists are the builder's call, as long as "Coming up" can reach everything
published and the page doesn't become an endless scroll on a phone.

## Station states

The cassette and the Now playing line say what is happening, in plain words.

| State | Cassette | Text |
|---|---|---|
| Playing | turning | song |
| Stopped | still | the show on air, "press Play" |
| Between shows (no timeline entry) | still label: station name | station name |
| Reconnecting | still | "Reconnecting…" |
| Off the air | still | "The station is off the air." and a Try again button |

The blocked `index.html` (`offair.html`) gets the same look as far as it can: no
player, no scripts, its styles inline, and system fonts in place of the hosted
ones. While blocked the kill-switch rule serves only `/`, `/index.html`,
`/offair.html` and `/style.css`, so `/assets/` returns 403. That rule does not
change: it is the spend stop.

## Car and lock screen

Use the Media Session API, on both native HLS and hls.js:
- title: the song, or the DJ segment during a clip; the show name between songs if
  there is no file;
- artist: the band;
- album: venue and concert date;
- artwork: the fixed cassette picture, at the sizes the API asks for.

Metadata updates when the song or show changes. Handlers: `play`, `pause`, `stop`.
`pause` from the car means stop, and `play` rejoins live, matching the page. No
seek or skip handlers: this is radio.

If the phone pauses the audio on its own (a call, Bluetooth disconnecting), that
counts as Stop and it stays stopped (operator): the listener presses Play. A phone
must never start playing aloud by itself after the car is switched off.

What a given car shows is up to the car and the phone. The target is the
operator's iPhone and car.

## Recovery

Today any fatal hls.js error or native `error` puts the player into a dead
"unavailable" state until someone presses Try again. Replace that:

- While the listener wants to be playing, any failure that isn't definitely
  off-air retries from the live edge, with increasing delays up to about 30 s and
  jitter, until it recovers or the listener presses Stop. This includes a stall
  after a playlist that stepped backwards, which is the backlog item: no special
  handling of the sequence numbers, just the same recovery.
- Definite off-air stays as it is now: a 403 or `#EXT-X-ENDLIST`, with the existing
  two-verdict probe. It stops, shows the notice and does not reconnect.
- A retry restarts with the same `<audio>` element, so that an iPhone in a pocket
  keeps permission to play. If the browser still refuses, the page falls back to
  the Try again button.
- At most one retry runs at a time, and a retry never issues requests the normal
  player wouldn't. Everything it fetches is a cached object.

## Show pages

Each ticket opens `show/<slug>.html`, an open cassette case (`show-page.html`):

- A full-width ticket with the concert date on its stub, the artist, the venue and
  city, and a button "Hear the full tape on archive.org".
- Setlist on the tape's card, grouped by set where the show has more than one.
- The briefing as "Liner notes": the operator approved publishing it as written,
  with its headings shown as headings and its `- ` lines as bullet lists, except
  the "Cautions for the scriptwriter" section, which is left off (operator). The
  `# Briefing: …` title line is dropped and the raw marks no longer appear.
  Today's page prints them. `notes/<slug>.json` keeps the whole briefing, as now.
- Air times in the listener's zone, labelled as on the main page, read from
  `notes/<slug>.json` as now. Taper's lineage.
- Small, in the bottom corner, visible: "Show notes are AI generated and may
  contain mistakes."
- A link back to the station.

A title that already ends in a segue mark (`>` or `->`) doesn't get a second one.
The tape log shows the title as `timeline.json` carries it, tidied to the same
spacing; a segue held only in the notes' flag doesn't appear there, because the
log shouldn't make a second fetch for it.

Rendering stays in `site.py` from `antenna/templates/show.html`. Only a small,
fixed Markdown subset is handled (headings, paragraphs, bullets); everything is
escaped.
`notes/<slug>.json` keeps its shape.

**Existing pages:** the publisher re-renders only shows in the timeline window, so
older `show/*.html` stay on the old template and keep using the old `style.css`,
which stays in place, unchanged. The first publish after deploy re-writes every
show in the window, a one-off of about 60 PUTs within the existing publish budget.

## Link previews

- **Station link:** `og:title` is the station and the show on air; the description
  is the newcomer line; the image is the cassette picture.
- **Show link:** `og:title` is the artist and date; the description is the first
  real paragraph of the notes (today it is the `# Briefing` line); the same image.
  `og:image` needs an absolute URL: the Worker gets a committed `SITE_URL` var
  (`https://listen.lma-radio.com`, already public), and show pages use
  transmitter's `site_url`, omitting the image when that is unset.

The station preview means the clock rewrites `index.html` at show boundaries, as
the parent intended and never built. `reconcileIndex` already writes only when the
body's hash changes. It gains one R2 read of `timeline.json` per invocation
(about 44k Class B a month, well inside the allowance) to pick the show on air, and
about 30 writes a day. If that read fails or the file is unusable, the page is
written without a show, and the clock carries on: this step must never disturb
the playlist. The show text is escaped. While blocked, the off-air page wins, as
now.

## Home screen

On an iPhone, "Add to Home Screen" must give a proper quasi-app: its own icon and
name, opening full-screen with no browser bars, laid out around the notch and home
bar, with the page's colours in the status area. That means a web app manifest and
icons under `/assets/`, the Apple meta tags, and safe-area handling. Links to show
pages stay inside the app window, and each show page has its way back. The
archive.org link opens outside it.

No service worker and no offline mode: it would add nothing for a live stream and
could serve a stale page or player.

## How it's built

- Plain HTML, CSS and JavaScript modules, as now. No framework or build step
  beyond `npm run pages`. hls.js stays.
- Fonts are hosted with the site (no third-party requests): an openly licensed
  handwriting face for the label, plus a typewriter and a serif face. The
  fonts and pictures join `deploy-assets.mjs`.
- All new JS, CSS, fonts and pictures live under `/assets/` with new names, and
  the old `player.js`, `nowplaying.js` and `style.css` stay published. Those cache
  for an hour, so this keeps a new page from loading an old script at launch and
  makes rollback clean. Later changes to those files can mismatch for up to an
  hour; that's accepted for this station.
- The cassette is drawn in CSS or SVG so it stays sharp and can animate. The
  fixed picture is a committed image file.
- Pure logic stays in `nowplaying.js` or a sibling, unit-tested. Vitest for the
  helpers and the clock step. pytest for `site.py`, on Python 3.11 as usual.
  A Playwright smoke test of the page against canned files, as the parent planned.

**Preview:** before go-live the operator judges the real page from an unlisted
copy under `/assets/preview/` in the production bucket, playing the real stream
(all cached objects, removed afterwards). The early iPhone restart test runs from
there too, so it's a planned pause near the start of the work.

**Deploy:** `npm run deploy:assets` first, then `npx wrangler deploy` (the clock and
bundled pages), and a pull and restart on hugo for the show template. The page
needs no new published field.

**Manual checks by the operator:** iPhone lock screen, the car display, a dropout
on the road (airplane mode for a minute with the screen locked), all of these from
the home-screen version as well as Safari, and Chrome on a computer.

## Left to the builder

Sizes, spacing, type choices within the mood, exact backoff numbers, how long the
lists run, the order of work.

## Unverified

- Whether an iPhone lets a page restart audio by itself after a long dropout with
  the screen locked. If it doesn't, recovery there ends at Try again, and the
  plan should find out early with a short test.
- Whether audio, background play, the lock screen and the car display behave the
  same when opened from the home screen as in Safari. The same test checks it, and
  if they don't, the home-screen version is what has to be fixed or dropped.
- Whether timers keep running on a locked iPhone well enough to update the car
  display at each song change. The same test checks it.
- What the operator's car actually shows from Media Session.
