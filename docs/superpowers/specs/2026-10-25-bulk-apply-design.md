# Bulk apply of held-backlog pieces 1-4: design

Status: approved (Shawn, 2026-10-25), after Opus spec review. Review mode: **Opus** (Shawn, 2026-10-25).
Inputs: the piece-4 spec section 5 (`2026-10-23-junk-short-keep-design.md`), the piece-4 plan
Appendices A-C (`docs/superpowers/plans/2026-10-24-junk-short-keep.md`), the migration
handoff (`~/.llama-harness/piece4/handoff-migration.md`). The overrides migration is DONE
(2026-10-25, 606 shows re-keyed, self-check 0 differences; snapshot
`~/.llama/rekey-snapshot-20261025T171454Z`); llama and emcee 2.18.0 are installed.

## Stakes

The library holds 3,983 shows; 2,786 are delivered to the station root
(`/Volumes/media/lma-radio/delivered`), 224 of those are voiced. A Voxtral voicing is the
scarcest resource here (~100 shows a month on the free tier, shared with a 2,562-show
first-voicing backlog); LLM spend is the second (Claude 5x plan, the weekly window is the
binding one and is shared with Shawn's dev work); Shawn's attention is the third. Nothing
is on air yet, so no listener sees an error, but every show voiced on wrong data wastes a
credit and has to be voiced again before go-live.

**Strict surfaces** (anything irreversible; reviewers hold these to the strict standard):
- writing a field into a delivered package's `manifest.json` on the station (the mark below);
- re-delivering over a station copy, above all `deliver --replace-voiced`, which discards a
  voiced show's DJ script and audio (a Voxtral credit each to redo);
- deliver's purge of library `package/audio/*` after a re-delivery;
- rewriting library `show.json`/briefings/packages in bulk (the migration snapshot predates
  this work and does not cover it);
- any path that downloads audio already held on the station (bandwidth, hours) or loses
  station audio that the library no longer has.

## Why

Pieces 1-4 (v2.15.0 to v2.18.0) fixed how llama builds a show: venue tie-breaks and
small fixes, the taper's set/encore markers, title hygiene, short real pieces kept,
doubled derivatives collapsed, ~2,000 segues restored. They change the computation, not
the shows already built. Every show in the library was built before them, so what would
be voiced and aired still carries the old mistakes. The bulk apply brings the existing
library up to the fixed code.

The point is **accuracy of what airs**, not any new capability (Shawn). The station goes
live only when there are enough voiced, accurate shows across profiles to run about a
month without repeats. Extra spend (a bigger Mistral plan, Claude 20x) waits until spend
is the only thing standing between the station and go-live.

## What the post-migration replay says (2026-10-25, `migration-post.json`, code 9a85cac)

Per show: llama state x replay outcome x briefing leg. "Changed" = a field visible in the
manifest moves. "Label-only" = only `title_source` or `structure.alignment` moves; such a
show keeps its briefing and is not marked (below). A show whose replay needs an LLM call
counts only in that column, whatever its briefing leg.

| | unchanged | label-only, briefing reusable | changed, fresh briefing | replay needs an LLM call | newly held |
|---|---|---|---|---|---|
| delivered, unvoiced (2,562) | 863 | 20 | 1,311 | 345 | 23 |
| delivered, voiced (224) | 85 | 3 | 114 | 20 | 2 |
| packaged (842) | 299 | 2 | 249 | 99 | 193 |
| briefed (21) | 3 | 1 | 11 | 4 | 2 |
| held (334) | | | 12 (9 structure-changed, 3 needs-brief) | 186 | 135 still held, 1 still-held-package |

The fresh-briefing column includes 2 unchanged shows whose stored briefing fails today's
briefing guard (`cowboyjunkies-2012-04-15`, `moe-2004-10-31`).

Totals: 1,697 shows need a fresh briefing and no other LLM call (18 more have a fresh
briefing leg but sit in the needs-LLM column); 654 shows' replay needs an LLM call (reasons,
overlapping: `align_structure` 629, a stored `llm` alignment 530, `extract_setlist` 3); 26
label-only; 220 newly held. The 220 include 194 shows the 2026-10-21 overnight adjudication
cleared and a re-gather would hold again, because overrules do not survive a re-gather today;
the backfill below restores those whose verdict ruled the flags spurious, leaving about 29
genuinely held (see "Overrules persist").

