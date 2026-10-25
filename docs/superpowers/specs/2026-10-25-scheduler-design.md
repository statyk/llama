# Playout phase 3: the scheduler — design

**Date:** 2026-10-25
**Scope:** `packages/transmitter` only: the clock, the scheduler that replaces
phase 1's shuffle planner, station IDs and schedule announcements, rotation
history, and the `schedule`, `library` and `announcements` commands. Possibly a
small `antenna/public/` change so the player shows something sensible during a
station break (see "Timeline"). llama, emcee and herder are untouched.
**Parent:** `docs/superpowers/specs/2026-10-09-playout-design.md` ("Scheduler
(phase 3)", plus the phase list). This document replaces the parent's anchor and
fill model where they differ. The parent still governs everything about
rendering, publishing, the clock Worker and the cost guard.
**Review mode:** Fable (operator, 2026-10-25). Stakes paragraph confirmed by the operator the same day.
**Status:** design, awaiting review.

## Stakes

The risk here is **on-air continuity and the listening experience**. Money and
data are not at risk. The scheduler only chooses what plays and when. It adds no
R2 writes beyond what phase 1 already makes, because the segment count is fixed
by wall-clock time, not by content, and `timeline.json` is still written once per
publish batch. It reads the station root and a new interstitials folder, and it
writes only transmitter's own workspace.

**Strict surfaces (irreversible once wrong):**
- **The frozen prefix.** A rendered segment may already be published, and
  published keys are immutable and cached for a year. The scheduler must never
  change a plan row whose audio is rendered. It plans only after the render
  frontier, starting from whatever prefix it is given, including one an older
  clock or the phase-1 planner produced.
- **Never cut a show and never leave silence.** These are the parent's operator
  rules, unchanged. Every gap is the configured inter-show gap, plus an
  interstitial when one is placed.
- **Never list a segment that does not exist.** Unchanged and owned by
  render/publish. The scheduler must not give them a plan they cannot render.

A defect anywhere else costs a badly chosen show or a block that starts late,
and the next re-plan corrects it within one lead (about 24 h).

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
   to today's voiced library (roughly 80/20 Dead/funk). It must handle a clock
   that asks for more than the library has without drama.
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
3. **Compromise in this order** (operator-confirmed) when a block can't be
   filled exactly:
   1. the next block starts early or late **within its wiggle room**;
   2. a concert from another profile (the open-time pool) fills the remaining
      time;
   3. the next block starts **outside** its window. This is a **miss**: it is
      recorded and reported, and never cuts a show or leaves silence.
   Filling with other profiles is a compromise to minimise, not a design goal.
4. **Open time.** A block with no profile pool takes whatever fits. Each show
   there airs with its own DJ intro naming its own program (emcee's per-profile
   on-air title). The operator accepts this.
5. **Station IDs** ("You're listening to LMA Radio…") from a pool of short
   clips, placed between shows and rotated.
6. **Schedule announcements** that name upcoming **blocks** (not specific
   concerts): "Stay tuned for Here Comes the Funk at 11, followed by Gravel &
   Steel at 1." They play at block boundaries. Both IDs and announcements count
   toward timing: they are short pieces of known length.
7. **Rotation rules** designed for the final library (below). They are
   preferences that **bend rather than block** when the library is too small.
8. **Rotation history** (`aired.jsonl`): one row per piece once its air time
   has passed. It drives recency, and later the web page's recently played list.
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
# {title}/{time} = the next block; {next_title}/{next_time} = the one after it
two = "Stay tuned for {title} at {time}, followed by {next_title} at {next_time}."
one = "Stay tuned for {title} at {time}."

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
  match. *(My call, from the builder check.)* Open time and fill draw from every eligible package except
  `[open] exclude_profiles`. A package with no `source.profile` is open-time
  only. A block whose pool has no eligible show is **open time for that
  occurrence**: it is not announced, and `status` notes it.
- **Preferences** (`prefer`): soft weights, as in the parent. `years` matches
  the show date's year range. `on_this_day` is a global rotation preference
  (below) and may be overridden per block.
- **Local time** follows the parent: `zoneinfo`; a nonexistent local time
  (DST spring-forward) resolves to the next valid instant and an ambiguous one
  to its first occurrence.
- **Wiggle room** is symmetric by default (`wiggle_minutes`). A block may set
  separate `early_minutes` and `late_minutes` instead, and the measurement
  below needs that for a like-for-like baseline. *(My call: symmetric default,
  asymmetric allowed.)*
- **No clock file** means one implicit all-week open block. That is phase 1's
  behaviour (any eligible show, back to back) with the rotation rules added, so
  rollout needs no clock. The phase-1 shuffle planner (`choose_next`/`extend`)
  is retired. *(My call.)*

**Clock edits reach air after the frozen prefix**, so within about one lead
(24 h). This is phase 1's existing property and does not change.

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

Plan rows gain the fields this needs (at least `kind` and `block`), and
`plan.jsonl` written by phase 1 must still load.

### Selection score and rotation rules

The parent's score is the starting point: recency (never aired highest, then
days since last aired) plus the block's preference weights plus the
`on_this_day` boost.

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
  concert gap, then adjacency. The builder may refine it.
