# Playout phase 3: the scheduler — design

**Date:** 2026-10-25
**Scope:** `packages/transmitter` only: the clock, the scheduler that replaces
phase 1's shuffle planner, station IDs and schedule announcements, rotation
history, and the `schedule`, `library` and `announcements` commands. Plus a
small `antenna/public/` change so the player shows the station name when no
show is airing (see "Timeline"). llama, emcee and herder are untouched.
**Parent:** `docs/superpowers/specs/2026-10-09-playout-design.md` ("Scheduler
(phase 3)", plus the phase list). This document replaces the parent's anchor and
fill model where they differ. The parent still governs everything about
rendering, publishing, the clock Worker and the cost guard.
**Review mode:** Fable (operator, 2026-10-25). Stakes paragraph confirmed by the operator the same day.
**Status:** approved by the operator 2026-10-25 (after two review rounds).

## Stakes

The risk here is **on-air continuity and the listening experience**. Money and
data are not at risk. The scheduler only chooses what plays and when. It adds no
R2 writes beyond what phase 1 already makes, because the segment count is fixed
by wall-clock time, not by content, and `timeline.json` is still written once per
publish batch. It reads the station root (including a new interstitials folder
inside it), and it writes only transmitter's own workspace.

**Strict surfaces (irreversible once wrong):**
- **Persisted rows.** A rendered segment may already be published, and
  published keys are immutable and cached for a year. The scheduler only
  appends to `plan.jsonl`: a persisted row never changes except by phase 1's
  two existing paths, both owned by render/publish (see "Planning"). It extends
  whatever plan it is given, including one an older clock or the phase-1
  planner produced.
- **Never cut a show and never leave silence.** These are the parent's operator
  rules, unchanged. Every gap follows the gap layout rule in "Planning".
- **Never list a segment that does not exist.** Unchanged and owned by
  render/publish. The scheduler must not give them a plan they cannot render.

A defect anywhere else costs a badly chosen show or a block that starts late,
and a fix reaches air within about one lead (about 24 h) plus one show.

## Intent

What gets built is **a scheduler, not a schedule.** The final clock can't be
written yet. The library is far from complete (2,786 packages delivered, 221
voiced, 2026-10-25), profiles are still being redefined, and emcee voicing is
throttled by LLM and TTS spend, so it will take weeks or months. The operator
will keep editing the clock as the library grows.

So this phase has three goals:
1. A clock config that can express **any clock the operator will plausibly
   want**.
2. A scheduler that **goes on air as soon as it is built**, with a clock suited
   to today's voiced library (roughly 60/34 Dead/funk by voiced airtime, about
   22 days of audio in all). It must handle a clock that asks for more than the
   library has without drama.
3. A way to **try a clock edit before it airs**.

Until the library is much larger the station is in **soft launch**: the
listening experience is secondary, but the rules are designed for the final
library.

### The station the operator expects (shape, not specifics)

- **Tent poles:** at least two Grateful Dead shows a day, and perhaps a
  Dead-tribute act overnight. The median Dead package is 168 min (p10 136, p90
  213), so this covers roughly 7–9 hours a day.
- At least one bluegrass show a day, perhaps two.
- Other profiles slot in where the library allows: daily where there are
  enough shows, otherwise by weekday ("Americana Monday", "Funky Tuesday").
  Weekends may swap a Dead slot for dead-family.
- **Loosely fixed showtimes, each tied to a profile, with wiggle room.** The
  priority is to keep the scheduled profile at the scheduled time.
- **Some stretches are open time** and take whatever fits.
- **Diversity:** spread the airtime across as much of the LMA as the library
  allows.

Measured lengths of delivered packages (minutes; voiced counts in brackets),
2026-10-25: dead 413 (112) median 168; indie 329 (17) 89; americana 329 (1) 110;
bluegrass 307 (2) 135; southern 275 (0) 117; jam 244 (0) 168; livetronica 232
(0) 155; dead-family 225 (0) 180; funk 221 (89) 119; dead-tribute 208 (0) 170;
country 2 (0) 125.

## Goals

1. **Blocks.** The weekly clock is a sequence of blocks. Each has a nominal
   start, wiggle room, a profile pool (or open time), an on-air title, and the
   days of the week it applies to. A block runs until the next block starts.
2. **Fill a block from its own profile first.** A block may hold **more than
   one concert of its profile** (normally at most two) when that lands the next
   block inside its window. In a profile mixing 150-minute jam-band shows with
   60–90-minute traditional acts, two short shows can fill a long block.
