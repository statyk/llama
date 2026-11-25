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
   a new artist entering the library usually gets its pieces before it can
   air.
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
transmitter `CLAUDE.md` scheduler paragraph, and "The break row" below), and
a bug must never produce a plan that render cannot render. Second-strictest:
the station root, which transmitter will now write to (one subfolder only).

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
- The clock file and `config.toml` are both strict (`extra="forbid"`), so new
  settings cannot go in either without breaking a rollback (see "Config").

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
   "with <X artist>." (comma only when Followed comes next; period
   otherwise, including when only Then follows, so it never reads "with
   Cracker, Then, ...").
3. **Followed** (optional): when the show after X, call it Y, is in the same
   block occurrence as X: "followed by <Y artist>," + "<time phrase for Y's
   actual start>."
4. **Then** (optional): when the first show of the next block occurrence, Z,
   is the show directly after the last show named so far (X, or Y when
   Followed is present), Z's block is titled and not degraded, and Z's
   predicted start is inside its window (the truth condition today's `later`
   announcements use): "Then, at <Z's nominal time> Eastern, <Z's block
   title>" + "with <Z artist>."

So at most three shows are named, and the named shows are always contiguous
in the plan. (Contiguity is what makes Goal 2 cheap; see "Promises".)

If X's block is untitled or degraded, the break falls to today's logic
(the last rung of the fallback ladder), so an untitled block's last boundary
before a titled one still gets its `later`. A **fill show inside a profile
block** (taken from the open pool, block not degraded) is named under its
block like any other: "The Music Never Stopped with Cracker" (Shawn's
choice). This matches the web player, which groups coming-up shows under the
occurrence they air in (`antenna/public/assets/programs.js` `comingUpGroups`),
while each show's own ticket keeps its own program line.

**Entering vs continuing a block** (Shawn, 2026-11-25): when X is the first
show of its block occurrence, Next is "Coming up next, <block>" + "with
<artist>"; when X continues the block the previous show was in, Next is
"<block> continues" + "with <artist>" ("Overnight Variety continues with
Cracker, followed by Ryan Adams, …"). The artist pieces are shared.

Z's time is the block's **nominal** clock time ("at 2"), as today's
announcements use; Y's time is its **actual** planned start, bucketed.

### Time phrases (Eastern)

H is the hour at or below the show's actual start, and m the minutes past
it; hours are spoken 12-hour, "midnight"/"noon" for 0/12:

| m | phrase |
|---|---|
| 0-2 | "at H" |
| 3-10 | "just after H" |
| 11-19 | "around quarter past H" |
| 20-40 | "around half past H" |
| 41-49 | "around quarter to H+1" |
| 50-57 | "a few minutes before H+1" |
| 58-59 | "at H+1" |

Each phrase ends "Eastern." 12-hour labels give 13 distinct hour words (1-11,
midnight, noon), so 6 phrases x 13 = 78 pieces. "Eastern" is a fixed literal
(Shawn: Eastern only); it does not use the clock's `announce.zones`. Bucket
edges are my call and may be adjusted. Shawn ruled the times **loose**: a
phrase computed from a predicted start that later shifts by seconds to a
minute or so is fine.

**Y's start is a prediction.** Y starts after X and after the next break
(between X and Y), whose length is not decided when the current break is
planned (it ranges from a bare ID to a full announcement, ~15-20 s apart).
The scheduler predicts that break's length (builder's choice: e.g. assume a
typical full announcement) and picks Y's phrase from the prediction. No
re-check or bucket-edge dropping is needed. Z's "Then, at 2" uses the
nominal clock time; Z's predicted start is used only for the window check.

### Piece inventory

| Piece | Count |
|---|---|
| Station ID (one text, from config) | 1 |
| "Coming up next, <block title>" | one per titled block |
| "<block title> continues" | one per titled block |
| "Then, at <time> Eastern, <block title>" | one per (titled block, nominal start time) |
| "with <artist>," / "with <artist>." / "followed by <artist>," | 3 per artist (291 artists in the delivered library on 2026-11-25, so ~870) |
| time phrases | 78 |

Artist = the manifest's `show.artist`. Spoken forms go through emcee's
pronunciation lexicon as usual. Total on the order of 1,000 pieces: one-time,
overnight on local Qwen; afterwards only new artists or clock edits add
pieces.

### The contract: `interstitials/pieces/`

- transmitter writes `piece-<id>.txt` (UTF-8, the exact text) for every piece
  it needs, where `<id>` is a hash of the text (as `ann-<id>` today). It
  derives the set from the clock (blocks, nominal times), the artists of
  **all delivered packages** in the scan, ineligible ones included (delivery
  usually precedes voicing by hours to days, so a new artist's pieces are
  requested before it becomes airable), the fixed time phrases and the ID
  text. Written only when missing; it never deletes. *(Stale pieces are
  harmless; pruning is a later convenience.)*
- Only `plan_step` writes these files; the read-only views (`schedule`,
  `status`, `library`) never write. Writes are atomic: a dot-prefixed temp
  file unique per process, then rename (emcee ignores dotfiles). The list is
  written whether or not announcements are switched on, so pieces get voiced
  before the switch is turned on. It must not slow or block planning; a write
  failure is logged and alerted with a gated code, never fatal to planning.
  A hung hard NFS mount blocks the write as it already blocks the pool scan;
  no new risk.
- The plan step also persists the needed-piece list (a small JSON in the
  workspace); `status` reads that file rather than scanning the library.
- emcee voices every `piece-<id>.txt` without a `piece-<id>.mp3` and writes
  the MP3 atomically beside it. A new emcee command (name the builder's call,
  e.g. `emcee pieces <dir>`), run on the Mac on a launchd timer, exits at
  once when nothing is pending. It does not take the station lock (it touches
  no package) and must coexist with `emcee run`, with which it shares the mlx
  server. While it runs it counts as an emcee process for llama's
  `station_mark` gate and the `emcee retitle` gate.
- **How a piece is voiced (emcee owns this):** dry (no bed), one call (no
  chunking), the house/announcer presenter's voice and backend (config: which
  presenter; today `roydemure` on mlx_audio), lexicon applied, then:
  - **verify, strictly**: transcribe (the existing STT verification path)
    and require every normalised word to match in order, numbers and hour
    words included, compared after lexicon respelling. Only `tts/verify.py`'s
    normaliser is reused, not its tolerance (`MISS_FLOOR`, the 15 % allowance,
    number-word skipping). A piece may carry an optional expected-transcript
    override for names STT can't spell (e.g. "moe.", "STS9"). On mismatch
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
- After changing the announcer presenter, or a lexicon entry that affects
  pieces, clear `pieces/*.mp3` by hand so they are re-voiced. There is no
  mechanism for this.
