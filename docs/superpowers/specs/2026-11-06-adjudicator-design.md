# llama adjudicator: design

Date: 2026-11-06. Status: draft for review. Review mode: **Opus** (Shawn, 2026-11-06).

## Stakes

The library holds ~3,500 shows. ~350 are held for review and the campaign's needs-LLM classes will
add more. A held show never airs; a wrongly fixed show airs wrong until someone notices, and if it was
voiced, fixing it costs a re-voice. Shawn's attention is the scarce resource: he did not read most of
the 277 escalations from the 2026-10-21 overnight run, so a long escalation queue is a failure mode,
not a safety net.

**Strict surface: the audio track list** (which files air). A real song dropped, or minutes of
non-music kept, is what listeners hear. Cost scales with duration in both directions: 20 s of tuning
kept is harmless, 3 min loses listeners ("changes the channel"); dropping a 20 s fragment is minor,
dropping a 6 min song is not.
**Near-strict:** track titles (Shawn: "I would really prefer to get these right"), then set/encore
placement ("somewhat less important, but I'd still prefer to get these right").
**Loose:** segue markers (an occasional miss is acceptable), venue wording (variants naming the same
place are fine), research claims and briefing cautions (not a big concern).
**Bounded:** the adjudicator never delivers, never deletes a show, never writes a station copy, and
its LLM spend runs under llama's existing usage pacing.

## Intent

Cut the held backlog with LLM judgement instead of Shawn's time, now (a backlog sweep) and from now on
(a pipeline step), so that what reaches Shawn is a short list of dozens, each with a ready proposal he
accepts with one keystroke. This ports the 2026-10-21 overnight prototype (`~/.llama-harness/t3/`:
`adjudicator-brief-v2.md`, `tools/build_bundles.py`, `tools/daemon.py`) into llama proper. It is the
held-backlog work's "part 2" backstop: deterministic fixes take the common causes, it the long tail.

A re-judge alone does not reach dozens. Measured 2026-11-06: 347 shows held; 316 have a prototype
verdict, and 254 of those were escalated, not applied. Their dominant classes: partial tape ~69 (30 of
them also have a better sibling), better sibling recording ~57, untitled or flags echoing an untitled
tape ~48, scrambled or shifted tags ~30, needs a listen ~23. The queue gets to dozens only with the
operator class rulings below.

## Goals

1. `llama adjudicate [SLUG...] [selectors]`: judge held shows, auto-apply verdicts that pass the
   policy gate, leave the rest held with a stored proposal. For the backlog sweep.
2. A pipeline step: when `get`/`redo`/`run resume` would leave a show held, adjudicate it first.
   Default on; `[adjudicate] enabled` in `config.toml`; `--adjudicate/--no-adjudicate` on those
   commands overrides config for that run (Shawn).
3. `llama triage` shows the stored proposal and accepts it with one key.
4. A recording pin, so a better sibling recording can be selected (by the adjudicator or by Shawn).
5. A pilot that measures cost per show and compares Opus with Sonnet before the full sweep.

## Non-goals

- Delivering, re-delivering, `clear-mark`, voicing. For a station-marked or delivered show only the
  library copy is fixed; the run report says how to re-deliver it (Shawn: fine with doing that
  himself; expected to be rare once the pipeline step exists).
- Reprocessing the campaign's **needs-LLM** class (`replay.legs`: a show cannot be re-derived without
  gather's LLM touchpoints; not "needs adjudication"). The existing machinery (`redo` /
  `reapply --with-gather-llm`) reprocesses them; whichever end up held are adjudicated like any other.
- Reusing the 2026-10-21 prototype verdicts (evidence and schema stale); every show is re-judged.
- Web access: the adjudicator judges from evidence llama already has, as the prototype did.
- Replacing deterministic guards. Flags still fire; the adjudicator judges them.

## Anti-goals (failure even if it works)

- A long-music track dropped, or minutes of non-music added, on the adjudicator's say without strong
  evidence.
- A taper's title replaced on weak evidence (violates the accuracy rule: tape notes are presumed
  correct; better to repeat a taper's error than mis-correct it).
- An escalation queue in the hundreds.
- Loops: an adjudicated show re-adjudicated by its own apply, or by every later `redo`, with no new
  evidence.