Of the 117 voiced changed shows, 81 go to presenters that resolve to Voxtral today (phil,
monroe) and 36 to mlx (jamesbrown, kurt); of the 20 voiced needs-LLM shows, 1 is Voxtral and
19 mlx. The split is by the presenters' current pins (`~/.emcee/presenters/`), not by recorded
backends: most voiced shows carry no `tts` record. Unvoiced delivered shows by current
assignment: ~930 to Voxtral presenters (phil, monroe, prine), ~1,630 to mlx presenters
(roydemure as the `[assign] default`, kurt, jamesbrown). The default-presenter shows will get
their own presenters later; the Voxtral/mlx mix is undecided (Shawn).

Two consequences shape everything below:
1. **Almost all of the work is gated on LLM spend.** A changed show cannot be re-packaged
   without a briefing that matches it; the only 26 shows that keep theirs are label-only.
2. **Most changed delivered shows are not voiced yet**, so fixing them before they are
   voiced costs no voice credit; voicing them first wastes one.

Per-briefing cost is unmeasured on the current plan. The only data point (Tier 1 pilot,
2026-10-20, 20x plan): 8 fresh briefings moved the 5-hour meter 1%. Scaled to 5x that is
roughly 0.5% of a 5-hour window per briefing: a guess, which the trial replaces.

## Goals

1. Every show the fixes change is re-processed with the fixed code, at the lowest LLM spend
   that keeps its briefing honest, reusing audio llama already has.
2. **Nothing changed gets voiced or aired on its old data.** A delivered show awaiting its
   fix is visibly blocked, in llama, in emcee and (via the scheduler session) in transmitter.
3. The work runs as a **queue in an order Shawn chooses at run time**, mostly by profile
   readiness, paced so it never crowds out dev work, and resumable across weeks.
4. Per-show cost is **measured** in a trial before the bulk of the spend.
5. Shawn's attention is spent only on spot checks, a short list of famous shows he names,
   and the shows the fixes genuinely newly hold (an overrule already made stays made).

## Non-goals

- No new deterministic fixes, no retuning of pieces 1-4, no adjudicator (that is the next
  project, after this one).
- No automation of voicing: `emcee run` stays a manual, per-profile, operator decision.
- No presenter work, no change to `[assign]`.
- No transmitter/scheduler change in this project: the scheduler session builds its side of
  the mark against the field this design fixes (below).
- No change to the briefing model tier or prompt to save money (a possible lever, not
  measured; out of scope unless Shawn asks).

## Anti-goals (would make this a failure even if it "works")

- A show voiced on data the fixes have since changed.
- Voxtral credits spent re-voicing mostly-correct shows while the first-voicing backlog waits.
- The bulk apply eating the weekly LLM window Shawn needs for dev work.
- A per-show human step on the bulk of 1,700+ shows.
- Re-downloading audio the station already holds, or losing station audio the library no
  longer has.
- A mark that breaks today's readers: emcee's manifest rewrite, llama's audio reuse (which
  reads the station track list), or transmitter.

## Decided (Shawn, this session)

- **Order by profile readiness, chosen at run time.** Funk (James Brown, mlx) is ripe now;
  indie (Kurt, already on mlx) when Shawn says it is ripe; Bluegrass is the next Voxtral
  profile; new profiles as their presenters exist; shows falling to the default presenter
  last. No fixed pattern: the tooling must let Shawn pick the next slice by profile (and by
  llama state).
