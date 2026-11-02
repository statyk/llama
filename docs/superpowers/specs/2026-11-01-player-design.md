# Playout phase 4: the player — design

**Date:** 2026-11-01
**Scope:** `antenna/public/`, `antenna/templates/`, `antenna/scripts/`,
`packages/transmitter`'s show page and notes rendering (`site.py`), and
`docs/playout-setup.md`, whose off-air expectations and asset list change. The
clock's code is unchanged; `npm run pages` regenerates the bundled `src/pages.ts`.
llama, emcee and herder are untouched.
**Parent:** `docs/superpowers/specs/2026-10-09-playout-design.md` ("Full
antenna", "antenna", "Player"). This document replaces the parent's phase 4
where they differ. The parent still governs the clock, the guard and publishing.
**Review mode:** Opus (operator, 2026-11-01).
**Status:** approved by the operator 2026-11-01 (after two review rounds).
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
  must not be able to turn one listener into a request storm.
- **Untrusted text.** Titles, venues, lineage and briefings come from
  archive.org uploaders and an LLM. All of it reaches the page as text: escaped
  on the server, `textContent` in the browser, never as HTML. A link is emitted
  only for an `https://archive.org/` URL; otherwise the button is left out. Ticket
  links are built from the encoded slug, not taken from the file.

Everything else is judged proportionately.

## Goals

- A vintage page built around a cassette, with concert-ticket stubs.
- What's playing now, with the show and the song.
- Recently played tracks and shows; upcoming shows (never upcoming tracks).
- Every show leads to its archive.org item, through its notes.
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
- **Cassette:** the show on air, hand-lettered on its label: the artist on one
  line above the window (a long name steps down in size, then ends in an ellipsis),
  the venue and city with the concert date on one line below it (the venue gives
  way, the date stays). The hubs turn only while audio is playing, and not at all
  under `prefers-reduced-motion`. With nothing on air the label carries the
  station name. It keeps a real cassette's 100.4 x 63.8 proportions at every width,
  with the paper wrapping the window, four holes and a centre screw along the bottom edge, and the hubs about the middle of the shell's
  height, 42.5 mm apart.
  The cassette's scaling uses container units (iOS 16, Chrome 105, Firefox 110); older browsers get a plain-sized fallback.
- **Play and Stop keys,** styled as tape-deck keys. Play is the large one. Both
  are real buttons. Radio semantics are unchanged: Play always joins live. During a session Play
  waits for an HTTP answer first, and with no answer leaves the element alone.
- **Now playing:** the song title, or during a clip the clip's title with its
  parenthetical removed ("DJ intro", "DJ outro"). While stopped with a show on air it
  reads the constant "Press Play to listen." (no artist, so it never wraps or shifts the
  page on Play; the cassette carries the artist). A quiet "Show notes" link under it
  opens the on-air show's notes in the panel, and is hidden with no show on air.
- **Tape log:** recent songs in the current show with their air times, newest
  first, continuing into the previous show when the current one has just started.
  DJ clips are left out.
- **Coming up:** the remaining shows in the timeline, as concert tickets (see
  the mockup): the stub carries the listener's day and air time and "GEN ADM";
  the main part carries "LMA RADIO PRESENTS", the artist, the venue and city, the
  concert date. Perforated line, notches and paper texture are what make it read
  as a ticket, so they stay.
- **Just aired:** past shows from the timeline as torn, faded tickets, newest
  first.
- **Every ticket** is a link to that show's page, and tapping it opens the show's
  notes in a panel over the player (see "Show notes panel").
- **Time zone:** all times are the listener's, and the page says which zone in
  words near the schedule ("Times shown in Eastern Time"), from the browser.
- **Concert dates** are calendar strings, formatted from the string and never
  through `Date`, so they never shift by time zone. A missing or partial date (day
  `00`) prints as stored. Blank fields are left out, never printed as "null".
- **Footer:** the Live Music Archive credit and "Non-commercial; no ads", and the
  stream URL for VLC and apps, kept small.

The page shows all of this before Play is pressed. That changes the parent's rule
that `timeline.json` is fetched only while playing: it is now fetched on load and
refreshed about every 3 minutes while the page is visible or audio is playing
(a locked phone in the car is "hidden" and still needs it), and also fetched when
Play is pressed from the lock screen or car. Stopped and hidden, it never fetches.
It is a cached static object (`max-age=30`), so this stays within the spend rule.

Position in the timeline: while playing, the playback position (as now); while
stopped, the wall clock. "Just aired" and the tape log come from `shows[]` against
this position, never from `recent`, which can be hours stale.

Long lists are the builder's call, as long as "Coming up" can reach everything
published and the page doesn't become an endless scroll on a phone.

## Station states

The cassette and the Now playing line say what is happening, in plain words. In
every state the hubs turn only while audio is playing.

| State | Cassette | Text |
|---|---|---|
| Playing | show on the label | song |
| Stopped | show on the label | "Press Play to listen." (the artist is on the cassette) |
| Between shows (no timeline entry: station IDs, announcements, the fallback loop) | label: station name | station name |
| Loading or no timeline | label: station name | station name, and the schedule area says so plainly |
| Reconnecting | as Stopped | "Reconnecting…" |
| Gave up reconnecting | as Stopped | "Lost the stream." and a Try again button |
| Off the air | label: station name | "The station is off the air." and a Try again button |
| Play refused by the browser | as Stopped | "Playback was blocked." and a Try again button |
| Unsupported browser | as Stopped | "This browser can't play the stream; open the stream URL in VLC." |

The blocked `index.html` (`offair.html`) gets the same look as far as it can: no
player, no scripts, its styles inline, and system fonts in place of the hosted
ones. While blocked the kill-switch rule serves only `/`, `/index.html`,
`/offair.html` and `/style.css`, so `/assets/` returns 403. That rule does not
change: it is the spend stop. A cached player page briefly losing its styling
during a block is accepted.

The blocked page also has a plain link to `/` and
`<meta http-equiv="refresh" content="300">`, because a home-screen window has no
reload button.

## Car and lock screen

Use the Media Session API, on both native HLS and hls.js:
- title: the same text as Now playing; the show name between songs if there is no
  file;
- artist: the band;
- album: venue and concert date;
- artwork: the fixed cassette picture, one square PNG, 512 px.

In any state with no audio, or with no show on air, the title is the station name
and no stale song remains.

Metadata updates when the song or show changes, driven by the page's timer: the
early test measured it running at 6 s on a locked phone while audio is in use, so
the display can lag a song by a few seconds, which is accepted.
`mediaSession.playbackState` is set to match the player. Handlers: `play`, `pause`,
`stop`. `pause` from the car means stop, a normal teardown, and `play` rejoins live,
matching the page. Play still reaches the page after a teardown. No seek or skip
handlers: this is radio.

If the phone pauses the audio on its own (a call, Bluetooth disconnecting), that
counts as Stop and it stays stopped (operator): the listener presses Play. A phone
must not start playing aloud by itself after the car is switched off. The one
exception is a dropout already under way, which the 10-minute limit in "Recovery"
bounds.

What a given car shows is up to the car and the phone. The target is the
operator's iPhone and car.

**Limitation (measured, iOS):** after Stop or a Bluetooth disconnect iOS sleeps the
page within about a minute, so a car or lock-screen Play made after that waits until
the phone is unlocked. Play within seconds of stopping works. In the home-screen app, once
stopped, lock-screen and car Play reach the page but audio does not load until the app
is opened, where it then starts. A second station's home-screen app does the same, which
points to iOS.

## Recovery

Today any fatal hls.js error or native `error` puts the player into a dead
"unavailable" state until someone presses Try again. Replace that:

- **A failure** means the playback position has stopped advancing. A fatal hls.js
  error while buffered audio is still playing restarts nothing until the position
  stalls. On native HLS, wait about 30 s of stall, or an `error` event, before
  tearing down, which gives the iPhone's own player its chance first; iOS recovers
  short stalls by itself, about 5 s measured, but not one of about 3 minutes.
  `stalled` events are not a signal: a healthy iPhone fires one about every 11 s.
  `waiting` is. Recovered means the position advanced again, never `playing` or a
  resolved `play()`: on an iPhone both happened with the position frozen for 23
  minutes.
- **Retries:** while the listener wants to be playing, any failure that isn't
  definitely off-air retries from the live edge, but only after a probe of
  `live.m3u8` gets an HTTP response. While the network is unreachable the element is
  left alone and probing continues about every 15 s; a failed fetch costs nothing.
  Measured on the iPhone: a teardown while offline ended the audio session and iOS
  froze the page within seconds, while an element left alone kept the page alive
  through a locked stall of at least 5 min 36 s, and the locked page could then
  restart audio. The test is the fetch's result, never `navigator.onLine`, which
  lagged the network by seconds. This includes a stall after a playlist that stepped
  backwards, which is the backlog item: no special handling of the sequence numbers,
  just the same recovery. Delays between restarts start at about 5 s and rise to
  about 30 s with jitter, for a stream that restarts and then fails again. The delay
  resets only after about 60 s of advancing playback, never on `playing`. These
  values may be tuned in the plan.
- **Giving up** (operator): after 10 minutes without audio, counted from the last
  advancing playback, recovery stops, shows Try again and stays stopped. This is so
  the phone doesn't start playing aloud after the car is off. Every retry checks
  the wall clock against this limit immediately before any `play()`, so a page
  whose timers were frozen while locked gives up rather than starting audio late.
  A shorter window remains, and that is accepted.
- **Definite off-air** means what it does now: a 403 or `#EXT-X-ENDLIST` on two
  probes of `live.m3u8`, or `ended`, plus hls.js's immediate signals (a 403, an
  empty level, a playlist no longer live). It stops, shows the notice and does not
  reconnect. Each failure probes before restarting, and that probe always has a
  time limit. Unlike today, the verdict count survives retries and inconclusive
  probes, and resets only on real progress. Position tracking is cleared on retry,
  and the first position after a retry is a baseline, not progress. So an iPhone,
  which gets no status code, reaches the off-air notice in a bounded time.
