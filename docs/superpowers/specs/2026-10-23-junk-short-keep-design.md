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
  hand-authored operator data. Section 4 says exactly what is written and when, the verified
  whole-library snapshot taken first and the wholesale restore from it, how an old binary is
  kept from reading migrated data silently, and that an ambiguous mapping refuses and names the
  show.
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
- it trips the spam-shape tripwire (2.3);
- its tag is wholly junk (2.3); or
- its duration is zero (2.3, Checkpoint A ruling): an audio-less stub keeps `implausibly short`.

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
  - a file failing the short arm and another arm (7 files);
  - a zero-duration file, which keeps `implausibly short` (2.3, Checkpoint A ruling).
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
    r"|\b(?:house|p\.?\s?a\.?|intro|walk[\s-]*(?:on|in|out|off)|recorded|pre-?show|closing|exit|outro)\s+music\b"
    r"|\binterview\w*"
    r"|(?=.*\b(?:dj'?s?|radio)\b)(?=.*\b(?:talk\w*|intro\w*|outro\w*|banter|announc\w*|moderator\w*|host\w*|id|spots?)\b)"
    r"|\b(?:over|on)\s+(?:the\s+)?p\.?a\.?(?=\W|$)"
    r"|(?=.*\b(?-i:[KW][A-Z]{2,3})(?:-?FM)?\b)(?=.*\b(?:talk\w*|intro\w*|outro\w*|banter|announc\w*|moderator\w*|host\w*|id|spots?|wrap\w*)\b)"
    r"|\bhost\s*#\s*\d",
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
- **NONPERF additions (Checkpoint A ruling, 2026-10-24).** Four additive alternatives, for the
  6 library files the original vocabulary kept (`Rock and Roll (Played over PA - fades in)`,
  `Mardi Gras Celebration (Hey Pocky Way on PA)`, `WXRT Intro`, and three `Host #NN` tracks of
  `theotherones-2002-08-03`): PA playback (`over PA`, `on the PA`); `closing`, `exit` and
  `outro` joining the `<x> music` group; a broadcast call sign (`K` or `W` plus 2-3 capitals,
  optional `-FM`) with a spoken qualifier, the call letters **case-sensitive** (the scoped
  `(?-i:...)` inside the `re.I` pattern), so `kdhx intro` and `wake intro` stay kept; and
  `host #<n>`. A bare `PA` is not a term (`Ardmore, PA` stays kept). Measured over the 3,547
  rows: the four alternatives newly drop exactly those 6 files, and no other row changes
  through them. Three of the six carry census kind `music` or `music-fragment` (the two PA
  playbacks and the `HOST #12` intermission); the ruling classes them as non-performance. The
  task review re-measured independently over 13,202 short drops and all 75,277 library track
  titles: only the ruled rows change, and every new hit is broadcast or PA material.
- **Zero-duration files (Checkpoint A ruling, 2026-10-24).** In `_apply_short_rule`'s first
  loop a file whose `duration_sec` is zero (`length_seconds("00:00")` is `0.0`, not `None`, so
  the `missing duration` arm does not fire) is not re-decided: it keeps `implausibly short`.
  Coded as `if e["reasons"] != ["implausibly short"] or not e["duration_sec"]: continue`. An
  exact test, no threshold, drop-only. Such a file is an audio-less stub (e.g. a 1,017-byte
  `gd73-10-29d2t01_vbr.mp3`) that would take its show off playout.
- **Stage banter is kept in general** (operator): `Stage Announcements`, `Banter Promote CD`,
  `banter - promoting the new CD`.
- **The operator-ruled broadcast examples.** 20 of the 21 drop. The one that does not is
  `Stage Banter: Consummation Station` (`thegourds-2009-10-17`): it is the band's stage banter
  (`station` without id/plug), which the census regex had mis-classed.

**Measured:** 651 junk and 34 non-performance drops at the original vocabulary (685), no music
among them, and none operator-included. After the Checkpoint A additions above the junk-test
drops number 691 (the 6 files added, 3 of which carry census kind `music`, ruled
non-performance). No sibling has a track of its own at any of these positions. 360 of them fold
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
  it as today. A tripwire drop records `spam-shaped name or tag` (2.3). A zero-duration file
  keeps `implausibly short`, never the tripwire's reason, even when its name is spam-shaped: the
  skip runs first and only ever drops (2.3).
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

### 2.6 Format choice and doubled derivatives (fix wave FW1, operator rulings 2026-10-25)

Both rulings came from the final whole-branch review and are built in `junk.filter_files`. They
change the plan's Global Constraint on the format choice and v2.17.0's "first format whose kept
set is non-empty".

