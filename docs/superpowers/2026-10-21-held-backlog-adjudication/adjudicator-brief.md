# Held-show adjudication — exploratory pass (read-only)

You are helping design an automated "judge" for llama, a tool that builds radio-ready packages of
Live Music Archive (archive.org) concert recordings. Shows that look suspicious are HELD for human
review. You are looking at held shows whose hold includes a flag raised by checking llama's web
**research** against the show data:

- `research asserts N sets but structure has M` — research says the show had N sets; llama's track
  list has M numbered sets (an encore does not count as a set).
- `research asserts unknown song: X` — research names a song llama's setlist doesn't have.
- `research asserts wrong date: D` — research names a date that isn't the show's date.

Your job, per show: decide what is actually true, the way the operator would — **he first reads the
archive.org item (description, notes, track list), then the sibling recordings of the same
performance**, then whatever else is specific. Each show's evidence is pre-assembled in one bundle
file: `~/.llama-harness/t3/bundles/<slug>.md` (flags, what llama would ship, track table, research,
claims extracted from it, jerrybase/setlist.fm data if any, the selected item's metadata and audio file
list, and up to 8 siblings' metadata). Work from the bundle. You may also read files under
`~/.llama/shows/<slug>/` and `~/.llama/cache/md_<identifier>.json` if the bundle truncated something.
**Do not use the web**, and do not run any `llama` command or write anywhere except the verdict file.
If the web would have been needed to decide, say so in the verdict — that is a design finding.

## The operator's standing rulings (binding)

- **Tape notes are presumed correct unless there is clear contrary evidence.** He would rather repeat a
  taper's error than mis-correct it. The taper's own wording ships ("J" ships as written; "Untitled #12"
  is a real title).
- Venue: the archive string ships; a same-city spelling/name variant is not an error.
- Discs are not sets in general — but a disc split that coincides with an independently-sourced set
  break is strong evidence.
- Research is an LLM's web summary. It can be right (it found a real setlist article), wrong (another
  night, another band, a reviewer's faulty memory), or the flag can be spurious (the extraction
  misread the research, the "unknown song" is just a spelling/alias of a song that IS on the tape, a
  tease, a song mentioned for context such as "they'd debuted X the night before").

## Possible actions (what a fix would look like)

`llama fix <slug>` flags: `--set-breaks N[,N...]` (track numbers a set break falls AFTER; numbered sets
only), `--set-encore N` (every track after N is the encore; must exceed every set break; on a multi-set
show combine with `--set-breaks` or every set flattens into "1"; any structure override loses segue
marks), `--set-date YYYY-MM-DD`, `--set-venue`, `--set-city`, `--set-title N="..."`,
`--exclude N|FILE`, `--include FILE`, `--narration vague` (briefing names no songs and asserts no set
structure), `--overrule` (ship as-is, clears the hold without changing anything).
Or: leave it held (needs a human, or the show is genuinely broken/partial), or `llama rm` (not a usable
show at all).

## For each show, write `~/.llama-harness/t3/verdicts/<slug>.json`

```json
{
  "slug": "...",
  "claims": [
    {"flag": "<exact flag text>",
     "verdict": "research-wrong | research-right-show-wrong | flag-spurious | undecidable",
     "why": "one or two sentences",
     "decisive_evidence": [{"source": "selected-description | selected-files | sibling:<identifier> | setlist.fm | jerrybase | research-cited-source | track-durations | other", "quote": "short verbatim quote"}],
     "confidence": "high | medium | low"}
  ],
  "other_flags": [{"flag": "...", "assessment": "one sentence: real problem / spurious / what fixes it"}],
  "action": {"kind": "overrule | fix | hold | rm | narration-vague",
             "commands": ["llama fix <slug> ..."],
             "rationale": "why this action ships a correct show (or why it can't)"},
  "show_correct_after_action": "yes | no | unsure",
  "needed_beyond_bundle": "nothing | what you'd have needed (web page, audio listen, etc.)",
  "root_causes": ["one or more tags from the list below"],
  "design_notes": "what kind of case this is; what evidence decided it; could a deterministic rule have decided it; anything surprising about llama's output (wrong titles, wrong order, partial tape, wrong show)"
}
```

`root_causes` tags (use as many as apply; add `other:<short-name>` for anything new):
`research-wrong` (the research itself is mistaken: other night, disc counted as set, reviewer memory),
`spurious-tease-or-footnote`, `spurious-alias-or-spelling`, `spurious-context-mention` (song/date named
as context, e.g. debuted the night before, broadcast date), `spurious-past-midnight-or-adjacent-date`,
`spurious-suite-movement` (movement of a suite track), `flags-echo-untitled-tape` (unknown-song flags
only because llama's titles are unresolved/placeholders), `set-source-precedence` (taper's explicit
set/encore headers lost to setlist.fm or alignment), `jerrybase-anchoring-wrong`, `partial-tape`,
`wrong-content-on-tape` (another act, another night), `placeholder-titles-shipped` (e.g. "Track NN",
"tmp" shipped as titles), `same-item-other-format-has-titles`, `description-positional-titles`
(taper's description lists titles in order, count-exact), `shifted-or-scrambled-tags`,
`junk-filter-dropped-real-music` (a real short segment/segue dropped as "implausibly short"),
`selection-should-prefer-sibling` (another recording of the same show would ship correctly),
`titles-from-reviews-only`, `matcher-bug` (e.g. curly apostrophe).

What the pilot already learned (keep doing this):
- The bundle now also lists **files llama dropped** (with reasons and durations) and **archive.org
  reviews** for the selected item and siblings. Check dropped files against the description: a short
  file with a segue/tease tag inside continuous music is usually real.
- `--include`/`--exclude` renumber tracks: put them in their own first command, and give later
  commands in the post-renumbering track numbers (say so in the rationale).
- Held-at-vet shows have no briefing yet; after a fix or overrule, brief runs and its own guard can
  still hold. If you expect research flags to re-appear after a redo (taper shorthand like "SOTM" won't
  string-match), add a final `llama fix <slug> --overrule` and mark it conditional in the rationale.
- Durations are evidence: compare against siblings' file lengths and taper timestamp notes to detect
  shifted or scrambled tags, which llama currently never flags.

Judge the WHOLE show, not only the research flag: if fixing the research claim would still ship a show
with wrong titles, a wrong set structure, or a partial tape, the action must say so. Be concrete:
commands should be runnable as written, with the track numbers from the bundle's track table.
Prefer `undecidable` + `hold` over a guess. Wrong confident verdicts are the expensive failure here,
since these become fixes applied to shows that air.

When all your shows are done, reply with a compact table: slug | each claim's verdict | action |
confidence | one-line design note. The files are the durable copy; the reply is the summary.