- **Rules a block's own pool makes impossible don't count as bends.** For
  example, a single-artist Dead block can't avoid the Grateful Dead twice a day,
  so that is not worth reporting. Bends caused by scarcity in a mixed pool are
  counted.
- **Reporting.** Bends appear in `schedule` and as aggregate counts in
  `status`, and never as alerts.
- **Tunable.** Every default can be changed in the clock file.

### Planning

The scheduler is **pure**: (frozen prefix, eligible pieces with lengths,
clock, history, now) → the plan from the frontier onward. It is deterministic,
so `schedule`'s preview and the live plan agree for the same inputs.

- **Block by block in time order.** For each block occurrence, choose 1 to
  `max_shows` shows from its pool, plus the interstitials at its boundaries, so
  that the next block's start lands inside its wiggle room. Prefer landing
  close to the nominal time, and prefer higher summed score. Then apply the
  compromise order (Goals 3).
  - **Fill** goes at the end of the block, before the next one starts.
  - A **show that would overrun** the next block's window is avoided when an
    alternative exists.
  - **Overlapping windows** resolve as a late start plus a miss, never a cut,
    as in the parent.
- **Search method.** The builder chooses the bounded search and how far ahead
  it looks. It should not consume the only show that fits a hard block today if
  that show is the one that rescues a harder block tomorrow; how far to go
  there is a builder call. The parent planned anchor to anchor over a 7-day
  lookahead.
- **Mid-block starts.** The plan may begin inside a block: after a clock edit,
  after phase 1's prefix, or at a fresh run after an outage longer than the
  lead. The occurrence in progress is then that block, and it is filled so the
  next block lands in its window. *(My call.)*
- **Persistence.** `plan.jsonl` persists only up to the lead, as today, except
  a block committed with its announcement (see "Station IDs and
  announcements"). Beyond
  that the plan is recomputed on every plan step from the prefix. A choice
  made for a block that extends past the lead may change before it renders.
  That is fine, because only rendered rows are frozen.
- **Exact timing.**
  - Placement uses the exact frame counts render will produce, as today
    (`Station.frames_of`).
  - **Search may use estimates.** The manifest's `total_duration_sec` plus DJ
    clip durations is enough to choose shows, and analysing every eligible
    package in one plan step is not acceptable. Phase 2's verification
    measured one plan step analysing a few shows over NFS at about 17 minutes.
  - The analyses of chosen shows are made before their rows are written. Any
    remaining backfill is the builder's call (incremental, a bounded number per
    step, idle time).
  - An estimate that turns out wrong by more than the wiggle room must still
    produce a valid plan; it may produce a miss.
  - The watchdog must keep being fed during a long plan step.
- **Re-validation.** Phase 1's rules stand: a piece that fails re-validation
  before encoding is skipped at its boundary, and the plan is re-made from
  there (`plan-changed`).

### Station IDs and announcements

- **Placement.**
  - At every boundary between two shows, place a **station ID** (rotated, least
    recently used first), unless the boundary carries an announcement.
  - At each **block boundary**, place an **announcement** naming the next block
    and the one after it. Open time without a title is skipped, and the `one`
    template is used when only one block qualifies.
  - The builder may choose a lighter cadence for IDs if every boundary proves
    too often. *(My call: every show boundary.)*
