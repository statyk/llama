# Keep short files that belong to the show (held-backlog part 1, piece 4)

Date: 2026-10-23. Branch `held-backlog-junk-filter` from `main` @ `e37f670` (v2.17.0).
Inputs: the sizing censuses, hand-checks and decision record in
`docs/superpowers/2026-10-23-junk-short-keep-evidence/`:
- `census-handback.md`, `census2-handback.md`;
- the `p4-*` and `r-*` hand-check packets;
- `shipped-broken.md`, `voiced-severe-review.md`, `decisions-r1.md`.

The operator rulings of 2026-10-23 are binding and are restated where they apply. Measurements
come from the replay harness at `~/.llama-harness/piece45/spec/` (round scripts in `r1/`). It
ran read-only against the whole library (3,983 shows) at `e37f670`.

**Review mode: Opus** (Opus spec and plan reviewers, Opus final branch reviewer).

**Stakes.** About 4,000 shows, ~2,800 of them delivered and on air at listen.lma-radio.com. One
operator, whose attention is the scarce resource. The operator's accuracy rule is that
**omitting real show content is worse than including a little that does not belong, and tape
notes are presumed correct.**

Today the junk filter's short-duration arm drops the `Drums >`, the `St. Stephen` reprise or the
`Slipknot!` that sits between two songs. The show then airs with a hole and no flag.

Strict surfaces:

- **(a) The positional-overrides migration.** It rewrites `overrides.json`, which is
  hand-authored operator data. Section 4 says exactly what is written and when, how it is
  undone, how an old binary is kept from reading it silently, and that an ambiguous mapping
  refuses and names the show.
- **(b) Re-delivering voiced shows.** `llama deliver --replace-voiced` discards paid TTS voicing,
  and that cannot be undone. Only the 37 approved shows are in scope, one named invocation each
  (section 5).
- **(c) Relaxing a safety filter.** The change must not admit spam or non-performance audio. The
  filename-convention arm is untouched, and every short candidate passes a spam-shape tripwire
  (2.3).

Everything else is proportionate.

## Why

