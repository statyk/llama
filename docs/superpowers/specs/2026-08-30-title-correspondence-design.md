# Title correspondence: resolving untagged tracks from the setlist

Status: approved design, not yet implemented.
Date: 2026-08-30.

## The problem

An untagged tape whose songs are fully documented still ships with filenames as
titles. `yondermountainstringband-2005-12-31` is the motivating case: the chosen
recording `ymsb2005-12-31.flac16.wav` has 24 mp3 files with **no embedded tags**
(`title_fraction` 0.0), while the item's own description parses to **25 correct
setlist items at `confidence="high"`**, setlist.fm agrees, and a sibling
archive.org item for the same performance is fully and correctly tagged.

Every one of the 24 tracks shipped `title_source="unresolved"`, the show was
held, and clearing it by hand means 24 `llama fix --set-title N=...` calls.

The information is present in three sources. The only thing missing is the
**correspondence**: 25 songs map onto 24 files because the tape merges three
pairs and adds two untitled filler tracks (a 1:56 intro at the head of set 2,
3:06 of crowd noise before the encore).

### Why every existing rung declines

- `titles.py:129` — the setlist rung requires exact whole-tape count equality:

  ```python
  aligned = setlist.items if (setlist.confidence != "low" and len(setlist.items) == n) else None
  ```

  25 != 24, so it is skipped. **Measured: across the 89-show library / 2,015
  tracks, `title_source` counts are tags 1917, unresolved 75, sibling 21,
  override 2, and `setlist` 0.** That rung has never fired once. Exact count
  equality between a parsed description and a tape's file list is close to a
  measure-zero event.
- `titles.py:148` `_sibling_titles` carries the same exact-count requirement, so
  the correctly-tagged sibling is rejected too (28 tracks vs 24 — a genuinely
  different split, where positional transfer would be wrong).
- `_recover_format_titles` declines: the item has no tagged lossless copy.
- Deterministic `structure.align()` scores **0.0** — it matches on `t.title`,
  which here is a filename.

The downstream `research asserts unknown song` flags (24 of them on this show)
are a pure cascade: `vet_research.py:110` builds its known-song vocabulary from
the track titles, so with filenames as titles every asserted song is unknown.

## Evidence

Everything in this section was measured during design. Numbers are load-bearing;
do not restate them from memory without re-measuring.

### What was tried and rejected

**LLM-sourced titles.** `AlignedTrack.matched_title` already carries a song name
per track, and `apply_llm_alignment` (`structure.py:949`) reduces it to a bool
and discards the string. Adopting it — guarded by a monotone claim-once walk
requiring exact `fuzzy_norm_title` equality against canonical items, consecutive
indices for chains, and a same-set cross-check — was designed, then measured
against a real `align_structure` call on the motivating show:

- The model returned **zero** `>`-chains (the prompt asks for a singular
  "canonical song title") and did a naive positional 1:1 walk that ignored merges
  entirely, despite durations being in the prompt.
- It shifted by one at the first merged track and stayed shifted through set 1.
- Final tally against ground truth: **12 ok, 8 wrong, 2 partial, 1 wrong-stolen
  onto a filler track, 1 correct decline.**
- **Every one of the 9 wrong titles passed the proposed walk** — monotone,
  claim-once, exact canonical text, same-set. A uniform off-by-one shift
  satisfies all of those properties by construction. The guard verified
  consistency; the failure was consistent.
- `coverage` read 0.958 while 9 titles were wrong. **Coverage counts matched,
  not correctly matched.**

Ruling: the LLM aligner is good at coarse structure (it got the set breaks right)
and bad at fine per-track correspondence. Titles need the latter. Do not source
titles from a model's fine-grained judgement.

### What the blind-the-tags experiment showed

Take every well-tagged cached item that has an item-count mismatch, hide the
tags, run a deterministic correspondence DP, and score against the hidden tags as
ground truth. This is the instrument that decides the design.

| approach | population | wrong |
|---|---|---|
| duration DP on ymsb2005-12-31 alone | 1 show | 0/24 |
| duration DP, blind-the-tags | 258 shows, 5,470 adoptions | **45-52%** |
| same, restricted to margin >= 240 s | same | 41.8% — margin does not discriminate |
| same, with item-hygiene gate | 213 shows | 44.3% — gate does not help |
| sibling-duration DP, tape vs tape | 68 pairs, 10,412 trials | 20%; margin sweep floors at 6.4% |
| **anchored count-forced gap-fill** | 1,652 firings, 3,144 adoptions | **2.4% interior, 1.5% edge** |

The single-show 0/24 was real but conditional on properties the mechanism cannot
verify from inside itself: a clean 25-item parse, and merges that happen to be
duration-conspicuous (a 750 s file among 300 s songs).