- transmitter treats a piece as present when its MP3 exists, is non-empty and
  is past `[station] quiet_minutes`, like other interstitials.

### Assembly (transmitter, at plan time)

- For a break, transmitter decides the text phrase by phrase (above), keeping
  only phrases whose pieces are all present; then joins the pieces with the
  tight gaps (spike: 0.4 s after the ID, ~0.05 s plus the pieces' own edges
  between pieces within a phrase, ~0.15 s after a comma-ending piece; the
  builder tunes) and mixes the house bed under the whole clip with a short
  lead-in and tail (spike: bed 20 dB under the voice, 0.5 s lead-in, 1 s
  tail).
- **Length is a pure function.** The clip's sample count is an exact function
  of the pieces' analysed sample counts, the gaps and the bed lead-in/tail,
  then padded to whole AAC frames the way render pads clips. The scheduler
  computes it with no IO, from cached piece analyses. Pieces are analysed
  lazily, the first time a break uses them, and cached by file-set key; the
  inventory is never decoded up front.
- The assembler decodes and mixes in numpy, as render does (not an ffmpeg
  concat), and must produce exactly the computed count. A mismatch or any
  assembly failure (piece missing or undecodable, bed missing or unreadable,
  write error) sends that break to the last rung (today's logic), alerted
  with a gated code; it never raises out of `extend`.
- **Key = content, not text.** The clip's key is a hash of the file-set key
  (size+mtime, `station.file_set_key_and_sizes`) of every piece and of the
  bed, plus the gaps and the bed gain. The clip is written to transmitter's
  own workspace on hugo (not the station root) and is then an ordinary
  one-clip interstitial piece: analysis, encode and the frame store are
  reused.
- **Loudness**: emcee normalises each piece to one target so pieces match
  each other; the assembler does not normalise, and sets only the bed's gain
  relative to the voice. Render normalises the whole clip as it does every
  clip (`render.file_gain`, `speech_target_lufs`).
- **At render**, an assembled row resolves from the row itself (its piece ids
  and key) plus the voiced pieces in `interstitials/pieces/`; if the
  workspace file is missing it is re-assembled. If the rebuilt key differs (a
  piece was re-voiced), the existing skip/re-plan path applies before the
  break's first segment is encoded. If the break is already on air with its
  encode lost, the existing on-air refusal (`LayoutError`) applies; this is a
  documented limitation.
- **Purge** is garbage collection by reference, as `_gc_encodes` does for
  encodes: an assembled clip is deleted when no plan row ending after the
  published high-water mark references it, with an age floor (e.g. 1 h) for
  temp files and for clips of candidates that were never appended. Deletion
  is always safe because a clip can be re-assembled from its pieces.

### The break row

An assembled break is one plan row:

- `kind` "interstitial", as today's clips;
- `role` a new value (e.g. `"concert"`);
- `block`/`nominal_start`: X's occurrence, so `_continuing` resumes correctly
  on both the new and the old build;
- `names`: occurrence-key pairs exactly as today (never slugs);
- two new list fields: the named show slugs in order, and the ordered piece
  ids.

Broken-promise accounting reuses the existing `announcement_broken` field
(already carried into `aired.jsonl` and read by old builds): the show row that
takes a promised slot in place of the promised show sets it. The new role joins
`pipeline.ANNOUNCEMENT_ROLES`, so a named block landing outside its window or
degraded is flagged exactly as `_announcement_broken` flags it today.

**Rollback.** At the rollback floor (`af46d72`) `PlanRow.role` is a free
`str | None` and `from_json` keeps unknown keys in `extra` (round-tripped by
`to_json`), so these rows load there and on the current build. An older build
finds no assembled clip in its pool scan, so a new break not yet rendered is
skipped and re-planned once with the old logic (acceptable). A new break
already on air whose encode is lost raises the existing on-air refusal
(documented limitation).

### Promises (Goal 2)

The break names X, maybe Y, maybe Z, all contiguous. Because the scheduler
appends one row at a time, those shows are not yet in the plan when the break
row is written. Requirement: **the shows that a break names are the shows the
plan then places, in order, at those slots**, wherever that can still be
true. The break row records them (the slug list above).

- **Measure before promising.** Before a break row is appended, the shows it
  would name (X, and Y/Z when named) are analysed exactly (frame counts, with
  the watchdog pinged after each, as `Station.frames_of` does), and the names
  are chosen on exact lengths. A show that cannot be analysed is not named
  for that step: the break names fewer shows, or falls to a lower rung.
- **Keeping a promise.** Later plan steps place a promised show at its slot
  only while its slug is in the current pool and the plan has not been cut
  or re-planned at or before the promising break, with no `run_start` in
  between. Once Z has been named it is placed even if exact lengths would
  now land it slightly off its window (promises win over the window); that
  occurrence is flagged `announcement_broken` when Z lands outside its
  window.
- **A void promise is never fatal.** Otherwise the promise is void: the
  scheduler plans normally, counts a broken promise, alerts once (ungated)
  and shows it in `status`. A promise can never cause a `PlanError`, a
  re-plan loop or a stall.
- **Re-planning.** Re-planning from row i voids the promises of every break
  row at or after i. When render's skip path drops a named show, that show
  is excluded from the pool (as today); the break before it stays and its
  promise is void (counted).

Render does no extra check of the named shows before encoding a break: X is
placed within a tick of its break and Y/Z rest on the plan-time promise, so a
show failing between plan and render is the rare counted broken promise.

How the scheduler finds X/Y/Z for a break (running its existing block search
from the break's position, using the known assembled length, with the
run-1/run-2 exact-length pattern) is the builder's call, within the existing
rules (window landing, rotation rules, compromise order). With the feature on,
the block search's boundary estimate (`boundary` in the scheduler: gap +
typical ID + gap) uses a typical assembled announcement length in place of
the typical ID.