- **A show waiting for a fresh briefing is held from delivery and voicing.** Its old
  briefing is not shipped in the meantime.
- **"Awaiting fix" is a status**, visible and enforced on both sides (library and station).
- **Voiced shows that change:** re-voice is triage, not a rule. Before go-live they must be
  right; mlx ones can be re-voiced whenever convenient; Voxtral ones queue behind the
  first-voicing backlog, ranked by how wrong they are. The 37 voiced-severe shows keep their
  individual approvals (`~/.llama-harness/piece45/voiced-severe-review.md`) and the piece-4
  Appendix C runbook (`short_keep_probe.py voiced-precheck`, then one named
  `deliver <slug> --replace-voiced`, then `emcee voice <slug>`).
- **Overrules persist across re-gathers** (see "Overrules persist").
- **Little manual checking.** Spot checks per wave, plus a short list of famous Dead shows
  Shawn will name that must be hand-verified before they go through. Everything else goes
  through with `--allow-structure-change` and no human step.
- **A trial first**, with nothing else spending (no other Claude sessions, no sweep loop, no
  `emcee run`), to measure the average cost per show of each kind. The earnest run likely
  starts after the 7-day reset (2026-10-31 07:00 ET); Shawn has higher-priority dev work
  until then.
- **Audio comes back from the station, not archive.org** (spec 5.4, `audio_reuse.py`,
  built): paired by position and title against the current `show.json`, checked by decoded
  length, copied, never moved. Measured: 20/20 sampled shows paired, 0 paired files fell
  back; only newly kept short files download (at most ~2.6 GB overall).
- **Review mode Opus.**

## The `awaiting_fix` contract (fixed here; the scheduler session builds against it)

A new optional top-level field in a delivered package's `manifest.json`:

```json
"awaiting_fix": {"reason": "<one line>", "marked_at": "<UTC ISO-8601>"}
```

- Absent or `null` means no fix is pending. Any other value means the package is **not to
  be voiced and not to be aired**.
