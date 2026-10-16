# emcee: moving shows between profiles, recording the TTS, and a pause before `emcee run` — design

**Date:** 2026-10-16
**Scope:** `packages/emcee`, plus documentation. llama: one
documentation-model edit, no behavior. transmitter: one docstring edit, no
code change. herder is untouched.
**Review mode:** Opus.

## Stakes

The station root holds 341 delivered packages on the NAS
(`/Volumes/media/lma-radio/delivered/`), and transmitter airs from it. Nothing
in this work touches a show's music or llama's library. What it does touch:

- **Re-voicing a ready package is destructive and costs money.** It overwrites
  the package's DJ script and clips (regenerable, at LLM + TTS cost). Today
  this happens only on an explicit `emcee voice`. After this change, adding
  one artist rule makes every matching ready package pending at once (17
  Tedeschi Trucks Band shows for the motivating rule), and the next `emcee
  run` re-voices them all.
- **What "pending" means for air changes.** A package made pending by the
  profile check alone keeps airing its old voicing. It drops out of
  transmitter's pool only while its own re-voice runs (`_process_one` clears
  the DJ blocks first) or if that re-voice fails. transmitter's eligibility
  deliberately does not gain the profile check: it cannot see rules or moves.
  `emcee status` "pending" therefore no longer means "off air".

**Strict surfaces:**

1. **No spend without a confirmation.** `emcee run` never makes an LLM or TTS
   call until it has printed what it will do and the operator has said yes
   (or passed `--yes`). With no terminal attached and no `--yes`, it refuses.
2. **A recorded move is never silently lost.** `moves.json` is the only list
   of the operator's one-off decisions. An unreadable or malformed file is a
   hard error for every command that resolves a profile, never "no moves":
   treating it as empty would mark every moved show pending and re-voice it
   back under its old profile. A missing file is a hard error too whenever a
   package records that it was voiced under a move (section 3). **Limit:**
   that record exists only for moves that have been voiced. A move not yet
   voiced, and an exemption move (one that leaves voicing unchanged, such as
   `--delivered`), live only in `moves.json`; if the file goes missing, those
   are lost without an error, and `emcee run`'s plan, which names every
   re-voice and its reason, is the last guard.
3. **Existing packages are not re-voiced by this release alone.** With no
   rules and no moves, every package that is ready today stays ready, whether
   or not its manifest predates the new fields.

## Background

- **Where the profile comes from.** llama records the profile that found a
  show in `provenance.json` (`models.py:318`) and stamps it into the
  package manifest as `source.profile` (`manifest.py:31`). Nothing edits it
  after that.
- **How emcee uses it.** `assignment_for` (`process.py:44`) looks the profile
  up in `[assign.profiles]`, falling back to `[assign] default`, then the
  house voice. Today the presenter is resolved twice per package: once in
  `cli._process_one` (`cli.py:250`), and again inside `process_package`
  (`process.py:282`) for the presenter and the on-air title.
- **Readiness is derived, never stored** (`station.py:57`): script present,
  DJ audio present, `broadcast.m3u` present, every track's audio present.
  `emcee run` voices whatever is not ready.
- **`dj_audio` already records the presenter** (`models.py:33`), always
  serialized so `null` (house) is distinct from a legacy manifest with no key.
- **The TTS record was deliberately left out before.** The 2026-10-12 local
  TTS spec put "recording backend/model in the manifest's `dj_audio` block"
  out of scope because "the presenter file already says, unless re-pinned
  later". The re-pinning gap is the reason to add it now, and this work
  already changes the same block.
- **The render cache key includes the provider's `voice` and `model`**
  (`audio.py:332`), so every clip in one package, cached or fresh, comes from
  the provider resolved for that package. One TTS record per package is
  exact; a per-clip record would repeat it.
