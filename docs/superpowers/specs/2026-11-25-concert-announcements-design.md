# Concert announcements: design

Status: draft for review (2026-11-25). Builds on the scheduler spec
(`docs/superpowers/specs/2026-10-25-scheduler-design.md`, "Station IDs and
announcements", "Interstitial audio") and the dynamic-announcement idea agreed
2026-11-07 (transmitter owns what and when; the Mac owns how it sounds).

## Intent

Today a break between shows carries a bare station ID, and only block edges
carry an announcement, which names blocks, never concerts ("Coming up next,
Overnight Variety. Then at 2 Eastern, 11 Pacific, The Music Never Stopped.").
Shawn wants every break to tell the listener what is actually coming:

> You're listening to LMA Radio. Live concert tapes from the Live Music
> Archive. Coming up next, Overnight Variety with Cracker, followed by Ryan
> Adams, a few minutes before midnight Eastern. Then, at 2 Eastern, The Music
> Never Stopped with Dark Star Orchestra.

The text is only knowable once the scheduler has chosen the shows, so it has
to be produced as the plan is written. Voicing must not depend on the Mac
being up at that moment, and when the Mac is unavailable the station must
fall back gracefully to what it does today.

## Decisions made with Shawn

- **Announcements are assembled from pre-voiced pieces**, not voiced as whole
  sentences. A listening spike (2026-11-24/25, Qwen 3 TTS via the `roydemure`
  presenter, files under the session scratchpad) judged stitched pieces
  "not perfect but usable"; whole-sentence reads sound better but would need
  the plan to run hours ahead of render and a fixed-length padded slot.
  Stitching removes both: every piece is voiced long before it can air, and a
  stitched clip's exact length is known at plan time.
- **Pieces are phrase-sized, not word-sized.** "a few minutes before midnight
  Eastern." is one piece. Names never end a piece unpunctuated in a way that
  swallows a final consonant (the spike lost the "s" of "Adams" when the name
  ended a bare piece).
- **Times are approximate phrases**, more precise than "around":
  "a few minutes before midnight", "around quarter past", etc. (buckets below).
- **Eastern only.** No Pacific in the new announcements.
- **Every break** between two shows gets an announcement (not just block
  edges).
- **Tight joins**: the spike's "tight" gaps were preferred over "tighter"
  (subtle) and "loose".
- **Dead air:** never more than 3 consecutive seconds of non-speech without
  bed; the stitched design stays far under it (joins are 0.1-0.5 s).
- **Voice: Qwen** (local mlx_audio on the Mac) in production, so the voicing
  path targets it.

## Goals

1. Every break between two shows plays: station ID, then "Coming up next,
   <block> with <artist>", then (when it qualifies) "followed by <artist>,
   <time phrase>", then (when it qualifies) "Then, at <time>, <next block>
   with <artist>".
2. Everything named on air is what actually airs at that slot.
3. Pieces are voiced on the Mac asynchronously, verified, and reused forever;
   a new artist entering the library gets its pieces days before it can air.
4. Graceful degradation, phrase by phrase, down to today's behaviour when no
   pieces exist.
5. Visibility: `transmitter status`/`schedule` say which pieces are missing.

## Non-goals

- Whole-sentence voicing (possible later upgrade; its length mismatch problem
  is why it is out).
- Venue, city or date in the announcement.
- Pacific (or any second zone) in the new announcements.
- LLM-varied phrasing. Text is deterministic templates.
- Per-block beds, rotating ID texts (later, if wanted).
- Changing how DJ intros/outros inside packages work.

## Anti-goals (failure even if it "works")

- Naming a concert that does not then play, or a time that is noticeably
  wrong. Being a minute or so off a bucket edge is fine (Shawn: "11:11
  being occasionally voiced as 'just after 11' is fine"); that slack is why
  the times are fuzzy.
- Audible dead air over 3 s, clipped word starts, or swallowed word ends
  shipping without detection.
- Any path where the Mac being down stops or delays planning or rendering.
- transmitter importing or invoking emcee (the package/folder contract stays
  the only interface).

## Review mode

Opus mode (two Opus reviewers). On the Pro plan the strict-surface checklist is folded into
the two breadth reviewers' brief instead of a separate strict pair.

## Stakes

This is on-air output for a small in-house station: a bad announcement is
embarrassing, not destructive. No user data is deleted or overwritten. The
**strict surface** is the persisted plan (`plan.jsonl`): rows are append-only
and final, they feed render, the timeline, `aired.jsonl` and rollback. Any
new row field must be tolerated by the oldest safe rollback (see the
transmitter `CLAUDE.md` scheduler paragraph), and a bug must never produce a
plan that render cannot render. Second-strictest: the station root, which
transmitter will now write to (one subfolder only).

## Constraints

- transmitter never imports llama or emcee; runs on hugo (Debian 12, Python
  3.11, ffmpeg 5.1, no MLX). emcee runs on the Mac.
- hugo reads the station root over NFS (`/nfs/media/lma-radio/delivered/`,
  mounted rw), but transmitter's user **cannot write `interstitials/` today**
  (checked 2026-11-25). Setup must grant write on one subfolder.
- The scheduler is pure and append-only; a plan step appends at most
  `max_new` rows; render follows within minutes of planning (the 16-24 h
  lead is between render and air, not between plan and render).
- Station-root writes by transmitter must be atomic (write temp, rename) and
  idempotent.

## Approaches considered

1. **Whole sentences voiced per announcement**, after a planning look-ahead
   of some hours. Best sound. Needs the planner hours ahead of render,
   promises held across that gap, and a fixed-length padded slot so a fallback
   clip doesn't shift later times (fallback clips are shorter: padding risks
   the 3 s dead-air limit). Biggest scheduler change.
2. **Stitched pre-voiced pieces (chosen).** Finite vocabulary voiced days
   ahead; transmitter assembles at plan time with exact known length; no
   padding, no look-ahead deadline. Cost: some stitch audibility (judged
   acceptable).
3. **Hybrid** (pieces as base, whole sentences as upgrade). Reintroduces
   approach 1's length mismatch; deferred.

## Design

### The announcement text

Per break, after show P and before show X (X is the next show):

1. **ID**: the station ID piece.
2. **Next**: "Coming up next, <X's block title>" + "with <X artist>," or
   "with <X artist>." (comma if a further phrase follows, period if not).
3. **Followed** (optional): when the show after X, call it Y, is in the same
   block occurrence as X: "followed by <Y artist>," + "<time phrase for Y's
   actual start>."
4. **Then** (optional): when the first show of the next block occurrence, Z,
   is the show directly after the last show named so far (X, or Y when
   Followed is present), and Z's block is titled and not degraded:
   "Then, at <Z's nominal time> Eastern, <Z's block title>" + "with <Z
   artist>."

So at most three shows are named, and the named shows are always contiguous
in the plan. (Contiguity is what makes Goal 2 cheap; see "Promises".)

If X's block is untitled or degraded, the break carries the ID only, as
today. *(My call.)* A **fill show inside a profile block** (taken from the
open pool, block not degraded) is named under its block like any other:
"The Music Never Stopped with Cracker" (Shawn's choice). This matches the web
player, which groups coming-up shows under the occurrence they air in
(`antenna/public/assets/programs.js` `comingUpGroups`), while each show's own
ticket keeps its own program line.

**Entering vs continuing a block** (Shawn, 2026-11-25): when X is the first
show of its block occurrence, Next is "Coming up next, <block>" + "with
<artist>"; when X continues the block the previous show was in, Next is
"<block> continues" + "with <artist>" ("Overnight Variety continues with
Cracker, followed by Ryan Adams, …"). The artist pieces are shared.

Z's time is the block's **nominal** clock time ("at 2"), as today's
announcements use; Y's time is its **actual** planned start, bucketed.

### Time phrases (Eastern)

Minute offset m of the show's actual start from the nearest-below hour H
(H+1 is the next hour), spoken 12-hour, "midnight"/"noon" for 0/12:

| m | phrase |
|---|---|
| 58-59 or 0-2 (relative to the nearer hour) | "at H" |
| 3-10 | "just after H" |
| 11-19 | "around quarter past H" |
| 20-40 | "around half past H" |
| 41-49 | "around quarter to H+1" |
| 50-57 | "a few minutes before H+1" |

Each phrase ends "Eastern." 6 x 24 = 144 pieces. Bucket edges are my call
and may be adjusted. Shawn ruled the times **loose**: a phrase computed from
a predicted start that later shifts by seconds to a minute or so is fine.

**Y's start is a prediction.** Y starts after X and after the next break
(between X and Y), whose length is not decided when the current break is
planned (it ranges from a bare ID to a full announcement, ~15-20 s apart).
The scheduler predicts that break's length (builder's choice: e.g. assume a
typical full announcement) and picks Y's phrase from the prediction. No
re-check or bucket-edge dropping is needed. Z's "Then, at 2" uses the
nominal clock time and is unaffected.

### Piece inventory

| Piece | Count |
|---|---|
| Station ID (one text, from config) | 1 |
| "Coming up next, <block title>" | one per titled block |
| "<block title> continues" | one per titled block |
| "Then, at <time> Eastern, <block title>" | one per (titled block, nominal start time) |
| "with <artist>," / "with <artist>." / "followed by <artist>," | 3 per artist (291 artists in the delivered library on 2026-11-25, so ~870) |
| time phrases | 144 |

Artist = the manifest's `show.artist`. Spoken forms go through emcee's
pronunciation lexicon as usual. Total on the order of 1,100 pieces: one-time,
overnight on local Qwen; afterwards only new artists or clock edits add
pieces.

### The contract: `interstitials/pieces/`

- transmitter writes `piece-<id>.txt` (UTF-8, the exact text) for every piece
  it needs, where `<id>` is a hash of the text (as `ann-<id>` today). It
  derives the set from the clock (blocks, nominal times), the eligible library
  (artists), the fixed time phrases and the ID text. Written atomically, only
  when missing. It never deletes. *(Stale pieces are harmless; pruning is a
  later convenience.)* When it runs is the builder's call (e.g. on each plan
  step's pool scan, rate-limited); it must not slow or block planning, and a
  write failure is logged and alerted, never fatal to planning.
- emcee voices every `piece-<id>.txt` without a `piece-<id>.mp3` and writes
  the MP3 atomically beside it. A new emcee command (name the builder's call,
  e.g. `emcee pieces <dir>`), run on the Mac on a launchd timer. It does not
  take the station lock (it touches no package) and must coexist with
  `emcee run`.
- **How a piece is voiced (emcee owns this):** dry (no bed), one call (no
  chunking), the house/announcer presenter's voice and backend (config: which
  presenter; today `roydemure` on mlx_audio), lexicon applied, then:
  - **verify**: transcribe (the existing STT verification path) and compare
    to the text with the same normalisation `tts/verify.py` uses; on mismatch
    re-voice, up to a small cap (spike: a swallowed "Stopped" was fixed by one
    re-take, 3/3 re-takes correct);
  - **onset check**: reject a take whose first 50 ms is already speech-level
    (spike: Voxtral clipped "You're"); re-voice;
  - **trim** leading/trailing silence gently (spike values: -60 dB threshold,
    keep ~80 ms lead and ~120 ms tail) and **loudness-normalise** every piece
    to one target, so pieces match each other;
  - after the cap, leave no MP3, record the failure (a sidecar or log the
    builder picks) so `status` can show it, and don't retry it every timer
    tick forever (backoff is the builder's call).
- transmitter treats a piece as present when its MP3 exists, is non-empty and
  is past `[station] quiet_minutes`, like other interstitials.

### Assembly (transmitter, at plan time)

- For a break, transmitter decides the text phrase by phrase (above), keeping
  only phrases whose pieces are all present; then concatenates the pieces with
  the tight gaps (spike: 0.4 s after the ID, ~0.05 s plus the pieces' own
  edges between pieces within a phrase, ~0.15 s after a comma-ending piece;
  the builder tunes) and mixes a bed under the whole clip (one house bed from
  config, with a short lead-in/out fade; spike: bed 20 dB under the voice,
  0.5 s lead-in, 1 s tail).
- The assembled clip is written to transmitter's own workspace on hugo (not
  the station root), keyed by a hash of (piece ids, gaps, bed, gain), and is
  then an ordinary one-clip interstitial piece: analysis, encode and the frame
  store are reused. Its exact frame count is known before the row is
  appended. Whether transmitter assembles to WAV/MP3 via ffmpeg 5.1 or to AAC
  directly is the builder's call.
- **Purge:** an assembled clip is deleted once its break has aired (same
  "has aired" test as plan-row trimming; never one a row in the lead or the
  timeline window still needs). Deletion is always safe because the clip can
  be re-assembled from its pieces.
- Re-validation at render: the assembled clip exists with the same key;
  if not, it is re-assembled from its pieces; if a piece is gone, the existing
  interstitial re-validation path applies (drop and re-plan from the
  boundary).
- Loudness: the assembled clip should land at the same perceived level as
  existing `ann-*`/`id-*` clips and DJ clips (emcee normalises speech to about
  -20 dBFS speech-active); the builder measures and matches.

### Promises (Goal 2)

The break names X, maybe Y, maybe Z, all contiguous. Because the scheduler
appends one row at a time, those shows are not yet in the plan when the break
row is written. Requirement: **the shows that a break names are the shows the
plan then places, in order, at those slots.** The break row records them (the
existing `names` field of `PlanRow` holds occurrence keys today; a field for
the named show slugs is added, tolerated by the rollback floor), and later
plan steps treat pending promises as fixed choices. The time phrase for Y is computed
from a predicted start (see "Time phrases"); it is loose by design.

How the scheduler finds X/Y/Z for a break (running its existing block search
from the break's position, using the known assembled length, with the
run-1/run-2 exact-length pattern) is the builder's call, within the existing
rules (window landing, rotation rules, compromise order).

**Render checks the named shows before encoding a break.** Today
`render_step` encodes in ascending order and re-validates a show only when its
own first segment is due, so a break would normally be encoded before the show
it names is checked, and `replan_from` would then keep the break. So: before
encoding a break row's first segment, render re-validates the shows the break
names (as far as they are in the plan); if one fails, the plan is dropped and
re-extended from the break itself (the existing skip path, applied at the
break). A named show re-planned in place with a new length (emcee re-voice)
needs nothing: the name stays true and times are loose. If a named show fails
after its break is already encoded, the break stays (no deleting rendered
segments): count it, show it in `status`, alert once, ungated. *(My call.)*

### Fallback ladder (per break)

1. Full assembled announcement with every qualifying phrase.
2. Missing optional phrases (Followed, Then) dropped; missing artist piece
   for X: "Coming up next, <block>." (period variant of the block piece is not
   needed if the block piece is voiced ending without punctuation and the
   assembly ends there; builder's call).
3. ID piece missing but Next present: assemble without the ID, or use an
   existing `id-*.mp3` before it; builder's call.
4. No usable Next phrase: today's logic exactly (the `next`/`later` `ann-*`
   clips at block edges, station ID elsewhere, then a gap).

So with the Mac gone for good, the station behaves as it does today.

### Existing announcements

- The `next`/`later` placement logic and `ann-*` clips stay as rung 4. The
  `transmitter announcements --export` workflow stays for them.
- Nothing else about station IDs changes.

### Visibility

- `transmitter status`: pieces needed/present/failed counts; breaks in the
  next 24 h by rung; broken promises.
- `transmitter schedule`: per break, the text that would air (or the rung).
- emcee side: the new command prints what it voiced, re-took and failed.

### Setup (operator, once)

- On the NAS, create `interstitials/pieces/` writable by hugo's transmitter
  user and the Mac's user (exact uid/permissions per the NAS).
- Config: transmitter `[announce]` gains the ID text, the bed file, gaps (if
  configurable), and an on/off switch defaulting off until the first pieces
  are voiced; emcee config names the announcer presenter.
- launchd job on the Mac for the voicing command.

## Left to the builder

- Command names, config key names, sidecar formats.
- When transmitter writes the needed-piece list and how often.
- The scheduler mechanics for choosing and holding promises.
- Exact gaps, bed gain, trim parameters, loudness target (measure).
- Bucket edges; how Y's start is predicted.
- Rollback-floor compatibility proof for the new row field.

## Open premises to verify in the plan's first task

- Qwen re-take rate across ~1,100 pieces (spike saw 1 bad take in ~17).
- Whether STT normalisation handles names (e.g. "moe.", "STS9") or needs a
  per-piece expected-transcript override.
- Assembly + analysis time on hugo per break (must not slow a plan step
  noticeably).