### Fallback ladder (per break)

There is always one assembled clip per break unless the break falls to the
last rung.

1. Full assembled announcement with every qualifying phrase.
2. Reduced: missing optional phrases (Followed, Then) dropped; missing artist
   piece for X: "Coming up next, <block>." (a period variant of the block
   piece is not needed if the block piece is voiced ending without
   punctuation and the assembly ends there; builder's call); missing ID
   piece: the clip is assembled without it.
3. No usable Next phrase, X's block untitled or degraded, or assembly failed:
   today's logic exactly (the `next`/`later` `ann-*` clips at block edges,
   station ID elsewhere, then a gap).

So with the Mac gone for good, the station behaves as it does today.

### Existing announcements

- The `next`/`later` placement logic and `ann-*` clips stay as rung 3. The
  `transmitter announcements --export` workflow stays for them.
- Nothing else about station IDs changes.

### Config

New settings live in a new file the old build never reads:
`<TRANSMITTER_ROOT>/announce.toml` (the ID text, the bed file, the bed gain,
the gaps if configurable, and an on/off switch defaulting off). Nothing is
added to the clock file's `[announce]` or to `config.toml`: both are
`extra="forbid"`, so a rollback would lose the clock or fail to start. The
switch gates assembly and placement only; the needed-piece list is always
written. emcee config names the announcer presenter.