- **The motivating data**, funk-profile packages by artist at the time of
  writing: Soulive 20, Tedeschi Trucks Band 17, JJ Grey and MOFRO 9, Lettuce
  7, New Mastersounds 6, Dumpstaphunk 6, The Motet 5, Karl Denson's Tiny
  Universe 5 plus 3 more spelled "Karl Densons Tiny Universe", Robert Randolph
  [and the Family Band] 3, and singletons. The spelling drift is why artist
  matching must be loose.
- **Out of band, already done:** the funk profile's criteria
  (`~/.llama/profiles/funk.toml`) now exclude blues-influenced rock and
  slide-guitar-led southern rock, naming Tedeschi Trucks Band, so future
  winnows stop putting them there. That is operator config, not part of this
  build.

## 1. The effective profile

One pure function decides which profile a package is voiced as:

```python
def effective_profile(config, moves, manifest) -> Effective
# Effective(profile: str | None, source: "move" | "artist" | "llama",
#           rule: str | None)   # the matching rule's artist key, for messages
```

First match wins:

1. a **move** recorded for the manifest's `source.performance_id`;
2. an **artist rule** whose normalized key equals the normalized
   `show.artist`, and whose `from` list (if any) contains llama's profile;
3. llama's profile (possibly `None`, for a one-off `llama get`).

"llama's profile" is always read through `station.manifest_profile`, the
existing total accessor that never raises and maps `""` and non-strings to
`None`.

The presenter/title lookup (`assignment_for`) then runs on
`Effective.profile`, unchanged.

**Config and moves are loaded once per command invocation** and passed
explicitly to everything that needs them: the scan, the plan, and voicing. No
function in the resolution path takes moves as an optional or defaulted
parameter, so no caller can resolve without them.

**Every reader of the profile switches to the effective one:** voicing
(presenter, title and bed, section 4), `station.scan`/`_scan_broad`
(`PackageStatus.profile`), `emcee run`'s `--profile` and `--assigned`
filters, `--dry-run` rows, `emcee status` (summary grouping, `--profile`,
`--list`, `--json`), and `_note_unmatched_profiles`. `emcee run --profile
southern` therefore includes moved TTB shows, and `--profile funk` no longer
does.

`PackageStatus` gains `delivered_profile` (llama's profile) beside `profile`
(now the effective one). `emcee status --json` rows carry both, plus
`profile_source` (`move`/`artist`/`llama`). The table and summary show the
effective profile; a row whose effective profile differs from the delivered
one is marked, e.g. `southern (from funk)`.

`scan` currently takes only a root. It gains the config and the loaded moves
so it can compute the effective profile; it stays read-only.

## 2. Artist rules (A)

Hand-edited, in `~/.emcee/config.toml`:

```toml
[assign.artists]
"Tedeschi Trucks Band" = "southern"                         # from any profile
"JJ Grey and MOFRO"    = { profile = "southern", from = ["funk"] }
```

- The string form is shorthand for `{ profile = "..." }`.
- `from` is optional. Absent: the rule applies whatever profile delivered the
  show, including a show with no profile. Present: it applies only when
  llama's profile is in the list. An empty list is a config error (it could
  never match).
- **Matching** compares normalized names. `normalize_artist(s)`, in order:
  casefold; drop one trailing `[...]` group; replace `&` with ` and `; delete
  apostrophes (`'` and `’`), so "Denson's" and "Densons" meet; replace every
  other character that is not a Unicode letter or digit with a space (so
  "Béla Fleck" keeps its `é`); collapse whitespace and strip; then drop a
  leading `the `. "Robert Randolph [and the Family Band]" and "Robert
  Randolph" match; "Robert Walter's 20th Congress" and "Robert Walters 20th
  Congress" match.
- **Validation at config load** (the strict config base, `extra="forbid"`):
  - a rule's `profile` with no `[assign.profiles.<name>]` entry is an error
    naming the rule and the missing entry (otherwise a typo silently routes
    shows to the default presenter);
  - two keys that normalize to the same name are an error naming both;
  - a key that normalizes to the empty string is an error.