3. **Land the next block on time, then compromise** (operator-confirmed
   order). Within the block's own profile, choose shows so the next block starts
   inside its wiggle room (closest to nominal is best). When that is impossible,
   compromise in this order:
   1. a concert from another profile (the open-time pool) fills the remaining
      time;
   2. the next block starts **outside** its window. This is a **miss**: it is
      recorded and reported, and never cuts a show or leaves silence.
   Filling with other profiles is a compromise to minimise, not a design goal.
4. **Open time.** A block with no profile pool takes whatever fits. Each show
   there airs with its own DJ intro naming its own program (emcee's per-profile
   on-air title). The operator accepts this.
5. **Station IDs** ("You're listening to LMA Radio…") from a pool of short
   clips, placed between shows and rotated.
6. **Schedule announcements** that name upcoming **blocks** (not specific
   concerts): "Stay tuned for Here Comes the Funk at 11, followed by Gravel &
   Steel at 1." They play at the boundary into a block and at the last show
   boundary inside the block before it. Both IDs and announcements count toward timing:
   they are short pieces of known length.
7. **Rotation rules** designed for the final library (below). They are
   preferences that **bend rather than block** when the library is too small.
8. **Rotation history** (`aired.jsonl`): one row per piece once it has been
   published and its air time has passed. It drives recency, and later the web
   page's recently played list.
9. **Commands:** `transmitter schedule` (preview, and a draft clock),
   `transmitter library`, `transmitter announcements`, and new `status` lines.
10. **Room for partial sets.** Playing one set of a multi-set show, with
    set-specific intros and outros, is a future feature. Nothing here may make
    it harder (see "Program pieces").

## Non-goals and future work

- **Not in this phase:**
  - partial sets and their alternate DJ audio;
  - alternate DJ intros for open time;
  - announcements of specific upcoming concerts (these need transmitter→emcee
    plumbing);
  - transmitter invoking `emcee say` itself (keep the door open: see
    "Interstitial audio");
  - a schedule page on the web player (phase 4);
  - one-off pinned shows;
  - dayparted open-time pools;
  - any change to llama or emcee.
- **Anti-goal:** a clock that is hard to change. The operator will reshape it
  many times as the library grows, and editing it must be low-risk.
- **Anti-goal:** status noise. A rule that bends because today's library is
  small is expected during soft launch. Report it so it can be found, but never
  alarm on it.

## The clock

The clock lives in **its own file**, `~/.transmitter/clock.toml` (under
`$TRANSMITTER_ROOT`), not in `config.toml`, so that a draft is just another file
of the same shape (`schedule --clock <draft>`). Validation is strict, like
`config.toml`: unknown keys and bad values are `ConfigError`. *(My call:
separate file.)*

Sketch (the field names are a proposal and the builder may refine them):

```toml
timezone = "America/New_York"
wiggle_minutes = 15              # default for every block: start may be this early or late

[announce]
# {title}/{time} = the block named first; {next_title}/{next_time} = the one after it
next = "Coming up next, {title}. Then at {next_time}, {next_title}."
next_one = "Coming up next, {title}."
later = "Stay tuned for {title} at {time}, followed by {next_title} at {next_time}."
later_one = "Stay tuned for {title} at {time}."
# time_format = ...              how one zone's time reads ("11", "11:30"); the builder picks the default
zones = [ { tz = "America/New_York", label = "Eastern" },
          { tz = "America/Los_Angeles", label = "Pacific" } ]   # {time} names every zone, in order

[open]                           # what open time and fill may play
exclude_profiles = []

[[block]]
name = "dead-evening"            # stable id (history, status, announcements)
title = "Prime Time Dead"        # on-air name, used by announcements
days = "daily"                   # or ["sat", "sun"], ["mon"]
start = "19:00"                  # nominal, local time
profiles = ["dead"]              # omitted or empty = open time
max_shows = 2                    # default 2 for a profile block
wiggle_minutes = 20              # overrides the default
prefer = [ { years = "1972-1977", weight = 1.5 } ]
```

- **Weekly sequence.** The clock expands to a weekly sequence of block
  starts. Two blocks on the same day at the same start are a config error.
  Weekday rotations are blocks with the same `start` and disjoint `days`.
- **Block extent.** A block runs from its start to the next block's start, which
  may fall on the next day. A clock with one block covers the week.