- **A dropout or a phone pause:** a `pause` counts as a phone-initiated Stop only
  when no stall was under way, and a `pause` from the player's own teardown is
  ignored. The early test confirms this rule: it logs the order of `pause`,
  `waiting`, `stalled`, `error` and `ended` on a locked iPhone during a dropout.
- **The restart** uses the same `<audio>` element, so that an iPhone in a pocket
  keeps permission to play, in the full form: `src` removed and set, the same as Stop
  then Play. A browser refusal ends at Try again. The retry sequence
  never starts audio after the listener's Stop.
- **Limits:** at most one retry runs at a time, and a retry never issues requests
  the normal player wouldn't. Everything it fetches is a cached object. A retry does
  not force a `timeline.json` fetch.

## Show notes panel

Tapping a ticket must not stop the music (operator). It opens the show's notes in a
panel that slides up over the player, on phone, computer and home-screen app alike.
The audio keeps playing and the page's hubs and controls keep working. Closing it,
by its own close control or the browser's back gesture, returns to the player.
Opening it adds a history entry on the same URL, and the close control goes back
through that entry, so a reload never lands on another page and a stale entry never
leaves the player. A page load never opens the panel.

Tickets stay real links to `show/<slug>.html`, so a new-tab open, a shared link and
a crawler all work, and a modified click is left to the browser. A plain tap opens
the panel at once with a loading state, then fetches the notes. If they can't be
loaded or are the older shape (no `sections`), the panel shows a plain new-tab link,
"Open the show page". An empty `sections` is the new shape and reads "No notes yet."