- `from` names are not validated against anything: emcee does not know
  llama's profile list, and a `from` naming a profile no package carries is
  harmless.

## 3. One-off moves (B)

```
emcee move <show> <profile>     # record a move
emcee move <show> --delivered   # record a move back to the delivered profile
emcee move <show> --clear       # remove it
emcee move --list               # every recorded move
```

- `<show>` is addressed exactly like `emcee voice`: a path, or a name or
  unique substring under `[station] root` (`--station-root` overrides), exact
  name beating substring hits (`cli._resolve_package`).
- **Stored** in `<config.root>/moves.json`: the emcee workspace root, the
  same root that holds `presenters/` (default `~/.emcee/moves.json`). It is
  keyed by the manifest's `source.performance_id`, so a move survives llama's
  `--replace-voiced` re-delivery, which replaces the package directory
  wholesale:

  ```json
  {"TedeschiTrucksBand/2012-11-29": {"profile": "southern",
                                     "package": "tedeschitrucksband-2012-11-29",
                                     "moved_at": "2026-10-16T20:14:03Z"}}
  ```

  `package` is informational (for `--list`); resolution uses the key only.
  `profile` is `null` for a move back to a delivered profile of `None`.
- **Writing.** `emcee move` takes an `fcntl.flock` on `moves.json.lock`
  (beside the file) around load, modify and write, so two concurrent `emcee
  move`s cannot drop each other's entry. It modifies the raw loaded dict in
  place, so unknown keys in other entries survive, and writes via unique temp
  + fsync + rename. `--clear` never deletes the file: clearing the last move
  leaves `{}`.
- **Refusals** (exit 1, file unchanged):
  - the target profile has no `[assign.profiles.<name>]` entry and is not the
    package's delivered profile;
  - the manifest has no `source.performance_id`;
  - the package is unsupported (pre-v3) or its manifest is unreadable.
- **A move to the delivered profile is valid without an assignment entry**,
  whether written by name or as `--delivered` (the only spelling for a
  delivered profile of `None`). It beats an artist rule, so it is how one show
  is exempted from a rule ("this TTB show stays in funk").
- `emcee move` makes no LLM or TTS call. It prints the effective-profile
  change and the package's resulting state, taken from the readiness profile
  check after the move:
  - pending, e.g. `moved: tedeschitrucksband-2012-11-29  funk -> southern
    (pending; voiced on the next emcee run)`;
  - ready, e.g. an exemption of a show a rule had made pending:
    `moved: tedeschitrucksband-2012-11-29  southern -> funk (ready; already
    voiced as funk)`;
  - unvoiced packages say `(unvoiced; voiced as <profile> on the next emcee
    run)`;
  - the identical move already recorded: `unchanged`, exit 0.
- **`--clear` addressing.** Recorded entries are matched first, by exact
  `performance_id` or exact recorded package name, so a stale move whose
  package is gone can be cleared. Only if none matches is `<show>` resolved as
  a live package (exact name, then unique substring) and its move cleared.
  If more than one recorded entry matches (e.g. a stale entry and a new one
  under a re-keyed `performance_id` share a package name), `--clear` refuses
  as ambiguous and lists the `performance_id`s, which can then be cleared
  exactly. `--clear` always prints the `performance_id` it removed.
- `--list` prints one row per move: the package name, the target profile,
  the delivered profile, `missing` when no package under the station root
  carries that `performance_id`, and `[no assign entry]` when the move fails
  use-time validation (below).
- **Stale moves.** A move whose `performance_id` matches no scanned package
  is harmless and kept. `run` (in the plan) and `status` print `note: N
  recorded move(s) match no package (emcee move --list)` whenever there is
  one. This also covers llama re-keying a performance, e.g. the early/late
  `/eN` split.