- **The format choice (I-1).** Among the wanted formats, the winner is the format whose
  **kept** files have the greatest total running time. `FORMAT_BY_AUDIO`'s order breaks ties
  only, and the "no format keeps anything" fallback (the first format with any audio, so
  `excluded` still explains) is unchanged. "Kept" means after the junk arms, the short rule and
  both dedupes (duplicate listings, then derivatives), so a format listed twice does not win on
  its doubled time. `_kept_running_time` also leaves out an operator-excluded derivative whose
  original another, non-excluded kept derivative carries, so a doubled song the operator
  repaired by excluding one copy does not count twice (FW2 addition A).
  - Operator, on the first-non-empty rule: "Why would we pick a format with 1 file for a concert
    containing many songs?" The case was `tsp2007-07-28.csb.flac24`: a lone 61 s `Flac` file
    the short rule now keeps beat the whole show in `24bit Flac`.
  - Measured over the 15,607 cached items: under mp3, 0 format flips; under flac, 31 flips, all
    to `24bit Flac`, with more tracks and running time.
- **Doubled derivatives (I-2; supersedes Checkpoint A ruling 5, "not in this branch").** Within
  the winning format, `_dedupe_derivatives` keeps at most one derivative per `original` across
  all kept files, long and short. A dropped copy goes to `excluded` with the reason
  `duplicate derivative`. It runs after the duplicate-listing dedupe, before `include`'s
  re-admission, and only drops: play order is decided as if the dropped copies were still there.
  - **Which copy:** a copy in the operator's `include` first; then the plain `X.mp3` over
    `X_vbr.mp3` (`PREFER_VBR_DERIVATIVE = False`, one named constant); then the copy whose stem
    is its original's stem (a group with no `_vbr` copy is a stale derivative of a renamed or
    re-split original); then name order. A copy in the operator's `exclude` is never grouped,
    so excluding one copy keeps the other and the song ships once.
  - **Measured basis:** over 104 cached items and 2,017 pairs, the plain `X.mp3` is the newer
    file in 2017 of 2017; in the 23 non-`_vbr` groups the copy named after its original is the
    newer file in 23 of 23.
  - **Measured effect:** 23 library shows / 414 files change, every one a `_vbr` dropped as
    `duplicate derivative`. Nothing else drops, adds or reorders, and no song loses its last
    copy. The selected recording changes on 20 GD dates (they re-gather and re-research in the
    bulk apply).
  - **No flip.** Checkpoint C Q1/Q2 (Shawn, "Recommendations accepted on all points"): keep the
    plain copy. A flip to `_vbr` would air truncated copies, since in all 13 library / 48 cache
    pairs whose durations differ the truncated copy is the `_vbr` one (e.g. 16 s against 725 s).
    A flip needs a duration tie-break or refusal first (filed, section 7).
- `short_keep=False` reproduces v2.17.0 exactly: first non-empty format, no derivative dedupe.
  Only the migration's consistency check passes it.

### 2.7 The segue donor (fix waves FW3 and FW4)

The cause of both: the de-doubling above changed which LMA parse `build_canonical` ranks as the
segue donor for `blend_segues` (it ranks by `target_count=len(kept)`), and
`gratefuldead-1988-06-23` lost 5 real marks. The plan froze structure behaviour; the rulings
below unfreeze `blend_segues`' pooling, and nothing else in `structure.py`.

- **(A) The donor is segue-bearing (Checkpoint C Q6, "Go on both. Recommendations accepted on
  all points").** When setlist.fm wins the canonical, the segue donor is ranked only among LMA
  parses carrying at least one segue; with none there is no donor.
- **G5 (FW4 ruling, Shawn 2026-10-25 ~10:10, "Let's do that targeted fix").**
  `_drop_dangling_segues` clears the segue flag of a donor item followed by an entry that begins
  with a filler word (`_leads_with_filler`, `structure._FILLER` used verbatim, anchored with
  `.match`; `is_filler` and `_FILLER` untouched) or by nothing: `Ripple > Outro`, `Sugar
  Magnolia > Crowd`, `Excitable Boy > Banter`, a final `>`. Applied to the chosen donor after it
  is ranked, never to the canonical winner. Leading-word only because a search anywhere cost 5
  real marks on titles such as `Cumberland Blues (Band Intros)`.
- **Own alignment wins over pooling (FW4 item 2).** `donor_segues` aligns the donor to the
  tracks with the same `align()`; on every track that alignment matches, the track's segue is
  the donor item's, and `blend_segues`' exact-title pooling stays the fallback where it does not.
  Only `segues` changes. The own alignment may remove a pooled mark wherever it matches. It may
  add one only when the track is not the show's last AND either its **shipped** set label (after
  jerrybase anchoring and the taper decision) equals the next track's or its own title ends in
  `>` or `->`. Skipped when `align_structure` (the LLM) won.
