# Junk-tag drop: tuning, crowd and intro tracks of any length

Status: design, awaiting operator approval. Date: 2026-11-13.
Review mode: **Opus** (operator, 2026-11-13).

## Stakes

The library is ~3,930 shows; 699 are touched: 678 delivered (150 voiced, 528 unvoiced)
and 21 not on the station. What this changes is what goes to air, so a wrong drop removes
real music from the broadcast. The operator has ruled the tradeoff acceptable: "we are a
radio show, not the system of record for these shows. Dropping the occasional 'real' thing
in service of making sure the radio program moves along and doesn't have long minutes of
dead air is the right tradeoff."

A wrong drop is undone per show with `llama fix <show> --include <file>`, which restores
the track in the library. On an unvoiced show, re-delivery puts it back on air cheaply. On
a voiced show it takes `deliver --replace-voiced` plus a full re-voice (off air in between;
Voxtral credits on a Voxtral show).

**Strict surfaces** (irreversible or costly; reviewers hold these to the highest bar):

- `deliver --replace-voiced` discards a show's DJ script and audio, and the show is off
  air (transmitter needs `dj_audio`) until it is re-voiced. Re-voicing on Voxtral spends
  paid credits (~269 clips for the 96 Voxtral shows measured 2026-11-13). Voiced shows are
  replaced only by name, in batches the operator approves before anything is replaced,
  each show followed by its re-voice.
- A station manifest carrying `awaiting_fix` is **not airable** (transmitter) and emcee
  skips it. This rollout marks only unvoiced station copies, which are not airable anyway,
  so a mark takes nothing off air; **no voiced station copy is marked**. A stray station
  mark is reversed with `bulk_apply.py unmark`, by its marking batch (`llama clear-mark`
  refuses unvoiced copies).
- The manifest is the only contract between llama, emcee and transmitter. Its new field
  must be additive and optional: every existing reader must keep working on packages with
  it, without it, and with it `null` or `[]`. The same holds for the new key in the
  website's notes JSON, and a deployed antenna module gains no exports.

## Why

`gratefuldead-1979-12-05` opens with a 4:40 track tagged `Tuning`. It airs, because the
junk filter only judges tags of files that are *already* implausibly short (under 0.25 x
the tape's median track length; 104 s on that tape). No rule drops a track for its tag
alone. Across the library that leaves ~960 tuning, crowd, silence and intro tracks in the
library; 225 of them (9.3 h) are in voiced, airable shows today, some of them long
stretches of dead air.

## Goals

1. Drop tuning/crowd/silence tracks wherever they sit, at any length.
2. Drop intro-labelled tracks at the start of the show or of a set, and outro-labelled ones
   at the end of the tape, at any length.
3. Hold a show instead when the drop is big enough that a mislabelled song is a real
   possibility (the circuit breaker).
4. Record what was dropped in the delivered package, show it on the website struck
   through, and let the host know (rarely mention).
5. Roll it out across the library, voiced shows included, in operator-approved batches.

## Non-goals

- Banter. "Banter is less clear-cut so let's leave that alone." Any title containing a
  banter word keeps.
- Detecting or fixing mislabelled tapes deterministically (operator: "a bit too much").
  The hold is the answer to mislabelling.
- Widening the vocabulary beyond the operator's words (no `applause`, `fade`, `set break`,
  `dead air` here; those already drop when short via `JUNK_PART`).
- Changing the short arm, its constants, or the fix-2201 edge-label rule.
- Showing dropped tracks on the main "now playing" view.

## Anti-goals

- A dropped real song with no hold and no record. Every drop this rule makes is listed in
  the package and every large one holds.
- Taking a voiced show off air, or discarding its voicing, outside an operator-approved
  batch.

## The rule (decided by the operator)

Matching is on the track's **final title** in gather (whatever rung produced it), case- and
whitespace-insensitive, after the existing tag cleaning (`clean_tag_title`). `junk.parts`
is normative for splitting a title into parts and cleaning their edges: it splits on `/`,
`&`, `,`, `and`, ` - ` and also on `+ ; ~ | ( ) [ ] -- -> >`, so `(crowd)`, `[crowd]`,
`***crowd noise***`, `Crowd + Tuning` and `Crowd~` drop too.