- **Validation at use time.** After loading moves, a move whose target has no
  `[assign.profiles.<name>]` entry, and is not the package's delivered
  profile, makes `run` and `voice` report that package as an error row
  (`move target "<p>" has no [assign.profiles] entry`) and not voice it; other
  packages proceed. `status` marks such a move `[no assign entry]`.
- **Loading** (`moves.load_moves(root)`): any read or parse failure, or a
  shape that is not `{str: {"profile": str | null, ...}}`, raises an
  `EmceeError` naming the file (strict surface 2). Every command that
  resolves a profile loads moves first and so fails loudly on a bad file:
  `run`, `voice`, `status`, `move`.
- **A missing file.** A missing `moves.json` is "no moves", unless a scanned
  package's `dj_audio.profile_source` is `"move"` (for `voice`, the named
  package). Then `run`, `voice`, `status` and `move` fail with an
  `EmceeError` naming the expected path and the count of such packages,
  before any work. `move` scans the station for this check before writing:
  otherwise recording one new move would create a fresh `moves.json` and
  silence the check for every move that was lost. (`move --list` and
  `--clear` refuse the same way.) The error names both ways out: rebuild the
  entries (below), or write `{}` to the path to accept the loss.
- **Recovery.** Every move-voiced package records its profile and
  `profile_source: "move"` in its manifest, so voiced moves can be rebuilt
  from the station root by hand. Unvoiced and exemption moves cannot (see
  strict surface 2's limit).

## 4. What emcee records, and readiness

**One resolution per package, passed through.** `_process_one` computes the
package's `Effective`, its assignment (presenter, title) and its
`TTSResolution` once, and passes them into `process_package` as required
arguments with no defaults. `process_package` no longer calls
`resolve_assignment`, and `resolve_assignment` changes to take a profile
(the `Effective`'s) instead of a manifest, so no caller can key it on the
delivered profile by accident. Today the presenter is resolved twice; a second
resolution that missed the moves would pair one presenter's voice with
another's persona, title and bed, and record the wrong profile, so the
package would be re-voiced on every run.

`DJAudioBlock` (`models.py:33`) gains three required fields (no defaults).
Today `audio._synthesize_dj_audio` builds the block (`audio.py:355`) and
`process_package` sets `presenter` afterwards; instead,
`_synthesize_dj_audio` returns only the clip paths and `process_package`
builds the whole block, with `presenter`, `profile`, `profile_source` and
`tts`. Test helpers that build a block directly (`tests/test_process.py`,
`tests/test_run_cmd.py`, `tests/test_package_io.py`) supply the new fields.

```python
profile: str | None                                  # the effective profile voiced as
profile_source: Literal["move", "artist", "llama"]  # where that profile came from
tts: TTSRecord                                       # how its clips were synthesized

class TTSRecord(BaseModel):
    backend: str          # "voxtral" | "elevenlabs" | "mlx_audio" | "fake"
    model: str | None
    voice: str            # the provider's voice identity: a preset name, or
                          # "clone:<sha256[:16]>" of the reference clip
                          # (voxtral) or of the clip plus its transcript
                          # (mlx_audio)
```

`backend` comes from the `TTSResolution`; `voice` and `model` come from the
provider instance (`speech.voice`, `speech.model`), the same values the
render-cache key uses (`audio.py:332`). For `mlx_audio` the clone identity
hashes the reference clip plus the transcript (`tts/mlx_audio.py:47,70`); for
voxtral, the clip alone.

The fields are required so that a legacy block round-tripped through the
model fails loudly instead of writing `"profile": null`, which would make the
package pending. Legacy `dj_audio` blocks are only ever updated as raw dicts.
`scripts/backfill_voiced_by.py` round-trips through the model; it touches no
live manifest today (all 219 voiced blocks already carry `presenter`), and
changes either to refuse a block that already carries `profile` or to a
raw-dict update, whichever is simpler.

**Readiness gains a fifth leg**, the profile check. When `dj_audio` is
present:

- the **voiced profile** is `dj_audio["profile"]` if the key is present,
  else llama's profile (a legacy manifest was voiced under llama's profile,
  since no rules or moves existed). llama's profile is read through
  `station.manifest_profile` on both sides of the comparison;
- if the voiced profile differs from the effective profile, the package is
  `pending`, with one reason per direction:
  - `voiced as funk, now southern (artist rule "Tedeschi Trucks Band")`
  - `voiced as funk, now southern (move)`
  - `voiced as southern, now funk (move no longer recorded)`, when
    `dj_audio.profile_source` is `move` and no move exists now
  - `voiced as southern, now funk (delivered profile; no rule or move
    applies)`, otherwise.

With no rules and no moves, the effective profile is llama's profile, so a
legacy manifest compares equal and stays ready (strict surface 3). A missing
`tts` never makes a package pending: changing a presenter's TTS, or its
presenter, is not a re-voice trigger in this work.

transmitter's eligibility does not mirror the profile check (see Stakes).

`emcee status` shows the recorded TTS in `--json` (`tts` object, `null` when
absent) and nowhere else.

**llama's behavior is unaffected.** Its `DJAudio` model (`models.py:262`) is
a documentation copy of the block, kept shape-compatible by hand; it gains the
three fields as optional. llama reads a delivered manifest's `dj_audio` only
as "is it non-null" (`cli.py:2005`). Its `status`/`deliver --profile` keep
using the delivered profile; that is a documented limitation, not a bug.

## 5. The pause before `emcee run`

After scanning and filtering, and before any LLM or TTS call, `emcee run`
prints a plan and asks, both on stderr:

```
to voice: 20 packages, 60 clips
  new        2
  re-voice  17  voiced as funk, now southern (artist rule "Tedeschi Trucks Band")
                tedeschitrucksband-2012-11-29
                tedeschitrucksband-2013-07-11
                ...
  repair     1  emerson-1999-03-03
TTS:
  gregg (Mr. LeNoir)   voxtral  voxtral-mini-tts-2603   18 packages
  kurt (K.C.)          mlx_audio  Qwen3-TTS-12Hz-1.7B   2 packages
note: 1 recorded move(s) match no package (emcee move --list)
Proceed? [y/N]
```

- **Categories:**
  - `new`: `dj_audio` absent;
  - `re-voice`: `dj_audio` present and the profile check fails. Grouped by
    reason with counts, and every re-voice package listed by name, since
    re-voicing is the destructive action;
  - `repair`: pending for a missing clip or missing `broadcast.m3u`, with the
    profile check passing; listed by name like re-voices, since a repair also
    overwrites the existing script and clips.
  - A package whose only failing leg is missing track audio is left out of
    the plan and reported as a skip row (`skip <slug>: N audio file(s)
    missing; re-deliver from llama`): voicing cannot fix it, so it would be
    paid for again on every run. If it also fails another leg, it is still
    skipped: tracks come first.
- **Clips** is exact: per package, one intro per non-encore set in the
  manifest's tracks plus one outro (`script_guard` enforces this,
  `scriptwrite.py:145-149`).