The failure mode at scale is **the same off-by-one shift the LLM made**, in
deterministic clothing: one junk item near the head (`'Set List:'`, a
comma-split `'Oh'` + `'The Wind and Rain'`), the DP absorbs it with one spurious
merge, and every downstream title is consistently and cheaply wrong. On
homogeneous ~4-minute material a uniform shift costs almost nothing in duration
terms, which is why margin cannot see it. This is the third instance in this
design of a confidence metric that is blind at exactly its own boundary; the
tail-guard evidence docs record the first two.

A side finding worth keeping: several "wrong" gap-fill adoptions are **tag typos
that the adoption corrects** — `Loset` -> `Loser`, `Supplictaion` ->
`Supplication`, `Senor` diacritics, `Lazy Lightnin'` / `Lazy Lightning`.

**Standing caveat on all of the above.** The pilot ran on raw `parse_setlist`
output, not the real gather canonical (`rank_parses` ->
`_strip_head_banner` -> `_drop_artist_items` -> `blend_segues`). The failure it
describes is head junk, which is precisely what `_strip_head_banner` exists to
remove, so the 45-52% figure is probably pessimistic. The **relative** comparison
survives regardless: anchored beat unanchored by roughly 20x under the same
instrument. M1 below exists to redo this properly.

### Population

- After `_recover_format_titles` (which already fixes 46 of 58 untagged cached
  items), the whole cache contains exactly **2** whole-tape candidates.
- The library's remaining unresolved inventory is **75 tracks across 6 shows**:

  | show | unresolved / tracks |
  |---|---|
  | `yondermountainstringband-2002-12-31` | 38 / 38 |
  | `yondermountainstringband-2005-12-31` | 24 / 24 |
  | `delmccouryband-2003-04-19` | 8 / 21 |
  | `infamousstringdusters-2014-03-15` | 3 / 28 |
  | `greenskybluegrass-2007-08-05` | 1 / 20 |
  | `trampledbyturtles-2007-07-20` | 1 / 25 |

- Piece 1 reaches **<= 5 tracks** today. Piece 2 reaches effectively all of them.

## The ruling this design rests on

**Unanchored monotone correspondence — from parsed text or from sibling
durations — is not auto-adoption grade**, by the same evidence standard that
killed the LLM approach. The one evidence class that measured at tag-rung
reliability is *count-forced gaps between tag-verified anchors*.

Everything weaker requires a human. The human's decision lands in
`overrides.json`, where it is durable and auditable.

## Piece 1 — anchored gap-fill rung (automatic)

### Placement

In `run_gather` (`stages/gather.py`), between the `resolve_titles` call at line
594 and the `overrides.titles` loop at line 599. Operator overrides therefore
still win, and everything below — `align()`, the closer tripwire, the spans
check, the flags block — sees the adopted titles.

### Mechanism

A new pure function locates maximal runs of `title_source == "unresolved"` tracks
whose flanking tracks matched canonical items, and adopts item titles 1:1 into
the run.

It **reuses the existing matching-layer primitives** — `fuzzy_norm_title`,
`title_components`, `_merge_run`, `_window_match`, `_window_hi` — rather than
reimplementing a walk. It lives in `structure.py`, beside `apply_llm_alignment`:
this is a matching-layer concern, and CLAUDE.md is explicit that fuzzy matching
stays at that layer.

### Adoption conditions — all required

1. **Count-forced.** The gap's canonical-item count exactly equals its file
   count. No merges, no fillers, no skips are needed to make it fit. This is the
   whole safety argument: with the count forced, there is no assignment freedom
   for a shift to hide in.
2. **Anchored.** Both flanking tracks are real matches (interior gap), or the run
   touches a tape edge with the other anchor real.
3. **Hygiene**, per adopted title: passes `titles.is_real_title`; is not junk
   per `setlist._is_junk_title`; is within `setlist.MAX_TITLE_LEN` (80); does not
   end in `:`; and is not show-metadata residue — a "song" titled like the venue
   is a banner line, not a song.

Anything else leaves the track `unresolved`, exactly as today.

No margins and no scoring. Scoring measurably cannot carry this decision.

### Interface and layering

Two constraints the implementation must respect, both discovered during spec
review:

- **`_show_metadata_norms` lives in `gather.py` (line 321), not `structure.py`.**
  `structure` importing `gather` would invert the layering and create a cycle, so
  the norms set is **passed in as a parameter**. Signature shape:

  ```python
  def adopt_gap_titles(tracks, canonical, aligned, *, metadata_norms) -> list[Track]
  ```

  `gather` already computes `metadata_norms` for the head-banner strip and can
  hand the same set down.