- **Measured** (whole-library arms, cand-g against cand-d): G5 removes 23 false marks and loses
  0 real ones. Item 2 removes 107 marks (the 11 target marks on 5 shows among them) and adds
  about 2,000 well-supported ones, and loses 6 real marks through a wrong-item alignment. Item 2
  reaches about 1,050 shows (as first built) and costs 371 more fresh briefings at the bulk apply.
- Classes B and C and the residue are filed follow-ups (section 7).

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

  - **Legacy values** are the track-number forms: any `titles` key, `set_breaks` item or
    `encore_after` that v2.17.0's model accepts as an int. The test is v2.17.0's own rule,
    pydantic's lax `int` parsing, not Python's `int()`. So `"7"`, `" 7"`, `"7.0"`, `"07"`,
    `"+7"`, `"7_0"` (read as 70), `true`, a JSON integer and `2.0` are all legacy. The
    migration and the new resolver use the same test, so the resolver treats all of them as
    legacy. Its test uses the vendored v2.17.0 model as the oracle.
  - Every real filename has an extension, so v2.17.0's model accepts none as a number.
- **Both forms always parse.** The new `Overrides` model types the three keys as
  `titles: dict[str, str]`, `set_breaks: list[int | str] | None` and
  `encore_after: int | str | None`. Parsing never refuses; only the resolver and the writers
  judge legacy or mixed values. A test: the new `iter_shows` lists a library holding a legacy
  file, a migrated file and a mixed file without raising.
- **Old binaries fail loudly.** v2.17.0's model (`dict[int, str]`, `list[int] | None`,
  `int | None`) rejects every migrated file with a `ValidationError`. An old binary or a sweep
  loop therefore fails loudly instead of silently dropping the overrides. A test runs
  `e37f670`'s `Overrides` model, vendored as a fixture, against a migrated file and asserts that
  it raises.
  - **An old-commit harness arm is not loud.** At `e37f670` the harness catches the error,
    records the show `unreplayable`, and the run still exits 0. So an old-commit arm is never
    run against a migrated library; the runbook's order (4.3) runs both arms first. As a harness
    requirement, `compare` treats an arm with any `unreplayable` row caused by an overrides
    validation error as invalid.
  - **The failure is library-wide.** v2.17.0 reads every show's `overrides.json` whenever it
    lists or resolves shows (`catalog.iter_shows`). Once any file is migrated, the old binary
    fails on every command that lists or resolves shows, and on any gather, brief or reapply that
    reads a migrated file. That is by design: it is the loud failure. It is also why the
    migration checks every show before writing any, and why its rollback is a wholesale restore
    (4.3).