- **TTS** lists each presenter (or `house`) that will voice something, by id
  with the presenter's `name` in parentheses, the backend and model
  `resolve_tts` gives, and its package count. A presenter that cannot be
  resolved shows the same markers `--dry-run` already uses (`[missing …]`,
  `[invalid …]`, `[unresolved: …]`), and those packages fail individually as
  today.
- **`--yes` / `-y`** skips the question.
- **Interactive** requires stdin to be a TTY, checked through a small
  module-level helper (`_stdin_is_tty()`) that tests patch. With no TTY and no
  `--yes`: print the plan, then exit 1 with `error: refusing to voice without
  confirmation; pass --yes`.
- **Declined:** `nothing voiced`.
- **Nothing to voice:** no plan, no question.
- **`--dry-run` always wins:** it prints the per-package `would voice:` rows
  as today, then the same plan block, and never asks; with `--yes --dry-run`
  nothing is voiced.
- **Exit code:** 1 whenever any error row was printed, whether the operator
  proceeded, declined, or there was nothing to voice; otherwise a decline or
  nothing to voice exits 0.
- **After the yes**, `emcee run` voices exactly the packages counted in the
  plan, from the same scan, with the same loaded config and moves. It never
  re-scans.
- Error and unsupported rows are still reported as they are found, and do not
  count toward the plan.
