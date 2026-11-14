# Junk-tag drop: tuning, crowd and intro tracks of any length

Status: design, awaiting operator approval. Date: 2026-11-13.
Review mode: **Opus** (operator, 2026-11-13).

## Stakes

The library is ~3,930 shows; 678 delivered shows and 146 voiced ones are touched. What
this changes is what goes to air, so a wrong drop removes real music from the broadcast.
That is reversible per show (`llama fix <show> --include <file>`), and the operator has
ruled the tradeoff acceptable: "we are a radio show, not the system of record for these
shows. Dropping the occasional 'real' thing in service of making sure the radio program
moves along and doesn't have long minutes of dead air is the right tradeoff."

**Strict surfaces** (irreversible or costly; reviewers hold these to the highest bar):

- `deliver --replace-voiced` discards a show's DJ script and audio, and the show is off
  air (transmitter needs `dj_audio`) until it is re-voiced. Re-voicing on Voxtral spends
  paid credits (~269 clips for the 96 Voxtral shows measured 2026-11-13). Voiced shows are
  replaced only in batches the operator approves, each followed by its re-voice.
- A station manifest carrying `awaiting_fix` is **not airable** (transmitter). Marking a
  show takes it off air until it is re-delivered.
- The manifest is the only contract between llama, emcee and transmitter. Its new field
  must be additive and optional: every existing reader must keep working on packages with
  and without it.

## Why