- **`_is_junk_title` and `MAX_TITLE_LEN` are in `setlist.py`, which does not
  import `structure.py`** — so `structure -> setlist` is acyclic and safe.
  `_is_junk_title` is private, though; **promote it to `is_junk_title`** rather
  than reaching across a module boundary into a private name. Keep the old name
  as an alias only if the diff would otherwise be noisy.

### Surfaces

- New `title_source` value **`"setlist-gap"`**. Add it to the enumerating comment
  at `models.py:157`. The CLI's width-14 column (`cli.py:660`) already
  accommodates it.
- The dead rung at `titles.py:129` **stays**, with a comment recording the
  measurement (`0 of 2,015 tracks in the 89-show library, 2026-08-30`) so nobody
  re-diagnoses it. House style; the codebase annotates its inert branches.
- Partial adoption is a **good** outcome. A show going from 24 unresolved to 2 is
  an honestly smaller hold, not a false clear.

## Piece 2 — proposal and one-shot adoption (assisted)

This is the piece that answers the actual complaint: *"avoid having to manually
label 24 tracks of a show when the data is right there."*

### Interface

- `llama fix <show> --suggest-titles`
- A corresponding resolution inside `llama triage`, offered when a held show's
  flags include `unresolved track titles`.

### Behaviour

Run the full correspondence DP using **every** evidence source available:
canonical items with their set and segue structure; segue-gated merge candidates;
a per-track duration cost model; per-track durations lifted from a tagged
same-performance sibling when one exists; and per-track margins.

Render the proposal as a table — track number, duration, proposed title(s),
evidence, margin — and require confirmation. On confirmation, write every title
into `overrides.json`'s `titles` map in one shot.

Because `overrides.titles` is set, this is a `did_meta` edit in `fix`'s existing
classification, so the auto-redo runs **from `gather`**, exactly like the other
metadata flags. No new redo plumbing.

Merged files use the existing `"A > B"` convention: `title_components` parses it,
`vet_research._known_song` handles chains, and `audio.packaged_filename`
sanitizes `>` to `_`.

### Why this shape

The human **is** the decline rule, so the DP does not need corpus-calibrated
safety. It needs to be right most of the time on the handful of shows where it is
invoked, and visibly wrong when it is not. It writes to the one durable,
auditable operator input the design already has, needs no new `title_source`, and
converts 24 invocations into one confirmation.

Verified: it produces the exactly-correct 24-row table for
`yondermountainstringband-2005-12-31`.

### The segue prior

Descriptions mark segues with `>`, and `parse_setlist` already captures this as
`SetlistItem.segue`. On the motivating show there are 9 segue-marked items, and
**all three merge points land on a segue-marked item**. The arithmetic pins the
count (25 items, 24 files, 2 filler tracks => exactly 3 merges), reducing the
search to C(9,3) = 84 candidates, which durations then disambiguate. The segue
gate is a candidate-space prune, not a safety guarantee.

### When the DP cannot decide

`yondermountainstringband-2002-12-31` is the honest negative case: 9 segue markers
against 13 needed merges, junk parse items, and a 994 s medley make the DP
infeasible. It must render **"no consistent correspondence — parse quality too
low"** rather than a guess.

**A partially-feasible show renders a partial table**: the rows the DP is
confident about are proposed, the rest render as `(unresolved — hand-edit)`, and
confirmation writes only the proposed rows. Declining wholesale would leave the
`2002-12-31` class with 38 manual edits when some subset is recoverable. Only a
show with *no* usable canonical at all gets the flat decline message.

## How the two pieces relate

One mechanism — a monotone assignment where each file consumes 0..3 canonical
positions — with pluggable cost evidence.

Text-side and sibling-duration-side evidence are **not** substitutes. The text
side is junk-prone and has no durations; the sibling side has durations on both
sides and no junk items, but transfers differ and partial or differently-cut
donors are common (20% wrong, measured). Neither survives as an autonomous rung.
Both survive as proposal generators inside Piece 2, where sibling durations
sharpen the display (on the motivating show, total drift 634 s vs 2,188 s for the
duration-model-only variant) and the segue gate prunes candidates.

Fallback order inside a Piece 2 proposal: sibling durations when a tagged sibling
exists, else the duration model; both always segue-gated.

## Failure modes

A wrong title propagates to manifest v3 `tracks[].title`, the ID3 `TIT2` frame
via `audio.tag_audio`, the packaged filename via `audio.packaged_filename`, the
briefing, and emcee's scriptwrite. The terminal cost is a DJ confidently
announcing a song that was never played.

**Both factual guards are structurally blind to it.**
`brief.briefing_guard` checks the briefing's mentioned songs against the
tracklist, and emcee's `script_guard` does the same against the manifest — both
define truth by the very field that is wrong.