- `emcee voice` (one named package) does not pause.

**Limitation:** a move recorded, or config edited, while a run is in progress
or its prompt is open takes effect on the next run, and the affected package
may be voiced twice. Record moves before `emcee run`.

## Error handling summary

| Situation | Behavior |
|---|---|
| `moves.json` unreadable or malformed | `EmceeError` naming the file; `run`/`voice`/`status`/`move` exit 1 before any work |
| `moves.json` missing while a package records `profile_source: "move"` | `EmceeError` naming the expected path and the count; `run`/`voice`/`status`/`move` exit 1 before any work |
| artist rule targets a profile with no `[assign.profiles]` entry | config load error, which blocks every emcee command |
| two artist keys normalize alike, or one normalizes to empty, or `from = []` | config load error |
| `emcee move` to a profile with no `[assign.profiles]` entry (other than the delivered profile), or a package with no `performance_id` | refuse, exit 1, file unchanged |
| a recorded move whose target has no `[assign.profiles]` entry (other than the delivered profile) | `run`/`voice`: error row for that package, not voiced; `status`/`move --list`: `[no assign entry]` |
| a move whose package is gone | kept; `--list` shows `missing`; `run`/`status` print a note; `--clear` removes it |
| `emcee run` with no TTY and no `--yes` | plan printed, exit 1, nothing spent |
| `emcee run` printed any error row | exit 1 |

## Rollout

1. Create the presenter (`emcee presenter add`).
2. Add its `[assign.profiles.<name>]` entry.
3. Then add artist rules that target it. A rule naming a profile without an
   entry is a config load error that blocks every emcee command, including
   `presenter add`.

Today's config has entries only for bluegrass, dead, indie and funk. All 14
packages delivered as `southern` are unvoiced, so adding the `southern` entry
strands nothing.