`gratefuldead-1979-12-05` opens with a 4:40 track tagged `Tuning`. It airs, because the
junk filter only judges tags of files that are *already* implausibly short (under 0.25 x
the tape's median track length; 104 s on that tape). No rule drops a track for its tag
alone. Across the library that leaves ~960 tuning, crowd, silence and intro tracks on air,
some of them long stretches of dead air.

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

- A dropped real song with no hold and no record. Every drop is listed in the package and
  every large one holds.
- Taking a voiced show off air, or discarding its voicing, outside an operator-approved
  batch.

## The rule (decided by the operator)

Matching is on the track's **final title** in gather (whatever rung produced it), case- and
whitespace-insensitive, after the existing tag cleaning (`clean_tag_title` / `junk.parts`
splitting on `/`, `&`, `,`, `and`, ` - `).

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

**Segue arrows keep**, as in the existing operator ruling: a title whose taper text ends in
`>`/`->` never drops under any rule, and at the last track one starting with an arrow
(`-> Outro`) keeps. **The test reads the taper's text, not the shipped title and not the
`segue` flag (my call):** gather strips trailing arrows from shipped titles
(`titles._SHIPPED_TAIL`), and the flag can come from setlist alignment, the segue donor or
the segue restore, none of which is the taper saying this track runs into music. Use the
pre-strip title of whatever rung produced the final title.

**An operator `include` always wins.** A file named in `overrides.include` is never dropped
by this rule.

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
  any other exclusion. A dropped track carrying a segue mark loses it (measured: 1 track).
- A held drop (breaker) still drops in `show.json`, and the show carries a new review flag
  naming the file, title, duration, % of show and x median. Resolutions, both existing
  mechanisms: `fix --include <file>` (keep the track; the flag no longer reproduces) or
  `fix --overrule` / triage overrule (accept the drop; recorded in `overrides.overrules`
  as for any flag, so it does not re-hold).
- **The adjudicator does not resolve this flag** (my call): its bar is `never`
  (operator-only), like `lineage-unknown`. The hold exists because a human ear is the
  test; an LLM reading tags cannot hear a mislabelled song.

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

## The package: `dropped_tracks`

The manifest gains an optional top-level list (schema stays v3; absent = none):

    "dropped_tracks": [
      {"title": "Tuning", "duration_sec": 280.4, "set": "1", "after_track": 0,
       "filename": "gd79-12-05d1t01.mp3", "reason": "junk title"}
    ]

- `after_track`: the kept track index it sat after (0 = before the first track), so a
  reader can place it inline. `set`: the set label it carried. A short tag-judged drop
  never had a set label (it leaves before structure); it takes the label of the next kept
  track in play order, else the previous one (my call; it renders on the public site).
- **Which drops are listed** (my call): this rule's drops, plus the
  existing tag-judged short drops (`short_tag_is_junk`, edge labels), because those are
  the same kind of thing a listener would see in a setlist. **A manifest that changes
  only by gaining `dropped_tracks` does not make a show part of the rollout (my call):**
  short drops reach the site whenever a show is re-delivered for some other reason. Not listed: spam, duplicate
  or derivative copies, filename-convention mismatches, missing durations, untagged short
  files.
- llama's `Manifest` model gains the field; emcee's manifest rewrite must preserve it
  (emcee edits manifests as raw dicts in places; check every rewrite path).

## The website

- transmitter's `build_notes` passes `dropped_tracks` through into the notes JSON, merged
  inline into `setlist` with a `dropped: true` marker at its `after_track` position;
  `_setlist_html` (the static `show/<slug>.html`) and antenna's `setlistCard`
  (`panel.js`, the slide-up notes panel) render those entries greyed and struck through,
  **not counted** in the list numbering (the setlist is an `<ol>`).
- Nothing changes on the now-playing view.
- A manifest or notes file without the field renders exactly as today (shows not yet re-delivered
  keep their old manifests until the rollout reaches them). transmitter stays Python 3.11-compatible.

## The host

emcee's scriptwrite input gains the dropped list, with a prompt line saying these were cut
from the broadcast as non-music and are normally not worth mentioning; mention one only
when it matters (e.g. a long cut that explains a jump in the show). No other mechanism.
emcee never imports llama; it reads the manifest field.

## Rollout

1. Release llama, emcee and transmitter/antenna (deploy) with the change.
2. A separate pass after the release (operator, 2026-11-13), not part of the 2026-10
   bulk-apply campaign, whose batch work is done. It may reuse that campaign's machinery
   (`scripts/bulk_apply.py`, `scripts/CLAUDE.md`). Re-process every show the rule changes:
   ~699 by the 2026-11-13 measurement. Build the lists from LIVE state at rollout time
   (station manifests' `dj_audio` and `tts.backend`), never from notes: shows get voiced in
   the meantime, and a show voiced before the pass reaches it falls into step 4 or 5 by its
   engine.
   Pending (delivered, unvoiced) shows are ordinary unvoiced shows here, including the ones
   re-delivered with `--replace-voiced` during the campaign that await re-voicing; they get
   no special priority either way (operator).
3. **Unvoiced delivered (~532):** re-deliver as the campaign does today.
4. **mlx_audio-voiced (54):** re-deliver by name with `--replace-voiced`, then re-voice
   locally (`emcee run --dry-run`, operator approves, `--yes`).
5. **Voxtral-voiced (96 on 2026-11-13; operator 2026-11-14: "Let's just do all of them"):**
   the same route as step 4, re-voiced on Voxtral, in batches the operator approves
   (`emcee run --dry-run` shows the clip count before any spend).
6. **Held (19):** go to the operator's triage, whatever their voicing. A held show's
   station copy is not marked and keeps airing as it is until the hold is resolved and the
   show re-delivered. One of the 19 is Voxtral-voiced (`gratefuldead-1969-03-01`); once
   resolved it joins step 5.

## Acceptance

- Library replay: drop and hold counts match the 2026-11-13 measurement within what the
  final-title vs show.json-title difference explains (report every difference).
- Zero drops of a title outside the vocabulary (a test over the replay output).
- The 1979-12-05 case: its `Tuning` would drop (the operator is fixing that show by hand
  first; test on a fixture).
- Every manifest reader (llama, emcee, transmitter, antenna) passes on a package with the
  field and on one without.

## Planned follow-up (not this work)

A local audio classifier (YAMNet/PANNs-style, AudioSet labels; backlog memory
`llama-audio-tagging-backlog`) re-checks every drop this rule makes by listening: a drop it
hears as music is held or restored. It is what catches a mislabelled song under the
breaker's thresholds, which this design accepts dropping without a hold in the meantime
(operator, 2026-11-14: ship this first, classifier next). This design's distinct reason
string and the manifest's `dropped_tracks` are what let that pass find every drop.

## Left to the builder

The reason string, the flag wording, where in `compute_gather` the rule sits (within the
constraints above), the field's exact key names, and test layout.

## Measurements behind this (2026-11-13, show.json titles, not final-title gather)

Script and per-track output: `docs/superpowers/2026-11-13-junk-tag-drop-evidence/`
(`measure.py`, `drops.tsv`: 960 rows, 508 A / 431 B / 21 C, 19 held). This is the baseline
acceptance compares against.


- Rule A alone (four exact words): 424 tracks / 341 shows; with combinations 508 / 374.
- Rules A-C: ~960 tracks / 699 shows; 678 delivered, 146 voiced (92 Voxtral, 54 mlx_audio).
- Breaker variants tested: 2-of-3 at 7 min 16 holds; at 6 min 19; at 5 min 26; boundary
  exemption would have left 4.
- Operator listened to the 15 longest candidates: most were mislabelled, chiefly by wrong
  archive.org data (e.g. `yondermountainstringband-2006-08-25`: tags off by one, the encore
  labelled `outro`).
