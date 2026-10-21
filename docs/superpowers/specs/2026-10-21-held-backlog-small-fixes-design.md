# Held-backlog small fixes: venue tie-break, safe `fix`, curly apostrophe

Status: draft for review, not approved, not implemented.
Date: 2026-10-21.
Inputs: the 2026-10-21 overnight Opus adjudication of every held show
(`~/.llama-harness/t3/`: 1,063 verdicts, `synthesis.md`, `bugs-found.md`,
`handoff-design.md`), plus a read-only measurement over the live library
re-run for this spec (venue: 3,982 shows). Builds directly on the Tier 1 spec,
`2026-10-19-held-backlog-guard-fixes-design.md`, whose strict list this spec
respects.

## Kickoff

**Review mode: Opus** (Opus reviewers and an Opus final branch reviewer).

**Stakes.** llama feeds an automated radio station; venue and date are spoken
by the DJ and shown to listeners. Strict surface in this spec:

- **`llama fix`, `redo` and triage writing `overrides.json` and dropping stage
  artifacts** (slice C). This overwrites a show's state: today a refused
  structure edit leaves a show with no `show.json` and no CLI route back
  (`billystrings-2021-12-04` needed a hand edit). After this spec, a refused
  or failed edit or redo leaves every file of the show byte-identical to
  before the command.

Ordinary: the venue tie-break (slice B; cosmetic, new gathers only) and the
apostrophe fold (slice D). Tier 1's strict list still binds: `normalize_song`,
`DEFAULT_ALIASES` and every do-not-retune constant named in `CLAUDE.md` stay
byte-identical.

## Where this sits

The adjudication found the held backlog is mostly llama's own gather defects.
The owner (Shawn) split the deterministic work into five pieces, in this order:

1. **This spec:** three small confirmed bugs.
2. The taper's explicit set/encore markers win over unlabelled setlist.fm and
   one-set jerrybase rows (398 shows; the largest cause).
3. Title hygiene: remaining 2b placeholder gaps, unknown-song flags on an
   untitled tape folded into the unresolved hold, lossless originals' tags over
   stale MP3 tags, count-exact description title lists.
4. Junk-filter exemption for segue/reprise pieces (needs an owner ruling; junk
   constants stay put).
5. Partial tapes, better siblings, shifted tags (mostly flags; later).

Each is its own spec. Nothing here may anticipate pieces 2-5.

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

- A tie is counted exactly as grouping counts (raw venue strings, blank ones
  not counted, `grouping.py` `_make_candidate`); the string that ships is
  stripped, as the swap arm strips it. No new normalization.
- The tie-break applies only when the selected recording's city is blank or
  `cities_compatible` with the vote's city; otherwise the vote ships
  unchanged, venue and city both. When it applies, the city is
  `sel_city or vote_city`, as in Tier 1's swap and 1c arms. Measured: of about
  270 ties, 92 would change the city and at least 15 of those pair an
  equivalent venue with an incompatible city
  (`stringcheeseincident-2000-10-24`: Lackawanna vs Buffalo;
  `tedeschitrucksband-2026-08-01`, whose selected city field is `Red Rocks
  Amphitheatre, Morrison, CO,`), so a tie-break there would ship a mismatched
  or junk city.
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

## Slice C: a failed `fix` or `redo` leaves the show as it was

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
No show in the library is in this state today
(`yondermountainstringband-2005-12-31`, the last one, was rebuilt on
2026-10-21).

Refusal is not the only way to end there. An archive or download error, an
LLM failure, a usage-limit refusal or Ctrl-C between the drop and gather's
write leaves the same state, and so does a `redo --from
research|vet|brief|package` whose show has no `show.json` (it re-runs
gather). `redo --from select` may also pick a different recording than the
one the edit was made against, so no check made before the redo can predict
what gather will accept.

**Requirements** (my call).

- **C1, one invocation is one transaction.** Every command that edits
  overrides or redoes a show runs as one unit under the show lock: `fix`
  (every flag combination, `--suggest-titles`, `--untitled` and its
  follow-on overrule/brief steps), triage's edit paths (`_metadata_editor`,
  `[t]`, `[i]`, `[u]`, accept-vague, overrule), and `redo <show> --from
  <stage>`, single and batch (each show its own unit). The command takes the
  show lock **before** it reads `overrides.json` and holds it through every
  write, the drop and the redo (today `fix` writes overrides without the
  lock, so two concurrent edits can lose one). `_redo_show` gets a lock-held
  inner form that callers already holding the lock use; `file_lock` opens a
  new descriptor per call, so taking it twice in one process deadlocks.
  `process_show` stays lock-free.
- **C2, a failed unit leaves the show as it was.** Before changing anything,
  the unit sets aside every file it will remove or rewrite in the show
  directory: the stage artifacts `drop_stage_artifacts` would delete,
  `provenance.json` and `overrides.json`. If the unit raises anything
  (gather's `LlamaError` refusals, archive and download errors, LLM failures,
  `RateLimited`, `KeyboardInterrupt`), it puts every set-aside file back and
  removes anything the unit created, so every file in the show directory is
  byte-identical to before the command; then it reports the error and, for
  Ctrl-C, re-raises. On success the set-aside copy is deleted. Set-aside is
  by rename within the show directory (no audio is copied). A held outcome is
  success, not failure. The ledger, the item cache and downloads outside the
  show directory are not rolled back (the ledger is append-only history; a
  `selected` row from an unfinished redo is harmless).
  A process killed outright (SIGKILL, power loss) leaves the set-aside copy
  behind: the next `fix`/`redo`/triage unit on that show restores it first
  and says so. Other commands ignore it (documented limitation).