When `emcee run` is invoked by an agent (Claude Code's shell has no TTY), the
agent runs `emcee run --dry-run`, shows the plan, and passes `--yes` only
after the operator approves. The `--yes` run scans again, so anything
delivered, moved or edited between the dry run and the approval is voiced
without having been shown; keep that gap short, and run nothing else against
the station in between.

## Docs

- transmitter's `station.py` module docstring lists emcee's readiness legs:
  say the profile check is deliberately not mirrored.
- `docs/station-brief.md`: the new `dj_audio` shape.
- The README and CLAUDE.md readiness wording; CLAUDE.md also gains the agent
  line from Rollout.
- llama's `DJAudio` (`packages/llama/src/llama/models.py:262`): the three new
  fields, optional.
- `docs/playout-incident-runbook.md`: a note on how transmitter treats a
  re-voice (Verified premises).

## Testing

All offline, on the `fake` LLM and TTS backends, extending the existing emcee
suite.

- **`normalize_artist`:** each rule above, including the Denson's/Densons,
  Robert Randolph bracket and Robert Walter pairs from the real data, and
  that two genuinely different artists stay different.
- **`effective_profile`:** move beats artist rule beats llama; `from`
  present and absent; a show with `source.profile` null under a rule with
  and without `from`; a move back to the delivered profile beating a rule.
- **Config:** shorthand and table forms parse to the same thing; each load
  error in the table above.
- **Readiness:** a legacy manifest (no `profile` key) with no rules stays
  ready (strict surface 3), including with `source.profile` = `""`, null,
  and `source` missing; the same manifest under a matching rule goes pending
  with the right reason; each of the four reason texts; a manifest voiced as
  the effective profile stays ready; a missing `tts` never makes a package
  pending.
- **`_scan_broad`:** a station with one malformed manifest plus one moved,
  ready package: the moved package stays ready in `status` and in the `run`
  plan.
- **Recording:** a voiced package's `dj_audio` carries `profile`,
  `profile_source` and `tts`, including `profile: null` serialized for a
  no-profile show; a clone presenter's `voice` is `clone:<hash>`; a legacy
  block round-tripped through `DJAudioBlock` is rejected.
- **`emcee move`:** record, `unchanged`, the result state taken from the
  readiness check (pending, ready for an exemption, unvoiced),
  `--delivered` without an assignment entry, `--clear` (present and stale,
  recorded entries matched before live packages, ambiguous recorded matches
  refused with their ids listed, the removed
  `performance_id` printed, the last move leaving `{}`), `--list` with
  `missing` and `[no assign entry]` rows, each refusal leaving the file
  byte-for-byte unchanged, the lock held around load–modify–write, other
  entries' unknown keys preserved, and a move surviving a simulated
  `--replace-voiced` (the package directory replaced with a fresh unvoiced
  copy that has the same `performance_id`).
- **`moves.json` failures:** truncated JSON and a wrong shape each fail `run`
  and `status` loudly, and `run` makes no LLM or TTS call (strict surface 2);
  a missing file with a move-voiced package fails `run`, `voice`, `status`
  and `move` (which writes nothing) with the path, the count and both ways
  out; a missing file with none is "no moves".
- **Use-time validation:** a move whose target lost its assignment entry is
  an error row in `run`, others still voiced.
- **Stale-move note:** printed by `run` and `status`.
- **The pause:** the plan's categories (`new`, `re-voice` grouped and listed
  by name, `repair` listed by name, a tracks-missing package skipped with
  `re-deliver from llama` and never voiced) and exact clip count; plan and prompt on stderr; `--yes`;
  a decline; no TTY without `--yes` refusing with no LLM or TTS call made
  (strict surface 1); `--dry-run` printing the plan and never prompting, and
  `--yes --dry-run` voicing nothing; nothing to voice → no prompt; exit 1
  whenever an error row was printed, including on a decline and with nothing
  to voice. Existing `run` tests (CliRunner, no TTY) gain `--yes`.
- **Filters:** `--profile` and `--assigned` select by the effective profile.

## Out of scope

- Re-voicing when a profile's presenter, a presenter's TTS pin, or the house
  voice changes. Only a change of effective profile makes a package pending.
- Any llama behavior change: which profile finds a show, `provenance.json`,
  and llama's `status`/`deliver --profile` filters all stay on the delivered
  profile.
- Publishing the effective profile from transmitter: it waits for a consumer
  (the phase-4 player).
- A command to manage artist rules; `config.toml` stays hand-edited.
- `llama run list --no-flags` (one row per run) and a survey of other
  listing commands: requested in the same conversation, deliberately a
  separate pass.

## Verified premises

- **No false normalization collisions in real data** (checked 2026-10-16
  against all 341 packages: 65 normalized names). The only merges are the
  intended spelling variants: "Karl Denson's / Densons Tiny Universe" and
  "Robert Walter's / Walters 20th Congress".
- **transmitter and a re-voice in flight** (`transmitter/pipeline.py:241,
  256-258, 281-289`). An already-encoded row keeps airing its stored encode; a
  planned, unencoded row whose package changed is re-planned in place; a
  package caught mid-re-voice is ineligible and planned around. `LayoutError`
  comes only from an on-air row whose encode is missing, which a re-voice does
  not cause. A runbook note is enough.