### Visibility

- `transmitter status`: pieces needed/present/failed counts (from the
  persisted needed-piece list); breaks in the next 24 h by rung; broken
  promises.
- `transmitter schedule`: per break, the text that would air (or the rung).
- emcee side: the new command prints what it voiced, re-took and failed.

### Setup (operator, once)

- On the NAS, create `interstitials/pieces/` writable by hugo's transmitter
  user and the Mac's user (exact uid/permissions per the NAS).
- Create `announce.toml` with the switch off; turn it on once the first
  pieces are voiced. Name the announcer presenter in emcee config.
- launchd job on the Mac for the voicing command.

## Left to the builder

- Command names, config key names, sidecar formats.
- How often `plan_step` writes the needed-piece files.
- How the scheduler searches for X/Y/Z.
- Exact gaps, bed gain, trim parameters, piece loudness target (measure).
- Bucket edges; how Y's start is predicted; the typical assembled length
  used for the boundary estimate.

## Open premises to verify in the plan's first task

- Qwen re-take rate across ~1,000 pieces (spike saw 1 bad take in ~17).
- Qwen's runaway guard (`tts/calibration.py`) on 2-4 word texts: voice the 10
  shortest pieces.
- STT on a swallowed final consonant ("Adam" for "Adams"): transcribe a
  known-bad take under the strict comparison.
- Assembling the same inputs twice gives the identical sample count
  (re-assembly safety): test in the Debian-12 container.
- Rename atomicity hugo to Mac across the share: write and rename on hugo
  while emcee polls.
- Assembly + analysis time on hugo per break (must not slow a plan step
  noticeably).
