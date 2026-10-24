# Keep short files that belong to the show (held-backlog part 1, piece 4)

Date: 2026-10-23. Branch `held-backlog-junk-filter` from `main` @ `e37f670` (v2.17.0).
Inputs: the two sizing censuses and hand-checks in
`docs/superpowers/2026-10-23-junk-short-keep-evidence/` (`census-handback.md`,
`census2-handback.md`, `p4-*`/`r-*` hand-check packets, `shipped-broken.md`,
`voiced-severe-review.md`). Operator rulings of 2026-10-23 are binding and are restated where
they apply. The measurements quoted here come from the replay harness at
`~/.llama-harness/piece45/spec/` (scripts `rprime.py`, `dump_rp.py`, `m1`-`m7`). They ran
read-only against the whole library, 3,983 shows, at `e37f670`.

**Review mode: Opus** (Opus spec and plan reviewers, Opus final branch reviewer).

**Stakes.** About 4,000 shows; ~2,800 are delivered and on air at listen.lma-radio.com. One
operator, whose attention is the scarce resource. The operator's accuracy rule: **omitting real
show content is worse than including a little that does not belong, and tape notes are presumed
correct.** Today the junk filter's short-duration arm drops the `Drums >`, `St. Stephen`
reprise or `Slipknot!` that sits between two songs, and the show airs with a hole in it and no
flag. Strict surfaces:

- **(a) The positional-overrides migration.** It rewrites `overrides.json`, which is
  hand-authored operator data. Section 4 states exactly what is written, when, how it is undone,
  and that an ambiguous mapping refuses and names the show.
- **(b) Re-delivering voiced shows.** `llama deliver --replace-voiced` discards paid TTS voicing,
  and that cannot be undone. Only the 37 shows the operator approved are in scope (section 5).
- **(c) Relaxing a safety filter.** The change must not admit spam or non-performance audio. The
  filename-convention arm stays the spam guard and is not touched (section 2.1).

Everything else is proportionate: the change only alters what a future gather keeps.

## Why