- **Open time** is a block with no `profiles`, so it is explicit. It may have
  a title (it is then announced) or none (it is never announced).
- **Pools.** A profile block draws from packages whose **voiced profile** is in
  `profiles`. That is `dj_audio.profile` when the block records it, else
  `source.profile`, so a show's DJ intro always names the block's program even
  after an `emcee move` or an `[assign.artists]` rule. Today the two never
  differ: 219 of 221 voiced packages predate the field, and the 2 that have it
  match. *(My call, from the builder check.)* Open time and fill draw from every
  eligible package except `[open] exclude_profiles`. When that leaves the open
  pool empty, the exclusion is bent (the last rule to bend); `PlanError` is
  raised only when nothing at all is eligible. A package with no
  `source.profile` is open-time only. A block whose pool has no eligible show is
  **open time for that occurrence**: it is not announced, and `status` notes it.
- **Preferences** (`prefer`): soft weights, as in the parent. `years` matches
  the show date's year range. `on_this_day` is a global rotation preference
  (below) and may be overridden per block.
- **Local time** follows the parent: `zoneinfo`; a nonexistent local time
  (DST spring-forward) resolves to the next valid instant and an ambiguous one
  to its first occurrence. A block occurrence that resolves to zero length
  (spring-forward collapsing two starts) is dropped.
- **Wiggle room** is symmetric by default (`wiggle_minutes`). A block may set
  separate `early_minutes` and `late_minutes` instead, and the measurement
  below needs that for a like-for-like baseline. *(My call: symmetric default,
  asymmetric allowed.)*
