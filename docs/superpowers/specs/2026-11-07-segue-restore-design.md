# gather segue restore: design

Date: 2026-11-07. Status: draft for review. Review mode: **Opus** (Shawn, 2026-11-07).
Supersedes the direction in `docs/superpowers/2026-11-07-needs-llm-segue-keep/handoff.md`
("keep stored segues"), which Shawn dropped on 2026-11-07 after the evidence below.

## Stakes

The change is to gather's segue decision, so it touches every show gathered or reprocessed from now
on. Most immediately it touches the campaign's 621 needs-LLM shows (332 station copies, 20 of them
voiced; 289 library-only), which stay off air until they're reprocessed. Beyond them, E3 adds
segues on a couple of hundred other library shows the next time each is re-gathered (an offline
estimate from the 2026-11-07 review with a slightly different E3; Measurement 2 gives the real
number), and each such show then reads as
`structure changed` in `reapply` and loses briefing reuse (one fresh brief call). Those shows are
not swept by this work; see Measurement 2. A v2.23.0 campaign arm would show each as a visible
`segues` change and `mark` would take delivered copies off air, so Measurement 2 counts them by
state and Shawn decides before any `mark --apply`. **Segues are a loose surface**
(Shawn's rulings: "an occasional miss is acceptable"). A wrong segue airs as a wrong `>` in the
setlist and may be mentioned in a DJ script. Nothing is lost that a later re-gather can't fix.
**Strict surfaces this change must not touch:** the audio track list (which files air), titles, and
set/encore labels. The rule changes only `segue` flags. It never deletes or overwrites user data
beyond what gather already rewrites (`show.json`), and it makes no LLM call.

## Why

On 2026-10-27 Shawn held the needs-LLM class out of the campaign waves because re-running gather
(including its `align_structure` LLM step) churned segues both ways. The trial had 37 shows; 17
changed, with 19 segues added and 17 dropped. The candidate fix was to keep the stored segues.

On 2026-11-07 the 14 segue changes surviving in the trial spot checks
(`~/.llama-harness/bulk/spot-{dead,funk}-llm-v3.txt`; the pre-trial `show.json`s were overwritten
and the 37 trial shows now air with the re-run's segues) were judged against the archive.org
descriptions and setlist.fm in `~/.llama/cache`:

| Show | Change (stored → re-run) | Right side |
|---|---|---|
| deadandcompany-2015-11-10 | Row Jimmy +>, Drums +>, Space +>, Uncle John's Band −> | re-run (4) |
| lettuce-2008-08-06 | 5 drops (the stored list was missing a track; its segues sat one track off) | re-run (5) |
| deadandcompany-2015-10-31 | China Cat Sunflower −> | stored |
| deadandcompany-2016-07-15 | Slipknot! −>, Terrapin Jam −> | stored (2) |
| robertrandolphandthefamilyband-2005-05-29 | 2 drops; the re-run also lost the titles, show held | unclear |

The re-run was right 9 times and the stored side 3 times. Keeping stored segues would have undone 9
correct changes to save 3. The 3 wrong drops have one thing in common: the evidence for the segue is
strong and was already inside gather's own inputs, and none of the three is the LLM's fault alone:
- **China Cat > Rider** is in every description and in setlist.fm (`"info": ">"`), but gather never
  sees it as a segue. `from_setlistfm` (`structure.py:511`) writes `segue=False` for every song and
  never reads `info`. `blend_segues` pools donor marks by exact title, so `China Cat Sunflower bw`
  doesn't pool. And the donor's own alignment is used up by a copied block at the head of its
  description. The deterministic decision itself says no segue (spec review, 2026-11-07, run
  offline against the cache).
- On **2016-07-15** the selected tape's own track titles are `Slipknot! >` and `Terrapin Jam >`. Those
  two drops are invisible on air: every setlist renderer (`transmitter/site.py` `_setlist_line`,
  `antenna/public/assets/notes.js` `setlistLine`) shows a title ending in an arrow as a segue
  whatever the flag says, and emcee and brief read the arrow in the title. So the rule doesn't
  touch them. Restoring the flag from the title would flip about 1,400 flags on about 600 shows,
  with no effect a listener sees and with real churn (structure-changed rows, lost briefing
  reuse, adjudicator restores).

So the one drop a listener hears is China Cat, and the cause is upstream of the LLM. The largest unused input is setlist.fm's own
marks: in `~/.llama/cache`, 3,536 of 52,885 setlist.fm songs (6.7%) have an `info` beginning with
`>`, 3,053 of them exactly `>`, and gather has never read one.

The adjudicator isn't the place for this. Re-gathered shows mostly come out cleared, and a segue
change raises no flag, so it never sees them. It refuses stale shows. And its only structure edit
replaces the whole layout and drops every segue (adjudicator spec, "Verdict schema").

## Goals

1. **A segue restore pass** at the end of gather's structure decision. It only adds segues, never
   removes one, and makes no LLM call. Where gather's own inputs clearly carry a segue that the chosen
   alignment dropped, it puts the segue back.
2. **The 20 voiced needs-LLM shows are re-voiced** (Shawn, 2026-11-07: "I'll end up revoicing them";
   most are on local Qwen, so a re-voice is cheap). Nothing new is built for them. After a reprocess
   they take the existing route, `llama deliver <slug> --replace-voiced` then `emcee run`, as
   campaign work. Today they are 17 funk (jamesbrown), 2 indie (kurt) and 1 bluegrass (monroe).
3. **A measurement** that proves the rule before release (see Measurement).

## Non-goals

- Keeping stored segues (the dropped direction).
- Changing the adjudicator. Its staleness check compares filenames only, so it would judge a held
  show the pass changes, and its apply's re-gather would read the add as an unpredicted segue
  change and restore (`adjudicator/apply.py` `whole_show_diff`). So the campaign re-gathers held
  shows on v2.23.0 (`reapply --allow-structure-change`) **before** adjudicating them, and `before`
  already carries the adds. That ordering goes into the campaign handoff; nothing in the adjudicator changes.
- Setting the flag from a title that already ends in an arrow (it already renders as a segue).
- Blocking or removing segues the alignment adds. The sample's adds were right (4 of 4).
- Re-running the 621 needs-LLM shows. That's campaign work after the release; the campaign handoff
  owns it.
- Any new route for voiced station copies (clearing their marks, writing their manifests).
- A web lookup or any new evidence source. The rule reads only what gather already fetches
  (setlist.fm's `info` is in the response gather already caches).
- Changing `from_setlistfm`, `blend_segues` or canonical ranking. setlist.fm's marks enter through
  the restore pass only (E3), so canonical choice, title rungs and the LLM prompt are unchanged.

## The rule

It runs once, after the final set labels are decided and after `donor_segues`, on every path that
computes segues, i.e. every `structure.alignment` value except `override`: `deterministic`,
`jerrybase`, `taper` and `llm`. It does **not** run on the structure-override path, where an override deliberately drops every segue
(adjudicator spec and `llama fix` help: "Any structure override loses every segue").

Track `k` (not the last track) whose shipped segue is False, and whose title does **not** already
end in an arrow (`junk.TRAILING_ARROW`; such a title already renders as a segue), gets
`segue = True` when either evidence holds and the add guard passes:

- **E2, the deterministic decision (only where `alignment == "llm"`):** the segues the
  deterministic path would have shipped, i.e. `align(tracks, canonical)` followed by
  `donor_segues` exactly as the non-LLM branch runs it (with the final shipped sets), say True for
  track `k`. On the non-LLM paths E2 is not computed: there the shipped segues already ARE that
  decision, and re-adding the canonical's pooled marks would undo FW4 item 2's deliberate
  removals (the repeated-title mis-pooling cases, `Crazy Mona`, `Turbin`). Accepted limitation: the
  LLM branch runs only when that deterministic alignment fell under the coverage threshold, so E2
  reads an alignment gather already judged weak. That's fine for a loose surface; Measurement 3
  hand-checks it.
- **E3, setlist.fm's mark (every path, when setlist.fm returned a setlist):** `align()` of the tracks
  against a setlist.fm parse (with `aliases=family_aliases`, as every structure `align()` in
  `compute_gather` passes) matches track `k`, and the matched song is marked. The parse keeps the
  same songs `from_setlistfm` keeps, goes through `build_canonical`'s `clean()` like the canonical,
  and gives no E3 when it has under 5 items (the stub rule). A song is marked when its `info`
  **ends** in an arrow (`junk.TRAILING_ARROW.search(info)`). That catches `>`, `->` and setlist.fm's
  joined form `John Mayer on lead vocals) (>`. It excludes `> 'Bridgeless' reprise` and other
  forms that only start with an arrow: those say the song went into something, which flows into
  the next track only when the tape split it out, and offline they misfired (`In the Kitchen` →
  `Come Closer`). A merged track takes its last component's mark, as `align()` already does.
  **Not where the donor said no:** when `CanonicalBuild.segue_donor`'s own alignment matches track
  `k` with no mark, E3 doesn't add. The donor is a taper's description, and Shawn's standing
  accuracy steer is that tape notes stand unless there's clear contrary evidence (this also keeps
  FW4 item 2's `Turbin` removal). Offline, 56% of E3's candidate adds fell there. Measurement 2
  reports them as a separate count so the call can be revisited with numbers.
  This is the China Cat case (Shawn, 2026-11-07: option 1). `CanonicalBuild` carries the marked
  setlist.fm parse alongside its existing fields, and nothing else reads it.

**Add guard:** reuse `donor_segues`' `may_add`. The track isn't the show's last, and either the
shipped set labels put it in the same set as the next track or its title ends in `>`. Also, a mark
whose next track `_leads_with_filler` (G5's dangling-segue test) is not added: `Ripple >` before
`Crowd` is track flow, not a segue. `may_add` is a closure inside `donor_segues` today; it becomes
a module-level helper both call, with no change in behaviour (the existing donor tests pin it).

The rule writes only `segue`. Sets, `matched`, coverage, conflicts, titles and flags are untouched.

When it adds at least one segue, gather appends one line to `op_notes` (notes.json; **not** the
structure `notes`, which flow into `StructureInfo.conflicts`, show.json and the briefing input):
`segues restored: track <n> '<title>' (<evidence>); ...`. The wording is the builder's call.

### Expected effect on the sample

China Cat comes back (E3; checked offline). Slipknot! > and Terrapin Jam > already render as segues
from their titles. None of the 9 good changes is a drop of a segue the evidence supports (the
lettuce drops were stored segues one track off; Uncle John's Band has no `>` in any source), and
the rule never removes, so none of them is undone. Expected adds beyond China Cat: `Greazy
Groceries >` and `She's Music >` on dumpstaphunk-2009-02-09 (E2; the selected description has
both), and likely more from E3. The measurement checks all of this, not this paragraph.

## Measurement

1. **Offline, no LLM:** the 10 spot-check shows gathered against the cache twice on the same code,
   rule off and rule on (A/B), with the LLM-won shows fed their recorded alignment (the current
   `show.json`'s segues and sets, mapped **by filename**, not index: current code drops an edge
   `Intro` on lettuce-2008-08-06 and soulive-2009-04-16). Pass: China Cat is restored, none of the 9 good
   changes is reverted, and every other add is listed with its evidence (E2/E3).
2. **Library-wide, no LLM:** a replay over every library show that gathers without an LLM call today
   (the campaign's clean classes). It counts the segues the rule would add (E3 only; E2 needs an
   LLM-won alignment), with a hand-check of about 20 adds drawn across `info` forms (`>`, `->`,
   `) (>`). It also counts, without adding, the E3 marks skipped because the donor said no, with
   about 20 of those hand-checked too, so Shawn can revisit that call with numbers. This sizes the rule's reach outside needs-LLM. Clean
   shows that would change are reported, not reprocessed. Whether to sweep them is Shawn's call after
   the numbers.
3. **Live sample:** about 37 held needs-LLM shows (the 10-27 trial's size; ~0.2 points of the 5-hour
   meter each, under usage pacing), re-gathered with `--with-gather-llm` in a scratch copy. Nothing is
   delivered. Report the adds and drops versus stored, and the rule's restores, with a hand-check of
   every restore and a sample of the remaining drops.

## Constraints

- No new constants or thresholds. The rule reuses `may_add`, `TRAILING_ARROW` and
  `_leads_with_filler` as they are.
- The rule is one function, unit-tested on its own, plus a gather integration test per path
  (`deterministic`, `jerrybase`, `taper`, `llm`, and `override` as the case where it must not run),
  plus a donor case. Use fixtures built from the three real cases above.
- `from_setlistfm`'s existing output is unchanged; E3 reads `info` in its own parse.
- The suite stays offline and deterministic (`pytest -q`).
- Ships in v2.23.0 alongside the adjudicator (the release is held for this).

## Left to the builder

- Where exactly the pass sits in `compute_gather`, as long as it follows the final sets and
  `donor_segues`.
- The note wording.
- How the offline measurement stands in for the LLM alignment.