**A. Anywhere, any length.** Every part of the title is one of the operator's words:
`tuning` (with `tuning up`, `tune up`, `tuneup` spellings), `crowd`, `crowd noise`,
`silence`. Examples that drop: `Tuning`, `crowd`, `Crowd Noise`, `Crowd/Tuning`,
`crowd & tuning`, `Tuning Up`. Examples that keep: `Crowd/Banter`, `crowd encore call`,
`Mexican Hat Dance Tuning`, `Crowded Tub`, `Tuning >`.

**B. Start of the show or of a set, any length.** Every part is an intro word (`intro`,
`introduction`, `introductions`) or a rule-A word, and the track is the first track of the
show or the first track of a set (its set label differs from the previous track's).
Drops: a bare `Intro` opening set 2, `Intro/Tuning`, `Tuning & Intro`, `crowd/intro`.
Keeps: an `Intro` in the middle of a set ("Intro in the middle of the show may mean
something else"), `Intro Jam`, `Intro > Song`.

**C. End of the tape, any length.** Every part is an outro word (`outro`, `outros`) or a
rule-A word, and the track is the last track. (My call: the operator set the start rule;
the end rule mirrors it and touches 2 tracks today.)

**Edge runs (my call).** "First of the show/set" and "last of the tape" are judged
AFTER rule A's drops, so a run at an edge goes whole: set 2 opening `Crowd`, `Intro`
drops both; `Outro`, `Crowd` at the end drops both. (The 2026-11-13 baseline judged
position on the original list, so expect a few more B/C drops than it shows; report them.)

**Segue arrows keep**, as in the existing operator ruling: a title that ends in
`>`/`->` never drops under any rule, and at the last track one starting with an arrow
(`-> Outro`) keeps. **The test reads the final title's own trailing arrow, not the `segue`
flag (my call):** the flag can come from setlist alignment, the segue donor or the segue
restore, none of which is the taper saying this track runs into music. The arrow is read
after `junk.TIME_PAREN` is removed (so `Crowd > (1:20.19)` counts as arrowed), and where
slice 2a fired, the raw tag's arrow counts too. Limitation: a list-rung title whose arrow
was parsed away is judged without it.

**An operator `include` always wins.** A file named in `overrides.include` is never dropped
by this rule. An operator `overrides.titles` value that is a vocabulary word drops like
any other title (30 tracks measured); the operator's opt-out is `--include`.

**The circuit breaker (operator, 2026-11-13).** A drop holds the show when it meets **two
of three**: duration > 6 min (360 s); duration > 5% of the show's total running time;
duration > 1.0 x the show's median track length. Position does not exempt a track (the
operator first proposed exempting set boundaries, then withdrew it after the measurement
showed 11 of the 15 heard, mostly mislabelled, tracks sit at boundaries). Measured
2026-11-13 over show.json titles: 19 shows held, 0.48% of the library. These three numbers
and the two-of-three rule are operator-set constants: do not retune without the operator.

Median and total are taken over the show's tracks **before** this rule's drops (so the
drop itself is in the population it is compared against; this is what was measured).

## What a drop looks like

- The file leaves the kept track list and is added to `show.json` `excluded_files` with a
  new reason string (proposed `junk title`; the builder may choose, but it must be distinct
  from `implausibly short` so `show --tracks`, triage `[i]` and the adjudicator can tell
  them apart).
- Track numbering, set breaks and segues are recomputed over the remaining tracks as for
  any other exclusion. Everything computed before the drop and indexed by track number is
  re-indexed or recomputed: flag and note text naming track numbers, `title_paths` /
  cascade records, and segues. A dropped track carrying a segue mark loses it (measured:
  1 track). A kept track whose next track was dropped loses its segue, unless its own
  title carries an arrow (which renders anyway).
- Overrides are resolved against the pre-drop list. A `set_breaks` or `encore_after` key
  on a dropped file falls after the last kept file before it (the rule
  `briefing_reusable` uses for breaks). After the drop, any other key naming a dropped
  file is inert.
- A held drop (breaker) still drops in `show.json`, and the show carries a new review flag
  naming the file, title, duration, % of show and x median. Resolutions, both existing
  mechanisms: `fix --include <file>` (keep the track; the flag no longer reproduces) or
  `fix --overrule` / triage overrule (accept the drop; recorded in `overrides.overrules`
  as for any flag, so it does not re-hold). The flag gets an `overrules._PATTERNS` entry
  with its own kind, keyed on the filename, not the numbers.
- **The adjudicator does not resolve this flag** (my call): its bar is `never`
  (operator-only) in `OVERRULE_BAR`, like `lineage-unknown`. The hold exists because a
  human ear is the test; an LLM reading tags cannot hear a mislabelled song. An
  adjudicator `include` of a file carrying the new reason is propose-only (the reason
  joins the gate's refused-include set).

## Placement in gather (builder's choice, with constraints)

Rule A needs only the title; rules B and C need final set labels. The existing junk
filter (`junk.filter_files`) runs before play order and structure, so this rule cannot
live there whole. Constraints:

- It must see the final titles and final set labels, and run before `Show` is built.
- Gather's other hold checks (structure guard, jerrybase closer tripwire and
  `filler_tail_closers`, the multi-event span check, `no playable tracks`) may see the
  list before or after the drop, builder's choice. Any hold they add or clear across the
  library replay is reported to the operator with the show and the flag; it need not be
  zero (my call).
- Dropping must not change which tracks the structure/alignment step saw in a way that
  moves set boundaries for the remaining tracks; if the builder re-runs structure after
  the drop, measure the delta on the library replay and report it.
- The short arm's median and floor are untouched (they are computed earlier, on files).
- The replay harness and `reapply` pass through the same code (one implementation).
- Staleness compares against the post-drop list: `staleness.stale_message` and the
  `--suggest-titles` comparison in `cli.py` use one shared helper, gather's final kept
  list (`gather.final_kept`) minus this rule's drops, so a show the rule changed is not
  reported stale.

## The package: `dropped_tracks`

The manifest gains an optional top-level list (schema stays v3):

    "dropped_tracks": [
      {"title": "Tuning", "duration_sec": 280.4, "set": "1", "after_track": 0,
       "filename": "gd79-12-05d1t01.mp3", "reason": "junk title"}
    ]

- `after_track`: the kept track index it sat after (0 = before the first track), so a
  reader can place it inline. `set`: the set label it carried.
- **Only this rule's drops are listed** (my call). The short arm's drops (tag-judged or
  not) record no title or position and share their reason with untagged drops, so listing
  them would need a second implementation of the short rule. Spam, duplicate or
  derivative copies, filename-convention mismatches and missing durations are not listed
  either.
- gather records each drop's title, set label and `after_track` (on its `excluded_files`
  row or in a new `Show` field, builder's choice), and `package` reads them from `Show`.
- Absent, `null` and `[]` all mean none, in every reader.
- The field is not added to `station_mark.COMPARED`: neither `clear-mark`'s nor
  `deliver`'s equal-copy test changes, and a test pins that. Rollout membership is decided
  by tracks, never by the field alone (see Rollout).
- llama's `Manifest` model gains the field; emcee's manifest rewrite must preserve it
  (emcee edits manifests as raw dicts in places; check every rewrite path).

## The website

- transmitter's `build_notes` leaves `setlist` exactly as today and adds a new key to the
  notes JSON (e.g. `dropped`: entries with `title`, `set`, `after_track`), tolerating a
  damaged value the way `part()` does. An old or cached reader ignores the key.
- `_setlist_html` (the static `show/<slug>.html`) and the slide-up notes panel merge those
  entries inline at their `after_track` position and render them greyed and struck
  through. On the antenna side only new code merges them, in a new module (antenna's rule:
  a deployed module gains no exports); `setlistCard` (`panel.js`) renders the result.
- Struck entries are **not counted** in the list numbering (the setlist is an `<ol>`;
  `<li value=...>` or a CSS counter, builder's choice). A dropped entry whose set has no
  kept tracks adds no set heading.
- Nothing changes on the now-playing view.
- A manifest or notes file without the field renders exactly as today (shows not yet re-delivered
  keep their old manifests until the rollout reaches them). transmitter stays Python 3.11-compatible.

## The host

emcee's scriptwrite input gains the dropped list, with a prompt line saying these were cut
from the broadcast as non-music and are normally not worth mentioning; mention one only
when it matters (e.g. a long cut that explains a jump in the show). A second prompt line:
dropped titles are not songs and never go in `mentioned_songs`. No other mechanism (the
guard is unchanged).
emcee never imports llama; it reads the manifest field.

## Rollout

1. Release llama, emcee and transmitter/antenna (deploy) with the change.
2. A separate pass after the release (operator, 2026-11-13), not part of the 2026-10
   bulk-apply campaign, whose batch work is done. It reuses that campaign's machinery
   (`scripts/bulk_apply.py`, `scripts/CLAUDE.md`), run from a campaign worktree pinned to
   the new release (re-pin the campaign and bump its minimum version). ~699 shows by the
   2026-11-13 measurement: 150 voiced (96 Voxtral, 54 mlx_audio), 528 unvoiced delivered,
   21 not on the station. Build the lists from LIVE state at rollout time (station
   manifests' `dj_audio` and `tts.backend`), never from notes: shows get voiced in the
   meantime, and a show voiced before the pass reaches it takes the voiced route.
   Pending (delivered, unvoiced) shows are ordinary unvoiced shows here, including the ones
   re-delivered with `--replace-voiced` during the campaign that await re-voicing; they get
   no special priority either way (operator).

   **Membership:** a show is in the rollout when its live station manifest lists a source
   file that the re-processed library show drops under this rule. Not "library `show.json`
   changed" (that misses shows fixed after the release) and not "library differs from
   station" (that sweeps in shows the operator ruled with `--accept-change`). A show not on
   the station is in when the rule drops a file from its library show. Before a show is
   re-processed, membership is judged from the release's library replay (the drops it
   would make) against the live station manifest; step 6 checks it again before any
   voiced replacement.
3. **Mark every affected show first.** `reapply` skips a show whose campaign record is
   processed and unmarked, and 480 of the 699 carry `processed`. The mark uses a new
   reason, `junk-title drop`, which joins the campaign's set. Two kinds, by the show's
   live station state:
   - **Unvoiced station copy** (held or not): a normal station mark (`awaiting_fix`). It
     takes nothing off air (transmitter needs `dj_audio`), and emcee skips marked copies,
     so no affected show is voiced from its stale manifest in the meantime. Mark these at
     release, before any further `emcee run`.
   - **Voiced station copy, or no station copy:** a library-only mark (a `campaign.json`
     mark with no station write; a small new option on `bulk_apply.py mark`, e.g.
     `--library-only`). No voiced station copy is ever marked in this rollout.
4. **Re-process:** `llama reapply --from-list <list> --allow-structure-change`. Shows with
   a stored `llm` alignment (81 of 699 measured) need `--with-gather-llm`: they run in
   their own waves, sized from a pilot's meter readings (the reapply rule), or are left
   library-unchanged and listed.
5. **Unvoiced delivered (~528):** re-deliver with `llama deliver --fixed`, which also
   clears the mark.
6. **Voiced (150):** mlx_audio and Voxtral alike (Voxtral, operator 2026-11-14: "Let's
   just do all of them"), in batches the operator approves **before anything is replaced**.
   The approval list is built per show from live state: the current clip count (set
   intros plus outro, from its `dj_audio`); the presenter's currently resolved backend (as
   in `emcee status`'s `(now:)` column, not the recorded one); the show's drop list
   (titles, durations; the cheapest moment to catch a mislabel); and any other
   station-vs-library difference. After approval, per show: re-check membership (the drop
   is still there and the station copy still differs on tracks; a show `--include`d in the
   meantime leaves the batch), then `llama deliver <slug> --replace-voiced` by name, then
   `emcee voice <slug>`. Not `emcee run`: it voices every pending package on the station
   (2,784 today) and has no slug selector. A re-voice that fails is retried with
   `emcee voice <slug>`; until then the show is off air.
7. **Held (19):** go to the operator's triage, whatever their voicing. Only an overrule
   (accepting the drop) sends a held show on to re-delivery: unvoiced by `deliver --fixed`,
   voiced by the step 6 batch route. An `--include` resolution changes nothing at the
   station: the station copy already has the track and stays as it is; if unvoiced, its
   mark is cleared by `deliver --fixed`, a re-delivery with no change. A voiced held show
   keeps airing as it is throughout. `gratefuldead-1969-03-01` (Voxtral, held) follows
   this.

**Cost.** ~700 fresh briefs (every changed show fails `briefing_reusable` on "tracks
differ"; reapply's pacing gate paces them); 81 `--with-gather-llm` shows; Voxtral ~269
clips over 96 shows (counted in segments; chunked synthesis may make more API calls per
clip).

## Acceptance

- Library replay: drop and hold counts match the 2026-11-13 measurement within what the
  final-title vs show.json-title difference explains (report every difference). Expected
  deltas: ~14 extra drops from `junk.parts` splitting (`(crowd)`, `[crowd]`,
  `***crowd noise***`, `Crowd + Tuning`, `Crowd~`, ...), 2 operator includes that will not
  drop (`billystrings-2017-07-15`, `cubensis-2011-01-22`), and the extra B/C drops from
  edge runs.
- Zero drops of a title outside the vocabulary (a test over the replay output).
- The 1979-12-05 case: its `Tuning` would drop (the operator is fixing that show by hand
  first; test on a fixture).
- A show the rule changed is not reported stale (a test).
- An `encore_after` key on a dropped `Crowd` file moves to the last kept file before it
  (a test on one of the 12 such shows, e.g. a `railroadearth` one).
- Adding `dropped_tracks` changes neither `clear-mark`'s nor `deliver`'s equal-copy test
  (a test).
- Every manifest and notes reader (llama, emcee, transmitter, antenna) passes on a package
  with the field, without it, and with it `null` or `[]`.
- The rollout reports the `--with-gather-llm` shows as their own bucket.

## Planned follow-up (not this work)

A local audio classifier (YAMNet/PANNs-style, AudioSet labels; backlog memory
`llama-audio-tagging-backlog`) re-checks every drop this rule makes by listening: a drop it
hears as music is held or restored. It is what catches a mislabelled song under the
breaker's thresholds, which this design accepts dropping without a hold in the meantime
(operator, 2026-11-14: ship this first, classifier next). This design's distinct reason
string and the manifest's `dropped_tracks` are what let that pass find every drop.

## Left to the builder

The reason string, the flag wording, where in `compute_gather` the rule sits (within the
constraints above), where each drop's record lives in `Show`, the field's and the notes
key's exact names, how struck entries skip the numbering, and test layout.

## Measurements behind this (2026-11-13, show.json titles, not final-title gather)

Script and per-track output: `docs/superpowers/2026-11-13-junk-tag-drop-evidence/`
(`measure.py`, `drops.tsv`: 960 rows, 508 A / 431 B / 21 C, 19 held). This is the baseline
acceptance compares against.


- Rule A alone (four exact words): 424 tracks / 341 shows; with combinations 508 / 374.
- Rules A-C: ~960 tracks / 699 shows (per-slug counts from `drops.tsv`): 150 voiced
  (96 Voxtral, 54 mlx_audio), 528 unvoiced delivered, 21 not on the station; 225 of the
  tracks (9.3 h) in voiced, airable shows.
- Breaker variants tested: 2-of-3 at 7 min 16 holds; at 6 min 19; at 5 min 26; boundary
  exemption would have left 4.
- Operator listened to the 15 longest candidates: most were mislabelled, chiefly by wrong
  archive.org data (e.g. `yondermountainstringband-2006-08-25`: tags off by one, the encore
  labelled `outro`).