- **No clock file** means one implicit all-week open block. That is phase 1's
  behaviour (any eligible show, back to back) with the rotation rules added, so
  rollout needs no clock. The phase-1 shuffle planner (`choose_next`/`extend`)
  is retired; its `[planner]` config keys stay (see "Selection score and
  rotation rules"). *(My call.)* `status` says "no clock: open all week" when
  the file is absent.
- **Read at every plan step**, not only at start. transmitter keeps a copy of
  the last clock that loaded in its workspace. An invalid `clock.toml` raises an
  alert and planning continues with that copy (render's skip path uses the same
  copy); with no valid copy ever, the implicit open block is used.
  `schedule --clock <file>` is the way to check an edit before moving it into
  place (the runbook says so).

**Clock edits** reach air after the persisted plan has aired: about one lead
plus at most one show. `transmitter schedule` shows the new clock's effect at
once; `status` shows the persisted plan, which is what will actually air.

## Scheduling

### Program pieces

The scheduler plans **pieces**. A piece is anything with an ordered list of
audio files, its own file-set key, its own length, and the metadata needed to
place it. This phase has two kinds:
- **show**: a package's whole `broadcast.m3u`;
- **interstitial**: one station ID or announcement clip.

A future **set** piece (one set of a package with its own intro and outro)
must be addable without reworking the scheduler, the plan file, render or the
timeline. Concretely:
- nothing below the scheduler may assume a piece is a whole package;
- the encode cache, the analysis cache and plan rows are keyed by the piece's
  own file set;
- rotation history records which package a piece came from, so a future set
  piece counts against its concert's recency.

Code below the scheduler that is package-shaped today, and must be made
piece-aware as part of this phase:
- render-time re-validation, which looks rows up in the station scan by slug;
- `service.row_analysis`, which re-evaluates `root/row.dir`;
- `build_timeline`, which lists every plan row as a show (interstitial rows
  are left out of the timeline);
- the meaning of `PlanRow.dir`.

**Plan rows.**
- Rows carry what history needs at decision time: at least `kind`, `block`,
  `nominal_start`, `miss` and `bends`. An announcement row also records the
  block occurrence(s) it names. Field detail is the plan's.
- `PlanRow.from_json` tolerates unknown keys and keeps them through a
  read-write round-trip, so `plan.jsonl` written by phase 1 still loads, an
  older reader still loads scheduler rows, and their keys survive a rollback and
  roll-forward. Interstitial rows keep string `slug`, `dir` and `key` (for
  example the clip's name, the folder name and its file-set key). The tolerant
  reader lands in the plan's first deployable task and is deployed to hugo
  before the scheduler, so a later rollback lands on a reader that tolerates
  scheduler rows. The runbook names that commit as the oldest safe rollback
  target, says never to truncate `plan.jsonl` by hand, and has its rollback
  step also remove `[interstitials]` from `config.toml` (the strict config of an
  older build rejects it).

**Unverified premise:** the frame model holds for single-clip pieces. The plan
tests `planned_frames` against a real encode of an ID clip.

### Selection score and rotation rules

The parent's score is the starting point: recency (never aired highest, then
days since last aired) plus the block's preference weights plus the
`on_this_day` boost. Ties break deterministically on phase 1's
`shuffle_rank(seed, slug)`, so `[planner] seed` stays as a config key when
`choose_next`/`extend` are retired; so does `start_delay_minutes`.

**The compromise order outranks every rotation rule.** Rotation rules only rank
options within the same tier: a block filled from its own profile always beats
one that keeps a rotation rule by using fill.

The rotation rules are designed for the final library, and every one is soft:

| rule | default intent |
|---|---|
| **Same concert** | Never-aired shows first, then least recently aired. A minimum gap before a concert repeats (builder sets the default from the full delivered library; my guess is 30–60 days). |
| **Same artist, adjacent** | Never back to back, including the two halves of a paired block and across a block boundary. |
| **Same artist, same day** | Not twice in one local day. |
| **Same era** | A soft penalty on the same artist and year on the same day (two 1977 Dead shows). |
| **On this day** | A boost for a show whose month-day matches the slot's local date. |

- **Bending.** When the library can't satisfy a rule, the scheduler relaxes
  rules, softest first, rather than leaving a block empty or reaching for
  filler. The proposed order is: era, then same-artist-same-day, then the
  concert gap, then adjacency. The builder may refine it. `[open]
  exclude_profiles` bends last, and only when the open pool is otherwise empty.
- **What counts as a bend.** A bend is counted only when an option that kept the
  rule existed in the same tier and was passed over. A rule the pool makes
  impossible (a single-artist Dead pool cannot avoid the same artist twice a day
  or in a pair) is not applied within that pool at all, and is not a bend. The
  same holds for the concert gap when the pool's eligible airtime is shorter
  than the gap: least recently aired first still applies.
- **Reporting.** Bends appear in `schedule` and as aggregate counts in
  `status`, and never as alerts.
- **Tunable.** Every default can be changed in the clock file.

### Planning

The scheduler is **pure**: (the persisted plan, eligible pieces with lengths,
clock, history) → the next row(s) to append to it.

- **The plan is append-only, as in phase 1.** The scheduler never changes or
  removes a row of `plan.jsonl`. Each plan step runs the scheduler from the end
  of the persisted plan (its lookahead is recomputed in memory every step and
  never persisted) and appends the next row(s). Every persisted row is
  therefore final; there is no frontier to compute.
- **Phase 1's two drop paths stay as they are.** The only paths that drop
  persisted rows are owned by render/publish, not the scheduler:
  - the render-time re-validation skip (`replan_from`): a piece that fails
    before its first segment is encoded is dropped with every row after it, and
    the plan is re-extended from that row's own start frame and `run_start`
    flag;
  - recovery after an outage longer than the lead (`cut_for_recovery` at
    `listed_bound`), which deletes the unpublished segment files before the new
    plan lands.

  The scheduler is just the extender those paths call.
- **Lookahead is anchored to the frame line**: block occurrences are counted
  from the end of the persisted plan, never from `now`, so unchanged inputs give
  the same choice on every step.
- **Plan lock.** One non-waiting flock (the `publish_lock` pattern, for example
  `plan.lock`) is held around `plan_step` and `render_step`. The service holds
  it for its plan and render steps; the `plan` and `render` commands take it and
  refuse when it is held. `schedule` and `status` take no lock. This also closes
  a race phase 1 has: two appenders reading the same plan could each append a
  different row at the same start while render uses the other.
- **Gap layout.** Every appended row that is not a run start starts at the
  previous row's end + `gap_frames` (the configured inter-show gap),
  interstitials included, as phase 1's `next_start` already does. A boundary
  with an interstitial is therefore show, gap, clip, gap, show. The rule is
  asserted on each appended row only; existing rows are checked only for
  non-overlap, as today, so a `show_gap_seconds` change never fails a step.
- **Block by block in time order.** For each block occurrence, choose 1 to
  `max_shows` shows from its pool, plus the interstitials at its boundaries, so
  that the next block's start lands inside its wiggle room. Prefer landing
  close to the nominal time, and prefer higher summed score. Then apply the
  compromise order (Goals 3).
  - A block's **actual start** (for its window and `miss`) is the start of its
    first show; the `next` clip before it belongs to the boundary.
  - **Fill** goes at the end of the block, before the next one starts. It is
    reported by cause: "pool short" (the block's own pool could not fill it) or
    "longer than max_shows" (structural: the block is longer than `max_shows`
    of its shows can fill). Only "pool short" is a compromise.
  - A **show that would overrun** the next block's window is avoided when an
    alternative exists.
  - **Overlapping windows** resolve as a late start plus a miss, never a cut,
    as in the parent.
- **Search method.** The builder chooses the bounded search and how far ahead
  it looks. It should not consume the only show that fits a hard block today if
  that show is the one that rescues a harder block tomorrow; how far to go
  there is a builder call. The parent planned anchor to anchor over a 7-day
  lookahead.
- **Mid-block starts.** The end of the persisted plan usually falls inside a
  block, including the end of a phase-1 plan and a fresh run after an outage
  longer than the lead. The occurrence in progress is then that block, and it is
  filled so the next block lands in its window. *(My call.)*
- **Persistence.** `plan.jsonl` persists rows up to the lead, as today. Trimming
  it is the builder's call, but it only ever removes rows that have aired, and
  never one the timeline's 24 h window or the history appender still needs.
- **Exact timing.**
  - Each piece carries its exact frame count when its analysis is cached, else
    an **estimate**. The scan carries what estimates need: each entry's size,
    the manifest's `total_duration_sec` and the voiced profile. An estimate is
    `total_duration_sec` plus each DJ clip's length from its size and its own
    MP3 bitrate (read from its first frame header), not an assumed 64 kbps:
    unchunked, unbedded clips ship the provider's MP3. Estimates are keyed by
    file-set key and marked as estimates. Unvoiced packages (for `--library
    delivered`) are keyed by the manifest's mtime and size and get a flat
    4-minute clip allowance. `schedule` keeps estimates in memory and writes
    nothing.
  - The scheduler is pure **for given lengths**: preview and live agree when
    they see the same cache state.
  - A plan step appends at most `max_new` rows (the service's pacing stands).
    For the next row: run the scheduler on best-known lengths; analyse that
    row's piece; run the scheduler **once more** with the exact count; append
    run 2's pick if its piece is analysed, otherwise run 1's analysed pick
    (accepting a possible miss). A step always appends at least one row while
    the plan is short of `until_frame`. Written rows always carry exact counts.
  - Interstitial clips are short and are always analysed exactly (never
    estimated) when the pool is scanned.
  - Analysing the rest of the eligible library to replace estimates is
    background work whose pacing is the builder's call; the watchdog keeps
    being fed.
  - `total_duration_sec` counts an unmeasured track as 0, so such a show is
    under-estimated until analysed. Accepted.
  - **Unverified premise,** tested in the plan's first task on hugo: estimates
    land within seconds of decoded counts (compare the analyses in
    `~/.transmitter/cache/` with the estimate), and one cold analysis's duration
    on hugo.
- **Re-validation.** Phase 1's skip path stands (above): a piece that fails
  re-validation before its first segment is encoded is dropped with every row
  after it, and the plan is re-extended from there (`plan-changed`).
  - Interstitial rows re-validate against the interstitials folder: the file is
    present, has the same file-set key, and is past the quiet period. A failing
    clip is removed from the interstitial pool for the rest of that call, and
    the plan is re-extended from its boundary without it.
  - One `render_step` call has a hard cap on re-plans, greater than the
    interstitial pool size plus the rows in the lead, since a re-plan that
    writes no segment could otherwise repeat without bound. Exceeding it fails
    the step (alerted).

### Station IDs and announcements

- **Placement.**
  - At every boundary between two shows, place a **station ID** (rotated, least
    recently used first), unless the boundary carries an announcement.
  - At the boundary into block X, place a **`next`** announcement: it names X
    as starting now and, when it qualifies, the block after X with its nominal
    time.
  - At the **last** show boundary inside the block before X, when there is one,
    place a **`later`** announcement: it names X with its nominal time and, when
    it qualifies, the block after X. Every other show boundary inside a block
    gets a station ID.
  - Each template has a two-block form and a one-block form. If X is untitled,
    no announcement is placed there (a station ID is). If the block after X is
    untitled or degraded to open time, the one-block form is used. A two-block
    form that fails only on the second block falls back to the one-block form,
    not to an ID.
  - The builder may choose a lighter cadence for IDs if every boundary proves
    too often. *(My call: every show boundary.)*
- **Truthful or silent.** An announcement is placed only when X (and the
  second block when named) starts within its window and on its own profile,
  that is, not degraded to open time. This is judged on the scheduler's
  in-memory lookahead, which must reach every block the announcement names.
  Otherwise the announcement is dropped, and a station ID takes its place if one
  exists. The stated time is the nominal time. What the lookahead shows for a
  block not yet appended is a prediction; that is an accepted limitation,
  counted under `announcement-broken`.
- **A promise kept where possible** (operator ruling 2026-10-25: a promise, not
  a guarantee). Every block is already planned to land the next block in its
  window, which is exactly what an announcement promises, so no lock is needed:
  the lookahead is recomputed from the same inputs at every step, and the
  scheduler's own objective keeps the promise unless the library or clock
  changes. Whether the promise held is judged when each named block's first
  show row is appended. A broken one (the named block starts outside its window
  or degrades to open time) is logged `announcement-broken` and recorded in
  history, not alerted.
- **The text is derived from the clock alone**, so the set of announcements a
  clock can need is finite: at most four per block start in the weekly sequence
  (two templates, each in two forms), under a hundred for a typical clock. Each
  announcement's id is a hash of its rendered text, so operator edits
  (templates, titles, `time_format`, `zones`) change ids and stale clips are simply
  never chosen. The shipped defaults for the templates, `time_format` and `zones` are
  part of the clock contract: changing one in a later release retires every
  clip voiced from it, so such a change is a deliberate, noted breaking change.
- **Time phrasing.** The station is on the Internet, so a stated time always
  names its time zone, and may name several (operator, 2026-10-25). `{time}`
  renders the nominal time in each of `[announce] zones`, in order, each
  followed by its spoken label: "11 Eastern, 8 Pacific". Each zone's time is
  formatted by `[announce] time_format` ("11", "11:30"; the builder picks the
  default). The default zones are Eastern and Pacific
  (`America/New_York`, `America/Los_Angeles`). Labels are the operator's words
  ("Eastern" covers EST and EDT alike).
- **Missing audio.** If no audio exists for a needed announcement, a two-block
  form falls back to the one-block form's clip if present, then to a station ID;
  a one-block form falls back to a station ID. `status` lists what is missing.
  If there are no ID clips, nothing is placed and the gap is the plain
  inter-show gap.

### Interstitial audio (the manual hand-off)

transmitter has no voice of its own and runs on hugo, away from the TTS keys.
In this phase the operator voices clips on the Mac with `emcee say`, which
writes `<file>.mp3` beside `<file>.txt`.

- **Folder.** `<station root>/interstitials/` by default, configurable with
  `[interstitials] dir` in `config.toml`. It holds no `manifest.json`, so no
  scanner sees it: transmitter's (`station.py:226`) and emcee's
  (`station.py:323-326`) scans skip directories without one, as does
  `scripts/backfill_voiced_by.py:42`, and llama's deliver touches only
  `<dest>/<slug>` and never lists the root (`cli.py:2300-2385`). transmitter
  only reads this folder.
- **Naming.**
  - station IDs are `id-*.mp3`, the operator's own, any number;
  - announcements are `ann-<id>.mp3`.
- **The command.** `transmitter announcements` lists every announcement the
  current clock (or `--clock <draft>`) needs: id, text, and present or missing.
  `--export DIR` writes `ann-<id>.txt` for the missing ones into DIR, an
  explicit operator-chosen write.
- **Operator workflow:**
  1. Export the scripts, straight into the interstitials folder when hugo's
     mount of the station root is writable, else elsewhere and copy them into
     the folder.
  2. On the Mac, run `emcee say` over each; it writes `ann-<id>.mp3` beside its
     script, in the folder.
  The runbook gets a copy-paste version.
- **Loudness.** Clips are loudness-normalised with the speech target, as DJ
  clips are.
- **Quiet period.** A clip must be older than the quiet period before it airs.
- **Door left open.** A future transmitter→emcee path only has to produce the
  same `ann-<id>.mp3` files. Nothing here assumes a human made them.

### Rotation history

- **`aired.jsonl`** gets one row per piece that was published: its end is at or
  before the end of segment `PublishState.last`, and at or before now. A row
  cut by recovery records its cut end. A row records at least:
  - kind;
  - package slug (and, for future set pieces, which set);
  - block name;
  - start and end;
  - whether that boundary was a miss;
  - which rules bent.
  The service tick appends to it.
- **Identity** is (epoch id, start_frame). The appender adds only rows not
  already present, so restarts never double-append.
- **At rollout,** it is backfilled once from `plan.jsonl` rows, by the same
  rule.
- **Recency** counts both aired rows and persisted rows not yet aired.
- **Unknown fields** are ignored on read, so old rows still load.

### Timeline

- **Interstitials are not written to `timeline.json`.** It lists shows only,
  as today. R2 writes stay as phase 1's.
- **The player's no-show text** (what `nowplaying.js` shows when no show
  covers the instant) becomes the station name instead of "We'll be back
  shortly." This small `antenna/public/nowplaying.js` change covers a station
  break and the existing inter-show gaps (2 s by default) alike. The builder checks the
  off-air path still shows its own text.
- **`anchors`** stays `"anchors": []`, as today. Filling it is phase 4; rows
  already carry `block`, so phase 4 can build it.

## Commands

- **`transmitter schedule [--days N] [--clock FILE] [--library eligible|delivered]`**
  - Shows the persisted plan from now, then what the scheduler would append
    after it: each block occurrence with its nominal and actual start and slip,
    its shows (artist, date, length), any fill, interstitials, misses, bent
    rules, blocks that became open time, and missing announcement audio.
  - Ends with a summary over the span: misses, fill minutes as a share of the
    span (split into "pool short" and "longer than max_shows"), bends by rule,
    and the shortest repeat gap.
  - Defaults are 7 days, the live clock and the eligible library.
  - `--clock` previews a draft from the end of the persisted plan, with the
    current history, without touching the live plan. Read-only: it writes
    nothing.
  - `--library delivered` rehearses against every delivered package (voiced or
    not) on estimated lengths. It's a nice-to-have, since even the delivered
    library isn't representative of the eventual one, but cheap once estimates
    exist.
  - Estimated lengths are marked as such.
- **`transmitter library`:** eligible pieces by profile, with count and median,
  p10 and p90 length; the interstitial pool; and ineligible packages summarised
  by reason.
- **`transmitter announcements [--clock FILE] [--export DIR]`:** as above.
- **`transmitter status`** gains:
  - the current and next block, or "no clock: open all week";
  - misses and fill minutes (split by cause) over the last 24 h and the planned
    next 24 h;
  - bend counts;
  - blocks degraded to open time;
  - missing announcement audio.
  None of these are alerts. The next-24 h figures come from persisted plan rows
  only: `status` never runs the scheduler or scans the library.

## Measurement

The parent requires the scheduler to be "built and measured against every
available manifest".

- **What to run.** Offline, run `schedule`'s engine over the delivered library
  on estimated lengths, with at least:
  - (a) the naive script's five anchors written in the new clock format:
    07:00 dead, 12:00 bluegrass and 19:00 dead daily, Saturday 22:30 funk,
    Sunday 15:00 dead-family;
  - (b) an example of the operator's shape (two Dead blocks, a Dead-tribute
    overnight, a daily bluegrass, weekday rotations, an open stretch);
  - (c) a soft-launch clock for today's voiced library (Dead/funk, open time).
- **What to report:**
  - misses;
  - fill share, by cause;
  - bends by rule;
  - the repeat-gap distribution;
  - the share of block airtime on its own profile;
  - for (a), a comparison with the naive-filler baseline below.
- **No pass threshold.** The library isn't representative and the clock isn't
  final, so the measurement is evidence for the operator, not a gate. One
  exception, made like-for-like *(my call, from the builder check)*:
  - The baseline is the parent's naive filler
    (`docs/superpowers/2026-10-10-playout-review/feasibility-sim.py`), re-run on
    the same library and clock (a). It needs edits first: the station root as an
    argument; anchors read from the clock (a) file; separate "overran" and "not
    fillable" counts (it currently folds overruns in as a ×1000 weight and
    prints one figure); the same length estimate the scheduler uses; and its
    fill exclusion (`dead`, `funk`, `dead-family`) expressed in clock (a) as
    `[open] exclude_profiles`. The edited script is committed beside the
    evidence doc.
  - The baseline is re-derived, not copied: the parent's two-column table came
    from a variant not in the repo, and ran over 256 packages.
  - Run the scheduler on clock (a) with the parent's window semantics: start in
    `[nominal, nominal + 15 min]` (`early_minutes = 0`, `late_minutes = 15`).
    The scheduler keeps its own features (`max_shows`, interstitials off). Run
    it over at least 50 consecutive weeks with history accumulating (one week is
    22 block starts, too coarse), against the naive script's 50 seeds.
  - Pass: the scheduler's share of block starts outside the window is no
    higher than the naive script's "overran" plus "not fillable" (its silences
    count as misses).