The short arm drops 3,547 files in 1,870 shows whose only drop reason is `implausibly short`
(under `SHORT_FRACTION_OF_MEDIAN` x the tape's median). That is 96% of everything the filter
drops.

By tag:
- spoken band material (intros, banter, band introductions, stage announcements): 1,653;
- music (segue pieces, reprises, short songs, continuations): 864, plus 51 fragments;
- crowd: 315;
- tuning, fades and silence: 339;
- untagged: 197;
- radio and non-performance: 37.

The operator has re-admitted 239 dropped files by hand with `fix --include`. In the census, no
file whose tag says tuning, silence or a fade was music by any source.

## 1. The rule (operator ruling 1)

A file whose **only** drop reason is the short-duration arm is **kept**, unless:
- it trips the spam-shape tripwire (2.3); or
- its tag is wholly junk (2.3).

An untagged file follows 2.4.

## 2. Specification

### 2.1 Scope and what does not change

- **The floor.** The short arm computes the same floor from the same constants:
  `SHORT_FRACTION_OF_MEDIAN`, `MIN_PLAUSIBLE_SEC`, `MIN_MEDIAN_SAMPLE`, and the two-pass median
  over files passing every other arm. CLAUDE.md's "Plausible duration is RELATIVE" stays true.
  The arm now drops by duration **and** tag.
- **Other reasons are untouched:**
  - the filename-convention arm, which catches `FOLLOW-ME @BYPIKENO.mp3`;
  - provenance;
  - `missing duration`;
  - duplicate-listing;
  - a file failing the short arm and another arm (7 files).
- **Operator `exclude` always wins.** It is applied after the filter, as today.
- **`include` is unchanged.** A file the rule now keeps is no longer in `excluded`, so `include`
  re-admits nothing for it. 173 kept files are already operator-included.

### 2.2 The tag, and "tagged"

- **The tag** is the file's own `title`, else its original's `title`, passed through
  `titles.clean_tag_title`.
  - 42 files are tagged only through their original: 32 are kept and 10 are junk.
  - The tag rung reads only the file's own `title`. A kept file of this kind ships `unresolved`
    unless format recovery or a later rung names it.
- **A file is tagged when that cleaned tag is non-empty** (ruling 3). This includes:
  - a leaked timestamp prefix, e.g. `0:50) Going In The Right Direction`;
  - placeholders such as `d1t01`, `tmp` and `Track 9`.

  This is why the census's 197 untagged files become 136 here: 61 of them, 22 at a tape edge,
  now count as tagged. A placeholder-tagged kept file ships 2b-demoted as `unresolved`, and so
  usually holds.

### 2.3 The spam tripwire and the junk test

The functions below are **normative**: the plan ports them verbatim into `junk.py`
(`short_tag_is_junk`, `short_is_spam`). They are what was measured, except that the tripwire's
bare words are narrowed to the filename stem; narrowing cannot add to its measured 0 hits.

```python
LEAD = re.compile(r"^(?:\(?\d{1,2}:\d{2}(?::\d{2})?(?:[.:]\d+)?\)?\s*[-:)]?\s*|\d{1,3}\s*[.):_-]?\s+|d\d{1,2}t\d{1,3}\s*|\d{3,4}(?=[a-z]))+", re.I)
TIME_PAREN = re.compile(r"\s*[\(\[]\s*\d{1,2}:\d{2}[^)\]]*[\)\]]")
SPLIT = re.compile(r"\s*(?:/|,|&|\+|;|\band\b|\s-\s|-{2,}|-?>|~|\||\(|\)|\[|\])\s*", re.I)
EDGE = re.compile(r"^[\s\[\(<~*#.\-_'\":]+|[\s\]\)>~*#.\-_'\":]+$")
JUNK_PART = re.compile(
    r"^(?:"
    r"(?:set\s*(?:\d|i+|one|two|three)\s*)?(?:re-?)?tun(?:e|i|ni|in)?(?:ing|ning|eing|ig|in'?|e[\s-]*ups?|ups?)?(?:\s*up)?(?:\s+break)?"
    r"|instrument\s+change|warm[\s-]*up|(?:crowd|tuning)\s+(?:crowd|tuning)"
    r"|dead\s*air|silence|silent|blank"
    r"|(?:tape|side|disc|disk|reel)\s*(?:flip|change|cut|end|gap|break)|gap|cut[\s-]*in"
    r"|fade[\s-]*(?:in|out)"
    r"|(?:tape\s+|crowd\s+)?noise|hiss|static|test\s*tones?"
    r"|sound\s*check"
    r"|(?:opening\s+|encore\s+)?(?:crowd|audience)(?:\s+(?:noise|cheering|chanting|applause|yelling|encore\s+call))?"
    r"|(?:opening\s+|encore\s+)?applause|cheering|clapping"
    r"|(?:encore|set)\s*(?:break|call)(?:\s+i+)?|waiting(?:\s+for\s+(?:the\s+)?encore)?"
    r")$", re.I)
NONPERF = re.compile(
    r"\bcommercials?\b|\bpromos?\b|\badvert\w*|\bstation\s+(?:id|plug|identification)\b|\bnews\s+broadcast\b"
    r"|\b(?:house|p\.?\s?a\.?|intro|walk[\s-]*(?:on|in|out|off)|recorded|pre-?show)\s+music\b"
    r"|\binterview\w*"
    r"|(?=.*\b(?:dj'?s?|radio)\b)(?=.*\b(?:talk\w*|intro\w*|outro\w*|banter|announc\w*|moderator\w*|host\w*|id|spots?)\b)",
    re.I)
SPAM = re.compile(r"https?://|\bwww\.|\b[a-z0-9-]+\.(?:com|net|org|info|biz)\b|@\w{3,}", re.I)
SPAM_STEM = re.compile(r"\bfollow\b|\bdownload\b|\bsubscribe\b", re.I)
SPAM_TAG = re.compile(r"\bfollow\s+(?:me|us)\b", re.I)

def parts(t):    # t = clean_tag_title(tag)
    t = TIME_PAREN.sub("", LEAD.sub("", t))
    return [p for p in (EDGE.sub("", x) for x in SPLIT.split(t)) if p]

def short_tag_is_junk(tag):
    t = clean_tag_title(tag)
    if not t:
        return False
    if NONPERF.search(t):
        return True
    ps = parts(t)
    return bool(ps) and all(JUNK_PART.match(p) for p in ps)

def short_is_spam(filename, own_title, original_title):
    stem = basename_without_extension(filename)
    tags = (own_title or "", original_title or "")
    return (bool(SPAM.search(stem) or SPAM_STEM.search(stem))
            or any(SPAM.search(t) or SPAM_TAG.search(t) for t in tags))
```

**The spam tripwire runs first, on every short candidate, tagged or not.**
- **What it reads.** The filename stem plus the file's own and its original's `title`.
- **What it leaves out.** `album`, `artist` and `creator`. Those strings are item-wide: venue
  `@` signs and taper domains such as `Summerdance@Nelson Ledges` and `SeparateReality.org`.
  Including them gave 7 false hits and 0 true ones.
- **Matching.** Every term is word-bounded and case-insensitive. The URL, `www.`, domain and
  `@\w{3,}` terms apply to the stem and both tags. The bare words `follow`, `download` and
  `subscribe` apply to the stem only; in a tag only `follow me` or `follow us` counts.
  `John follows his fingers` (`mountaingoats-2017-06-02`), `I'll Follow the Sun`,
  `Follow You Down` and `bwww1996-12-31t01.mp3` stay kept.
- **Its own reason.** A tripwire drop records `spam-shaped name or tag`, so `show --tracks` and
  triage `[i]` show why it dropped.
- **Measured:** 0 hits on the library's 3,547 short-only drops, and 0 on the 9,655 short-only
  drops of the 9,844 cached sibling items.

**Notes on the junk test:**
- **Separators** are exactly those in `SPLIT`. A bare intra-word hyphen is not one.
- **Empty cleaning.** A tag that cleans to no parts is not junk.
- **Per-part anchoring.** A tag with any part outside `JUNK_PART` is kept (ruling 3):
  - kept: `intro/tuning`, `tuning/banter`, `Take A Step Back/Tuning`,
    `Mexican Hat Dance Tuning`, `crowd/tuning jam`, `Bob Weir comment to crowd`;
  - dropped: `crowd/tuning`, `Crowd & Tuning`, `2: crowd/tuning ->`.
- **`radio` and `DJ` alone never make a tag non-performance.** A broadcast qualifier is needed.
  - Kept: song titles such as `Mohammed's Radio`, `Radio Blues`, `Jesus on the Radio`,
    `Radio Free Europe` and `DJ Logic / Jam`.
  - **AUTHOR'S CALL:** `outro`, `id` and `spot(s)` join the qualifiers, because ruling 2 names
    sign-offs and sibling tags carry `Radio Outro` and `radio ID`.
- **Stage banter is kept in general** (operator): `Stage Announcements`, `Banter Promote CD`,
  `banter - promoting the new CD`.
- **The operator-ruled broadcast examples.** 20 of the 21 drop. The one that does not is
  `Stage Banter: Consummation Station` (`thegourds-2009-10-17`): it is the band's stage banter
  (`station` without id/plug), which the census regex had mis-classed.

**Measured:** 651 junk and 34 non-performance drops, no music among them, and none
operator-included. No sibling has a track of its own at any of these positions. 360 of them fold
into a neighbouring song's file on a sibling, e.g. `gratefuldead-1984-04-17` `01Tuning.mp3`
into Jack Straw. That is how tapers carry tuning and crowd noise, and it is today's behaviour.

### 2.4 Untagged short files (ruling 4)

- **Interior files are kept; edge files drop.** An untagged short file is kept only when it is
  interior: a kept file precedes it and another follows it in play order.
  - Play order is derived the way `filter_files` derives it: track-tag order when every file in
    the set has a unique track number, else filename order.
  - It is taken over the kept files, the tagged short files 2.3 keeps, and the untagged
    candidates.
  - Measured: 99 interior, 37 edge.
- **Filename junk** (AUTHOR'S CALL). An untagged short file whose filename stem is wholly junk
  under 2.3 drops. Leading digits and separators are removed first.
  - Measured: 3 files (`0201tuning.mp3`, `10 Crowd.mp3`, `09 Crowd.mp3`).
  - It only ever drops.
- **Measured:** 96 untagged interior files are kept.

### 2.5 Where the rule lives and what it records

- **The rule lives in `junk._keep_and_exclude`** (2.2-2.4). A file the junk test or 2.4 drops
  keeps the reason `implausibly short`, so `show --tracks`, triage `[i]` and `fix --include` read
  it as today. A tripwire drop records `spam-shaped name or tag` (2.3).
- **`filter_files` gains `short_keep: bool = True`.** `False` reproduces today's filter exactly.
  Only the migration's consistency check (4.3) passes it.
- **`filter_files` returns the names the rule kept** as `ordering["short_kept"]`.
- **`Track.short_kept: bool = False`.**
  - It is persisted in `show.json`, permissive, absent on old dirs, and not in the manifest.
  - **It is set where the cascade builds the `Track`s, in `resolve_titles` from the
    ordering.** That is before `align()`, the LLM alignment and the taper's coverage check, so
    every coverage computation sees it.
- **A short-kept file votes as an ordinary kept file** (AUTHOR'S CALL, and what was measured)
  in every recording-level vote: `recovery_basis`, `tag_gate_basis`, `title_fraction`,
  siblings. `include`'s reduced standing stays for operator re-admissions.
- **Every caller gets the rule:** siblings, `select_recording`, `best_donor`, format recovery.
- **The junk note.** When a `short_kept` track's final title, from any rung, is wholly junk
  under `short_tag_is_junk`, gather writes an operator note to `notes.json`. Measured: 2 files,
  `(crowd)` via `setlist-gap` on `thenewdeal-2005-09-17` and `Crowd Noise` via `desc-position`
  on `buckethead-2004-06-04`.

## 3. Coverage (ruling 5)

`structure._songish_coverage` already leaves out `is_filler` titles: `tuning`, `crowd`,
`banter`, `intro`, `outro`, `applause`, `announce`, `talk`, `encore break`, `soundcheck`, and
so on. That covers most spoken re-admissions.

**The new clause.** It goes in the same comprehension: `and not t.short_kept`. A re-admitted
`Jam >`, `Murph` or unresolved file therefore neither lowers nor raises coverage. No second
filter is added.

`matched` is still measured and shown.

Measured: the clause removes 43 of the 46 added holds whose only flag would be
`low-confidence structure alignment`.

## 4. Positional overrides re-keyed by filename (ruling 6; STRICT)

**The three positional keys.** Each is keyed by track number:
- `titles` (track to title);
- `set_breaks` (tracks a break falls after);
- `encore_after`.

`exclude` and `include` are already filenames, and the other fields are not positional. No other
persisted artifact is keyed by track number.

**What an inserted track does.** It re-points all three silently. Replayed without the re-key:
- 204 shows have a key at or after an insertion;
- **138 put an override title on a different file**, 46 of them with no flag at all.

### 4.1 Encoding, presence and the guard

- **Same key names, filename values.** Migrated data keeps the legacy key names, with filename
  values:

  | key | type | meaning |
  |---|---|---|
  | `titles` | `{"<filename>": "<title>"}` | forced title per file |
  | `set_breaks` | `["<filename>", ...]` | a break falls after each listed file |
  | `encore_after` | `"<filename>"` | encore starts after this file |

  - **Legacy values** are the track-number forms: a `titles` key made only of digits (JSON
    object keys are strings), an integer in `set_breaks`, or an integer `encore_after`.
  - Every real filename has an extension, so none is all digits.
- **Both forms always parse.** The new `Overrides` model types the three keys as
  `titles: dict[str, str]`, `set_breaks: list[int | str] | None` and
  `encore_after: int | str | None`. Parsing never refuses; only the resolver and the writers
  judge legacy or mixed values. A test: the new `iter_shows` lists a library holding a legacy
  file, a migrated file and a mixed file without raising.
- **Old binaries fail loudly.** v2.17.0's model (`dict[int, str]`, `list[int] | None`,
  `int | None`) rejects every migrated file with a `ValidationError`. An old binary, a sweep loop
  or an old-commit harness arm therefore fails loudly instead of silently dropping the overrides.
  A test runs `e37f670`'s `Overrides` model, vendored as a fixture, against a migrated file and
  asserts that it raises.
  - **The failure is library-wide.** v2.17.0 reads every show's `overrides.json` on every command
    (`catalog.iter_shows`), so once any file is migrated the old binary cannot run any command on
    this library. That is by design: it is the loud failure. It is also why the migration and
    its undo are all-or-nothing (4.3).
- **Writers refuse legacy.** Every new-code writer of `overrides.json` refuses before any prompt
  when the show's file holds any legacy value (`overrides.json uses track-number keys; run the
  migration`). That covers every `fix` edit flag (`--no-run` included), every triage edit,
  `--suggest-titles` and `--untitled`. A test pins it.
- **Presence semantics.**
  - `set_breaks` absent or `None` means no structure override.
  - `[]` means forced no breaks (the structure-override path, alignment skipped). It is
    preserved exactly.
  - `--untitled` and triage `[u]` keep writing `[]`.
  - "Has a legacy value" means any of the three integer-valued forms above. An empty
    `set_breaks: []` needs no re-key and is left as is.
  - A test pins the `delmccouryband-2008-05-24` shape (18 titles plus `set_breaks: []`) through
    the migration and a gather: alignment `override`, breaks `[]`.
- **One resolver.** `compute_gather` uses a single overrides resolver, so gather, redo, reapply
  and replay all pass through it.
  - It maps filename values onto the final kept list once, producing the positional values the
    cascade and the structure override already consume. Nothing downstream changes.
  - It refuses with `LlamaError`, naming the show:
    - a file with any legacy value (`overrides.json uses track-number keys; run the
      migration`);
    - a file mixing legacy and filename values;
    - a filename value whose file is not in the final kept list (naming the key and the file).

### 4.2 Who reads and writes them

- **Writers take track numbers.** `fix --set-title N=`, `--clear-title N`, `--set-breaks`,
  `--clear-set-breaks`, `--set-encore`, `--clear-encore`, `--suggest-titles`, `--untitled` and
  triage's `[t]`, `[u]` and edit prompts all take numbers.
  - **A number always means the `show.json` numbering the operator saw (`show --tracks`).** It is
    translated to a filename through `show.json`.
  - The staleness check compares `show.json`'s filename list with gather's final kept list.
    That list is computed with the overrides as they were **before** this invocation's own
    edits, by **one shared helper** that returns gather's final kept list (filter, include,
    exclude); gather itself uses the same helper. There is no separate recomputation.
  - **Until a show is re-gathered under the new rule**, its `show.json` still has today's kept
    list, so on every show the rule changes the check refuses positional edits with
    `re-gather under the new rule first (llama redo <show> --from gather)`. The runbook therefore
    triages after the bulk apply (4.3).
  - **Behaviour change.** `fix --exclude 3 --set-title 7=X` now titles `show.json`'s track 7.
    Today that title lands on old track 8. A test pins it.
  - Without `show.json` these flags refuse and name `llama redo <show> --from gather`.
    `--set-venue`, `--set-city`, `--set-date` and filename `--exclude` still work.
  - `--untitled`'s `Untitled (track N)` text keeps the number it was written with.
- **Exclusion refuses up front on a keyed file.** `fix --exclude N` (and triage exclusion)
  refuses when that file carries a title, break or encore key. It names the key and the
  `--clear-*` flag that resolves it.
- **A key whose file vanished** after a metadata-cache refresh makes gather fail loudly.
  **AUTHOR'S CALL:** `--clear-title` also accepts a filename, and the three `--clear-*` flags
  skip the staleness check. Removing a key cannot mis-point anything, so the operator clears the
  dangling key with `fix` and never hand-edits.
- **Readers.** All readers go through the resolver: gather, `reapply`, `replay`.
  - `scripts/replay_holds.py --strip-title-overrides`/`--strip-structure-overrides` strip the
    same keys.
  - `taper_probe.py` and `title_hygiene_probe.py` read the filename form.
  - `llama show` prints the stored mapping, and triage's current-values line converts it to
    today's track numbers.
- **The harness re-key** is for measurement only. It lives in `scripts/replay_holds.py` behind a
  harness-only option, never in `compute_legs`, and imports the migration's own mapping function
  (no second algorithm).

### 4.3 The migration and its runbook

`scripts/rekey_overrides.py [--apply] [--undo]` is a one-off. It is run as
`python scripts/rekey_overrides.py` with the repo venv's python, never through a `.venv/bin/*`
console script from a copy. It is a dry run unless `--apply`, and it never gathers.

**Runbook, in order** (section 5 refers here):
1. Stop any `llama run resume --all` loop.
2. Copy the current release binary to `~/.local/bin/llama-2.17.0`.
3. Install the new release and verify it (`which -a llama`, `llama --version`). The script
   refuses `--apply` while any `llama` on PATH reports 2.17.0 or earlier, or a dev build
   (`0.1.0`, `0.0.0+unknown`). `--undo` is exempt, since it runs after the old binary is
   reinstalled.
4. Run any pre-piece-4 base harness arm now, or on a library snapshot taken before step 5.
5. Migrate. Run the dry run. Repair each refused show with `llama-2.17.0` by the route the
   refusal names, while the library is still wholly legacy. Repeat the dry run until it reports
   0 refused, then `--apply`.
6. Restart the sweep loop, only once step 5's `--apply` has succeeded.
7. Build apply lists only from a harness run after the migration. Their `input_digests` include
   `overrides.json`.
8. Triage held shows only after the bulk apply has re-gathered them (4.2).

**Checks.** A show is refused, with its repair route, when any of these holds:

| reason | repair (old binary, before `--apply`) |
|---|---|
| the file mixes legacy and filename values | none; listed for the operator |
| `show.json` is missing | `llama-2.17.0 redo <show> --from gather` |
| a `titles` key is outside `1..len(tracks)` | `llama-2.17.0 fix <show> --clear-title k` |
| the track at a `titles` key is not `title_source == "override"` with exactly the forced title | `llama-2.17.0 redo <show> --from gather` |
| **when `set_breaks` or `encore_after` is present**, `show.json`'s `set_breaks` is not exactly `sorted(set_breaks ∪ {encore_after})` | `llama-2.17.0 redo <show> --from gather` |
| a track filename repeats | none; listed for the operator |
| `show.json`'s filename list differs from what the shared helper (4.2) keeps under today's rule (`short_keep=False`) from current metadata plus `include` minus `exclude` (the writers' staleness comparison) | `llama-2.17.0 redo <show> --from gather` |
| a backup exists while the file is still legacy and is not byte-equal to it | none; listed for the operator |

These checks prove that the stored positions, the stored `show.json` and the current inputs
agree. An ambiguous show is never guessed. A refusal with no route blocks `--apply` until the
operator resolves it.

**`--apply` is all-or-nothing.** It first runs every check over every show with a legacy value.
If any show would be refused it writes nothing and prints each refusal with its repair.
Otherwise, per show, under the show lock (`locks.file_lock(ws.lock)`):

1. **Map** each position to `tracks[N-1].filename`. Every other field round-trips unchanged.
2. **Write, in this order**, each as a temp file, `F_FULLFSYNC`, then rename:
   1. the backup `overrides.pre-rekey.json`;
   2. the sidecar `overrides.rekeyed.sha256`, the hash of the bytes about to be written;
   3. the new `overrides.json`.

An interrupt therefore leaves each show either legacy and equal to its backup, or matching its
sidecar. A re-run of an interrupted `--apply` completes the remaining legacy shows, which passed
the all-show check.

**Output.** One line per show: `rekeyed: <slug> (T titles, B breaks, encore)` (`would rekey` in
the dry run), or `refused: <slug>: <reason>` with its repair. Then a summary. Exit 1 if anything
was refused.

**Undo.** The undo set is every show with a sidecar. `--undo` is a dry run; `--undo --apply` is
all-or-nothing the same way and writes nothing unless every show in the set is undoable:
- when the current file's hash equals the sidecar, it restores the backup (temp, `F_FULLFSYNC`,
  rename) and removes the sidecar and the backup;
- when the current file equals the backup, it reports `already undone` and removes the sidecar
  and the backup;
- otherwise the show is not undoable, and is named.

Undo is only useful together with reinstalling the old binary. Its post-condition is the old
binary's `llama-2.17.0 redo <show> --from gather` for every show whose `show.json` has a
`short_kept` track, listed with
`grep -l '"short_kept": true' <root>/shows/*/show.json`.

**Measured today:**
- 606 shows carry legacy keys (3,203 titles, 427 breaks, 365 encore keys).
- **All 606 pass every check**, so 0 would be refused. On each, `show.json`'s filename list
  equals what today's code keeps. The migration-day dry run re-runs the checks.
- The re-key, simulated over the whole replay, mapped every key. Its arm has **0** override
  titles on a different file.

## 5. Applying it (ruling 8; what piece 4 needs from the bulk apply)

The bulk apply of pieces 1-5 is planned separately. Piece 4 needs these things from it.

1. **Order.** The runbook in 4.3 comes first.
2. **The list.** The rule changes 1,537 shows: 1,536 gain a file, and 1 held show changes only
   its flags.

   | state | changes | of which music restored |
   |---|---|---|
   | delivered, unvoiced | 1,028 | 392 |
   | voiced | 65 | 37 |
   | packaged | 311 | 65 |
   | held | 123 | 45 |
   | briefed | 10 | 1 |

   - **Held shows:** `llama reapply`.
   - **Packaged and delivered shows:** the same computation, via reapply's path extended to
     them: gather from the cache, the stored vet extraction, and the stored briefing when it is
     reusable. `redo --from gather` would spend a vet and a brief on each.
   - **The 28 voiced-minor shows** (`voiced-minor-final.json`) are left out until the
     re-voice-later decision.
3. **Briefing reuse** (owned by this branch, tested). `replay.briefing_reusable` leaves out, on
   both the stored and the new show, every track whose filename is among the new show's
   `short_kept` filenames (so the 173 already-included short files do not force a brief). Over
   what remains it compares:
   - per-track `(title, set, segue)`, matched by filename;
   - each set break, keyed by the last remaining file at or before it;
   - the existing show-level fields, with `briefing_guard` unchanged.

   The break key means a banter or crowd file that slides across a set boundary does not force a
   fresh brief. Every real track's set is still compared.

   **Measured:** 1,415 changed shows have a briefing. 1,017 keep it; 398 need a fresh brief.
   - Today's function keeps 0 of them, because any insertion changes `titles`.
   - Without piece 4, 1,129 would be reusable (the other 286 already differ from their stored
     show for other reasons). Piece 4 itself costs 116: 113 because a real track's title, set
     or segue changes, and 3 set breaks.
4. **Re-use existing audio** (owned by this branch). Re-packaging a show whose track list
   changed would otherwise download audio llama already has: a delivered show's library audio
   was purged at delivery, and a packaged, held or briefed show's library audio carries the old
   track numbers. A failed check falls back to the download.
   - **Why md5/size cannot verify it.** `build_package` renames every file
     (`packaged_filename`) and rewrites its tags (`tag_audio`), so a packaged copy's md5 and size
     never equal the archive original's, and the manifest records only the packaged filename.
   - **Where it runs.** In every unit that re-packages: `redo`, the auto-redo of `fix` and triage
     edits, and `reapply`. Before re-packaging a show whose track list changed, the unit moves
     the library's existing `package/audio/*` aside. `build_package` downloads straight to
     `packaged_filename(index, title)` and skips a name that already exists, so old-numbered
     files must never be left in place: a renumbered track with the same title as the old track
     at its number would inherit the wrong audio.
   - **Mapping.** Before the re-gather rewrites `show.json`, the unit pairs both copies, the
     moved-aside library audio and the station copy, to source files by index against the
     current `show.json`. Each copy's manifest (`package/manifest.json`, or the station's) must
     have the same length and the same title at every index, else that copy is not reused. The
     pairing gives source filename → existing file.
   - **Verification, per file.** A paired file is reused when it exists and `audio.read_duration`
     (mutagen, which the package step already uses, so no new runtime dependency) gives a length
     within the package step's `DURATION_TOLERANCE_S` (5 s) of the cached metadata length of its
     source file. The library
     copy is tried before the station copy. The reused file is placed at its new
     `packaged_filename(index, title)`, so packaging skips its download and re-tags it as usual.
     For MP3, `tag_audio` writes a fresh ID3v2 tag, replacing the whole old one. For FLAC, it
     overwrites the same six fields it set on the original; every other field is the original's.
     Either way the result matches what a fresh download would produce.
   - **Fallback.** Anything unpaired or failing (no pairing, a missing file, no readable
     duration, a duration mismatch) downloads from archive.org exactly as today. New short-kept
     files are in neither copy, so they always download. Moved-aside files that were not reused
     are deleted once the unit succeeds; a failed unit puts them back under their old names.
   - **Why this is enough.** Both copies came from md5-verified downloads, and the index pairing
     with equal titles ties each file to its source. The station copy was also checked against
     the library at delivery (`catalog.purge_package_audio`), and it is what airs today. The
     worst case of a bad reuse is re-shipping audio this show already packaged. This is not a
     strict surface.
5. **Re-delivery.**
   - **Unvoiced shows.** Delivered unvoiced shows are re-delivered, minor fixes included, and
     never with `--replace-voiced`. A show emcee voiced after the list was cut is then refused by
     `deliver` and goes to the operator's re-voice-later list. `reapply`'s `re-deliver with` hint
     is suppressed for a voiced destination.
   - **A changed track list replaces the destination.** When an unvoiced show's track list
     changed, `deliver` copies it through `_replace_destination` (wholesale, atomic), so the
     station directory keeps no old-numbered copies. A voiced destination still refuses as
     before.
   - **The 37 voiced shows where the rule restores music** (`voiced-severe-final.json`; operator,
     2026-10-23: "For #6, I think we will revoice all 37") are re-delivered with
     `deliver <slug> --replace-voiced`, **one single-name invocation per slug**. Before each,
     check that:
     - the slug is in the list;
     - the destination is voiced;
     - the re-packaged library `show.json`'s track filenames include every source file listed
       for that slug, each with `short_kept` set, and the library manifest exists with as many
       tracks as `show.json`.

     They are then voiced with `emcee voice <slug>`, one per slug. A station-wide `emcee run` is
     not used for this step unless `emcee run --dry-run` first shows a plan of exactly these
     packages.
   - **`deliver` itself refuses `--replace-voiced` whenever any batch selector is given**, using
     its existing `other_selector` computation, so `--held` and any future selector are covered.
     Owned by this branch, tested.
   - **`_destination_is_voiced`** treats only `FileNotFoundError` as unvoiced. Any other read
     error, or a malformed manifest, refuses the show. In a batch, the preflight marks that one
     show refused and continues. Owned by this branch, tested.
   - **Shows the apply turns into holds** are triaged before re-delivery. The station copy keeps
     airing in the meantime.
   - **Timing.** Shows outside the current playout horizon are re-delivered first, and shows
     inside it last or after they air.

## 6. Acceptance

**(a) Arms.**
- Base: `scripts/replay_holds.py run --all` at `e37f670`, before the migration (4.3 step 4).
- Candidate: the branch, with the harness re-key.
- `compare` passes its gates.
- The candidate must reproduce the reference harness (`~/.llama-harness/piece45/spec/r1/arm_r1.jsonl`)
  per show, or explain each difference: 1,537 shows changed, 2,649 files added, 20 holds
  cleared, 34 added.

**(b) Holds added, each class justified** (34):

| class | shows | why it is right or accepted |
|---|---|---|
| new unresolved track | 18 | An untagged or placeholder-tagged short file is kept (rulings 3-4) and ships `unresolved`. A hold by design. |
| long single-set show crosses 150 min | 6 | Restored audio is real runtime. The existing long-show check fires correctly. |
| positional rung lost | 4 | A kept file changes the count. On 3 shows one `setlist`-filled track (`Instrumental`, `FF`, `7-11`) reverts to `unresolved`. On `ratdog-2007-08-12` a kept 57 s untagged interior file breaks its description's count match, and 19 `desc-position` titles revert. It holds rather than ship shifted titles. |
| low confidence remains | 3 | A re-admitted piece consumes a canonical item another track matched (`The Overture (end)`, STS9 `Murph`). Flagged, not silent. |
| jerrybase closer not at a break | 2 | Spoken audio (`Donor Rap`, `bobby speaks`) sits between the closer and the break. An accepted false hold. |
| other | 1 | `robertwalters20thcongress-2004-01-02`, already held. |

A class outside this table, or one more than 25% larger, blocks the merge until the operator
rules on it. Each cleared show is listed for the operator.

**(c) Sonnet hand-check.**
- **Sample.** About 60 files from the candidate arm, in the `r-INSTRUCTIONS.md` packet format
  with the rulings written into the direction:
  - kept: music 10, fragment 5, spoken 10, mixed-with-tuning 6, untagged interior 8,
    placeholder-tagged 3;
  - dropped: junk 8, non-performance 5, untagged edge 3, filename 2.
- **Bar:**
  - zero kept spam or non-performance;
  - zero dropped music;
  - at least 90% right;
  - every wrong row in an accepted class (section 7) or fixed before merge.
- **Reference.** census2's 41-row packet re-scored under the rulings: 38 right. The 3 misses are
  inclusions: `Silent Track`, `crowd/tuning jam`, `Callin um back`.

**(d) Zero silent override mis-titles.** Every base `override` track keeps its title on the same
file. Measured: 0 shows.

**(e) Positional fills reported.** The candidate lists every show that gains or loses
`desc-position` or `setlist` titles. Expected:
- losses: `ratdog-2007-08-12` (19) and `derektrucksband-2004-11-20` (12), both accepted;
  `belafleckandtheflecktones-2003-04-12` (2); 1-track reversions on 7 shows;
- gains: 12 shows, including `darkstarorchestra-2015-07-11` (12, clears a hold).

**(f) Tests.** Unit tests:
- a corpus test: every measured drop stays dropped and every measured keep stays kept, over the
  3,547 rows;
- `short_tag_is_junk` and `short_is_spam` on every example named in 2.3, and the tripwire's
  own drop reason;
- interior/edge, and filename junk;
- `short_kept` at the gather level: an unmatched short-kept track does not lower coverage;
- the new `iter_shows` over a legacy, a migrated and a mixed file;
- the resolver's three refusals and the old-model `ValidationError`;
- the writers' refusal on a legacy file;
- the `set_breaks: []` shape;
- the `fix --exclude 3 --set-title 7=X` numbering;
- the exclusion refusal on a keyed file;
- the migration, against fixture show dirs: its refusals (the mixed file included), the
  all-or-nothing `--apply`, the backup rule, the write order, the version gate, the
  all-or-nothing undo and `already undone`;
- `deliver`'s selector refusal, `_destination_is_voiced` (the batch preflight included),
  briefing reuse, and the existing-audio reuse fallback.

A mutation check on the per-part anchoring, on the legacy-value test and on the undo hash
comparison must each turn a named test red.

## 7. Out of scope and accepted limitations

**The convention-arm class (ruling 7) is out of scope.** It is 13 shows and 90 files, 51 already
operator-included, and the data holds no narrow, clearly correct rule. The class contains:
- the canonical spam file (`gratefuldead-1973-06-10`, `FOLLOW-ME @BYPIKENO.mp3`, tagged
  `Morning Dew`);
- an opening act's set (`karldensonstinyuniverse-2011-10-28`);
- a disc carrying another date (`waynehancock-2004-04-08`);
- a second-show block (`soulive-2009-04-16`).

These stay with `fix --include` and the adjudicator.

**Also out of scope:** long spoken tracks (unchanged), 5a partial tapes, 5b better sibling and
5c shifted tags.

**Accepted limitations:**
- **`ratdog-2007-08-12`** holds after losing its 19 `desc-position` titles. `fix --exclude` of
  the untagged file, or the adjudicator, resolves it.
- **`derektrucksband-2004-11-20`** loses 12 `setlist` titles to a kept untagged interior file,
  and holds.
- **Spam with a lying tag.** A short clip that matches the naming convention, has no spam marker
  in its filename and carries a lying song tag is admitted. Measured: 0.
- **Interior timing.** The interior test runs before dedupe, re-admission and exclusion. A file
  interior only because of an operator-excluded neighbour is kept. The replay measured 0
  reorders of existing files.
- **A wholly junk final title** on a short-kept track ships with a note (2 files).
- **Very short files.** About 6 kept files have a metadata length under 5 s.
- **Inclusion errors the rule cannot see:**
  - `Silent Track`, named only in the description;
  - tuning-dominant mixes such as `crowd/tuning jam`;
  - titled spoken bits in the census "music" kind (`"really hot show"`, `Let Phil Sing Rant`).
- **The closer flag** fires on spoken audio after a closer (2 shows).
- **Future gets may select a different recording:** 25 of 2,263 multi-recording shows re-score
  differently. Existing shows keep `selection.json`.

## 8. Unverified premises, each with its cheapest test

1. **The candidate arm reproduces the reference harness.** That harness patched the filter and
   coverage in-process.
   - Test: a per-show diff against `r1/arm_r1.jsonl`.
2. **Sonnet's hand-check agrees with the operator.**
   - Test: the operator checks the first 10 rows first.
3. **The deny vocabulary holds beyond the library.**
   - Test: one look at the 5,024 kept sibling short tags in `r1/r1_sibs.json` that contain a
     junk or broadcast word.
4. **Briefing reuse is safe.** A reused briefing never claims the absence of a restored piece.
   - Test: 10 of the 37 voiced-severe briefings read by hand. `briefing_guard` already runs on
     every reuse.
5. **No other positional key exists.**
   - Test: a grep over every reader of `Overrides` and `Track.index` in `llama`, `scripts` and
     `emcee` (emcee reads only the manifest).
6. **The re-download is affordable.**
   - Test: sum the manifest audio sizes of the delivered rows that the existing-audio reuse
     cannot cover.
7. **Delivered station files pass the reuse duration check.**
   - Test: run it over 20 delivered shows and count the fallbacks.
8. **The reuse check is quick enough over SMB.**
   - Test: time it over one delivered show on the station share.