- **Truthful or silent.** An announcement airs only when the plan really does
  start each block it names within that block's window and on its own profile,
  that is, not degraded to open time. Otherwise it is dropped, and a station ID
  takes its place if one exists. The stated time is the nominal time.
- **Locked with its block** (operator ruling 2026-10-25: a promise kept where
  possible, not a guarantee).
  - When the scheduler places an announcement at the boundary into block X, it
    also commits X's whole contents in the same plan step, persisted to
    `plan.jsonl` even past the lead and placed by exact analysed frame counts,
    never estimates. The start of the block after X is then fixed when the
    announcement's audio freezes.
  - X's shows would be analysed within hours for rendering anyway, so this
    moves the work earlier rather than adding to it.
  - Committed rows past the frontier stay re-plannable only for the existing
    reasons: a render-time re-validation skip (a re-voiced or pulled package)
    or a clock edit. A re-plan of a committed block treats keeping the
    announced start in its window as a strong preference, not a hard
    constraint.
  - A promise that still breaks is logged (`announcement-broken`) and
    recorded in history. It is not an alert.
  - Absent operator intervention in those few hours, an announcement is true.
- **The text is derived from the clock alone**, so the set of announcements a
  clock can need is finite: at most one or two per block start per week, which
  is a few dozen. Each announcement's id is a hash of its text, so editing a
  title or template creates new ids, and stale clips are simply never chosen.
- **Time phrasing** ("at 11", "at 11:30", "at 1") is formatted from the
  nominal time. The builder picks a default the operator can edit in the
  templates.
- **Missing audio skips the clip.** If no audio exists for a needed
  announcement, it is skipped (an ID takes its place), and `status` lists what
  is missing. If there are no ID clips, nothing is placed and the gap is the
  plain inter-show gap.

### Interstitial audio (the manual hand-off)

transmitter has no voice of its own and runs on hugo, away from the TTS keys.
In this phase the operator voices clips on the Mac with `emcee say`, which
writes `<file>.mp3` beside `<file>.txt`.

- **Folder.** A configured interstitials folder (`[interstitials] dir` in
  `config.toml`; unset means none) that both the Mac and hugo can reach, outside
  every scanner's view:
  - transmitter's own package scan skips directories without `manifest.json`;
  - emcee's and llama's scans must also not see it. The builder verifies this
    and records it.
  transmitter only reads this folder.
- **Naming.**
  - station IDs are `id-*.mp3`, the operator's own, any number;
  - announcements are `ann-<id>.mp3`.
- **The command.** `transmitter announcements` lists every announcement the
  current clock (or `--clock <draft>`) needs: id, text, and present or missing.
  `--export DIR` writes `ann-<id>.txt` for the missing ones into DIR, an
  explicit operator-chosen write.
- **Operator workflow:**
  1. Export the scripts.
  2. Move them to the Mac.
  3. Run `emcee say` over each.
  4. Copy the MP3s into the folder.
  The runbook gets a copy-paste version.
- **Loudness.** Clips are loudness-normalised with the speech target, as DJ
  clips are.
- **Quiet period.** A clip must be older than the quiet period before it airs.
- **Door left open.** A future transmitter→emcee path only has to produce the
  same `ann-<id>.mp3` files. Nothing here assumes a human made them.

### Rotation history

- **`aired.jsonl`** gets one row per piece once its air time has passed. A row
  records at least:
  - kind;
  - package slug (and, for future set pieces, which set);
  - block name;
  - start and end;
  - whether that boundary was a miss;
  - which rules bent.
  The service tick appends to it.
- **At rollout,** it is backfilled once from `plan.jsonl` rows already aired.
- **Recency** counts both aired rows and frozen rows not yet aired.
- **Unknown fields** are ignored on read, so old rows still load.

### Timeline

- **The `anchors` key.** `timeline.json` already carries `"anchors": []`,
  reserved by the parent. This phase fills it with the block occurrences
  covering the timeline's span (name, title, nominal start, actual start), as
  data only. Showing it is phase 4.
- **Interstitials** must not make the player say "We'll be back shortly." That
  is what `nowplaying.js` shows when no show covers the instant. The builder
  chooses the smallest fix that holds: an entry the player already renders
  well, or a minimal `antenna/public/` change (e.g., the station name during a
  break).
- **Show pages** and `notes/` are per show, and interstitials have none.

## Commands

