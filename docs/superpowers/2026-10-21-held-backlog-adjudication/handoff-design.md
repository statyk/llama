# Handoff: deterministic gather/vet fixes from the 2026-10-21 held-backlog adjudication

Start here in a NEW session. The adjudication/apply run itself is finishing in a separate session
(`~/.llama-harness/t3/OVERNIGHT.md` is its runbook). Shawn's decision (2026-10-21): build in two parts,
in this order:

1. **Deterministic fixes in llama gather/vet** (THIS handoff) -- stop the holds at source and fix the same
   defects in shows that already shipped unflagged. Spec -> spec-review -> plan -> SDD, measured with
   the replay harness exactly like Tier 1 (`scripts/replay_holds.py`, `llama reapply`).
2. **Later:** a `llama` adjudicator command (LLM judge for what rules can't settle), porting the
   prototype in `~/.llama-harness/t3/tools/` (bundle builder, brief, daemon with expect-checks,
   re-hold reviewer), with escalations landing in `llama triage` as one-keystroke proposals + `--yes`.

## Evidence base (all under `~/.llama-harness/t3/`)

- `verdicts/<slug>.json` -- 1,063 Opus verdicts (160-show pilot in v1 format, 903 in v2 format with
  `flags[]`, `action.steps[]` + `expect`, `root_causes[]`, `evidence`). Every held show as of 01:00.
- `bundles/<slug>.md` -- the evidence each verdict was judged from.
- `synthesis.md` -- pilot write-up; `bugs-found.md` -- llama bugs found during the run.
- `apply/daemon-ledger.jsonl` -- what was applied (packaged / escalate / reheld) and why.
- `escalations.md` -- the morning report (regenerate: `python3 tools/report.py`).
- Briefs: `adjudicator-brief.md` (pilot), `adjudicator-brief-v2.md`, `rehold-brief.md`.

## Root causes across all 1,063 verdicts (shows; tags normalized)

| n | cause | rule candidate |
|---|---|---|
| 398 | taper's explicit set/encore markers lost (headers, `Disc N (Set M)`, `(set II)`, bare `1:`, `s1tNN`/`set01NN` filenames, `Set II intro` tracks, blank-line breaks, `Encore:`) to setlist.fm unlabelled single set / named-encore-as-set / alignment / jerrybase | parse markers; description markers outrank unlabelled setlist.fm; anchoring may not reduce below explicit headers |
| 229 | placeholder titles shipped as resolved (`tmp`, `Track eight`, filename stems, glued `03Song`, `07:20 - ` prefixes, `01.` from bare numbered lines; LLM alignment "matched" them) | close 2b gaps |
| 207 | unknown-song flags only echo an untitled tape | collapse into the unresolved hold |
| 189 | junk/format filter dropped real music (short segue/reprise pieces in `->` chains, set-intro tracks, odd-filename closers, filename-case, `.shn` labelled originals) | exemption arm (segue tag / named in description / continuous chain); junk CONSTANTS stay untouched (CLAUDE.md) -- needs Shawn's ruling |
| 120 | description is a count-exact positional title list | count-forced adoption (cf. setlist-gap rules) |
| 76 | same item's lossless originals carry corrected titles; stale MP3 derivative tags ship | per-track original-vs-derivative disagreement -> prefer original |
| 75 / 73 | partial tape (coverage 1.0) / a better sibling exists | head/tail unmatched-canonical-run check; selection completeness |
| 74 | shifted or scrambled tags (durations vs sibling expose it) | duration-vs-sibling check (flag, not fix) |
| 43 | jerrybase anchoring wrong -- esp. Phil Lesh & Friends one-set rows (`bugs-found.md` #4) | see above |
| 22 | yearless past-midnight date never gets the +-1 window -- **confirmed bug** `vet_research._date_flags` | resolve yearless against show year (year wrap) |
| 14 | venue string from a sibling while `venue_source: item` | bug |
| ~100 | spurious teases/footnotes, aliases, spelling, curly apostrophe, suite movements, context mentions | footnote-tease suppression, apostrophe fold |

Also in `bugs-found.md`: `llama fix` with an invalid structure combo drops show.json before failing, and
then fix validates the OLD overrides so it can't recover (hand-edit needed).

## Binding rulings (Shawn)

Taper/description wording ships; tape notes presumed correct unless clear contrary evidence
([[llama-accuracy-philosophy]]); archive venue string ships (same-city/festival-vs-site variants are not
errors); "J" and "Untitled #12" are real titles; wants to look before any bulk `--narration vague`;
review mode and stakes paragraph per the spec-review skill; never Sonnet as spec reviewer.