- **The arm's scope.** The short arm drops 3,547 files in 1,870 shows whose only drop reason is
  `implausibly short` (under `SHORT_FRACTION_OF_MEDIAN` x the tape's median). That is 96% of
  everything the filter drops.
- **What those files are.** By tag:
  - spoken band material (intros, banter, band introductions, stage announcements) 1,653;
  - music (segue pieces, reprises, short songs, continuations) 864 + 51 fragments;
  - crowd 315; tuning, fades and silence 339; untagged 197;
  - radio and non-performance audio 37.
- **Ground truth.** The operator has re-admitted 239 dropped files by hand with `fix --include`.
- **The tag tells them apart.** In the census, no file whose tag says tuning, silence or a fade
  was music by any source (siblings, setlist, description).

## 1. The rule (operator ruling 1)

A file whose **only** drop reason is the short-duration arm is **kept**, unless its tag is
wholly junk (2.3). An untagged file follows 2.4.

## 2. Specification

### 2.1 Scope and what does not change

- The short arm still computes the same floor from the same constants. `SHORT_FRACTION_OF_MEDIAN`,
  `MIN_PLAUSIBLE_SEC` and `MIN_MEDIAN_SAMPLE` are unchanged, and the two-pass median (taken over
  files passing every other arm) is unchanged. CLAUDE.md's "Plausible duration is RELATIVE" stays
  true: the arm now drops by duration **and** tag.
- A file with any other reason is untouched: the filename-convention arm (the spam guard;
  `FOLLOW-ME @BYPIKENO.mp3` is caught there), provenance, `missing duration`, duplicate-listing,
  and a file failing the short arm *and* another arm (7 files). No URL, @handle, "follow" or
  "download" exists among the 3,547 short-only drops.
- Operator `exclude` always wins. It is applied after the filter, as today.
- `include` is unchanged. A file the rule now keeps is simply no longer in `excluded`, so `include`
  re-admits nothing for it (`ordering["readmitted"]` is empty for it). 173 kept files are already
  operator-included.

### 2.2 The tag, and "tagged"

- **The tag** is the file's own `title`, else its original's `title` (the same rule
  `_track_number` uses for the track tag), passed through `titles.clean_tag_title`.
- **A file is tagged when that is non-empty** (ruling 3). This includes a leaked timestamp prefix
  (`0:50) Going In The Right Direction`) and placeholder tags such as `d1t01`, `tmp` and
  `Track 9`.
  - Consequence: 12 placeholder-tagged files are kept, about 8 of them at a tape edge. Each
    ships 2b-demoted as `unresolved`, and so holds.

### 2.3 Wholly junk (ruling 2)

The tag is first cleaned for matching:
- strip leading timestamps (`0:40) `, `00:35 - `), leading track numbers (`16 `, `2: `), disc
  stems (`d1t01`) and glued numbers (`0105tuning`);
- strip time annotations in brackets (`(1:28)`, `(02:38:69)`).

It is then split into parts on `/ , & + ; and - > ~ |` (including ` - `, `-->`), parentheses and
square brackets. Each part's edge punctuation is stripped.

**A tag is wholly junk when either test holds:**

1. **Non-performance, matched anywhere in the tag**, word-bounded and case-insensitive:
   - `commercial`, `promo`, `advert`;
   - `station id` / `station plug` / `station identification`;
   - `news broadcast`;
   - `house`/`PA`/`intro`/`walk-on`/`recorded`/`pre-show` + `music`;
   - `radio`, `DJ`/`DJ's`, `interview`, `moderator`, `announcer(s)`.
2. **Every part is a junk part**, i.e. one of:

   | class | parts (all variants and typos seen in the data) |
   |---|---|
   | tuning | `tuning`, `tunning`, `tunig`, `tuneing`, `tune up`, `tuning up`, `re-tune`, `set N tuning`, `instrument change`, `warm up` |
   | silence | `dead air`, `silence`, `silent`, `blank` |
   | tape edge | `tape`/`side`/`disc`/`reel` + `flip`/`change`/`cut`/`end`/`gap`; `gap`; `cut-in` |
   | fade | `fade in`, `fade out` |
   | noise | `noise` (incl. `tape noise`, `crowd noise`), `hiss`, `static`, `test tone` |
   | soundcheck | `soundcheck`, `sound check` |
   | crowd | `crowd`, `audience` (with optional `noise`/`cheering`/`chanting`/`applause`/`yelling`/`encore call`), `applause` (`opening`/`encore` applause), `cheering`, `clapping`, `encore break`/`set break`/`encore call`, `waiting (for the encore)`; `crowd tuning` / `tuning crowd` |

The test is anchored per part. **A tag with any part outside the table is kept** (ruling 3):
- `intro/tuning`, `tuning/banter`, `Take A Step Back/Tuning`, `Mexican Hat Dance Tuning`,
  `crowd/tuning jam`, `Crowd Doing Not Fade Away` and `Bob Weir comment to crowd` are kept;
- `crowd/tuning`, `Crowd & Tuning` and `2: crowd/tuning ->` drop.

**The non-performance terms are deliberately narrow:**
- Band stage talk is kept: `Stage Announcements`, `Banter Promote CD`,
  `banter - promoting the new CD` and `Stage Banter: Consummation Station`. `station` alone and
  `promote`/`promoting` do not match.
- `Stage/Radio Announcements` drops on `radio`.
- `Truckin'//, KSAN DJ Talk` drops on `DJ`. The operator ruled the radio-talk class drop with
  this row among the examples.

**AUTHOR'S CALL, a spam-shape tripwire.** A tag containing a URL, `www.`, `.com`/`.net`/`.org`,
an `@handle` of three or more characters, `follow`, `download` or `subscribe` is also wholly
junk. It measured 0 hits, so it costs nothing today. It means a spam clip that happens to match
the item's naming convention still drops (strict surface (c)).

**Measured:** 651 junk and 34 non-performance drops; no music among them, none
operator-included, and no sibling or canonical labels any of them a song. A false junk verdict
only reproduces today's behaviour.

### 2.4 Untagged short files (ruling 4)

- **Interior files are kept; edge files drop.** An untagged short file is kept only when it is
  **interior**: some kept file precedes it and some follows it in play order. Play order is
  derived the way `filter_files` derives it (track-tag order when every file in the set has a
  unique track number, else filename order), over the kept files, the tagged short files 2.3
  keeps, and the untagged candidates. Untagged files in the leading or trailing run drop.
  - Measured: 99 interior, 37 edge.
- **Filename junk** (AUTHOR'S CALL). An untagged short file whose filename stem, with leading
  digits and separators removed, is wholly junk under 2.3 drops. Measured: 3 interior files
  (`0201tuning.mp3`, `10 Crowd.mp3`, `09 Crowd.mp3`). The rule only ever drops, so it can never
  admit anything.
- **The count-match protection** (AUTHOR'S CALL among the options ruling 4 offered).
  - The two description readers of piece 3 D (`desc_list.read_numbered`, `read_parse`) each
    yield an admissible list or nothing, and a list's entry count does not depend on the tape.
  - **The tape's untagged short candidates are dropped together when an admissible list has
    exactly as many entries as the final kept list *without* them, and none has as many as the
    list *with* them.** Otherwise they are kept.
  - The protection runs on every tape, not only wholly untagged ones.
  - **Measured:** it drops 6 files in 3 shows (`ratdog-2007-08-12`,
    `belafleckandtheflecktones-2003-06-08`, `stevekimockband-2005-10-27`) and so keeps ratdog's
    19 `desc-position` titles, the library's one whole-tape D loss. Where the description lists
    the file it is kept: `darkstarorchestra-2015-07-11` gains 12 `desc-position` titles and
    clears a hold. The ruling's example rule ("on a wholly untagged tape, keep only when the list
    count includes it") drops 41 more interior files in 24 shows and protects nothing more.
  - **Whole-tape `setlist` (S) on wholly untagged tapes needs no protection:** piece 3's Q1
    means S never fills one. The one measured S loss is outside that scope and goes to section 7:
    `derektrucksband-2004-11-20`, a tape with two tags, loses 12 S titles because a 96 s untagged
    interior file is kept, and becomes a hold.
- **Where it runs.** The protection needs the description, so it runs in `gather.title_inputs`,
  for the selected recording only:
  - `title_inputs` reads both list counts before filtering;
  - it calls `filter_files` as today;
  - when the condition holds, it calls `filter_files` again with a keyword
    (`keep_untagged_short=False`) and re-applies the operator exclusion. Play order is then
    derived over the final set, never spliced.
  - The same keyword is passed to the lossless-format filter that `_recover_format_titles` runs
    for that recording, so the stem bijection compares like with like.
  - Every other `filter_files` caller uses the default: siblings, `select_recording`,
    `best_donor`, corroboration.

### 2.5 Where the rule lives and what it records

- **`junk._keep_and_exclude` applies 2.2-2.4** (minus the protection). The deny test is a small
  pure function, `junk.short_tag_is_junk(tag) -> bool`, beside the arm. A file the rule drops
  keeps the reason `implausibly short`, so `show --tracks`, triage `[i]` and
  `fix --include` read it exactly as today.
- **`filter_files` returns the names the rule kept** as `ordering["short_kept"]` (sorted), like
  `readmitted`.
- **Gather stamps `Track.short_kept: bool = False`.** It is persisted in `show.json`, permissive
  and absent on old dirs, and not in the manifest, the same treatment as `Track.included`.
- **Kept files are ordinary kept files for every recording-level vote** (AUTHOR'S CALL, and what
  the replay measured): `recovery_basis`, `tag_gate_basis`, `title_fraction` and siblings.
  `overrides.include`'s reduced standing stays for operator re-admissions only. The rule is a
  filter verdict about the file, not one operator's file deciding for the tape.

## 3. Coverage (ruling 5)

`structure._songish_coverage` already leaves out every `is_filler` title (`tuning`, `crowd`,
`banter`, `intro`, `outro`, `applause`, `announce`, `talk`, `encore break`, `soundcheck`,
...), which covers most spoken re-admissions. The new clause goes in the **same comprehension**,
`and not t.short_kept`, so a re-admitted `Jam >`, `Murph` or unresolved untagged file neither
counts against nor for coverage. No second filter is added.

`matched` is still measured on those tracks (it is independent evidence) and still shows in the
match column.

Measured: it removes 43 of the 46 added holds whose only flag would be
`low-confidence structure alignment`.

## 4. Positional overrides re-keyed by filename (ruling 6; STRICT)

Three `Overrides` fields are keyed by track number:
- `titles` (track -> title);
- `set_breaks` (tracks a break falls after);
- `encore_after`.

`exclude` and `include` are already filenames, and `venue`/`city`/`date`/`narration` are not
positional. No other persisted artifact is keyed by track number: the manifest, briefing and
`excluded_files` are regenerated or filename-keyed.

An inserted track re-points all three silently. On the final rule's replay without re-keying:
- 204 shows have a positional key at or after an insertion;
- **138 put an override title on a different file**, 46 of them with no flag at all.

The fix is to store the keys by filename (AUTHOR'S CALL between the ruling's two options). This
also closes the same hazard for every future `--exclude`/`--include`, which renumber tracks
today.

### 4.1 Storage and the guard

- **Fields.** `overrides.json` gains `titles_by_file: {filename: title}`,
  `breaks_after: [filename]` and `encore_after_file: filename`. The legacy
  `titles`/`set_breaks`/`encore_after` stay in the model, so an old file still parses. Names are
  the plan's call.
- **What gather does with the keys.** It resolves the filename keys **once**, against the final
  kept list (after `include` and `exclude`), into the positional values the cascade and the
  structure override already consume. Everything downstream is unchanged. A key naming a file
  not in the final kept list raises `LlamaError` naming the key and the file. It is a per-show
  failure, never a guess, and `fix`'s unit rolls an edit back on it.
- **The legacy guard.** Gather refuses a show whose `overrides.json` still has a non-empty legacy
  key. It raises `LlamaError: overrides.json uses track-number keys; run scripts/rekey_overrides.py`,
  naming the show.
  - So no gather under the new code can ever apply a stale number.
  - The positions in a legacy file therefore always refer to the on-disk `show.json` written by
    the old code, which is what the migration reads.
  - `fix` and triage refuse the same way before any prompt.

### 4.2 Who reads and writes them after the change

- **Writers** keep taking and showing track numbers: `fix --set-title N=`, `--clear-title N`,
  `--set-breaks`, `--clear-set-breaks`, `--set-encore`, `--clear-encore`, `--suggest-titles`,
  `--untitled`, and triage's `[t]`/`[u]` and edit prompts. Each translates number to filename
  through `show.json`, as `_resolve_exclude_tokens` does for `--exclude N`.
  - With no `show.json` these flags now refuse and name `llama redo <show> --from gather`.
    `--set-venue`/`--set-city`/`--set-date` and filename `--exclude` still work.
  - Before writing, every positional translation applies the staleness guard `--suggest-titles`
    already has (C1): the filename list `show.json` holds must equal what the current metadata
    and overrides keep. Otherwise it refuses.
  - `--untitled`'s `Untitled (track N)` text keeps the number it was written with.
- **Readers** go through gather's one resolver: gather itself (`title_cascade`,
  `_without_override_positions`, slice C, the 2b demotion guard, the structure override and its
  validation), and so `reapply` and `replay`. `scripts/replay_holds.py`'s
  `--strip-title-overrides`/`--strip-structure-overrides` strip the new keys; `taper_probe.py`
  and `title_hygiene_probe.py` read them.
- **Display.** `llama show` prints the stored mapping. Triage's current-values line converts
  filenames to today's track numbers through `show.json`.

### 4.3 The migration: `scripts/rekey_overrides.py [--apply] [--undo]`

A one-off in the style of `backfill_voiced_by.py`: a dry run unless `--apply`. It never gathers.

- **When.** Once, after the new code is installed and before the first gather under it. The
  guard in 4.1 enforces the order.
- **Per show** with a non-empty legacy key, under the show lock (`locks.file_lock(ws.lock)`):
  1. **Read `show.json`. Refuse the show** (write nothing, print `refused: <slug>: <reason>`)
     when any of these holds:
     - `show.json` is missing;
     - a `titles` key is outside `1..len(tracks)`;
     - the track at a `titles` key is not `title_source == "override"` with exactly the forced
       title;
     - `show.json`'s `set_breaks` is not exactly `sorted(set_breaks ∪ {encore_after})`;
     - a track filename repeats.

     These checks prove the stored positions and the stored `show.json` agree. Anything else is
     ambiguous, and an ambiguous show is never guessed.
  2. **Map** each position to `tracks[N-1].filename`.
  3. **Back up, then write.** Copy `overrides.json` to `overrides.pre-rekey.json`, only if no
     backup exists. Then atomically write `overrides.json` (`write_artifact`) with the legacy
     keys removed and the filename keys added. Every other field round-trips unchanged.
- **Output.** One line per show (`rekeyed: <slug> (T titles, B breaks, encore)` or `refused`),
  and a summary. It exits 1 if anything was refused.
- **Undo.** `--undo --apply` restores `overrides.pre-rekey.json` over `overrides.json` only
  when the current file is byte-identical to what the migration writes from that backup. That
  output is deterministic. If not, an operator edit came after the migration: the show is
  refused and named, never silently reverted. Undo needs the old code to be useful, since the
  new gather refuses legacy keys.
- **Measured today:** 606 shows carry legacy keys (3,203 titles, 427 breaks, 365 encore keys).
  **All 606 pass every check, so 0 would be refused.** The re-key simulated over the whole replay
  mapped every key, and its arm has **0** override titles on a different file.

## 5. Applying it (ruling 8; what piece 4 needs from the bulk apply)

The bulk apply of pieces 1-5 is planned separately. Piece 4 needs four things from it.

1. **Order.** The migration (4.3) runs first. The replay harness applies the same re-key to its
   scratch copy when it meets legacy keys, so a candidate arm measures the migrated state without
   writing the library.
2. **The list.** Of the 1,534 shows the rule changes, by derived state:

   | state | changes | of which music restored |
   |---|---|---|
   | delivered, unvoiced | 1,026 | 392 |
   | voiced | 65 | 37 |
   | packaged | 311 | 65 |
   | held | 122 | 45 |
   | briefed | 10 | 1 |

   - **Held shows.** `llama reapply` covers them.
   - **Packaged and delivered shows.** They need the same computation: gather from the cache,
     the stored vet extraction, the stored briefing when reusable. `reapply` refuses non-held
     shows. `llama redo <show> --from gather` works per show but spends a vet extraction and a
     brief on each.
   - **Piece 4's ask.** Extend reapply's path to packaged and delivered shows, and change
     `replay.briefing_reusable` to compare the broadcast fields over the tracks that are not
     `short_kept`, matched by filename (AUTHOR'S CALL). Measured:
     - **1,377 of 1,533 changed shows keep their briefing; 156 need a fresh brief.**
     - With today's rule all 1,533 need one, because any inserted track changes `titles`.
   - **Download cost.** A delivered show's library audio was purged at delivery, so re-packaging
     it re-downloads the whole show. The bulk apply has to size that.
3. **Re-delivery.**
   - Delivered unvoiced shows are re-delivered, minor fixes included.
   - The **37 voiced shows where the rule restores music** are approved for
     `deliver --replace-voiced` and a fresh `emcee run`. These are exactly the 37 in
     `voiced-severe-review.md`; the final rule changes none of them.
   - The **voiced shows whose gain is minor** (spoken, crowd or untagged only) are **not
     re-delivered**. They go on the re-voice-later list. Under the final rule there are 28,
     because 3 of census2's 31 gain only crowd files that now drop:
     `voiced-minor-final.json`.
   - A minor show may be re-gathered in the library. Its station copy is left alone.
4. **Holds the operator will see** (section 6 (b)): about 32 new holds, against 20 cleared.

## 6. Acceptance

**(a) Arms.**
- Base arm: `scripts/replay_holds.py run --all` at `e37f670`.
- Candidate arm: the branch, with the scratch re-key.
- `compare` must pass its gates.
- The R' harness under `~/.llama-harness/piece45/spec/` is the reference: the candidate arm must
  reproduce its counts, or explain each difference:
  - 1,534 shows changed, 2,643 files added;
  - 20 holds cleared, 32 added.

**(b) Holds added, each class justified.** The replay's 32 adds:

| class | shows | why it is right or accepted |
|---|---|---|
| new unresolved track | 17 | An untagged or placeholder-tagged short file is kept (rulings 3-4) and ships `unresolved`. A hold by design: the operator names it or excludes it. |
| long single-set show crosses 150 min | 6 | Restored audio is real runtime. The existing long-show check fires correctly. |
| positional rung lost (1 track) | 3 | A kept tagged file changes the count, so one `setlist`-filled track (`Instrumental`, `FF`, `7-11`) reverts to `unresolved`. It holds rather than shipping a shifted title. |
| low confidence remains | 3 | A re-admitted piece consumes a canonical item another track matched (`The Overture (end)`, STS9 `Murph`). Flagged, not silent. |
| jerrybase closer not at a break | 2 | Spoken audio (`Donor Rap`, `bobby speaks`) now sits between the closer and the break. An accepted false hold; teaching the closer check about trailing spoken tracks is out of scope. |
| other | 1 | `robertwalters20thcongress-2004-01-02`, already held. |

Any class outside this table, or any class more than 25% larger, blocks the merge until the
operator rules on it. Each cleared show is listed for the operator, as in pieces 1-3.

**(c) Sonnet hand-check of the rule's decisions.**
- **The sample.** A stratified sample of about 60 files from the candidate arm, in the existing
  packet format (`r-INSTRUCTIONS.md`, with the rulings written into the direction):
  - kept: music 10, fragment 5, spoken 10, mixed-with-tuning 6, untagged interior 8,
    placeholder-tagged 3;
  - dropped: junk 8, non-performance 5, untagged edge 3, protection and filename drops 2.
- **The bar:**
  - **zero kept spam or non-performance**;
  - **zero dropped music**;
  - at least 90% right overall;
  - every wrong row in a class the operator has accepted (below) or fixed before merge.
- **Reference.** census2's 41-row packet, re-scored under the rulings and the final rule: 38
  right. The 3 misses are inclusions: `Silent Track` (untagged interior,
  `littlefeat-1973-01-01`), `crowd/tuning jam` (kept by ruling 3) and a crowd call-back tagged
  `Callin um back`.

**(d) Zero silent override mis-titles.** On the candidate arm, every track whose base
`title_source` is `override` keeps the same title on the same file in every show, with or
without flags. Measured: 0 shows.

**(e) The count-match protection is measured.** The candidate arm reports which shows the
protection dropped files on (expected: the 3 in 2.4) and every show that gains or loses
`desc-position` or `setlist` titles. Expected:
- 1 S loss (`derektrucksband-2004-11-20`, accepted below) plus 1-track reversions;
- no `desc-position` loss.

**(f) Tests.** Unit tests cover `short_tag_is_junk` on every example named in 2.3 (both sides),
interior/edge, filename junk, both conditions of the protection, `short_kept` in
`_songish_coverage`, the resolver's refusal on an unkept key, the legacy guard, and the
migration's refusals, backup and undo against fixture show dirs. A mutation check on the deny anchoring (per part, not anywhere) and on the protection's "and none
matches with them" clause must each turn a named test red.

## 7. Out of scope and accepted limitations

- **The convention-arm class (4-conv; ruling 7): out of scope.** The census sized it at 13 shows
  and 90 files, with 51 already operator-included. No narrow, clearly-correct rule exists in the
  data:
  - the class contains the canonical spam file itself (`gratefuldead-1973-06-10`,
    `FOLLOW-ME @BYPIKENO.mp3`, tagged `Morning Dew`, 678 s);
  - an opening act's set (`karldensonstinyuniverse-2011-10-28`, `openerAndersOsborne…`);
  - a disc whose filenames carry a different date (`waynehancock-2004-04-08`, `…2004-08-04d2-…`);
  - a second-show block (`soulive-2009-04-16`, `nh2009-…`).

  These stay with `fix --include` and the adjudicator.
- **Also out of scope:** long spoken tracks (kept today, unchanged); 5a partial tapes (dropped);
  5b better sibling (adjudicator); 5c shifted tags (adjudicator and list).
- **Accepted limitations:**
  - `derektrucksband-2004-11-20` loses 12 S titles to a kept untagged interior file and holds.
  - About 6 files are kept with metadata length under 5 s (three read 0 s, e.g.
    `Promised Land \>`).
  - A few inclusion errors the rule cannot see: `Silent Track` named only in the description,
    tuning-dominant mixes such as `crowd/tuning jam`, and the ~15-25% of the census's "music"
    kind that is a titled spoken bit (`"really hot show"`, `Let Phil Sing Rant`).
  - The closer flag on filler after a closer (2 shows).
  - Future gets may select a different recording: 25 of 2,263 multi-recording shows re-score
    differently under the rule. Existing shows keep `selection.json`.

## 8. Unverified premises, each with its cheapest test

1. **The candidate arm reproduces the R' harness.** The harness patched `_keep_and_exclude` and
   `_songish_coverage` in-process, not the shipped code.
   - Test: the branch's arm against `~/.llama-harness/piece45/spec/arm_final.jsonl`, per show.
2. **Sonnet's hand-check agrees with the operator.** The reference packet was scored before
   rulings 2-4 changed the direction.
   - Test: the operator checks the first 10 rows of the new packet against Sonnet's answers
     before the bar is applied.
3. **The deny vocabulary covers future tags.** It was fitted to the library's 3,547 drops.
   - Test: run `short_tag_is_junk` over the short drops of the 9,844 cached sibling items (the
     census dump has them) and list every kept tag containing a junk word, for one look.
4. **The briefing-reuse rule is safe.** A stored briefing never claims the absence of a piece
   the rule restores.
   - Test: `briefing_guard` over the 1,377 reused briefings in the candidate arm (already part
     of `briefing_reusable`), plus 10 of the 37 voiced-severe briefings read by hand.
5. **No other positional key exists** (titles, set_breaks and encore_after are all of them).
   - Test: `grep` every reader of `Overrides` and of `Track.index` in `llama`, `scripts` and
     `emcee` (emcee reads only the manifest).
6. **The re-download cost is affordable.** About 1,100 delivered shows would re-download in full.
   - Test: sum the manifest audio sizes for the delivered rows of the list before the bulk apply
     plan sizes its waves.
