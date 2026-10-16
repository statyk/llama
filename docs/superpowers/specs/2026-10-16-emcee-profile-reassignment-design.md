# emcee: moving shows between profiles, recording the TTS, and a pause before `emcee run` — design

**Date:** 2026-10-16
**Scope:** `packages/emcee`, plus a one-field read in `packages/transmitter`.
llama and herder are untouched.
**Review mode:** Opus.

## Stakes

The station root holds 341 delivered packages on the NAS
(`/Volumes/media/lma-radio/delivered/`), and transmitter airs from it. Nothing
in this work touches a show's music or llama's library. What it does touch:

- **Re-voicing a ready package is destructive and costs money.** It overwrites
  the package's DJ script and clips (regenerable, at LLM + TTS cost), and while
  it runs, or if it fails, the package is `pending` and drops out of
  transmitter's playout pool until a later run succeeds. Today this happens
  only on an explicit `emcee voice`. After this change, adding one artist rule
  makes every matching ready package pending at once (17 Tedeschi Trucks Band
  shows for the motivating rule), and the next `emcee run` re-voices them all.

**Strict surfaces:**

1. **No spend without a confirmation.** `emcee run` never makes an LLM or TTS
   call until it has printed what it will do and the operator has said yes
   (or passed `--yes`). With no terminal attached and no `--yes`, it refuses.
2. **A recorded move is never silently lost.** `moves.json` is the only copy
   of the operator's one-off decisions. An unreadable or malformed file is a
   hard error for every command that resolves a profile, never "no moves":
   treating it as empty would mark every moved show pending and re-voice it
   back under its old profile.
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
  house voice. `process_package` calls `resolve_assignment` itself
  (`process.py:281`) to get the presenter and the on-air title for the script.
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
   `show.artist`, and whose `from` list (if any) contains `source.profile`;
3. llama's `source.profile` (possibly `None`, for a one-off `llama get`).

The presenter/title lookup (`assignment_for`) then runs on
`Effective.profile`, unchanged.