- **Writers refuse legacy.** Every new-code writer of `overrides.json` refuses before any prompt
  when the show's file holds any legacy value (`overrides.json uses track-number keys; run the
  migration`). That covers every `fix` edit flag (`--no-run` included), every triage edit,
  `--suggest-titles` and `--untitled`. A test pins it.
- **Presence semantics.**
  - `set_breaks` absent or `None` means no structure override.
  - `[]` means forced no breaks (the structure-override path, alignment skipped). It is
    preserved exactly.
  - `--untitled` and triage `[u]` keep writing `[]`.
  - "Has a legacy value" means any legacy value as defined above. An empty
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
    - a filename value whose file is not in the final kept list. The one message names every
      such key and its file, so a single `fix` clears them all.

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
    `--set-venue`, `--set-city`, `--set-date`, filename `--exclude`, `--clear-title <filename>`,
    `--clear-set-breaks` and `--clear-encore` still work, so a dangling key on a show with no
    `show.json` is cleared with `fix` too.
  - `--untitled`'s `Untitled (track N)` text keeps the number it was written with.
- **Exclusion refuses up front on a keyed file.** `fix --exclude N` and `fix --exclude <filename>`,
  with or without `--no-run`, and triage exclusion refuse when that file carries a title, break or
  encore key. The refusal names the key and the `--clear-*` flag that resolves it.
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

`scripts/rekey_overrides.py [--snapshot | --apply | --restore <snapshot-dir>]` is a one-off. It
is run from the repo as `/Users/shawn/projects/llama/.venv/bin/python scripts/rekey_overrides.py`
(branch code), never through a `.venv/bin/*` console script from a copy. With no option it is a
dry run. It never gathers. Its checks read only `overrides.json`, `show.json` and the cached
metadata of the item `show.json` names; a missing `selection.json` does not matter to it.

**Runbook, in order** (section 5 refers here):
1. Stop the sweep loop. Confirm with the process check (below) that no `llama` process is
   running.
2. With v2.17.0 still installed, run the dry run. It checks every show and prints each refusal
   with its repair route, and prints what the process check finds.
3. Repair each refusal with the installed v2.17.0 `llama`, by the route in the table below.
   Repeat steps 2 and 3 until the dry run reports 0 refused.
4. Snapshot the library with `--snapshot`.
5. Install the new release. `llama --version` must report the piece-4 version. Run nothing
   else in between.
6. Migrate with `--apply`.
7. Run the post-migration self-check (below), with the sweep loop still stopped.
8. Restart the sweep loop.
9. Build the apply lists from the self-check's re-run, then the bulk apply (section 5). Triage
   held shows only after the bulk apply has re-gathered them (4.2).

**Checks.** A show is refused, with its repair route, when any of these holds:

| reason | repair (step 3, v2.17.0 installed) |
|---|---|
| `overrides.json` is not valid JSON, or the new model cannot read it | the operator repairs the file by hand; the dry run lists every such file |
| the file mixes legacy and filename values | only a hand edit can produce this (writers refuse legacy files, 4.1): undo that hand edit. The refusal names each filename-valued key. Do it first, since v2.17.0 cannot run on a library holding the file |
| two `titles` keys parse to the same number (`"7"` and `"07"`) | hand edit (below) |
| `show.json` is missing | `llama redo <show> --from gather` |
| a `titles` key is outside `1..len(tracks)` | `llama fix <show> --clear-title k`; a key of -1 or below needs a hand edit (below) |
| the track at a `titles` key is not `title_source == "override"` with exactly the forced title | `llama redo <show> --from gather` |
| a `set_breaks` entry or `encore_after` is outside `1..len(tracks)-1`, or `encore_after` is not after every break (gather's own structure-override check, which would also fail the redo) | note the values, `llama fix <show> --clear-set-breaks` / `--clear-encore`, then set corrected values with `--set-breaks` / `--set-encore` |
| **when `set_breaks` or `encore_after` is present**, `show.json`'s `set_breaks` is not exactly `sorted(set_breaks ∪ {encore_after})` | `llama redo <show> --from gather` |
| a track filename repeats | note the affected keys' values, clear them with `llama fix <show> --clear-title k` / `--clear-set-breaks` / `--clear-encore`, then migrate. A filename key cannot name a repeated file, so that show carries no title/break/encore override on those files until the duplicate is resolved (accepted limitation; 0 shows today) |
| `show.json`'s filename list differs from what the shared helper (4.2) keeps under today's rule (`short_keep=False`) from current metadata plus `include` minus `exclude` (the writers' staleness comparison), or the item's cached metadata is missing | `llama redo <show> --from gather` |

**Routes with no CLI form.** A `titles` key of -1 or below (v2.17.0's `--clear-title` takes
digits only), two keys that collapse to one number, and a `redo --from gather` route that cannot
run (no `provenance.json`, a darked item) are repaired by a hand edit of `overrides.json`, with
v2.17.0 still installed. This is accepted: 0 shows today.

These checks prove that the stored positions, the stored `show.json` and the current inputs
agree. An ambiguous show is never guessed. Every refusal has a route, and `--apply` stays
blocked until each is taken; 0 shows are refused today.

**The process check.** `--snapshot`, `--apply` and `--restore` refuse when any process other
than the script itself has a command line that runs llama: the release binary, a venv `llama`,
`python -m llama`, or the sweep loop's shell. The refusal lists each process found.
**Limitation:** a sweep loop typed at an interactive prompt and sleeping between passes runs
in the login shell and is invisible to the check. The dry run prints a note saying so, and
step 1 of the runbook (stop the loop) is the operator's.

**`--snapshot`.** It runs the process check and takes the migration lock (`<root>/.rekey.lock`,
flock). It refuses a library holding any filename value, since a partly migrated library is no
rollback point. Its directory is named by the UTC time copying starts,
`<root>/rekey-snapshot-<UTC start time>/`, and it records the slug of every show directory
present then. Under each show's lock (`locks.file_lock(ws.lock)`) it copies every file of that
show directory outside `package/audio/` (about 280 MB today) into `shows/<slug>/...`, verifies
every copy against the sha256 of its source and flushes it (`F_FULLFSYNC`). It then writes
`manifest.json`, listing the slugs and every copied path with its sha256, and flushes it. Only
then does it report success. A directory without `manifest.json` is not a snapshot. The snapshot
is never modified afterwards. **AUTHOR'S CALL:** the per-show `.lock` files are neither copied
nor restored.

**`--apply`.** It uses the newest snapshot, and refuses and writes nothing unless all of these
hold:
- the whole snapshot verifies: every `manifest.json` entry exists and matches its sha256, and
  every show directory the library held at snapshot time (the slugs the manifest records) has
  its entries;
- every `llama` on PATH (`which -a llama`) reports at least `REKEY_MIN_VERSION`, compared
  numerically. That is a constant in the script, set to the piece-4 release version. A dev build
  (`0.1.0`, `0.0.0+unknown`) refuses, and so does no `llama` on PATH;
- the process check finds nothing.

It then takes the migration lock, and runs every check over every show with a legacy value. If
any show would be refused it writes nothing and prints each refusal. Otherwise, per show, under
the show lock:

1. **Re-check.** Re-read `overrides.json` and `show.json`. Each must be byte-equal (sha256) to
   its snapshot copy; a show with no snapshot copy fails this. Then re-run that show's checks on
   what was just read. A mismatch or a refusal here refuses that show and stops the run.
2. **Map** each position to `tracks[N-1].filename`, on the raw JSON object. The file is loaded
   with `json`, only `titles`, `set_breaks` and `encore_after` change, and every other key and
   its value, known or unknown, is kept unchanged. It is dumped the way `write_artifact` dumps
   (`json.dumps(..., indent=2)`).
3. **Write** it as a temp file, `F_FULLFSYNC`, rename, then `F_FULLFSYNC` the show directory.
4. **Record** the show in `<root>/rekey-applied.json`: the snapshot directory used, the UTC
   time, and the shows rewritten. It is written the same durable way, after each show.

Re-running `--apply` after an interruption continues with the remaining legacy shows. A migrated
show has no legacy value and is skipped. The run uses the same snapshot, since `--snapshot`
refuses a partly migrated library.

**Routes for an `--apply` refusal.** By then the new binary is installed, and its writers and
resolver refuse legacy files, so the table's routes cannot run under it. Every refusal `--apply`
prints, up front or under the lock, therefore reads: "reinstall v2.17.0, repair <show> with it
(route below), then return to step 2 (dry run) and take a NEW snapshot", followed by the table's
route. When the library already holds a migrated show, rewritten in this run or by an
interrupted earlier one, it first says: "run `--restore <snapshot>` with the new binary, then
reinstall v2.17.0". v2.17.0 cannot run on a partly migrated library.

**Output.** One line per show: `rekeyed: <slug> (T titles, B breaks, encore)` (`would rekey` in
the dry run), or `refused: <slug>: <reason>` with its repair. Then a summary. Exit 1 if a gate
failed or anything was refused.

**`--restore <snapshot-dir>`** is the rollback for "piece 4 is wrong", not a per-show tool. It
returns the library's metadata to the moment before the migration and **discards every edit,
gather and apply made since, including the bulk apply.** It has no version gate. It runs the
process check and takes the migration lock. It refuses, and writes nothing, when any hash in the
snapshot's `manifest.json` fails, or while any show directory created after the snapshot exists
(one not among the manifest's slugs). It lists each such show with its route: `llama rm <show>`
with the new binary, adding `--forget` when a later `get` should re-fetch it. Then, for every
slug in the snapshot, under that show's lock:
1. **Audio first.** Unless the snapshot holds a `package/manifest.json` byte-equal to the
   current one, it empties `package/audio/` (**AUTHOR'S CALL**). That covers a show packaged
   since the snapshot as well as one re-packaged. Those files carry the new numbering, and a
   restored manifest name could match the wrong one. v2.17.0's `redo <show> --from package`
   re-downloads them, the route the deliver gate's "audio files missing" names.
2. It copies every snapshotted file back over the library (temp, `F_FULLFSYNC`, rename).
3. It deletes every other file under the show directory outside `package/audio/`, `.lock` aside,
   such as a `notes.json`, `.txn/` or briefing written since (**AUTHOR'S CALL**). Each show is
   then exactly as at the snapshot, apart from `package/audio/`.

**Why audio comes first.** Were the manifest copied back first, a crash before the audio was
emptied would leave equal manifests, and a re-run would keep the new-numbered audio. Emptying
first means a crash between the two steps leaves a show that v2.17.0 re-downloads, never one
with wrong audio.

A restored show's `show.json` is the old rule's again, so v2.17.0's positional edits read the
numbering they write against.

**Wrong-snapshot refusal.** `--restore` also refuses, and writes nothing, when
`<root>/rekey-applied.json` exists and names another snapshot than the one given, or cannot be
read: the shows were rewritten from the recorded snapshot, and restoring an older one would
silently discard every edit between the two. The refusal prints the snapshot to use. With no
record (none taken, or renamed) there is no check. A successful restore renames the record to
`rekey-applied.restored-<UTC>.json`.

**What restore does not revert.** The ledger, `runs/`, the cache, and reapply batch progress
under `<root>/reapply/`. Restore lists the reapply batch directories and the runs created after
the snapshot, so the operator can remove them: re-running the same list would otherwise skip
shows. It does not touch the station either. It lists every station destination re-delivered
since the snapshot (a destination manifest newer than the snapshot), the 37 re-voiced shows
among them. Those keep the new packages until each show is re-delivered from the restored
library. The test is the manifest's mtime, so a manifest that emcee re-voiced in place since the
snapshot is listed as re-delivered too (Checkpoint C Q7): a show listed only for that reason
needs no `--replace-voiced`.

**Restore runbook.**
1. Stop the sweep loop, and confirm with the process check that no `llama` process is running.
2. Run `--restore <snapshot-dir>`, with the new binary still installed.
3. Reinstall v2.17.0 from the release.
4. Verify that `llama --version` reports 2.17.0.
5. Restart the sweep loop.

**The post-migration self-check and the apply lists (steps 7 and 9).** Both acceptance arms
(6(a)) are run and compared before the migration, exactly as measured. After the migration, with
the sweep loop still stopped, a candidate-only re-run must reproduce the pre-migration candidate
per show:
- the outcome;
- every track's `(filename, title, title_source, set, segue)`;
- the show's set breaks and encore position.

This is a per-show comparison, not `compare`'s digest gate, since every migrated
`overrides.json` has a new digest. Any difference stops the apply and is investigated.
`short_keep_probe.py repro` refuses to compare, and says why, when either arm has no replayable
row or the two arms name different library roots (an empty arm would pass on nothing). The bulk
apply's requirement: its apply lists come from that post-migration re-run, so their
`input_digests` match the migrated files.

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

   **Superseded by the restored-file gate below.** The 1,017 figure assumed a briefing stays
   true when a file is restored; premise 4 (section 8) failed that test.

   **The restored-file gate (Task 15a, operator ruling at Checkpoint B, 2026-10-24 ~14:25,
   "2").** `run_brief` passes the whole `show.json` to the LLM, `excluded_files`
   (`implausibly short`) and `structure.conflicts` included, so a stored briefing routinely
   says a restored file is absent (all 10 hand-read briefings of the 37 voiced-severe shows
   did), and `briefing_guard` checks no claim about which files are present. So when the new
   show has a **restored** file (a `short_kept` track whose filename is not among the stored
   show's tracks; the 173 already-included files do not count) `briefing_reusable` also refuses
   a briefing that mentions one, anywhere in any text field of `Briefing`
   (`BRIEFING_TEXT_FIELDS`, pinned against the model): by filename, stem or disc/track tail, or
   by exclusion or absence wording. The reason starts `briefing mentions a restored file`.
   Deterministic, and conservative on purpose: a false "not reusable" costs one brief call, a
   false "reusable" ships a false claim on air. The rejected alternatives: a fresh brief for
   every restored show unconditionally, and editing stored briefings.
   - **The wording vocabulary** is `replay._RESTORED_WORDING`, matched on the lowercased text and
     on punctuation-normalised copies (hyphen read as separator and as joiner, apostrophe read
     both ways): `excluded`, `implausibly short`, `too short`, `left out`, `omitted`, `absent`,
     `not present`, `missing`, `dropped`, `not represented`, `not part of`, `not a track`,
     `track count` (a count or range of tracks), then Task 15b's (Checkpoint B ruling 1, "Go
     ahead and add them") `not included`, `not listed`, `does not appear`, `unlisted`, `not in
     the setlist`, `no separate track`, `not tracked separately`, `not found` and its
     paraphrases, `not included or listed`, `no ... listed`, and FW2's `lacks`, `not
     recorded`, `cut from the recording`, `lists no` (a data subject, then `lists` or
     `contains`, then `no`).
   - **The 15b design:** a negation (`not`, `never`, `n't`, `cannot`, `no longer`, `nowhere`,
     `neither`, `nor`) followed by a bounded window of up to N words (2 to 5, per term) before
     the head word, over the normalised text, so "is not “officially” listed" and "should not,
     in fact, have been included" match. `too` and `implausibly` take a 2-word window ("too
     very short"). The apostrophe separator copy makes "not’listed" read `not listed`; FW3 M1
     folds U+02BB and U+02B9 into `_APOSTROPHES` with the other look-alikes. Every addition only
     refuses more, never less.
   - **Measured:** over the 1,014 reusable stored briefings of changed shows the gate refuses
     1,014 of 1,014, and the reuse arm's 901 of 901; the wording arm alone fires on every one,
     the name arm on 406 and never alone. In practice regeneration is **100%** on today's library
     (the ruling expected about 98%): of 1,410 changed shows with a briefing, 1,112 are `fresh`,
     298 `none` (held), 0 `reuse`. The bulk apply budgets about 1,000 fresh briefings, plus the
     de-doubling's (13) and the segue donor's (371).
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
   - **Identifier gating (Task 13).** Index pairing with equal titles ties a file to its source
     only within ONE archive.org item: file names repeat across items (138 of 288 multi-item GD
     dates share mp3 names), and a re-selection to another item would have shipped the old
     item's audio under the new identifier. So a library or station manifest pairs only when its
     `source.identifier` equals `show.json`'s (`audio_reuse.plan_reuse`); a manifest with no
     readable identifier pairs nothing. `ReusePlan.identifier` records the plan-time identifier,
     and `build_package` re-checks it against the show it packages: a mismatch discards the
     pairings (the old audio is still set aside), so everything downloads.
   - **Why this is enough.** Both copies came from md5-verified downloads, and the index pairing
     with equal titles, within one item (above), ties each file to its source. The station copy was also checked against
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
- Base: `scripts/replay_holds.py run --all` at `e37f670`.
- Candidate: the branch, with the harness re-key.
- Both run before the migration, against the same legacy library (4.3).
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

**(d) Zero silent override mis-points.** Every base `override` track keeps its title on the same
file. Measured: 0 shows. Every override-path structure keeps each break and its encore after the
same file. The post-migration self-check (4.3) compares the same structure, so all 427 break and
365 encore keys are exercised end to end.

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
- the resolver's three refusals (every dangling key named in one message) and the old-model
  `ValidationError`;
- legacy classification agreeing with the vendored v2.17.0 model (`" 7"`, `"7.0"`, `"07"`,
  `"+7"`, `"7_0"`, `true`, `2.0`, a filename);
- `compare` refusing an arm with an `unreplayable` row caused by an overrides validation error;
- the writers' refusal on a legacy file;
- the `set_breaks: []` shape;
- the `fix --exclude 3 --set-title 7=X` numbering;
- the exclusion refusal on a keyed file, in both forms and with `--no-run`;
- `--clear-title <filename>`, `--clear-set-breaks` and `--clear-encore` on a show with no
  `show.json`;
- the migration, against fixture show dirs:
  - its refusals, the mixed, the unreadable and the duplicate-key file included;
  - the process check finding a release binary, a venv `llama`, `python -m llama` and a loop
    shell, and not the script itself;
  - `--snapshot`'s copy and hash verification, its refusal of a library holding a filename
    value, and a missing `manifest.json` reading as no snapshot;
  - the `--apply` gates: no snapshot, a snapshot file deleted or changed, a show the snapshot
    does not cover, a `llama` on PATH below `REKEY_MIN_VERSION` (a dev build included) or none,
    and a running `llama` process;
  - the all-show check writing nothing when any show would be refused;
  - the re-check under the show lock: an `overrides.json` or `show.json` that differs from its
    snapshot copy refuses that show and stops the run;
  - the printed routes: a refusal with nothing rewritten names the v2.17.0 repair and a new
    snapshot, and one after a show was rewritten names `--restore` first;
  - `rekey-applied.json` recording the snapshot and every rewritten show;
  - an unknown key and its value preserved through the raw-JSON rewrite;
  - an interrupted `--apply` continuing with the remaining legacy shows;
  - a wholesale `--restore`:
    - a hash mismatch, or a show created after the snapshot, writing nothing (the latter listed
      with `llama rm`);
    - files back byte-equal to the snapshot, and files written since deleted;
    - `package/audio/` emptied unless the snapshot's `package/manifest.json` is byte-equal to
      the current one, a show packaged since the snapshot included;
    - a crash after emptying and before copying, then a re-run, leaving no audio beside the
      restored manifest;
    - reapply batch dirs and runs created since, and station destinations re-delivered since,
      listed;
- `deliver`'s selector refusal, `_destination_is_voiced` (the batch preflight included),
  briefing reuse, and the existing-audio reuse fallback.

A mutation check on the per-part anchoring, on the legacy-value test and on the snapshot's hash
verification must each turn a named test red.

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
- **Crowd chants stay kept (Checkpoint B ruling 2, 2026-10-24).** Operator, verbatim: "An NFA
  chant should absolutely not be dropped; other crowd chants could go either way but inclusion
  is safer." The six crowd-chant keeps (`Not Fade Away Chant`, two `Crowd Doing Not Fade Away`,
  `Unity College chanting`, `crowd/tuning jam`, `crowd/1812 Overture`) stay kept, with no
  vocabulary change. `test_a_not_fade_away_crowd_chant_is_kept_operator_ruling` pins that a Not
  Fade Away crowd-chant tag is kept by the short rule, so no later vocabulary change drops it.
- **Non-performance false-positive class.** The Checkpoint A additions can drop a short song
  whose title reads as a broadcast term: a K or W band abbreviation or all-caps title beside a
  spoken qualifier (the call letters are case-sensitive, so `kdhx intro` and `wake intro` stay
  kept), and a title that reads `<x> music` for `exit`, `closing` or `outro`, e.g. `Exit Music
  (For a Film)`. Measured over the library: 0 song-titled drops beyond the 6 ruled files.
- **A destination with audio but no `manifest.json` merges** (Task 16 Minor 1). `deliver`
  overlays it as before rather than refusing. Operator: "Leave it, low risk and unlikely."
- **Spam with a lying tag.** A short clip that matches the naming convention, has no spam marker
  in its filename and carries a lying song tag is admitted. Measured: 0.
- **Interior timing.** The interior test runs before dedupe, re-admission and exclusion. A file
  interior only because of an operator-excluded neighbour is kept. The replay measured 0
  reorders of existing files.
- **A wholly junk final title** on a short-kept track ships with a note (2 files).
- **Very short files.** About 3 kept files have a metadata length under 5 s (6 before the
  zero-duration skip; the three zero-length files now drop) (Checkpoint A ruling, 2026-10-24).
- **Crowd and tuning tags beyond the library (Checkpoint A ruling, 2026-10-24).** Outside the
  library the junk test keeps typo'd, pluralised, set-labelled, annotated and taper-prefixed
  crowd and tuning tags (about 200 of 5,024 sibling short keeps; e.g. `crown/tuning`,
  `Tunings`, `Set I: Tuning`, `Tune Up (AUD)`, `gd81-09-12 s1t01 Crowd`,
  `JKB110506_03 Noise`). They are seconds of junk, the error the operator ranks cheaper.
- **Doubled `_vbr` derivatives: built in this branch (2.6; supersedes the Checkpoint A ruling
  of 2026-10-24 that deferred it).** 20 GD shows shipped every song twice (`X.mp3` and
  `X_vbr.mp3`); not on air (all unvoiced). Filed: a `_vbr` preference flip needs a duration
  tie-break or refusal first (2.6), and FW2 M2 (a pair whose copies are BOTH operator-excluded
  counts twice in its format's running time; latent, multi-format items only, 0 library shows).
- **Segue donor, filed follow-ups (2.7).**
  - Class B: run-on chosen descriptions (`parse_setlist`'s documented merge).
  - Class C: `blend_segues`' exact-title pooling of `Space` and `Jam`, where the own alignment
    does not cover the track.
  - On the LLM `align_structure` branch item 2 does not apply, and pooled marks still feed
    `correspondence._merge_legal` and the `align_structure` prompt.
  - An in-track flow into a non-filler solo (`warrenzevon-1994-02-07` #15, `^ > Dr. Babyhead
    Solo`).
  - 4 real gains declined under a wrong shipped set label (upstream).
- **Two re-selections orphan operator overrides** (`gratefuldead-1970-05-06`,
  `gratefuldead-1985-11-10`): the bulk apply surfaces them (the dangling-key refusal names the
  `llama fix --clear-*` route) and they are fixed by hand afterwards (Checkpoint C Q3). The 20 GD
  dates whose selected recording changes re-gather at the apply (Q4).
- **Inclusion errors the rule cannot see:**
  - `Silent Track`, named only in the description;
  - tuning-dominant mixes such as `crowd/tuning jam`;
  - titled spoken bits in the census "music" kind (`"really hot show"`, `Let Phil Sing Rant`).
- **The closer flag** fires on spoken audio after a closer (2 shows).
- **Rule-changed shows outside the bulk apply** refuse positional edits until re-gathered
  (4.2). That covers the 28 voiced-minor shows. The re-gather is a redo that may spend a brief.
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
   - **Result (Checkpoint B): failed.** All 10 stored briefings claimed a restored file absent,
     excluded or not a track. The restored-file gate in 5.3 is the response.
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
9. **The snapshot is quick enough.** Its 280 MB copy and hash check, and `--apply`'s
   re-verification of it, run over the local disk.
   - Test: time `--snapshot` once on the real library before step 5.