One partial backstop exists: `vet_research.grounding_flags` checks *independent
web research* against the tracklist, so a wholesale-shifted tracklist would trip
`research asserts unknown song` holds. It needs >= 2 unknowns and more than a
third of asserted songs unmatched, so a single wrong title sails through.

Hence the posture: **the only silent adopter is the evidence class measured at
tag-rung reliability.** The residual wrong class even there — a filler file
stealing a real song title, e.g. `Tuning` -> `Blues For Allah` — is what M1's
hand-triage must characterize before Piece 1 ships unflagged.

## Testing

**Piece 1, unit** (`test_structure.py`): count-forced interior gap adopts; a gap
whose counts do not match declines whole; an unanchored run (missing flank)
declines; an edge run with one real anchor adopts; each hygiene rule rejects its
case; a track carrying an `overrides.titles` entry is untouched.

**Piece 1, integration** (`test_stage_gather.py`): using the existing
`FakeProvider(completes=[...])` pattern at line 224, a mixed show adopts its gap
and leaves the rest unresolved; a fully-tagged show is byte-identical.
`test_gather_low_coverage_uses_llm_alignment` is unaffected by construction — it
wrecks titles to `"Track N"`, which passes `is_real_title`, so those tracks are
`tags`-sourced and never enter the gap scan.

**Piece 2** (`test_cli.py`): `--suggest-titles` on a fixture writes the expected
`overrides.titles` map and triggers a redo from `gather`; declining writes
nothing; an infeasible show renders the decline message and exits without
writing. Capture `ymsb2005-12-31.flac16.wav` via `scripts/capture_fixture.py` as
the fixture — a real 24-file untagged tape against a 25-item description.

**Downstream, pinned**: adopted titles make the closer tripwire, the spans check,
and `vet_research.grounding_flags` live where they were previously inert on these
shows. That is desirable, and at least one test must pin it so the behaviour
change is owned rather than discovered.

## Measurement gates

Held to the standard of `docs/superpowers/2026-08-03-tail-guard-sanity-check.md`:
run the real functions over the real corpora, index by index, with an in-repo
evidence doc.

- **M1 — gates Piece 1.** Promote the blind-the-tags harness to evidence-doc
  standard: run on **real gather canonicals** (`rank_parses` winner plus
  `_strip_head_banner`, `_drop_artist_items`, `blend_segues`), not raw
  `parse_setlist`; both corpora plus the cache. **Hand-triage every wrong
  adoption** into {scorer artifact, tag typo where adoption is superior,
  genuinely wrong}. Ship unflagged only if genuinely-wrong is at or below the tag
  rung's own typo baseline; otherwise ship flagged, or not at all. Standing
  caveat: offline runs have `setlistfm=None` while the real canonicals for
  several of these shows were setlist.fm-won, so offline numbers are bounds, not
  truth.
- **M2 — gates both.** Full-library offline re-gather asserting **zero changes**
  to any currently-resolved track.
- **M3 — gates Piece 2.** Render proposals for all 6 held shows and check them by
  hand.

## Out of scope, filed not built

- **Audio-level evidence** (silence detection or fingerprinting against a tagged
  sibling). The only evidence class that could safely crack the whole-tape case
  autonomously, but it needs downloaded audio, ffmpeg analysis, and a new
  dependency class for ~2 shows.
- **Parser micro-fixes** that would raise yield for everyone, each a
  known-hazard-class change requiring its own corpus re-measurement:
  comma-splitting inside parentheses (`"Hoffman's Tune (new, unnamed song)"`
  should be two items — greensky's actual bug); `~` in `_LEAD_DECOR`
  (`'~Set 02~'` unrecognized — stringdusters' off-by-one); `vox` in
  `_CREDIT_INSTR` and `taped by` in `_RIG` (trampled's banner survived the head
  guard).
- **Re-running `align()` after adoption** to recover `conflicts` and
  `merge_conflicts`, which `apply_llm_alignment` never populates. Measured dead:
  16 library shows carry a merged track and **none** is `alignment == "llm"`, and
  both mixed LLM-aligned shows are single-set with no merges. Fable's alternative
  — a coverage cross-check between a second deterministic pass and the LLM's
  claim — is a genuinely different diagnostic and gets its own ticket.
- **Widening manifest v3** to carry `title_source`. emcee would not hedge
  per-track anyway, and it touches the cross-tool contract for a field with no
  consumer. `show.json` keeps per-track `title_source` as the audit record.
- **The junk-filter duplicate-directory gap.** `filter_files` kept 56 files for
  28 tracks on `ymsb2005-12-31.flac16` — the same set at top level and under a
  subdirectory. Real, unrelated to this design, and fixing it does not revive the
  sibling rung here (28 tagged tracks vs 24 kept still fails the exact-count
  test).