- **Who gets marked** (delivered shows): a replay that changes a field visible in the
  manifest (kept filenames, `source.identifier`, titles, set labels, segues, set breaks,
  venue, city, date: a same-count file swap is a change); a show on the **frozen needs-LLM
  list** (it may change): the needs-LLM rows of the first arm after the overrule backfill,
  kept as a list like the re-selection list, because a needs-LLM verdict never goes away
  (a re-processed show's fresh alignment is stored as `llm` again); an unchanged show whose stored briefing fails today's guard
  (`cowboyjunkies-2012-04-15`); and the verified re-selections ("Re-processing"), whatever
  the arm says. Not a label-only change (`title_source` or `structure.alignment` alone: 26
  shows, 23 delivered, 3 voiced: `elliottsmith-1998-06-02`, `-2000-02-20`, `-2000-11-10`),
  nor an already processed show ("The library side"). Marking shrinks the broadcast-ready
  set before it grows; the scheduler session knows.
- **Writing a mark**, per show, under the show lock: the campaign record (see "The library
  side") is written first and made durable, then the station mark, a read-modify-write on
  the raw JSON dict, never llama's `Manifest` model: re-read under the lock, only
  `awaiting_fix` added, unique temp + rename, re-read with every other key compared equal.
  `tracks` (audio reuse pairs against it), `dj_notes`/`dj_audio`, `broadcast.m3u` and the
  audio are untouched; the mtime changes (transmitter's quiet period sees that). An
  unreadable or malformed station manifest refuses that show and is never overwritten.
- **The marking batch** is recorded and idempotent: a record file lists the shows it marked,
  a re-run skips them, and the batch exits non-zero listing every show it could not mark;
  the runbook forbids `emcee run` on a profile holding such a show until it is marked, and
  after any marking batch that did not exit 0 (a killed batch prints no list) until a re-run
  exits 0. Marks are re-derived from every fresh arm and only ever added; a row whose input
  digests differ from the show's current files is skipped (as reapply's `inputs changed`). Before the first marking every
  station `manifest.json` is backed up (about 28 MB). A batch is reversible by its record:
  the key is removed only where the manifest still equals what marking wrote, and never for
  a show processed since its `marked_at` (those are listed instead: their station copy is
  old data the library knows changed). The reversal is the marking batch's only undo.
- **No concurrent emcee:** emcee takes no lock and a voicing in flight rewrites the same
  manifest, so marking refuses to write while an `emcee` process runs, checked before each
  write. The check cannot see scripts that import emcee (`scripts/backfill_*`); the runbook
  says not to run them during marking.
- **It clears by re-delivery**: deliver replaces the station manifest with the library's,
  which carries no mark, always through the staged copy and swap (`_replace_destination`),
  never the in-place overlay, so the mark goes only with a complete copy. For a voiced
  destination that is `--replace-voiced` (one named show), which also discards the DJ script
  and audio, so the show is not broadcast-ready until emcee voices it again.
- **Clearing without re-delivery is only for voiced destinations, one named show at a time**
  (unvoiced shows are re-delivered: it costs nothing), by a llama clear command (never a hand
  edit) that:
  - refuses unless the show's campaign record is processed after `marked_at`, the show is
    not held, and the library manifest's sha256 equals the one the record holds (any package
    build on a processed show refreshes that sha, so a later overrule's redo from `package`
    still qualifies);
  - compares the library and station manifests as raw JSON on `source.identifier`, venue,
    city, date, the track list (filenames and durations), titles, set labels, segues and set
    breaks. Equal: clears the mark and prints that the voicing is kept. Not equal: refuses
    unless `--accept-change` (Shawn judges the change cosmetic), and then clears;
  - writes through marking's station writer, and records its outcome (equal, or change
    accepted) in the campaign record;
  - in the equal case purges the library audio ("Re-processing"); after `--accept-change`
    the track lists differ, the purge refuses and the library keeps that show's audio. A
    show accepted once and marked again by a later arm-computed change is compared with the
    station's original manifest again, so Shawn judges it again (documented limitation).

  On a marked destination, `deliver --replace-voiced` refuses when that equality holds and
  names the clear command; an unmarked voiced destination keeps today's repair route.
- **emcee**: a marked package is a distinct state in `emcee status` (beside
  ready/pending/unsupported/error, counted per profile in the summary), skipped by `emcee
  run` (`awaiting fix from llama`) and refused by `emcee voice <pkg>`. `_process_one` (used
  by both) also re-reads the manifest and refuses a non-null `awaiting_fix` before preflight
  and any LLM or TTS spend. emcee's manifest rewrite preserves the field (belt and braces).
- **transmitter / scheduler**: treats a non-null `awaiting_fix` as not airable. Today's
  readers ignore unknown fields, so a reader that does not check it airs a marked show. A
  mark appearing after a show was planned or encoded is the scheduler session's to settle.