- The result goes in an evidence doc under `docs/superpowers/`.

## Testing

- **Approach.** Offline, deterministic pytest, as in the parent. The scheduler
  is pure, so test it on fixture libraries built from real manifest durations
  (the delivered library's distribution).
- **What the tests must cover:**
  - block expansion over a week, including DST transitions, blocks crossing
    midnight, and a zero-length occurrence being dropped;
  - pool filtering and degradation to open time;
  - an empty open pool bending `[open] exclude_profiles`, and `PlanError` only
    when nothing is eligible;
  - pairing within a block;
  - the compromise order, and its precedence over every rotation rule;
  - fill reported by cause;
  - misses and overlapping windows;
  - each rotation rule and the bend order;
  - bends counted only when a keeping option existed, and not for rules a
    single-artist pool makes impossible;
  - determinism for given lengths, including the seed tie-break;
  - estimates (each clip's own bitrate, the flat allowance for unvoiced
    packages), the one exact-count re-run with its fallback to run 1's pick, at
    least one row appended per step while short of `until_frame`, and written
    rows carrying exact counts;
  - mid-block starts;
  - the gap layout, asserted on appended rows only;
  - interstitial placement, rotation and truthfulness, including `next`/`later`
    selection (`later` on the last boundary only), the one-block fallback, and
    a broken promise judged when the named block's first show row is appended;
  - interstitial re-validation and the re-plan cap in `render_step`;
  - missing audio and its fallbacks;
  - announcement ids being stable for unchanged text;
  - `aired.jsonl` append (published rows only, no double-append across
    restarts, cut ends) and backfill;
  - old `plan.jsonl` rows loading, and unknown row keys surviving a read-write
    round-trip;
  - an invalid `clock.toml` alerting while planning continues on the last valid
    copy, and the implicit open block when there has never been one;
  - the append-only invariant: no persisted row changes under any clock edit,
    and only the skip path and recovery drop rows;
  - the plan lock: `plan` and `render` refused while it is held;
  - the timeline listing no interstitial rows.
- **Required scenarios**, each a test:
  - a clock edit mid-fill;
  - a manual `plan` or `render` while the service renders (refused by the lock);
  - the skip path dropping an interstitial row and a show row;
  - recovery with a guard stop longer than the lead;
  - a `show_gap_seconds` change;
  - a phase-1 plan being extended;
  - a crash between append and render.
- **Mutation testing.** The strict surfaces get it: a mutant that lets the
  scheduler alter or remove a persisted row must fail a named test.
- **Compatibility.** Python 3.11 compatibility still applies (hugo; the Debian-12
  script is the gate). `test_no_llama_or_emcee_imports.py` still passes.

## Left to the builder

- the search algorithm and its lookahead;
- the score's exact form and the rotation defaults;
- the exact clock field names;
- the plan-row fields beyond the minimum;
- how often a plan step runs;
- how analysis backfill is paced;
- how `plan.jsonl` is trimmed;
- ID cadence if every boundary proves too much;
- the time-phrasing default;
- how `schedule`'s output is laid out.

Each is constrained by the sections above.

## Calls made in this document (not operator decisions)

- the clock in its own file;
- the clock read at every plan step, with the last valid copy used when it is
  invalid;
- `[announce] time_format` and `zones` in the clock file, Eastern and Pacific
  by default;
- symmetric wiggle by default;
- no clock = one open block, and the phase-1 shuffle retired;
- `[planner] seed` kept as the scheduler's tie-break;
- the plan append-only, as in phase 1, with a plan lock around plan and render;
- one exact-count re-run per appended row;
- mid-block starts treated as that block;
- an ID at every show boundary;
- the `next` and `later` announcement templates;
- the interstitials folder inside the station root, its naming and the export
  workflow;
- announcements dropped when untrue;
- bends counted only when an option keeping the rule existed;
- the tolerant plan-row reader shipped before the scheduler;
- interstitials kept out of the timeline, and the player's no-show text
  changed to the station name;
- `anchors` deferred to phase 4;
- `--library delivered` included;
- the one measurement floor and how it's made like-for-like;
- pools by voiced profile, falling back to `source.profile`.
