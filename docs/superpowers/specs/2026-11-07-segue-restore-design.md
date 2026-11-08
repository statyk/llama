# gather segue restore: design

Date: 2026-11-07. Status: draft for review. Review mode: **Opus** (Shawn, 2026-11-07).
Supersedes the direction in `docs/superpowers/2026-11-07-needs-llm-segue-keep/handoff.md`
("keep stored segues"), which Shawn dropped on 2026-11-07 after the evidence below.

## Stakes

The change is to gather's segue decision, so it touches every show gathered or reprocessed from now
on. Most immediately it touches the campaign's 621 needs-LLM shows (332 station copies, 20 of them
voiced; 289 library-only), which stay off air until they're reprocessed. **Segues are a loose surface**
(Shawn's rulings: "an occasional miss is acceptable"). A wrong segue airs as a wrong `>` in the
setlist and may be mentioned in a DJ script. Nothing is lost that a later re-gather can't fix.
**Strict surfaces this change must not touch:** the audio track list (which files air), titles, and
set/encore labels. The rule changes only `segue` flags. It never deletes or overwrites user data
beyond what gather already rewrites (`show.json`), and it makes no LLM call.
**Strict surface added by goal 2:** clearing a voiced station copy's `awaiting_fix` mark puts it back
on air. It must clear only a show whose station-vs-library differences are segues alone, and only
through `clear-mark`'s existing path; a wrong clear airs a show whose songs or titles were awaiting a
fix.

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
strong and was already inside gather's own inputs. China Cat > Rider is in every description and in
setlist.fm (`China Cat Sunflower[>]`), and the LLM dropped it anyway. On 2016-07-15 the selected
tape's own track titles are `Slipknot! >` and `Terrapin Jam >`, and that show shipped on the
**deterministic** alignment (`structure.alignment = "deterministic"`). So this isn't only an LLM
problem. Any path can drop a segue the inputs plainly carry.

The adjudicator isn't the place for this. Re-gathered shows mostly come out cleared, and a segue
change raises no flag, so it never sees them. It refuses stale shows. And its only structure edit
replaces the whole layout and drops every segue (adjudicator spec, "Verdict schema").

## Goals

1. **A segue restore pass** at the end of gather's structure decision. It only adds segues, never
   removes one, and makes no LLM call. Where gather's own inputs clearly carry a segue that the chosen
   alignment dropped, it puts the segue back.
2. **Voiced shows: clear, keep the voicing, list them** (Shawn, 2026-11-07: option 2 of three).
   llama never writes a voiced station copy: `reapply` re-packages the library only, and the station
   copy keeps its old segues and its `awaiting_fix` mark. For a reprocessed show whose station copy
   is voiced, and whose station-vs-library differences (`station_mark.manifest_differences`, the
   check `clear-mark` uses) are **segues only**, the mark is cleared as `llama clear-mark <slug>
   --accept-change` clears it today. The show goes back on air with its old segues and old DJ audio
   (Shawn: skip re-voicing). Each such show is appended to a durable **voiced-segue list** that Shawn
   can read later and re-voice from by hand: slug, presenter, each differing segue as
   `index title station → library`, and whether the library briefing was rewritten (`brief` fresh
   vs reuse), so he can weigh the old voicing against it.
   - Scope (my call): only reprocesses that commit (`reapply ... --allow-structure-change`, as the
     waves run). A row reapply skips as `structure changed` is not cleared and not listed.
   - Any other difference (a song, title, set, break, duration or briefing field in `COMPARED`)
     disqualifies the show: it stays marked and goes through the existing route.
   - Who clears it, `reapply` itself or a campaign step that runs `clear-mark --accept-change` over
     the list, is the builder's call. Either way the clear goes through `clear-mark`'s existing code
     path (emcee-running refusal, show lock, `campaign.json` `clears` entry with outcome
     `change accepted`), never a new station write.
   - Today this is 20 shows: 17 funk (jamesbrown), 2 indie (kurt), 1 bluegrass (monroe), all marked
     for needs-LLM.
3. **A measurement** that proves the rule before release (see Measurement).

## Non-goals

- Keeping stored segues (the dropped direction).
- Changing the adjudicator.
- Blocking or removing segues the alignment adds. The sample's adds were right (4 of 4).
- Re-running the 621 needs-LLM shows. That's campaign work after the release; the campaign handoff
  owns it.
- Re-voicing anything.
- A web lookup or any new evidence source. The rule reads only what gather already has.

## The rule

It runs once, after the final set labels are decided and after `donor_segues`, on every path that
computes segues: deterministic, LLM-won (`alignment == "llm"`), sibling-aligned and taper-owned. It
does **not** run on the structure-override path, where an override deliberately drops every segue
(adjudicator spec and `llama fix` help: "Any structure override loses every segue").

Track `k` (not the last track) whose shipped segue is False gets `segue = True` when **either**
evidence holds and the add guard passes:

- **E1, the taper's arrow (every path):** the track's own title ends in a segue arrow
  (`junk.TRAILING_ARROW`, `-*>\s*$`). The title is the shipped title, as gather now sets it.
- **E2, the deterministic decision (only where `alignment == "llm"`):** the segues the
  deterministic path would have shipped, i.e. `align(tracks, canonical)` followed by
  `donor_segues` exactly as the non-LLM branch runs it (with the final shipped sets), say True for
  track `k`. On the non-LLM paths E2 is not computed: there the shipped segues already ARE that
  decision, and re-adding the canonical's pooled marks would undo FW4 item 2's deliberate
  removals (the repeated-title mis-pooling cases, `Crazy Mona`, `Turbin`). The builder check
  (2026-11-07) found this; it is my call, not Shawn's.

**Add guard:** reuse `donor_segues`' `may_add`. The track isn't the show's last, and either the
shipped set labels put it in the same set as the next track or its title ends in `>`. Also, a mark
whose next track `_leads_with_filler` (G5's dangling-segue test) is not added. E2 already sees
G5-cleaned donors; E1 needs the check explicitly, because `Ripple >` before `Crowd` is track flow,
not a segue.

The rule writes only `segue`. Sets, `matched`, coverage, conflicts, titles and flags are untouched.

When it adds at least one segue, gather records an operator note in the show's structure notes (the
existing `op_notes` list or its equivalent): `segues restored from <evidence>: <titles>`. That keeps
the change visible in `llama show` and in replay diffs. The wording is the builder's call.

### Expected effect on the sample

China Cat (E2, setlist.fm `[>]`), Slipknot! > and Terrapin Jam > (E1) come back. None of the 9 good
changes is a drop of a segue that E1 or E2 supports (the lettuce drops were stored segues one track
off; Uncle John's Band has no `>` in any source). So none of them is undone, because the rule never
removes. The measurement checks both claims, not this paragraph.

## Measurement

1. **Offline, no LLM:** the 10 spot-check shows replayed with the rule, in the replay harness, or by
   gather against the cache with a recorded LLM alignment where one is needed. The builder picks
   which; the current `show.json` holds the LLM alignment's output and can stand in for it. Pass:
   the 3 wrong drops are restored, none of the 9 good changes is reverted, and no other segue on the
   10 shows changes without the result saying why.
2. **Library-wide, no LLM:** a replay over every library show that gathers without an LLM call today
   (the campaign's clean classes). It counts the segues the rule would add, by evidence (on these shows only E1 can fire, since E2 needs an LLM-won alignment),
   with a hand-check sample of about 20 adds. This sizes the rule's reach outside needs-LLM. Clean
   shows that would change are reported, not reprocessed. Whether to sweep them is Shawn's call after
   the numbers.
3. **Live sample:** about 37 held needs-LLM shows (the 10-27 trial's size; ~0.2 points of the 5-hour
   meter each, under usage pacing), re-gathered with `--with-gather-llm` in a scratch copy. Nothing is
   delivered. Report the adds and drops versus stored, and the rule's restores, with a hand-check of
   every restore and a sample of the remaining drops.

## Constraints

- No new constants or thresholds. The guard reuses `may_add`, `TRAILING_ARROW` and
  `_leads_with_filler` as they are.
- The rule is one function, unit-tested on its own, plus a gather integration test per path
  (deterministic, LLM-won, donor, taper-owned, and override as the case where it must not run). Use
  fixtures built from the three real cases above.
- The suite stays offline and deterministic (`pytest -q`).
- Ships in v2.23.0 alongside the adjudicator (the release is held for this).

## Left to the builder

- Where exactly the pass sits in `compute_gather`, as long as it follows the final sets and
  `donor_segues`.
- The note wording, and the voiced-segue list's file location and format. A file under the batch
  directory, next to `progress.jsonl`, plus a stable aggregate path, is the suggestion.
- How the offline measurement stands in for the LLM alignment.