- **Rollout:** llama and emcee ship together. Before the overrule backfill (the first bulk
  write) and each marking batch, a version gate refuses unless every `llama` and `emcee` on
  PATH is at least the campaign release (`rekey_overrides.py`'s `which -a` shape).
  Installing it comes before the backfill: 2.18.0's deliver overlays the old manifest on a
  marked copy, and its `fix` rewrites `overrides.json` dropping unknown keys (overrules).
- **Limitation:** whether rename-over-existing is atomic on the SMB station root, and how the
  NFS playout host sees it, is unmeasured.

## The library side

- Every show meeting the marking rule, in any llama state (also the packaged
  `moe-2004-10-31`, whose briefing fails the guard), gets a **campaign record**: one small
  file in the show dir, kept, never deleted, outside `replay.input_digests` (never
  `show.json`/`overrides.json`: they are digested, and vet/brief/package rewrite `show.json`
  through pydantic copies that drop undeclared keys). It holds when and why the show was
  marked, the stage re-processing starts from (`select` for a verified re-selection, else
  `gather`), and once processed: when, the input digests and the sha256
  of the package manifest built (none for a held outcome); the clear command adds its
  outcome. Undelivered shows are blocked here only (no station copy to mark).
- **Awaiting fix** = marked and not processed since: shown (and selectable) in `llama
  status`, refused by `llama deliver` by name and in every selector, naming the route.
- **Processed** is written as the last step of a committed re-gather from the recorded stage
  or earlier, by any current llama (campaign worktree or installed release): reapply's `show.json` commit, or a `redo`/`fix`/triage
  unit from that stage or earlier. A redo from a later stage leaves the show awaiting fix, as
  does a `fix --clear-*` that re-gathers a re-selection's old recording. A crash before that
  step only causes a refusal that a re-run clears.
- **Marking skips** a processed show unless the arm computes a manifest-visible change for
  it: a needs-LLM verdict never re-marks a processed show or one off the frozen list (new
  shows from `get` or the sweep, triaged shows), and a redone re-selection drops off the
  verified list. A later release whose deterministic replay changes a processed show marks
  it again, which is right. Documented limitation: a release that changes gather does not
  reach processed needs-LLM shows through marking; Shawn redoes named ones.

## Overrules persist

`fix --overrule` and triage's overrule today set `needs_review=False` and empty
`review_flags` in `show.json` (`cli._clear_hold`), so nothing records what was overruled,
and every re-gather raises the flags again. Of the 220 newly held shows, 194 are
packaged/briefed shows the 2026-10-21 overnight adjudication cleared: 102 with an overrule
step (74 overrule, 26 fix plus overrule), 94 by a fix alone (these re-hold for flags the fix
did not address); 191 of the 220 were already newly held under the pre-piece-4 code
(`migration-base.json`). Without a fix decided shows go back to triage unpackaged, after
the apply or any later redo from gather: a durable fix, not a bulk-apply patch.

- **Decision (Shawn):** an overrule records the flags it cleared in `overrides.json`. When
  gather/vet/brief recompute flags, a flag that matches a recorded overrule becomes an
  operator note (`notes.json`), not a hold; any flag that does not match still holds.
- **Matching** is by flag kind and subject (the song, venue, city or date the flag names),
  never by track numbers, counts or positions, which piece 4 shifts. Design call: a record
  carries the show's `source.identifier`, and a re-selection voids every overrule recorded
  on the old recording. For "unresolved track titles" the subject is the set of unresolved
  filenames (stable across piece 4), matching only when the new set is a subset of it; other
  kinds with no stable subject (e.g. "single-set structure for a long show") match by kind
  while the identifier holds. Each flag family's normalisation is tested on the arm's flags.
- **Backfill**, before any other bulk write (a one-off, tested script or command, dry run by
  default): for every show not held today that was already newly held under the pre-piece-4
  code (`migration-base.json` flags, since `show.json` no longer has them) and has a verdict
  (`~/.llama-harness/t3/verdicts/<slug>.json`, two layouts: `flags` with a per-flag
  `verdict`, and `claims`/`other_flags`; both are read), record only the flags the verdict
  ruled spurious or false-hold or listed in `overrule_if_reheld_on`. Every other case is
  listed for Shawn, never recorded: no verdict (15 delivered, e.g. `dumpstaphunk-2008-04-25`,
  `gratefuldead-1977-05-09`), a base flag the verdict never ruled on, a flag ruled real
  (`real-fixed-by-action`, `undecidable`, etc.). The dry run prints both lists per show, with
  counts.
- After the backfill the arm is re-run at the new code; "newly held" is then the genuinely
  held shows (expected about 29, about 13 delivered and 16 packaged; the arm decides).

## Re-processing

- **`llama reapply` extended to packaged, briefed and delivered shows** (spec 5.2, not
  built): the computation it runs on held shows today (gather LLM-free from the cache, vet
  from the stored extraction, the stored briefing when `briefing_reusable` holds, else one
  fresh brief, then package with audio reuse), under the show lock, `show.json` written last
  as the commit marker; never research, never deliver. Outcome: cleared (re-packaged, ready
  to deliver) or held. A label-only show commits `show.json` only (no LLM call, re-package or
  re-delivery). Apply lists skip processed shows as marking does, clear-accepted ones too.
- **Audio reuse never silently falls back to archive.org.** Before each wave the station
  root is checked mounted and readable. A re-package of a delivered show (not a
  re-selection), by reapply or a `fix`/triage/`redo` unit, is refused retryably when none of
  the library copy, the held-outcome anchor (below) and the station copy pairs (`station copy
  does not pair`), or when the station manifest is unreadable or the dir missing (`station
  copy unreadable`); only the latter counts toward stopping the batch after 3 in a row (the
  mount is likely gone). Downloads are allowed only for files the station copy never held
  (newly kept short files). Each show prints files reused vs downloaded.
- **Purge after a re-package with no re-delivery** (voiced riders, the clear's equal case):
  `catalog.purge_package_audio` runs when the manifest tracks equal the station's.
- **Held outcomes keep a reuse anchor.** Today a held outcome whose shipped fields moved
  drops `briefing.*` and `package/manifest.json` (`drop:brief`) and commits the new
  `show.json`, so nothing pairs with the station copy and clearing the show later
  re-downloads every track. For a packaged or delivered show, reapply first writes the
  pre-commit `show.json` track list (source filename, title, `source.identifier`) as an
  anchor; `plan_reuse` and the pairing check consult it; it goes only when a package is built
  (a cleared outcome), never at a held commit.
- **Shows whose replay needs an LLM call** (654): the same path with gather's LLM
  touchpoints allowed (`align_structure`, `extract_setlist`), never research, in the same
  queue and pacing; the trial measures their cost separately. 530 have a stored LLM
  alignment, which a fresh `align_structure` call rarely reproduces, so most are expected to
  come out changed (the trial records how often). No stored-alignment reuse is added.
- **The GD re-selections** (piece-4 Checkpoint C Q4, accepted): the replay and reapply
  never re-select, so the arm classifies them on their stored recording. Of the 20 in
  `~/.llama-harness/piece4/fw1/m3_changed-r1.json`, 14 are delivered (3 voiced), 4
  packaged, 2 held.
  - **Voiced shows are not re-selected** (design call): the margins are about 1%
    (1973-11-14 12.774 vs 12.663; 1974-09-11 9.529 vs 9.419), so a new recording would
    spend a Voxtral credit for no accuracy gain. The 3 (`gratefuldead-1973-11-14`,
    `-1974-09-11`, `-1977-04-23`) keep their recording and follow the normal marking rule
    (1973-11-14 reads `clean` and stays unmarked).
  - The other 17 (11 delivered) are the verified list, re-checked at each marking by a
    read-only check comparing the recording selection would pick now with the stored one (a
    show already on the new recording drops off). The list feeds marking and the campaign
    record whatever the arm says; its shows stay off reapply lists and get a full redo from
    `select` in their wave (new recording downloaded, fresh briefing). **Research is kept**
    (design call): it is per performance, and `redo --from select` keeps `research.md`.
  - Two, `gratefuldead-1970-05-06` and `gratefuldead-1985-11-10`, orphan operator overrides:
    the redo surfaces the dangling-key refusal, Shawn clears the keys by hand with `llama fix
    --clear-* --no-run` (Checkpoint C Q3; no point re-gathering the old recording), then the
    redo from `select` is run again.
- **Newly held shows** (about 29 after the backfill, not the table's 220): the apply writes
  their hold and they wait for `llama triage` after it. A newly held delivered show stays
  marked.
- **Structure gate:** the bulk goes through with `--allow-structure-change` (decided);
  Shawn's famous-shows list is excluded and produces a hand-check packet instead.
- **Spot checks:** each wave yields a small random sample of changed shows rendered for a
  quick look (titles, sets, segues, before and after), reusing `replay_holds.py compare`'s
  hand-check sample if it fits.

## Delivery after the fix

Re-delivery is the step that clears the station mark, and stays an operator step, in
profile order:
- **Unvoiced** destinations: plain `llama deliver`, by name or with a selector for "station
  marked and library fixed", so a wave's re-delivery picks exactly the shows that need it.
  Audio was reused at re-packaging, and deliver's purge empties the library copy again.
- **Voiced** destinations: one named `deliver <slug> --replace-voiced` each, only when
  Shawn is ready to re-voice that show (mlx: whenever; Voxtral: from the ranked re-voice
  list, after first voicings), or the clear command when the re-processed show turns out
  unchanged or Shawn accepts the change. Until then the station copy stays marked and off
  the air.
- The tooling produces the **ranked re-voice list** for voiced changed shows: how wrong each
  is (e.g. songs moved across sets, titles changed, tracks added, segues changed), its
  presenter and its re-voice cost, read from emcee's `tts_now`. The ranking must be
  explainable per row.

## Pacing, ordering and resumability

- Work is selected per run by **profile** and llama **state** (and optionally an explicit
  slug list), so Shawn can say "funk, delivered" or "bluegrass" and get exactly that slice.
  "Profile" means emcee's effective profile (design call). Today it equals llama's
  `source.profile` on every delivered show (no moves or artist rules: 2,786/2,786), so
  llama's `--profile` selects it. When moves or rules exist, the runbook builds the slug
  list from `emcee status --json --profile <p>`; llama never reads emcee's config.
- **Voiced changed shows are marked at once but re-processed only when Shawn schedules
  their re-voice** (design call): re-processing copies a show's audio back into the
  library, and a Voxtral show may wait months behind first voicings. mlx voiced shows may
  ride their profile's wave (their re-voice is free), and so may the 20 voiced needs-LLM
  shows, so those that come out unchanged can be released by the clear command.
- **Unvoiced shows are re-delivered right after their wave** (no voicing lost), so the
  purge empties the library audio again promptly. Each wave first checks free disk against
  its shows' actual station audio sizes (Dead shows run long; 122 GB free on 2026-10-25) and
  refuses a wave that would not fit with margin.
- The existing pacing gate (meter read before each show, pause at a ceiling, resume
  command printed, stop after 3 consecutive LLM failures) applies. The weekly limit is a
  per-run override of `[pacing] seven_day_ceiling` (checked first), set from the trial's
  costs, so the apply cannot spend the week; no second ceiling mechanism. The learned
  per-show EWMA cannot size this work (spec "Re-processing cost"); the trial replaces it.
- Batches resume where they stopped (reapply's batch state does this today), and a run
  that pauses names its resume command.

## The trial

After the build, before the bulk, with no other Claude sessions, no sweep loop and no
`emcee run` going. All trial shows are unvoiced delivered shows, so the spend is real work.
The meter reads whole percent only, so the trial runs **one contiguous block per kind of
work and per show shape**, each until the 5-hour meter has moved at least 5 points within
one window (a block whose pool runs dry first reports its error bound); a block that
crosses a 5-hour reset (the reading carries the reset time) is discarded and re-run. Each
block's delta is divided by its show count. Two kinds: fresh briefing only, and re-gather
needing an LLM call (these blocks also record how often a fresh `align_structure`
reproduces the stored alignment). Two shapes, because funk shows are short single-set shows
and not representative (Shawn): **Grateful Dead long two-set shows must be in the sample**.
So four blocks: Dead and funk, each fresh briefing and needs-LLM. Unvoiced delivered counts
(2026-10-25): `dead` 208 fresh / 6 needs-LLM, `dead-family` 161 / 14, funk 50 / 18; the
Dead needs-LLM block draws on `dead` and `dead-family` together, and may merge with funk's
if both pools are too small. If the per-shape costs differ materially, the projection uses
each profile's own mix; otherwise one figure per kind. The 7-day cost per kind comes from
each block's 5-hour delta and the 5-hour/7-day ratio over the whole trial, since the 7-day
meter alone moves too little. Output: cost per show per kind and shape, and a projection of
the whole queue in weeks at a chosen weekly share. The ceiling binds on the **all-models
weekly meter** (the one Shawn tracks; `/usage` reports no separate Opus figure, only
all-models and Fable); Shawn sets the per-run ceiling from the projection. The 17
re-selections are not measured (small in the projection). The 3 held shows needing only a
fresh briefing can give an earlier, smaller sample with today's tooling if Shawn wants one.

## Undo

- Each library write batch (the overrule backfill, each wave) takes a snapshot of its own
  shows only: every file outside `package/audio/`, verified and flushed before the first
  write. A per-batch restore rewinds those shows' library files (campaign records
  included) and refuses, per show, any show whose library files or station manifest
  changed after the batch (the snapshot's verify code). The marking batch has no snapshot:
  its undo is its reversal. The order is backfill, re-run arm, marking, then the trial (a
  wave like the others) and the waves.
- A restore rewinds no station mark (a show left marked is safe) and no re-delivered copy:
  re-deliver a wave only after its spot check passes; after that the way back is forward.
- The migration's `rekey_overrides.py --restore` is retired at the first bulk write (that
  write updates the record it checks, so it refuses, naming why); its gates (a migrated
  library, the snapshot `rekey-applied.json` names, no show created since) do not fit this
  work. The new snapshots may share its copy/verify code, not its gates.

## Known constraints for the builder

- **Apply lists are tied to code.** `reapply --from-list` refuses a list whose `sha` is not
  the running `code_identity()` (and any `-dirty` identity). `migration-post.json` is at
  9a85cac; once the build lands, the lists must come from a fresh arm at the new code.
- **Waves run from a pinned, clean campaign worktree** at the build's merge sha with its own
  venv; both the arm and reapply run from it. The installed binary's `code_identity()` is
  `version:...` and never matches a list's sha, and dev commits on main would invalidate
  lists. Re-run the arm when the code or the library changed (a list row whose input
  digests changed since the arm is skipped as `inputs changed`, which is safe). The campaign
  is re-pinned at each llama release, and an arm or wave refuses when the installed llama is
  newer than the campaign's code (the older code would re-gather shows a newer release
  fixed). The campaign is pinned to a release tag's commit, with that release's version
  stored beside the pin, and the runbook runs the worktree's tools by path without
  activating its venv (its dev `llama` reports 0.1.0 and would fail the version gate).
- **No pre-piece base arm can run any more**: the old code cannot read the migrated
  overrides, and `replay_holds.py compare` exits 2 on a pre/post-migration pair (digests
  differ). Apply lists come from one post-migration arm (or a compare of two such arms); the
  overrule backfill only reads `migration-base.json`'s recorded flags.
- **reapply has no one-unit restore today** (it undoes only new audio and its own manifest).
  The extension runs inside `show_unit`'s `.txn/` snapshot, so any failure restores every
  file outside `package/audio/` byte-identical (held shows may stay as they are), keeping
  llama's lock order (run > show > ledger).

## Left to the builder

The re-voice ranking measure; spot-check sample size and format; whether marking is a
`llama` subcommand or a script (a tested code path either way, never a hand edit); the
per-family flag normalisation for overrules; exact command, flag, file and key names
(selection, ceiling override, clear command, delivery selector, overrule key, re-selection
check, campaign record, held-outcome anchor).