**Every reader of the profile switches to the effective one:**
`resolve_assignment` (and so `process_package`'s presenter, title and bed),
`station.scan`/`_scan_broad` (`PackageStatus.profile`), `emcee run`'s
`--profile` and `--assigned` filters, `--dry-run` rows, `emcee status` (summary
grouping, `--profile`, `--list`, `--json`), and `_note_unmatched_profiles`.
`emcee run --profile southern` therefore includes moved TTB shows, and
`--profile funk` no longer does.

`PackageStatus` gains `delivered_profile` (llama's `source.profile`) beside
`profile` (now the effective one). `emcee status --json` rows carry both, plus
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
  `source.profile` is in the list. An empty list is a config error (it could
  never match).
- **Matching** compares normalized names. `normalize_artist(s)`:
  casefold; drop one trailing `[...]` group; replace `&` with ` and `; delete
  apostrophes (`'` and `’`), so "Denson's" and "Densons" meet; replace every
  other character that is not a Unicode letter or digit with a space (so
  "Béla Fleck" keeps its `é`); drop a leading `the `;
  collapse whitespace; strip. "Robert Randolph [and the Family Band]" and
  "Robert Randolph" match; "Robert Walter's 20th Congress" and "Robert Walters
  20th Congress" match.
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
emcee move <show> --clear       # remove it
emcee move --list               # every recorded move
```

- `<show>` is addressed exactly like `emcee voice`: a path, or a name or
  unique substring under `[station] root` (`--station-root` overrides), exact
  name beating substring hits (`cli._resolve_package`).
- **Stored** in `<emcee root>/moves.json` (default `~/.emcee/moves.json`),
  keyed by the manifest's `source.performance_id`, so a move survives llama's
  `--replace-voiced` re-delivery, which replaces the package directory
  wholesale:

  ```json
  {"tedeschitrucksband/2012-07-14": {"profile": "southern",
                                    "package": "tedeschitrucksband-2012-07-14",
                                    "moved_at": "2026-10-16T20:14:03Z"}}
  ```

  `package` is informational (for `--list`); resolution uses the key only.
  Written atomically (unique temp + rename), like every emcee write. emcee is
  single-writer (no lock), as documented.
- **Refusals** (exit 1, file unchanged):
  - the target profile has no `[assign.profiles.<name>]` entry;
  - the manifest has no `source.performance_id`;
  - the package is unsupported (pre-v3) or its manifest is unreadable.
- **A move to the delivered profile is valid.** It beats an artist rule, so
  it is how one show is exempted from a rule ("this TTB show stays in funk").
- **A move that changes nothing** (the target equals the current effective
  profile, and the source is already `move`) prints `unchanged` and exits 0.
- `emcee move` makes no LLM or TTS call. It prints the result, e.g.
  `moved: tedeschitrucksband-2012-07-14  funk -> southern (pending; voiced on
  the next emcee run)`.
- `--list` prints one row per move: the package name, the target profile,
  the delivered profile, and `missing` when no package under the station root
  carries that `performance_id` (a stale move is harmless and listed so it
  can be cleared). `--clear` works on a stale move by its `performance_id` or
  recorded package name too, since its package may be gone.
- **Loading** (`moves.load_moves(root)`): a missing file is "no moves"; any
  other read or parse failure, or a shape that is not
  `{str: {"profile": str, ...}}`, raises an `EmceeError` naming the file
  (strict surface 2). Every command that resolves a profile loads moves
  first and so fails loudly on a bad file: `run`, `voice`, `status`, `move`.

## 4. What emcee records, and readiness

`DJAudioBlock` (`models.py:33`) gains two always-serialized fields:

```python
profile: str | None = None   # the effective profile this was voiced as
tts: TTSRecord | None = None # how its clips were synthesized

class TTSRecord(BaseModel):
    backend: str          # "voxtral" | "elevenlabs" | "mlx_audio" | "fake"
    model: str | None
    voice: str            # the provider's voice identity: a preset name, or
                          # "clone:<sha256[:16]>" of the reference clip
```

`process_package` sets both beside `presenter` before the manifest rewrite:
`profile` from the `Effective` it voiced under, `tts` from the package's
`TTSResolution` (`backend`, `model`) and the provider's `voice`. Always
serializing `profile` keeps `null` (voiced with no profile) distinct from a
legacy manifest with no key, the same convention `presenter` uses.

**Readiness gains a fifth leg**, the profile check. When `dj_audio` is
present:

- the **voiced profile** is `dj_audio["profile"]` if the key is present,
  else `source.profile` (a legacy manifest was voiced under llama's profile,
  since no rules or moves existed);
- if it differs from the effective profile, the package is `pending` with the
  reason `voiced as funk, now southern (artist rule "Tedeschi Trucks Band")`
  or `(move)`.

With no rules and no moves, the effective profile is `source.profile`, so a
legacy manifest compares equal and stays ready (strict surface 3). A missing
`tts` never makes a package pending: changing a presenter's TTS, or its
presenter, is not a re-voice trigger in this work.

`emcee status` shows the recorded TTS in `--json` (`tts` object, `null` when
absent) and nowhere else.

**llama is unaffected.** Its `DJAudio` model (`models.py:262`) is a plain
`BaseModel`, which ignores unknown keys, and llama reads a delivered
manifest's `dj_audio` only as "is it non-null" (`cli.py:2005`). Its
`status`/`deliver --profile` keep using the delivered profile; that is a
documented limitation, not a bug.

**transmitter reads the effective profile.** In `station.py:201` and
`site.py:114`, the `profile` it publishes becomes `dj_audio.profile` when
`dj_audio` is a dict containing that key, else `source.profile`. Nothing else
in transmitter changes; it still imports neither llama nor emcee.

## 5. The pause before `emcee run`

After scanning and filtering, and before any LLM or TTS call, `emcee run`
prints a plan and asks:

```
to voice: 19 packages, ~43 clips
  new        2
  re-voice  17  voiced as funk, now southern (artist rule "Tedeschi Trucks Band")
TTS:
  gregg (Mr. LeNoir)   voxtral  voxtral-mini-tts-2603   17 packages
  kurt (K.C.)          mlx_audio  Qwen3-TTS-12Hz-1.7B   2 packages
Proceed? [y/N]
```

- **Re-voice reasons** are grouped by reason text, with counts.
- **Clips** is an estimate: per package, one intro per non-encore set in the
  manifest's tracks plus one outro. It is labeled approximate because the
  script decides the final segments.
- **TTS** lists each presenter (or `house`) that will voice something, with
  the backend and model `resolve_tts` gives, and its package count. A
  presenter that cannot be resolved shows the same markers `--dry-run`
  already uses (`[missing …]`, `[invalid …]`, `[unresolved: …]`), and those
  packages fail individually as today.
- **`--yes` / `-y`** skips the question.
- **No terminal** (stdin not a TTY) and no `--yes`: print the plan, then exit
  1 with `error: refusing to voice without confirmation; pass --yes`.
- **Declined:** exit 0 with `nothing voiced`.
- **Nothing to voice:** no plan, no question, exit 0 as today.
- **`--dry-run`** prints the per-package `would voice:` rows as today, then
  the same plan block, and never asks.
- Error and unsupported rows are still reported as they are found, and do not
  count toward the plan.
- `emcee voice` (one named package) does not pause.

## Error handling summary

| Situation | Behavior |
|---|---|
| `moves.json` unreadable or malformed | `EmceeError` naming the file; `run`/`voice`/`status`/`move` exit 1 before any work |
| artist rule targets a profile with no `[assign.profiles]` entry | config load error |
| two artist keys normalize alike, or one normalizes to empty, or `from = []` | config load error |
| `emcee move` to an unassigned profile, or a package with no `performance_id` | refuse, exit 1, file unchanged |
| a move whose package is gone | kept; `--list` shows `missing`; `--clear` removes it |
| `emcee run` with no TTY and no `--yes` | plan printed, exit 1, nothing spent |

## Testing

All offline, on the `fake` LLM and TTS backends, extending the existing emcee
and transmitter suites.

- **`normalize_artist`:** each rule above, including the Denson's/Densons,
  Robert Randolph bracket and Robert Walter pairs from the real data, and
  that two genuinely different artists stay different.
- **`effective_profile`:** move beats artist rule beats llama; `from`
  present and absent; a show with `source.profile` null under a rule with
  and without `from`; a move back to the delivered profile beating a rule.
- **Config:** shorthand and table forms parse to the same thing; each load
  error in the table above.
- **Readiness:** a legacy manifest (no `profile` key) with no rules stays
  ready (strict surface 3); the same manifest under a matching rule goes
  pending with the right reason; a manifest voiced as the effective profile
  stays ready; a missing `tts` never makes a package pending.
- **Recording:** a voiced package's `dj_audio` carries `profile` and `tts`,
  including `profile: null` serialized for a no-profile show, and a clone
  presenter's `voice` is `clone:<hash>`.
- **`emcee move`:** record, `unchanged`, `--clear` (present and stale),
  `--list` with a `missing` row, each refusal leaving the file byte-for-byte
  unchanged, and a move surviving a simulated `--replace-voiced` (the package
  directory replaced with a fresh unvoiced copy that has the same
  `performance_id`).
- **`moves.json` failures:** truncated JSON and a wrong shape each fail `run`
  and `status` loudly, and `run` makes no LLM or TTS call (strict surface 2).
- **The pause:** the plan's counts and grouping; `--yes`; a decline; no TTY
  without `--yes` refusing with no LLM or TTS call made (strict surface 1);
  `--dry-run` printing the plan and never prompting; nothing to voice → no
  prompt.
- **Filters:** `--profile` and `--assigned` select by the effective profile.
- **transmitter:** published `profile` prefers `dj_audio.profile`, falls
  back to `source.profile` for a legacy block and for `dj_audio: null`.
  Run the Debian-12 script, since transmitter must stay Python 3.11
  compatible.

## Out of scope

- Re-voicing when a profile's presenter, a presenter's TTS pin, or the house
  voice changes. Only a change of effective profile makes a package pending.
- Any llama change: which profile finds a show, `provenance.json`, and llama's
  `status`/`deliver --profile` filters all stay on the delivered profile.
- A command to manage artist rules; `config.toml` stays hand-edited.
- `llama run list --no-flags` (one row per run) and a survey of other
  listing commands: requested in the same conversation, deliberately a
  separate pass.

## Unverified premises

- **transmitter and a re-voice in flight.** transmitter reads packages from
  the same station root and skips a package whose file set is still changing
  (`station.py:191`, `changing:`). It has not been checked what happens when
  an already-planned or already-encoded show is re-voiced underneath it: does
  it re-encode, keep airing the old encode, or treat it as ineligible? This
  is today's behavior for `emcee voice` too, but this work makes bulk
  re-voices routine. Reviewers: check `transmitter/station.py` and the
  planner, and say whether a note in the runbook is enough.

## Verified premises

- **No false normalization collisions in real data** (checked 2026-10-16
  against all 341 packages: 65 normalized names). The only merges are the
  intended spelling variants: "Karl Denson's / Densons Tiny Universe" and
  "Robert Walter's / Walters 20th Congress".
