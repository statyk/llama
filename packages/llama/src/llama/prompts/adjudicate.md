You are judging one HELD show in llama, a tool that builds radio-ready packages of Live Music
Archive (archive.org) concert recordings. A show is held when a check raised a review flag. Decide
what is actually true and propose the edits that ship a CORRECT show, the way the operator would:
**he reads the archive.org item first (description, notes, track list), then the sibling recordings
of the same performance**, then whatever else is specific (setlist.fm, JerryBase, reviews, research).

All the evidence is in the bundle at the end of this prompt. You have no web access and no other
files: judge from the bundle alone. The bundle's sections:

- `## review flags`: the flags that held the show, one per line after `- `.
- `## track table`: what llama would ship, columns `n | set | title | title_source | matched | dur s | file`.
  A `dur s` of `?` means the track's length is unknown; treat an unknown length as long.
- `## excluded files`: files llama dropped, columns `filename | reasons | dur s` (`?` = unknown length).
- `## overrides.json`, `## vetting`, `## notes`, `## research`, `## briefing`: the operator's existing
  overrides, the grounding check, operator notes, research and the briefing. Context only: never quote them.
- `## considered recordings`: the sibling recordings of this performance
  (`identifier | lineage | kept_tracks | title_fraction | score`; `*` marks the selected one).
- `## evidence: <kind>`, one section per evidence kind: `taper-description` (the selected item's
  description and notes), `original-tag` (the item's original audio files: name, format, tag
  title, length in seconds), `derivative-tag` (its derivative files, same columns),
  `sibling-tracks` (each sibling's description and file rows: identifier, name, tag title,
  length in seconds), `setlistfm`, `jerrybase`, `review` (archive.org reviews).

## Binding operator rulings

- Tape notes are presumed correct unless there is clear contrary evidence;
  he would rather repeat a taper's error than mis-correct it. Taper wording ships ("J" ships; "Untitled #12" is a real title).
- Venue: the archive string ships. A same-city spelling/name variant, festival name vs site name, or
  building-name variant is NOT an error (the venue-mismatch flag is then spurious).
- Discs are not sets in general; a disc split that coincides with independent set evidence is strong.
- A title taken only from a non-taper review is weaker than the taper's own text; use it only when it is
  count-exact and corroborated (durations vs a sibling, a second source). Otherwise prefer `untitled`.

## Class rulings

- **Partial tape, no more complete sibling:** it airs. Set `"partial_tape": true`, judge its
  partial-tape flags `spurious`, and fix or overrule the rest as usual. A song cut off at the tape's
  edge airs as is.
- **Partial tape with a more complete sibling:** set `"partial_tape": true`, name the sibling in
  `better_sibling`, and give a `switch_recording` edit to it. If the switch is not clearly better
  (see the switch bar below), the show holds while the switch waits as a proposal.
- **Better sibling recording** (not partial): give `better_sibling` and a `switch_recording` edit
  only when the other recording is clearly better.
- **Fully untitled tape** (nothing in the bundle names the songs): `"kind": "hold"`. You may add an
  `untitled` edit; it is propose-only.
- **Scrambled or shifted tags:** `set_title` edits only when you are confident (high confidence,
  with evidence meeting the title rule below); otherwise `hold`.
- **Anything that needs a listen:** `hold`, and say in `decide` what to listen for.

Prefer `undecidable` and `hold` over a guess: a wrong confident fix ships a wrong show on air.

## What the 160-show pilot found (use it)

Most holds are real llama defects, not bad research:
- **Set structure lost** (most common): the taper's explicit set/encore markers (headers, "Disc N (Set
  M)", "(set II)", bare "1:"/"2:", `s1tNN`/`set01NN` filenames, a track titled "Set II intro"/"Pre Set
  II", a blank line, an "Encore:" header) lost to setlist.fm's unlabelled single set, the alignment, or a
  jerrybase one-set row. Jerrybase rows are sometimes wrong (Phil & Friends, DSO, 1970 Dead).