The panel has the content of the show page below, including the AI disclaimer, with
a way to share that show (its `show/<slug>.html` link). It has no link back to the
station, since its close control does that job. The archive.org link always opens
in a new tab or outside the app, never in the player's window.

## Show pages

`show/<slug>.html` stays as the page for shared links, an open cassette case
(`show-page.html`):

- A full-width ticket with the concert date on its stub, the artist, the venue and
  city, and a button "Hear the full tape on archive.org".
- Setlist on the tape's card, grouped by set where the show has more than one.
- The briefing as "Liner notes": the operator approved publishing it as written,
  with its headings shown as headings and its `- ` lines as bullet lists, except
  the "Cautions for the scriptwriter" section, which is left off (operator). The
  `# Briefing: …` title line is dropped and the raw marks no longer appear.
  Today's page prints them. The cautions stay in `notes/<slug>.json`'s `briefing`
  and on old pages; the operator was told and accepted that.
- Air times in the listener's zone, labelled as on the main page, read from
  `notes/<slug>.json` as now. Taper's lineage.
- Small, in the bottom corner, visible: "Show notes are AI generated and may
  contain mistakes."
- A link back to the station.

**Titles:** a trailing `>` or `->` becomes " >", in the tape log and the setlist
alike. The setlist adds a segue mark from the notes' flag only to a title without
one. The log shows the title as `timeline.json` carries it, so a segue held only in
the notes' flag doesn't appear there: the log shouldn't make a second fetch for it.

**One parser:** rendering stays in `site.py` from `antenna/templates/show.html`.
`site.py` turns the briefing into structured sections and publishes them as a new
`sections` field in `notes/<slug>.json`, shaped like `[{"heading": str|null,
"blocks": [{"p": str} | {"ul": [str]}]}]`; `briefing` stays in the file. The static template and the panel both render from
it. The template's output is escaped and the panel uses `textContent` only, never
`innerHTML`. Show-page JavaScript lives under `/assets/`, not inline in `show.html`,
because `string.Template` substitutes `$`.

