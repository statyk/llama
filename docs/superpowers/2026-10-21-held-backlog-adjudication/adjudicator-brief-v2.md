# Held-show adjudication: full backlog pass (read-only)

You are judging HELD shows in llama, a tool that builds radio-ready packages of Live Music Archive
(archive.org) concert recordings. A show is held when a check raised a review flag. Your job, per show:
decide what is actually true and propose the action that ships a CORRECT show, the way the operator
would: **he reads the archive.org item first (description, notes, track list), then the sibling
recordings of the same performance**, then whatever else is specific.

Each show's evidence is pre-assembled in `~/.llama-harness/t3/bundles/<slug>.md`: its flags, what
llama would ship (track table: n | set | title | title_source | matched | dur s | file), files llama
dropped and why, research + the claims extracted from it, jerrybase / setlist.fm data, the selected
item's metadata, original AND derivative audio file lists with tags and lengths, archive.org reviews,
and up to 8 siblings' metadata. You may also read `~/.llama/shows/<slug>/*` and
`~/.llama/cache/md_<identifier>.json`. **No web. Run no `llama` command. Write only your verdict files.**

## Binding operator rulings

- Tape notes are presumed correct unless there is clear contrary evidence; he would rather repeat a
  taper's error than mis-correct it. Taper wording ships ("J" ships; "Untitled #12" is a real title).
- Venue: the archive string ships. A same-city spelling/name variant, festival name vs site name, or
  building-name variant is NOT an error (the venue-mismatch flag is then spurious).
- Discs are not sets in general; a disc split that coincides with independent set evidence is strong.
- A title taken only from a non-taper review is weaker than the taper's own text; use it only when it is
  count-exact and corroborated (durations vs a sibling, a second source). Otherwise prefer `untitled`.
- Partial tapes: say so; whether to air one is the operator's call (action `hold`).

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
- **Not fixable by `fix`** (action `hold`): partial tape (a better sibling exists or not), wrong act on
  the tape that excluding cannot cure, scrambled track order, a day-unknown date, anything needing a
  listen.
- Placeholder rule (2b) false-demotes real titles like "Track 9" or "2:22": restore with `--set-title`.

## Actions

`llama fix <slug>` flags: `--include FILE` (re-admit a dropped file), `--exclude N|FILE`,
`--set-breaks N[,N]` (break AFTER track N; numbered sets only), `--set-encore N` (everything after N is
the encore; must exceed every break and must NOT also appear in `--set-breaks` (encore 20 with breaks 10 = two sets + encore; `--set-breaks 10,20 --set-encore 20` is REFUSED and leaves the show broken); on multi-set shows ALWAYS combine with `--set-breaks`; any structure
override drops segue marks, acceptable), `--set-title N="..."`, `--set-venue`, `--set-city`,
`--set-date YYYY-MM-DD`, `--overrule` (ship as-is), `--untitled` (tape with no resolvable titles; must be
alone in its command). `llama redo <slug> --from research` (only when the research describes the wrong
act/show). Kinds: `overrule | fix | hold | rm | untitled | narration-vague`.

**Steps and renumbering.** `--include`/`--exclude` renumber tracks. Put them in their own FIRST step.
Every later step's track numbers are post-renumbering, and each later step carries `expect`: the
tracks it touches (or the track just before each break) with the filename suffix that must be at that
position when it runs. The applier checks `expect` against the re-gathered show and refuses on mismatch.
After an include/exclude step the redo re-derives structure and titles; a later step that turns out
unnecessary is harmless if `expect` still holds.

## Verdict file: `~/.llama-harness/t3/verdicts/<slug>.json`

```json
{
  "slug": "...",
  "flags": [
    {"flag": "<exact flag text from the bundle>",
     "verdict": "real-fixed-by-action | spurious | real-not-fixable | undecidable",
     "why": "one sentence",
     "confidence": "high | medium | low"}
  ],
  "action": {"kind": "overrule | fix | hold | rm | untitled | narration-vague",
             "steps": [
               {"cmd": "llama fix <slug> --include FILE.mp3", "expect": []},
               {"cmd": "llama fix <slug> --set-breaks 8 --set-encore 17",
                "expect": [{"track": 8, "file_endswith": "d1t09.mp3"}, {"track": 17, "file_endswith": "d2t09.mp3"}]}
             ],
             "overrule_if_reheld_on": ["exact flag texts you judged spurious that a redo will re-raise"],
             "rationale": "why this ships a correct show, or why it can't"},
  "show_correct_after_action": "yes | no | unsure",
  "evidence": "the decisive quotes, short",
  "root_causes": ["tags as in the pilot: set-source-precedence, junk-filter-dropped-real-music, placeholder-titles-shipped, same-item-other-format-has-titles, flags-echo-untitled-tape, partial-tape, spurious-*, jerrybase-anchoring-wrong, selection-should-prefer-sibling, wrong-content-on-tape, description-positional-titles, titles-from-reviews-only, shifted-or-scrambled-tags, research-wrong, other:<name>"],
  "needed_beyond_bundle": "nothing | listen | web | ..."
}
```

For `overrule`, steps = `[{"cmd": "llama fix <slug> --overrule", "expect": []}]`. For `hold`/`rm`, put
the command you would run if the operator agrees (or none) and say what he must decide.
Prefer `undecidable` + `hold` over a guess: a wrong confident fix ships a wrong show on air.

**When all your shows are written, reply with ONE line only:** `batch <n>: <k> verdicts written`.
No table, no summary. The files are the record.