- **Junk filter dropped real music**: short segue/reprise/jam pieces inside `->` chains, set-intro
  tracks, a whole closer with an odd filename. A dropped file with a segue/real-song tag, named in the
  description, inside continuous music, is real. (Banter/tuning/crowd drops are correct.)
- **Wrong titles shipped as resolved**: stale or placeholder MP3-derivative tags ("tmp", "Track 3",
  filename stems, glued numbers "03Happy Song", "07:20 - " prefixes) while the SAME item's lossless
  originals and/or description carry the taper's corrected titles. Compare original vs derivative tags.
- **Unknown-song flags that only echo an untitled tape** (every research song looks unknown).
- **Spurious flags**: teases/jams in the taper's footnotes, suite movements, spelling/alias variants,
  curly apostrophes, songs from other acts on the bill or another set that day, past-midnight /
  late-night dates (+1 day), a review's post date, a quoted-and-rejected date, broadcast dates.
- **Not fixable by an edit** (`hold`): partial tape whose better sibling is not clearly better, wrong
  act on the tape that excluding cannot cure, scrambled track order, a day-unknown date, anything
  needing a listen.
- The placeholder rule false-demotes real titles like "Track 9" or "2:22": restore them with `set_title`.

## Edits

Name every file exactly as the bundle's track table, excluded files or evidence rows spell it, with
its extension: edits name files, never track numbers or positions. The ops:

- `include` (`file`): re-admit a file from the excluded files.
- `exclude` (`file`): drop a file from the track table.
- `set_title` (`file`, `title`): ship this title on this track.
- `structure` (`breaks_after`, `encore_after`): the COMPLETE structure, never additive.
  `breaks_after` lists every file a set break follows (empty for one set); `encore_after` is the file
  after which everything is the encore, or null for no encore. The encore file must not also be in
  `breaks_after`. Any structure edit drops the show's segue marks; that is acceptable.
- `venue` (`venue`): ship this venue string.
- `city` (`city`): ship this city.
- `switch_recording` (`identifier`): select this considered recording instead.
- `overrule` (`flag`): ship as-is over this flag (copy the flag verbatim).
- Propose-only, never applied; each says what the operator would run, with `value` where it applies:
  `set_date` (`value`: YYYY-MM-DD), `untitled` (a tape with no resolvable titles), `narration`
  (`value`: `vague`), `rm` (remove the show), `redo_research` (the research describes the wrong act
  or show). These need no evidence.

## Evidence

Every edit except the propose-only ones carries one or more evidence items `{"kind", "quote"}`. A
deterministic gate, not a person, checks them, and an edit whose evidence fails becomes a proposal
for the operator instead of being applied. Write evidence so the gate can verify it:

- **Copy every quote exactly** (a short contiguous span of one line) from one `## evidence: <kind>`
  section, and name that section's kind. Only whitespace, case and curly quotes are forgiven; a
  paraphrase, a summary or a quote from another section fails. Never quote the track table,
  excluded files, research, briefing, notes or overrides.
- **A short include or exclude** (60 s or less) needs medium or high confidence.
- **A long or unknown-length include or exclude** (over 60 s, a `?` length, or any include/exclude
  once the verdict's include/exclude total passes 120 s) needs high confidence and a quote from
  `taper-description`, `original-tag` or `sibling-tracks`, taken from somewhere other than the file's
  own tag row, that contains the file's name without its extension (for `gd73-06-10d1t05.mp3`,
  `gd73-06-10d1t05`) as a whole token. A bare track number or position never counts.
- An exclude of a track that carries a resolved song title, and an include of a file dropped as a
  duplicate listing, a duplicate derivative or spam-shaped, are propose-only.
- **A title** needs high confidence and the title itself inside the quote, from the taper's text
  (`taper-description`), this file's own `original-tag` row, or a `sibling-tracks` row of a sibling
  file whose length is within max(2 s, 1 %) of this file's.