- **`transmitter schedule [--days N] [--clock FILE] [--library eligible|delivered]`**
  - Shows the plan from now: each block occurrence with its nominal and actual
    start and slip, its shows (artist, date, length), any fill, interstitials,
    misses, bent rules, blocks that became open time, and missing announcement
    audio.
  - Ends with a summary over the span: misses, fill minutes as a share of the
    span, bends by rule, and the shortest repeat gap.
  - Defaults are 7 days, the live clock and the eligible library.
  - `--clock` previews a draft from the current frozen prefix and history
    without touching the live plan. Read-only: it writes nothing.
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
  - the current and next block;
  - misses and fill minutes over the last 24 h and the planned next 24 h;
  - bend counts;
  - blocks degraded to open time;
  - missing announcement audio.
  None of these are alerts.

## Measurement

The parent requires the scheduler to be "built and measured against every
available manifest".

- **What to run.** Offline, run `schedule`'s engine over the delivered library
  on estimated lengths, with at least:
  - (a) the parent's example clock;
  - (b) an example of the operator's shape (two Dead blocks, a Dead-tribute
    overnight, a daily bluegrass, weekday rotations, an open stretch);
  - (c) a soft-launch clock for today's voiced library (Dead/funk, open time).
- **What to report:**
  - misses;
  - fill share;
  - bends by rule;
  - the repeat-gap distribution;
  - the share of block airtime on its own profile;
  - for (a), a comparison with the parent's naive-filler table.
- **No pass threshold.** The library isn't representative and the clock isn't
  final, so the measurement is evidence for the operator, not a gate. One
  exception, made like-for-like *(my call, from the builder check)*:
  - Re-run the parent's naive filler
    (`docs/superpowers/2026-10-10-playout-review/feasibility-sim.py`) on the
    same library and clock (a), as the baseline. Do not use the parent's frozen
    table: it ran over 256 packages.
  - Run the scheduler on clock (a) with the parent's window semantics: start in
    `[nominal, nominal + 15 min]` (`early_minutes = 0`, `late_minutes = 15`).
    The scheduler keeps its own features (`max_shows`, interstitials off).
  - Pass: the scheduler's share of block starts outside the window is no
    higher than the naive script's "overran" plus "not fillable" (its silences
    count as misses).
- The result goes in an evidence doc under `docs/superpowers/`.

## Testing

- **Approach.** Offline, deterministic pytest, as in the parent. The scheduler
  is pure, so test it on fixture libraries built from real manifest durations
  (the delivered library's distribution).
- **What the tests must cover:**
  - block expansion over a week, including DST transitions and blocks
    crossing midnight;
  - pool filtering and degradation to open time;
  - pairing within a block;
  - the compromise order;
  - misses and overlapping windows;
  - each rotation rule and the bend order;
  - not-counted bends for single-artist pools;
  - determinism;
  - mid-block starts and a phase-1 prefix;
  - interstitial placement, rotation and truthfulness;
  - missing audio;
  - announcement ids being stable for unchanged text;
  - `aired.jsonl` append and backfill;
  - old `plan.jsonl` rows loading;
  - the frozen-prefix invariant (no rendered row changes under any clock edit);
  - the timeline's `anchors` and interstitial entries.
- **Mutation testing.** The strict surfaces get it: a mutant that lets the
  scheduler alter a frozen row must fail a named test.
- **Compatibility.** Python 3.11 compatibility still applies (hugo; the Debian-12
  script is the gate). `test_no_llama_or_emcee_imports.py` still passes.

## Left to the builder

- the search algorithm and its lookahead;
- the score's exact form and the rotation defaults;
- the exact clock field names;
- the plan-row fields;
- how analysis backfill is paced;
- ID cadence if every boundary proves too much;
- the time-phrasing default;
- the interstitial timeline representation;
- how `schedule`'s output is laid out.

Each is constrained by the sections above.

## Calls made in this document (not operator decisions)

- the clock in its own file;
- symmetric wiggle by default;
- no clock = one open block, and the phase-1 shuffle retired;
- mid-block starts treated as that block;
- an ID at every show boundary;
- the interstitials folder, naming and export workflow;
- announcements dropped when untrue;
- `anchors` filled now and rendered in phase 4;
- `--library delivered` included;
- the one measurement floor and how it's made like-for-like;
- pools by voiced profile, falling back to `source.profile`.