The parser is line-based: a heading can be followed by text with no blank line. Inline
`**` is stripped to plain text, and the cut runs from a case-insensitive `## Cautions`
heading to the end. Headings vary by show (one per set, an optional encore), so the
parser keeps whatever it finds. Measured across 3,650 briefings on 2026-11-01:
all carry the Cautions heading, it is always the last section, and 61 carry inline
`**`. The heading text is llama's, and transmitter can't import llama, so a test here
pins the literal.

**Existing pages:** the publisher re-renders only shows in the timeline window, so
older `show/*.html` stay on the old template and keep using the old `style.css`,
which stays in place, unchanged. The first publish after deploy re-writes every
show in the window, a one-off of about 60 PUTs within the existing publish budget.

## Link previews

- **Station link:** fixed: the station name, the newcomer line and the cassette
  picture, all literal in the bundled `public/index.html`, with a literal absolute
  image URL (`https://listen.lma-radio.com/...`). This replaces the parent's
  per-show `index.html` rewrite. `reconcileIndex` keeps working unchanged: a new
  bundled page is written within a minute of `wrangler deploy`.
- **Show link:** `og:title` is the artist and date; the description is the first
  non-heading text of the notes; the same image. `og:image` needs an absolute URL:
  show pages use transmitter's `site_url`, omitting the image when that is unset.

## Home screen

On an iPhone, "Add to Home Screen" must give a proper quasi-app: its own icon and
name, opening full-screen with no browser bars, laid out around the notch and home
bar, with the page's colours in the status area. That means a web app manifest and
icons under `/assets/`, the Apple meta tags, and safe-area handling. Show notes open
there in the panel, and the archive.org link opens outside the app.

No service worker and no offline mode: it would add nothing for a live stream and
could serve a stale page or player.

## How it's built

- Plain HTML, CSS and JavaScript modules, as now. No framework or build step
  beyond `npm run pages`. hls.js stays.
- Fonts are hosted with the site (no third-party requests): an openly licensed
  handwriting face for the label, plus a typewriter and a serif face. The
  fonts and pictures join `deploy-assets.mjs`.
- All new JS, CSS, fonts and pictures live under `/assets/` with new names, and
  the root `player.js`, `nowplaying.js` and `style.css` stay published, frozen
  byte-for-byte. Those cache for an hour, so this keeps a new page from loading an
  old script at launch and makes rollback clean. Later changes to the new files can
  mismatch for up to an hour; that's accepted for this station.
- New code uses root-absolute URLs (`/live.m3u8`, `/timeline.json`, `/show/...`),
  since the preview lives elsewhere.
- The cassette is drawn in CSS or SVG so it stays sharp and can animate. The
  fixed picture is a committed image file.
- New logic gets new source files mapped to `/assets/`, and tests point there. Pure
  logic is unit-tested. Vitest for the helpers. pytest for `site.py`, on Python 3.11
  as usual. A Playwright smoke test of the page against canned files, as the parent
  planned, on a browser that can play AAC (bundled Chromium may not).

**Preview:** before go-live the operator judges the real page from an unlisted
copy under `/assets/preview/` in the production bucket, playing the real stream
(all cached objects, removed afterwards). It has its own manifest with `start_url`
and `scope` under `/assets/preview/`, is opened by full filename, and is uploaded
with a short cache time so each round of fixes shows up. The plan names its removal
step. The early iPhone test runs from there, so it's a planned pause near the start
of the work. The operator judges the whole page there later, panel included, once
hugo is publishing `sections`.

**Deploy,** in this order, with the old player live until the last step:
1. `npm run deploy:assets`.
2. A pull and restart on hugo for the show template and `sections`, the one new
   published field. Nothing on the old player reads either. The new static show
   pages go public here, as publishing reaches them: up to about 4 hours, because
   publishing only runs when new segments go up.
3. The operator judges the preview, panel included.
4. `npx wrangler deploy` (the bundled pages). This is go-live.

**Manual checks by the operator:** iPhone lock screen, the car display, a dropout
on the road (airplane mode for at least 4 minutes with the screen locked), all of these from
the home-screen version as well as Safari, and Chrome on a computer.

## Left to the builder

Sizes, spacing, type choices within the mood, how long the lists run, the order of
work.

## Unverified

The early iPhone test answered most of what this section listed; the results and
decisions are in `docs/superpowers/2026-11-01-player-probe.md`. Still open:

- Whether a restart recovers a stall after a backwards playlist step: it can't be
  produced on demand, so it is left to the road.
- Whether audio, background play, the lock screen, the car display, the back swipe
  and archive.org behave the same when opened from the home screen as in Safari. If
  they don't, the home-screen version is what has to be fixed or dropped.