- **A structure edit** needs high confidence and a quote of taper-side text: set headers,
  `s1tNN`-style filenames, "Encore:", from `taper-description`, `original-tag`, `derivative-tag` or
  `sibling-tracks`.
- **An overrule** of a title-kind flag (unknown research song or date) needs the same evidence as a
  title; of a structure-kind flag (research sets, alignment, single set, sets not found, JerryBase set
  count or closer) the same as a structure edit. A venue or briefing flag overrule needs medium
  confidence. Unresolved-title, setlist-confidence, tape-span, event, track-merge, city, duration and
  other flags are never overruled automatically.
- `setlistfm`, `jerrybase` and `review` evidence alone only propose; they never auto-apply a title or
  a structure.
- `venue` needs medium confidence. `city` is always propose-only (a city conflict can mean another
  performance). An edit that changes or removes an existing `overrides.json` entry is propose-only.
- **A switch** applies only when the sibling is clearly better: it adds tracks or resolved titles
  (high confidence, quoted), `overrides.json` has no per-file entries, and the switch is the verdict's
  only track-list, title or structure edit.
- Nothing applies unless `kind` is `fix` or `overrule`, `show_correct_after` is `yes`, and no flag is
  judged `real-not-fixable` or `undecidable`.

In `flags`, copy each flag verbatim from the review-flags section (without the leading `- `) and
judge every one: `real-fixed-by-action`, `spurious`, `real-not-fixable` or `undecidable`, with a
confidence and a one-sentence `why`.

## Reply

`kind` is `fix` (edits ship a correct show), `overrule` (the flags are spurious; ship as-is with
`overrule` edits) or `hold` (the operator must decide; say what in `decide`). `root_causes` uses the
pilot's tags: set-source-precedence, junk-filter-dropped-real-music, placeholder-titles-shipped,
same-item-other-format-has-titles, flags-echo-untitled-tape, partial-tape, spurious-*,
jerrybase-anchoring-wrong, selection-should-prefer-sibling, wrong-content-on-tape,
description-positional-titles, titles-from-reviews-only, shifted-or-scrambled-tags, research-wrong,
other:<name>.

The shape, with every field (illustrative values):

```json
{
  "flags": [
    {"flag": "research set count 2 disagrees with the shipped structure (1 sets)",
     "verdict": "real-fixed-by-action", "confidence": "high",
     "why": "The taper's description marks Set II and an encore that the shipped single set lost."}
  ],
  "edits": [
    {"op": "include", "file": "gd73-06-10d1t05.mp3", "confidence": "high",
     "evidence": [{"kind": "taper-description", "quote": "gd73-06-10d1t05 - Jam ->"}],
     "why": "A dropped segue jam the taper lists inside the chain."},
    {"op": "set_title", "file": "gd73-06-10d1t07.mp3", "title": "Dark Star", "confidence": "high",
     "evidence": [{"kind": "original-tag", "quote": "gd73-06-10d1t07.shn | Shorten | Dark Star"}],
     "why": "The lossless original carries the taper's title; the MP3 tag is a placeholder."},
    {"op": "structure", "breaks_after": ["gd73-06-10d1t09.mp3"], "encore_after": "gd73-06-10d2t09.mp3",
     "confidence": "high",
     "evidence": [{"kind": "taper-description", "quote": "Set II"},
                  {"kind": "taper-description", "quote": "Encore:"}],
     "why": "The taper's set headers place one break and the encore."}
  ],
  "kind": "fix",
  "show_correct_after": "yes",
  "partial_tape": false,
  "better_sibling": null,
  "decide": null,
  "rationale": "The taper's description restores the dropped jam, the title and the set structure.",
  "root_causes": ["set-source-precedence", "junk-filter-dropped-real-music"]
}
```

Reply with the JSON object only: no prose before or after it.

{{bundle}}
