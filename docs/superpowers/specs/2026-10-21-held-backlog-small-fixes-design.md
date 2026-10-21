# Held-backlog small fixes: yearless adjacent dates, venue tie-break, `fix` ordering, curly apostrophe

Status: draft for review, not approved, not implemented.
Date: 2026-10-21.
Inputs: the 2026-10-21 overnight Opus adjudication of every held show
(`~/.llama-harness/t3/`: 1,063 verdicts, `synthesis.md`, `bugs-found.md`,
`handoff-design.md`), plus two read-only measurements over the live library
re-run for this spec (venue: 3,982 shows; yearless dates: every
`vetting.json`). Builds directly on the Tier 1 spec,
`2026-10-19-held-backlog-guard-fixes-design.md`, whose slice 4b and strict
list this spec extends and respects.

## Kickoff

**Review mode: Opus** (Opus breadth reviewers and an Opus final branch
reviewer; this is a small, low-risk piece).

**Stakes.** llama feeds an automated radio station; venue and date are spoken
by the DJ and shown to listeners. Strict surfaces in this spec:

- **`llama fix` writing `overrides.json` and dropping stage artifacts** (slice
  C). This overwrites a show's state: today a refused structure edit leaves a
  show with no `show.json` and no CLI route back (`billystrings-2021-12-04`
  needed a hand edit). After this spec, a refused edit leaves every file of the
  show byte-identical to before the command.
- **The date change** (slice A), because it removes holds: a cleared hold
  ships a show nobody looked at. Every newly cleared show's research date
  discussion is hand-read before it ships, as Tier 1 did for 4b.

Ordinary: the venue tie-break (slice B; cosmetic, new gathers only) and the
apostrophe fold (slice D). Tier 1's strict list still binds: `normalize_song`,
`DEFAULT_ALIASES` and every do-not-retune constant named in `CLAUDE.md` stay
byte-identical.

## Where this sits

The adjudication found the held backlog is mostly llama's own gather defects.
The owner (Shawn) split the deterministic work into five pieces, in this order:

1. **This spec:** four small confirmed bugs.
2. The taper's explicit set/encore markers win over unlabelled setlist.fm and
   one-set jerrybase rows (398 shows; the largest cause).
3. Title hygiene: remaining 2b placeholder gaps, unknown-song flags on an
   untitled tape folded into the unresolved hold, lossless originals' tags over
   stale MP3 tags, count-exact description title lists.
4. Junk-filter exemption for segue/reprise pieces (needs an owner ruling; junk
   constants stay put).
5. Partial tapes, better siblings, shifted tags (mostly flags; later).

Each is its own spec. Nothing here may anticipate pieces 2-5.

## Slice A: yearless adjacent-day dates are context, under 4b's own condition

**Problem.** Tier 1's 4b treats a research date within `ADJACENT_DAY_WINDOW`
(1) day of the show's date as context, not a contradiction, when research
also asserts the show's own full date, year included. It only ever applies to
full dates. A yearless date (`Sept 3`, `10/29`, `Nov 1`) is compared in
`vet_research._date_flags` by exact month and day, so a late set that ran
past midnight, which research describes as "the early hours of Nov 1", flags
`research asserts wrong date: Nov 1` even when research also names the show's
full date. The adjudication counted 22 shows with this cause; all were
spurious.

**Rule (owner ruling, 2026-10-21: the stricter of the two options offered).**
When research asserts the show's own **full** date, year included (exactly
4b's `own_full`), a yearless asserted date that resolves to a date within
`ADJACENT_DAY_WINDOW` of the show's date is context and does not flag.
"Resolves" means: try the yearless month-day in the show's year and in the
years either side, so that a 12-31 show with research saying `Jan 1` (or a
01-01 show with `Dec 31`) counts as adjacent. A month-day that is invalid in
every candidate year (`--02-30`) stays flagged, as `_within_window` does today.

Unchanged, and must stay so:

- Without the own full date, every yearless date that is not the show's own
  month-day still flags. A yearless own date (`June 13`) does **not** satisfy
  the condition (**my call** to keep 4b's definition exactly rather than widen
  it). Nothing pins this for 4b today: Tier 1's
  `test_yearless_own_date_does_not_make_a_far_date_context` uses a date two
  days off, which flags under any own-date rule, and only 4a's parametrized
  "own date yearless only" row pins it, for the right-show gate. This spec
  adds the missing pins: `["June 10", "1973-06-11"]` and `["June 10", "June
  11"]` on a 1973-06-10 show still flag.
- 4a's right-show gate keeps reading the date flags computed **without** any
  window (`date_flags_raw`), yearless ones included, so research about an
  adjacent night still cannot clear unknown-song flags.
- Placeholder-date adoption, day-00 handling and full-date 4b are untouched.
- The window stays one day.

**Why the stricter rule.** A one-day misdating of the tape is exactly what
the wrong-date flag exists to catch, and research arguing a misdating usually
names only the date it believes is right. The owner rejected four 4b clears
on disputed adjacent dates at Tier 1's Checkpoint E. The looser rule (no own
date needed) would have cleared about one more show in today's library.

**Expected effect.** Of 30 adjacent yearless assertions found in the library,
19 come with the own full date (the rule applies), 3 with only a yearless own
date and 8 with none (both still flag). Most of the 19 were already overruled
by the overnight run; three are currently held with this date flag, which the
rule removes (other flags may keep them held):
`joerussosalmostdead-2015-06-06`, `philleshandfriends-2006-10-28`,
`thenewdeal-2004-11-26`. Tier 1's within-a-day misdating example,
`derektrucksband-2005-06-17` (research: "June 16"), asserts only a yearless
own date and so stays outside the rule, as intended.

## Slice B: a tied venue vote goes to the selected recording's own string

**Problem.** `grouping._make_candidate` sets the candidate's venue to
`Counter(...).most_common(1)`, which breaks a tie by first-seen order, i.e.
by archive listing order. When the recordings of a performance tie (commonly
1-1 or 1-1-1, every taper spelling it differently), a sibling's string ships
even though the selected recording has its own, and `show.venue_source` reads
`item`. That is how a sibling's truncated or junk-laden string can ship.

**Measured (3,982 shows, `venue_source: item`, selected recording's venue
non-blank):** 3,423 identical; 388 differ but are `venues_equivalent`
(spelling/phrasing: `Ampitheater`/`Amphitheater`, `Ctr`/`Center`), 196 of them
ties; 135 differ and are not `venues_equivalent`, 77 of them ties, and sampled,
nearly all are still one place named differently (`1st Avenue`/`First
Avenue`, a festival vs the park it was held in). So roughly 270 shows are
ties.

**Rule (owner ruling, 2026-10-21).** Keep the consensus. Only on a tie, where
the selected recording's own string has as many votes as the winning string,
the selected recording's string ships instead of the listing-order winner.

Invariants:

- **Tie** is decided with the same keying grouping uses to count (the
  recordings' venue strings, blank ones not counted). No new string
  normalization.
- City follows the swap the way it does in Tier 1's swap and 1c arms:
  `sel_city or vote_city`.
- `venue_source` stays `item`.
- **The tie-break never adds or removes a flag.** 1d (city conflict) and
  `two_venue_signature` keep reading the original vote and the candidate's
  recordings, exactly as today.
- **It applies only where the vote would otherwise ship without a venue
  flag** (my call): no jerrybase event; 1a's blank-jerrybase-venue arm when it
  raises no flag; and step 1, only when the selected string passes step 1's
  **full** test against jerrybase (`venues_equivalent` and, for a pair only 1b
  made equivalent, compatible cities: Narrowing S), so a string jerrybase
  corroborates is never replaced by one it doesn't. It does **not** apply in
  the arms that keep the vote and flag (`two_venue_signature`, the final
  `else`, 1a with conflicting cities): the show is held, and the flag text
  quotes the vote string, which must stay the string that ships. Arms that
  choose the venue themselves (enrichment, swap, 1c, 1d, operator override)
  are unaffected.
- Readers before selection keep the vote unchanged: winnow's rows, setlist.fm
  lookup, the research place filter (`gather._place_norms` inputs), and
  `catalog`'s suppress fallback. Readers of `show.venue` get the tie-broken
  string, as intended: the ledger's `selected` row (`pipeline.py`), the
  research prompt and the briefing header.
- The candidate's stored `venue` in `provenance.json` is unchanged; the
  tie-break lives in gather, where the selected recording is known.

**Delivered shows are not revisited** (owner ruling: not worth the
re-download). Already delivered or packaged shows keep their spelling until
something else re-gathers them; any later `fix`/`redo --from gather` of such a
show picks up the new rule, which is expected.

## Slice C: `llama fix` refuses an invalid edit without damaging the show, and can repair one already damaged

**Problem** (`bugs-found.md` #1-2, observed on `billystrings-2021-12-04`).

1. `llama fix <show> --set-breaks 10,20 --set-encore 20` writes
   `overrides.json` via `_edit_overrides`, then `_redo_show` runs
   `drop_stage_artifacts` (removing `show.json`, notes, reviews and later
   stages), and only then does gather's `_validate_structure_override` refuse
   (`encore_after must be greater than every set break`). The show is left
   with invalid overrides and no `show.json`.
2. Every later `llama fix` on that show is refused, because `fix` refuses
   every flag when `show.json` is missing (the bug report's "validates the
   existing overrides" was a misreading; the builder check confirmed nothing
   does). No CLI command can then edit the overrides.

Also today: the redo rewrites `provenance.json` (`process_show`, new
`processed_at`) before gather runs, and gather also refuses `overrides.titles`
out of range (`gather.py`, a `LlamaError`), not only structure overrides.
`yondermountainstringband-2005-12-31` has sat with `provenance.json` and
`overrides.json` but no `show.json` since 2026-09-05 (a different cause, not
investigated here); it is the one such show in the library.

**Requirements.**

- **C1, refuse cleanly, on every route.** Every route that writes overrides or
  re-runs gather on them refuses an override set gather would refuse **before
  writing anything**, exits non-zero with gather's own message, and leaves
  every file in the show directory byte-identical, `provenance.json`
  included. Routes (my call: all of them, since any one left out reproduces
  the damage): `fix`, `fix --no-run`, triage's edit paths,
  `redo <show> --from gather|select` (single and batch), and
  `_untitled_resolution`. Because `fix --no-run` runs nothing afterwards that
  could roll back, the shape is **validate before writing**: the edited
  overrides are checked before `overrides.json` is written, and `redo`
  checks the overrides on disk before `process_show` or
  `drop_stage_artifacts` runs.
- **C2, gather's checks, gather's count.** Validation calls the same checks
  gather runs (`_validate_structure_override` and the `titles` range check),
  against the track count gather would produce: the kept-file count from
  gather's own file filtering over cached item metadata, with this
  invocation's `exclude`/`include` applied. One shared helper, so the
  pre-check and gather cannot drift. If that count cannot be computed
  without network or LLM (metadata not cached), the pre-check refuses and
  says so rather than guessing.
- **C3, validate the result, not the input.** What is validated is the
  overrides *after* the edit. An edit that turns invalid overrides into valid
  ones is accepted.
- **C4, a narrow repair route.** With C1, new damage cannot arise, so the
  repair route is kept narrow (my call). When `show.json` is missing and
  `provenance.json` exists, `fix` accepts only the metadata, structure and
  title flags (`--set-*`/`--clear-*`), and only after taking the show lock
  **non-blocking**: a held lock means a `get` or redo is still building the
  show, and `fix` refuses with that message rather than writing into it.
  Every other flag keeps today's refusal, which also names the remedy,
  `llama redo <show> --from gather`. The repaired show ends packaged or held
  exactly as a normal redo from `gather` would leave it.
- **C5, triage keeps going.** In triage, a refused edit prints gather's
  message and returns to the same show's prompt; it does not end the
  walkthrough (`_interactive_resolve` has no `LlamaError` handler today).
- **C6, test from the real shape.** Tests reproduce the
  `billystrings-2021-12-04` sequence (its pre-repair overrides are in
  `~/.llama-harness/t3/apply/billystrings-2021-12-04.overrides.bak`:
  `set_breaks [10, 20]`, `encore_after 20`): the bad edit refuses with every
  file unchanged; the same bad overrides placed on disk with `show.json`
  removed are repaired by `fix --set-encore` or `--clear-encore`; and
  `fix --no-run` with the bad edit writes nothing.

## Slice D: the curly apostrophe matches the straight one

**Problem.** `normalize_song` deletes `'` but turns `’` (U+2019) into a
space, so `Don’t Ease Me In` and `Don't Ease Me In` do not match. The
adjudication found two shows flagged this way (`littlefeat-2016-01-09`,
`joerussosalmostdead-2017-11-09`, research unknown-song flags); both have
since been cleared by hand, so this slice is for future shows and removes
roughly no current holds. `structure._place_tokens` already folds `’` for
venues.

**Rule (my call; the owner raised no objection).** Fold `’` and `‘`
(U+2018) to `'` at the **matching layer only**, where `&`→`and` already
lives: `structure.fuzzy_norm_title`, `vet_research`'s song matchers
(`_known_song`, `_title_match`, the right-show gate's `known` lists), and
`brief.known_song`. `fuzzy_norm_title` reaches further than alignment and
closer matching: 2b placeholder demotion, 2a short-tag corroboration,
setlist-gap hygiene, correspondence proposals, gather's metadata norms, and
winnow's `setlist_constraints` via `contains_sequence`. That full reach is
intended; it is exactly the reach the `&` fold already has. The winnow effect
runs before selection, so the replay harness cannot see it; it is accepted
unmeasured (it can only make a curly-quoted title match its straight form).
`normalize_song` stays byte-identical (Tier 1 strict list; it also feeds
grouping and setlist.fm artist matching). No other characters are folded.

## Measurement and acceptance

Measured with the replay harness exactly as Tier 1 was:
`scripts/replay_holds.py run` for a base arm (main) and a candidate arm (this
branch) over all shows, each with its own tree's interpreter, then `compare`.

- **A.** The harness lists every show that loses a research-date flag, with its
  stored `asserted_dates`. Every one whose hold clears is hand-read for
  misdating language before it ships (an Opus pre-screen flags "actually",
  "misdated", "wrong date" and similar, then the owner reads the flagged rows
  and the rest of the list if it is short). No show gains a date flag.
- **B.** The harness lists every show whose shipped venue string changes, with
  both strings and the vote counts. **Zero flag changes are expected**; any
  flag change is a defect. Delivered shows are listed separately and are not
  redone.
- **C.** No harness effect. Unit and CLI tests per C1-C6.
- **D.** The harness lists flag and title changes; expect few or none in the
  current library. No show gains a flag.
- **Apply.** Held shows only, via `llama reapply --from-list
  predicted_list.json` after the hand-read. `reapply` never delivers;
  delivered shows are untouched.

Every behavioural change gets a test that fails on today's code, and the
mutation recipe Tier 1 used (named expected red test per mutant, isolated
bytecode cache) is applied to slices A and B's conditions.

## Non-goals

- Widening 4b's window, its own-date condition, or full-date handling.
- Changing how grouping votes (no counting by taper instead of by upload, no
  new venue normalization), or fixing performances grouped wrongly (several
  of the adjudication's 14 "venue from a sibling" cases are that, and they
  belong to a later piece).
- Re-delivering anything.
- Anything in pieces 2-5.

## Left to the builder

- The shape of C2's shared helper.
- Where exactly the tie-break sits in gather's venue chain, within slice B's
  invariants.
- Whether to look into `yondermountainstringband-2005-12-31`'s cause; it is
  out of scope, but C4 makes it repairable from the CLI.
- Test file placement and fixture shapes.