## Operator class rulings

Shawn ruled these on 2026-11-06. The prompt states them and the gate implements them.

- **Partial tape, no more complete sibling: airs by default** (Shawn: "in most cases a partial show is
  worth keeping, and can be useful to the scheduler in plugging short gaps"). Not held merely for
  being partial; its adjudication record notes that it is partial. A song cut off at the tape's edge
  airs as is. Every other bar still applies.
- **Partial tape with a more complete sibling:** handled as a better sibling.
- **Better sibling recording: switch automatically when the other recording is clearly better**
  (Shawn), else propose. See "Recording pin".
- **Fully untitled tape** (nothing names the songs): **hold** (Shawn). `--untitled` stays
  propose-only.
- **Scrambled or shifted tags: fix when confident** (Shawn): title edits at the title bar; else hold.
- **Needs a listen:** hold.
- **Partial tape whose better sibling fails the auto-switch bar: hold** (Shawn, 2026-11-06). The
  switch waits as a proposal and the show does not air under the partial-tape ruling meanwhile.

The pilot reports the projected queue per class against Shawn's tolerance: he can triage "dozens or
scores, maybe not hundreds", once the station has a solid base.

## How it works

### Evidence bundle

Built in-process per show from the show workspace and caches, mirroring the prototype bundle:
review flags; the track table (n, set, title, title source, matched, duration, filename); excluded
files with reasons and durations; `overrides.json`; vetting flags; notes; research, briefing
(truncated); JerryBase events; setlist.fm data; the selected item's archive.org metadata (description,
notes, original and derivative file lists with tags and lengths); archive.org reviews; up to 8
sibling recordings' metadata (the considered recordings, with their file lists and tags). Most sources
exist (`jerrybase.lookup`, `setlistfm` cache, `IAClient.metadata`, `catalog.recording_info`,
`read_model`). Each evidence source kind (below) is its own bundle section, so the gate can check
quotes against it. Sizes are capped so a large show fits one call.

Notes now reach an LLM; the `ShowNotes` docstring ("a note can never reach an LLM", a ruling about the
briefing) is updated to say so.

### The call

One new LLM task, `adjudicate`, tier **high** (Opus on `claude_cli`) by default, overridable via
`[llm.adjudicate]`. Prompt `prompts/adjudicate.md`, ported from `adjudicator-brief-v2.md` with its
binding operator rulings (taper wording ships, venue strings, discs are not sets, review-only titles
are weak), the class rulings above, and the pilot's catalogue of common causes. One call per show,
schema-validated through `herder.run_json_task` (its normal retries apply). Bundle text containing
`{{…}}` must not break rendering; a render or bundle error is caught per show (it stays held, the
error is logged) and never aborts a run.

### Verdict schema: typed edits keyed by filename

The verdict is a typed list of edits naming **files, not track numbers** (the prototype's shell
commands and `expect` checks broke on renumbering): include, exclude, set title, structure, venue,
city, switch recording, overrule. Overrides are already stored by filename.

**Structure is one edit:** the complete list of files a set break follows and the file the encore
follows (or none). It is the whole result, never additive. Any structure override drops segues and
disables the alignment checks; that is accepted, since segues are loose.