- **C3, `fix --no-run`** writes overrides under the lock and validates
  nothing; a later redo that refuses them rolls back under C2 and names the
  flag to change. (Stated so nobody adds validation ahead of the redo.)
- **C4, triage and runs keep going.** In triage, a failed unit prints the
  error and returns to the same show's prompt (today only the `[i]` branch
  catches `LlamaError`; the other `_redo_show` calls, including
  `_untitled_resolution`'s, do not). Ctrl-C still ends the walkthrough,
  after the restore. Batch `redo` keeps today's behaviour: `FAILED` per
  show, exit 0. `_execute`'s per-show loop also catches `LlamaError` per
  show, recording it as a failure of kind `other`, so one show's refused
  override cannot abort a whole run (today it does, and the sweep writes a
  crash marker).
  The existing refusal for a show with no `show.json` names the remedy,
  `llama redo <show> --from gather`.
- **C5, tests from the real shape.** Tests reproduce the
  `billystrings-2021-12-04` sequence (its pre-repair overrides are in
  `~/.llama-harness/t3/apply/billystrings-2021-12-04.overrides.bak`:
  `set_breaks [10, 20]`, `encore_after 20`): the bad `fix` refuses and every
  file is byte-identical, `provenance.json` and `overrides.json` included; a
  multi-flag `fix` whose last part fails leaves nothing of the first; an
  `IAError` and a `KeyboardInterrupt` raised after the drop both restore; a
  leftover set-aside copy is restored by the next `fix`; a triage edit that
  fails returns to the prompt; a run whose show refuses its overrides
  records a per-show failure and processes the next show; `reapply` on bad
  overrides leaves the show unchanged (already true: `reapply_show` computes
  in a scratch directory before writing anything; pinned).

## Slice D: the curly apostrophe matches the straight one

**Problem.** `normalize_song` deletes `'` but turns `’` (U+2019) into a
space, so `Don’t Ease Me In` and `Don't Ease Me In` do not match. The
adjudication found two shows flagged this way (`littlefeat-2016-01-09`,
`joerussosalmostdead-2017-11-09`, research unknown-song flags), in both with
the curly apostrophe on the **tape** side (`Don’t Bogart That Joint *`,
`He’s Gone ->`), not in research; both have since been cleared by hand, so
this slice is for future shows and removes roughly no current holds.
`structure._place_tokens` already folds `’` for venues.

**Rule (my call; the owner raised no objection).** Fold `’` and `‘`
(U+2018) to `'` at the **matching layer only**, where `&`→`and` already
lives, and on **both sides of every comparison**:
`structure.fuzzy_norm_title`; `vet_research`'s song matchers (`_known_song`,
`_title_match`, the right-show gate's `known` lists, and `grounding_flags`'
track-title `known` list, `vet_research.py:234`); and `brief.known_song`,
`brief.py`'s `exact`/`components` builders (`brief.py:226-227`) and
`song_components` (`brief.py:121`). `fuzzy_norm_title` reaches further than
alignment and closer matching: 2b placeholder demotion, 2a short-tag
corroboration, setlist-gap hygiene, correspondence proposals, gather's
metadata norms, and winnow's `setlist_constraints` via `contains_sequence`.
That full reach is intended; it is exactly the reach the `&` fold already
has. The winnow effect runs before selection, so the replay harness cannot
see it; it is accepted unmeasured (it can only make a curly-quoted title
match its straight form). `normalize_song` stays byte-identical (Tier 1
strict list; it also feeds grouping and setlist.fm artist matching). No other
characters are folded.

Tests cover both sides: curly in research with a straight track title, and
curly on the track title with straight in research.

## Measurement and acceptance

Measured with the replay harness exactly as Tier 1 was:
`scripts/replay_holds.py run` for a base arm (main) and a candidate arm (this
branch) over all shows, each with its own tree's interpreter, then `compare`.

- **B.** The harness gains a venue-change report (its own plan task:
  `replay_holds.OUTPUT_FILES` has none today) listing every show whose
  shipped venue or city changes, with both strings and whether the show is
  delivered. **Zero flag changes are expected**; any flag change is a defect.
- **C.** No harness effect. Unit and CLI tests per C5; the mutation recipe is
  applied to C2's restore (each set-aside and restore step removed in turn
  must turn a named test red).
- **D.** The harness lists flag and title changes; expect few or none in the
  current library. No show gains a flag.
- **Apply.** Held shows only, via `llama reapply --from-list
  predicted_list.json` after the reports above are checked. `reapply` never
  delivers; delivered shows are untouched.

Every behavioural change gets a test that fails on today's code, and the
mutation recipe Tier 1 used (named expected red test per mutant, isolated
bytecode cache) is applied to slice B's conditions and slice C's restore.

## Non-goals

- Yearless adjacent-day dates (`Nov 1` on a 10-31 show). Dropped by the
  owner: no rule over the extracted dates can tell a set that ran past
  midnight from a misdated tape, since research arguing a misdating names
  both dates (all four 4b clears the owner rejected at Tier 1's Checkpoint E
  did); the rule would have cleared no current hold (every candidate carries
  other flags); and about 2% of holds carry the flag. Those holds are left to
  the planned adjudicator command (the LLM judge that follows the
  deterministic pieces), which reads the research text. 4b itself is
  unchanged.
- Changing how grouping votes (no counting by taper instead of by upload, no
  new venue normalization), or fixing performances grouped wrongly (several
  of the adjudication's 14 "venue from a sibling" cases are that, and they
  belong to a later piece).
- Re-delivering anything.
- Anything in pieces 2-5.

## Left to the builder

- The set-aside mechanism's shape (directory name, how a leftover is
  detected), within C2.
- Where exactly the tie-break sits in gather's venue chain, within slice B's
  invariants.
- Test file placement and fixture shapes.
