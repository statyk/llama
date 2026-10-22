# Tier 3 exploratory adjudication — synthesis (2026-10-21)

Sample: 160 of the 551 held shows carrying a research-claim flag (research asserts N sets / unknown
song / wrong date), stratified by flag family x only/mixed x still-held/needs-LLM; seed 20261021
(`tools/build_bundles.py`, `sample.json`, `batches.json`). 20 Opus agents, 8 shows each, brief
`adjudicator-brief.md`, bundles `bundles/`, verdicts `verdicts/<slug>.json` (24 pilot verdicts tagged
by the parent from the agents' reports: `root_causes_tagged_by`). Tally: `tools/tally.py`.
Cost: 20 agents moved the 5h meter ~8 -> ~14% (about 0.3-0.5 pt per agent).

## Headline

- Claims: 438 research-right-show-wrong, 401 spurious, 37 undecidable, **10 research-wrong**.
  Research being wrong is the ONLY cause in **3 of 160** shows. The research flags are a
  high-value tripwire for llama's own gather defects, most of which no other flag catches.
- Actions: fix 111, overrule 24, hold 20, rm 3, narration-vague 2. Correct after action: yes 125,
  unsure 22, no 13. Needed beyond the cached bundle: nothing 124, a listen 28, web 2, other 6.
- Ready now at high confidence: 80 fixes + 22 overrules (all "correct after: yes").

## Root causes (shows; normalized tags)

| n | cause | deterministic? |
|---|---|---|
| 55 | taper's explicit set/encore markers lost to setlist.fm / alignment / jerrybase / parser (headers, `Disc N (Set M)`, `(set II)`, bare `1:`, `s1tNN` filenames, `Set II intro` tracks, blank-line breaks) | mostly yes (marker parsing + precedence) |
| 32 | junk/format filter dropped real music: short segue-marked pieces inside `->` chains, reprises, intros that mark set breaks; also filename-case and format-label misses | yes (segue/description-named exemption arm; constants untouched) |
| 27 | unknown-song flags only echo an untitled/placeholder tape | yes (collapse into the unresolved hold) |
| 22 | placeholder titles shipped (`tmp`, `Track eight`, glued numbers, timestamps, filename stems, `01.` from bare numbered lines; LLM alignment "matched" them) | yes (2b gaps) |
| 20+19+16+4 | spurious: alias/spelling, context mention (other acts, other night, quoted rejected date, review post date), tease/footnote, suite movement | partly (tease footnotes, curly apostrophe, sibling-tag aliases) |
| 14 | yearless past-midnight/adjacent date — **bug confirmed**: `vet_research._date_flags` checks yearless dates by exact month/day only, never the +-1 day window | yes, small |
| 14 | partial tape, coverage 1.0, unflagged (known unmatched-items gap) | yes (unmatched canonical run at head/tail) |
| 13 | selection should prefer a sibling (complete / fully titled) | needs re-select capability |
| 13 | same item's lossless originals carry corrected titles; stale/placeholder MP3 derivative tags ship | yes (per-track original-vs-derivative disagreement) |
| 14 | titles only from reviews | judge + confirm |
| 10 | description positional titles, count-exact | yes-ish (count-forced) |
| 7 / 7 / 7 | shifted or scrambled tags (durations vs sibling) / other set or show grouped in / wrong act on tape (Cubensis opener, Rat Brigade) | judge |
| 6 | jerrybase anchoring removed a correct break (one-set rows for Phil, DSO, 1970 Dead) | yes (anchoring must not reduce below explicit headers) |
| 3 | venue string from a sibling while `venue_source: item` | yes, bug |

## Capabilities the fixes lack today

re-select a different recording; month-precision (day-unknown) date; reorder tracks; redo research
after an `--include/--exclude` that changes which act is on the tape; reading the item's `.txt`
info file (set splits live there sometimes).