Per flag the verdict keeps the prototype's fields: verdict (`real-fixed-by-action | spurious |
real-not-fixable | undecidable`), confidence (`high | medium | low`), one-sentence why. Per edit:
confidence and one or more **evidence items**, each a short quote plus a source kind from a closed set:
taper description, original-file tag, derivative tag, sibling's track list, setlist.fm, JerryBase,
review. Plus an overall `kind` (`fix | overrule | hold`) and, for `hold`, what Shawn must decide.

Edits the adjudicator may only **propose**, never apply: `--set-date`, `--untitled`, `--narration`,
`rm`, `redo --from research`.

### Recording pin

`overrides.json` gains a recording field (an archive.org identifier, one of the performance's
considered recordings); `llama fix <slug> --recording <identifier>` and the "switch recording" edit
write it; select honours it.

Auto-switch bar ("clearly better"); failing any part makes the switch propose-only:
- Select's existing per-recording tests: the sibling has the wanted format, select found no recording
  complaints against it, and its lineage class ranks no worse than the current recording's.
- It adds tracks or resolved titles, with high confidence and substring-checked evidence.
- The show is neither delivered nor station-marked (a switch there forces a re-download and re-voice).
- `overrides.json` has no filename-keyed entries (exclude, include, titles, set breaks, encore), and
  the switch is the verdict's only track-list, title or structure edit.
- **Coverage**, checked after the re-gather against the pre-switch track list: every resolved
  pre-switch title (normalised with `songs.normalize_song`) appears; total kept duration is at least
  the pre-switch total; added duration on tracks with no resolved title or kept by the short-file rule
  is ≤ 60 s; and no blocking flags. A failure restores the snapshot. Coverage replaces the whole-show
  check for a switch, whose track list is new by design.

`fix --recording` and `[a]` on a switch refuse while filename-keyed entries exist, naming them and the
`fix` options that clear them (the plan adds a clear option for `include` entries, which `fix` lacks today).

### The policy gate (deterministic code, not the model)

Each edit is checked against a bar set by Shawn's priorities. A verdict auto-applies only if every
edit passes; otherwise nothing is applied and the whole verdict becomes the stored proposal.

**Substring check**, a hallucination filter: after whitespace, case and curly-quote normalisation,
every quote must be a substring of the bundle section for its claimed source kind, or the edit becomes
a proposal. It alone does not suffice for long track-list edits or titles; the table's anchored rules
apply there. **Sibling match:** a title from a sibling's track list needs the sibling file carrying it
to be within max(2 s, 1 %) of this file's duration (both in the bundle); a new title must appear in
its quote. **Duration** of an include/exclude is the named row's or track's, captured before the apply,
the larger of metadata and measured length; unknown counts as > 60 s.

| Edit | Auto-apply bar |
|---|---|
| include / exclude, ≤ 60 s (short bar) | confidence medium or high |
| include / exclude, > 60 s or unknown length, or any short-bar edit once the verdict's sum > 120 s (long bar) | high, evidence from the taper description, an original-file tag or a sibling's track list, and the quote comes from a section other than the file's own tag row and contains the filename stem or the track's position |
| exclude of a track with a resolved song title, any length | propose-only |
| include of a row dropped as duplicate listing, duplicate derivative or spam-shaped | propose-only |
| set title on an unresolved title, a placeholder (`is_placeholder_title`), or a title from `tags`, `desc-position`, `sibling-format`, `sibling-align`, `sibling`, `setlist` or `setlist-gap` (title bar) | high, and: from a sibling's track list with a sibling match; or from the taper description (substring-checked) or this file's own original-file tag row |
| set title from setlist.fm, JerryBase or reviews alone | propose-only |
| structure (structure bar) | high, with a substring-checked quote from taper-side evidence (the taper description, file tags or filenames, e.g. set headers, `s1tNN`, "Encore:"); from setlist.fm or JerryBase alone → propose-only (author's call, matching the existing rule that taper set markers win) |
| venue | medium |
| city | propose-only (a city conflict can mean another performance) |
| switch recording | the auto-switch bar |
| overrule | by flag kind, below |
| any edit that changes or removes any existing `overrides.json` entry | propose-only |
| any other edit, and propose-only edits | never |

**Overrule bars by flag kind** (llama's existing overrule kinds; an unmapped kind is never-auto).
Title- and structure-bar overrules need high confidence and a substring-checked quote.

| Flag kinds | Overrule bar |
|---|---|
| `research-song`, `research-date` | title bar |
| `research-sets`, `alignment`, `single-set`, `sets-not-found`, `jerrybase-set-count`, `jerrybase-closer` | structure bar |
| `venue`, `briefing-song`, `briefing-set`, `briefing-other` | medium |
| `titles`, `low-confidence-setlist`, `tape-spans`, `multi-event`, `events-unassigned`, `no-tracks`, `merged-tracks`, `city`, `other` | never (unresolved tracks are fixed by title edits; a fully untitled tape holds) |

A duration mismatch flag has no overrule kind and is never overruled.

**Verdict-level vetoes** (from the prototype): auto-apply only when `kind` is `fix` or `overrule`, the
show is judged correct after the action, and no flag is judged `real-not-fixable` or `undecidable`.

**Sibling-coverage veto** (Shawn, 2026-11-07, after the pilot: the model's `better_sibling: null` is
not trusted). A verdict with no `switch_recording` edit is propose-only while any considered
recording (selection.json `scores` minus the current recording) keeps more than the current one,
like with like: more `kept_tracks` than the current recording's own `scores` entry or, as a
tie-break only when the `kept_tracks` are EQUAL and both durations are known, more than
`SIBLING_COVERAGE_TOL_S` (60 s) more kept duration (each recording's select-filtered files' lengths
from its own metadata, as the bundle fetches it). A sibling with fewer kept tracks never vetoes on
duration, and equal tracks within the tolerance do not veto (duration as a tie-break only is
Shawn's ruling, 2026-11-07, resolving the R2 spec-review finding on the tolerance: full-show
sources with fewer, longer files no longer demote a correct verdict). It fails closed: no `scores` in selection.json, show.json and selection.json naming
different current recordings, or an entry (the current one's included) without a usable
`kept_tracks`, vetoes too; an unknown duration skips only the duration clause. A verdict with a switch is left to the
auto-switch bar. An operator pin on the current recording (`overrides.recording_source` `operator`, or absent on an older
pin; `fix --recording` and an accepted switch write `operator`, an auto switch `adjudicate`) exempts the show from this
veto, its unknown-coverage arms included (Shawn, 2026-11-07: his choice of recording is the decision). This enforces "partial tape whose better sibling fails the auto-switch bar: hold"
in code.

**Placeholder veto** (Shawn, 2026-11-07, after the pilot: Opus overruled five unknown-song flags on
a show shipping `Track 3`/`Track 9`/`Track 11`/`Track 12`, and those flags were all that held the
placeholders off the air). While any shipped title of the current (pre-verdict) show is a
placeholder, every overrule of a `research-song` flag is propose-only (bar `propose-only`, not
passed), with the reason `research-song overrule while <n> shipped title(s) are placeholders (e.g.
<file>: '<title>')`. A placeholder is `is_placeholder_title(title)`, failing closed: a blank or
missing title, or a `title_source` of `unresolved`, counts too. It is strict: `set_title` edits in
the same verdict that would replace the placeholders do not lift it, so a verdict mixing title
fills with a research-song overrule lands as a proposal (one keystroke for the operator). Other
overrule kinds and non-overrule edits are unaffected.

The veto also fires (Shawn, 2026-11-07, R3 fix round 1) when any title of the **predicted
post-verdict kept set** is a placeholder, reason `research-song overrule while <n> predicted
post-verdict title(s) are placeholders (e.g. <file>: '<title>' | no determinable title)`. That set
is the current tracks minus excluded files plus included files, with `set_title` edits applied. An
included file without a `set_title` takes the title gather's `tags` rung would give it: its own
cleaned metadata tag (`clean_tag_title`) when `is_real_title` accepts it; otherwise (no metadata
row, a blank, `unknown` or residue tag) its title is undeterminable and counts as a placeholder.
This closes the include gap at the gate. On every verdict, a research-song overrule or not, the
same prediction makes the include itself propose-only (Shawn, 2026-11-07), reason `include ships a
placeholder title (<file>: '<title>' | no determinable title)`. Apply's whole-show re-check is the
backstop: an included file that lands after the re-gather with a placeholder title
(`gate.is_placeholder_track`), whether or not the verdict `set_title`s it, fails the apply and the
show is restored (`<file>: included with a placeholder title '<title>'`).

Unsure on a long track means **held** (Shawn, 2026-11-06: hold for now; triaging dozens later is
reasonable, hundreds is not). The 60 s and 120 s lines and the bars are constants in one place, so a
later retune is one edit. (60 s is my call; Shawn's examples were 20 s vs 3 min.)

### Before judging

- **Stale pre-flight:** a show that fails llama's existing staleness check (`show.json` is not what
  gather keeps now; `fix` refuses such shows) is not judged. Its outcome is `stale: reprocess first`,
  listed in the run report; reprocessing is the campaign's or `redo`'s job.
- **Target validation**, before anything is written: exclude targets must be current tracks; title
  and structure targets must be current tracks or excluded files the same verdict includes (Shawn,
  2026-11-07, R4: re-admit a file and title it, or place a break or the encore on it, the latter
  valid but propose-only at the gate); include targets must be excluded rows; a recording target
  must be a considered recording. One file named
  by two conflicting edits (two set_titles, include and exclude, exclude and set_title, the same
  include or exclude twice; include plus set_title is no conflict), a structure naming a file the
  verdict excludes, an exclude of a file carrying a title, break or encore key (as `fix` refuses it),
  or any unknown filename makes the verdict malformed: the show stays held with the verdict stored.
  A flag judgement must name a current flag; repeated judgements of one flag that agree on verdict
  and confidence count as one, the first (its `why` is the one shown; R5, 2026-11-07:
  `review_flags` can carry a string twice, and the bundle lists each distinct flag once), and
  repeated judgements that differ in verdict or confidence are malformed (`judged twice with
  different verdicts or confidence`).

### Apply and re-check

The apply runs in its own `show_unit` (snapshot/restore) with the bundle's captured show view as the
expected state, so a concurrent change raises `ShowChanged` and the show is skipped (re-judged next
run). Inside the unit: capture the before state, write overrides through a filename-keyed path (not
the track-number writer), one `_redo_show_locked` from the earliest stage any edit needs, re-read the
show. With a track-list edit in the verdict, no subject-less structure-kind overrule is written before
the redo; those flags are judged only by the re-hold rule.

- **Whole-show check.** Before writing, capture per track its filename, title, title source, set and
  segue, plus the kept set. The predicted result is the before state plus includes minus excludes,
  with the named titles changed and set labels as the structure edit gives them. Any difference not
  predicted (a change in the relative order of unnamed tracks, or in an unnamed track's title, title
  source or set; a kept set that is not exactly the prediction) restores the snapshot and keeps the
  verdict as a proposal noting the diff. An included track's own title and set are not predicted,
  except that a `set_title` on it must land (that title, title source `override`, as on a current
  track) and a structure edit naming it must give it the set label its landed position implies (R4;
  a consistency check, not a position prediction, so the gate keeps a structure edit naming an
  included file propose-only, reason `structure names a file this verdict includes; its position
  is not predicted`; accepting one writes the break or encore on the included file to
  `overrides.json`, final2 F1); otherwise, if its title is unresolved, the usual `titles` flag holds the
  show. Segue loss from a structure edit is
  expected and stated.
- **Silenced flags.** Any pre-apply flag key absent after the redo that the verdict did not judge
  `spurious` or `real-fixed-by-action` at a passing bar restores the snapshot and becomes a proposal.
- **Re-hold rule.** If the show is still held, auto-overrule only post-apply flags whose full key
  (kind and subject) equals a pre-apply flag the verdict judged spurious at a passing bar; never
  `alignment` or a subject-less structure kind after a track-list or structure edit, never a duration
  mismatch. Otherwise the show stays held with the proposal. No second LLM call.
- **Apply failure.** A transient failure (download error, `RateLimited` inside the redo) restores the
  show and leaves it held and unjudged, re-judged next run. A station-reuse refusal restores it and
  becomes a proposal carrying the error.

Adjudicator overrules carry `source: "adjudicate"`. A marked show whose campaign record ends processed
becomes eligible for `deliver --fixed`; for every other changed delivered show the run report prints
`llama deliver <slug> [--replace-voiced]`.

### Adjudication record and loop guard

Every adjudication writes `<show>/adjudication.json`: the verdict, the gate outcome per edit, what was
applied and each applied edit's evidence source, the result, the model, and a digest. An applied
record is written inside the unit, so it commits and restores with the show; a proposal is written
after the restore. The digest is the one staleness test, computed over the final state at the end of
the unit (after the redo, or the restore): flags, track table, excluded rows, overrides without
timestamps, identifier; not research or briefing text.

The apply's own redo never re-adjudicates. A later pipeline run adjudicates again only if the show is
held **and** the digest changed (new flags, new overrides, new recording); `llama adjudicate --force`
re-judges anyway.

### Proposals in triage

`llama triage` prints the stored proposal under the flags (each edit with its evidence and why it did
not auto-apply) and adds `[a] accept proposal`. Accepting refuses on a digest mismatch (triage says
the proposal is stale instead of offering `[a]`), then captures a fresh view as the unit's expected
state and applies the typed edits (a recording pin included) through the same apply path, target
validation and whole-show diff, but not the gate or the re-hold auto-overrule. Propose-only items are
printed as the commands to run; a proposal with only those offers no `[a]`. `llama adjudicate SLUG...
--accept --yes` does the same non-interactively: named slugs only, each proposal printed first.

### Pipeline step

Trigger: the show is held (`needs_review`) after processing, by any stage's flags. Hook points are
exactly `get` (via the run executor), `redo` (single and batch) and `run resume`; not `fix`, `triage`,
`reapply`, or the adjudicator's own apply. Adjudication runs after the caller's lock and `show_unit`
are released; its failure never touches the caller's committed result. Not in `SHOW_STAGE_ORDER`.

Enabled by `[adjudicate] enabled = true` (new strict config section, default template updated) and
overridden by `--adjudicate/--no-adjudicate` on `get`, `redo` and `run resume` (tri-state, same
precedent as `--wait/--no-wait`; persisted run settings never replay it). `reapply` stays LLM-free;
its held rows are swept by `llama adjudicate`.

### Backlog command and pacing

`llama adjudicate` selects held shows by default (existing selectors work), skips shows whose
`adjudication.json` digest is current unless `--force`, and loops with the same pacing gate, `paused:`
handling of `RateLimited`, and stop-after-3-consecutive-LLM-failures as `reapply`'s list form.

Every adjudication call, pipeline or backlog, runs behind llama's existing pacing gate; a `redo` batch
gets the reapply-style gate before each adjudication. `RateLimited` during adjudication leaves the
show held and unjudged (no `adjudication.json` change) and pauses the run the way it does for shows.

`--dry-run` records verdicts and gate outcomes without applying anything; a dry-run record is marked
as such, is never current, and is never offered as `[a]`.

The run ends with a short report: counts by outcome; **every auto-applied track-list change with its
duration**, built from the whole-show diff rather than the edit list (so Shawn can skim what changed on
air, without being asked to approve it); the held-with-proposal list; the `stale: reprocess first`
list; the delivered shows that changed, each with its re-delivery command.

### Pilot (before the full sweep)

30 held shows, stratified by the classes in Intent, judged without applying and run twice: Opus and
Sonnet, each on an exact model pin (no tier escalation) so each arm is what it claims. Per-model
results go to a pilot directory, not `adjudication.json`. Measure per-show meter cost and wall time,
plus the full cost of a few real applies (they re-run vet and brief); compare the two models' gate
outcomes with each other and with the prototype verdicts for the same shows; report the projected
held-with-proposal count per class. Switches either model would auto-apply are applied and restored,
so coverage and the no-blocking-flags check are measured. An Opus reviewer checks every edit either
model would auto-apply, and the disagreements; the strict-surface ones (long track-list edits, title
fills and replacements, switches; expected under a dozen) are also listed for Shawn to spot-check.

Acceptance bar before the full sweep: zero wrong auto-applied > 60 s track-list edits, title fills or
replacements, structure edits or recording switches. Any class that fails becomes propose-only. Shawn
decided the model from the results (ruling 1, 2026-11-07): Opus is the default (task `adjudicate`,
tier `high`), and Sonnet stays an option via an `[llm.adjudicate]` override. He sees the projected
cost of the full sweep before it starts.

## Limitations

- An adjudicator overrule of a subject-less kind persists for that recording as an operator overrule
  does today, so a later change that makes the problem real is not re-flagged.

## Constraints

- llama never imports emcee/transmitter; the adjudicator touches only the library workspace.
- Station lock and show lock rules as everywhere; the apply runs under the show lock via `show_unit`.
- Offline deterministic tests with the `fake` backend. Gate tests are mutation-checked at every bar
  boundary: 60 s, 120 s cumulative, unknown duration, sibling-match tolerance, each flag kind, each
  evidence rule pass and fail.
- Unknown config keys are errors (`_StrictModel`); the default config template test must pass.

## Left to the builder

Bundle caps and layout; exact schema field names; `adjudication.json` layout; how the run report is
printed; whether `llama status` gets an `--adjudicated` view; how adjudication spend feeds the pacing
estimate; the pilot's show selection script (lives in `scripts/`).
