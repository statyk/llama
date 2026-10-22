# Classify where each show's set structure evidence comes from

You are classifying held concert recordings from llama, a tool that packages archive.org Live Music Archive tapes for radio. Each show was held for review. An Opus adjudicator decided that the show's set breaks (where set 1 ends, set 2 starts, where the encore starts) were wrong and proposed corrected ones. We are designing a rule: **"the taper's explicit set/encore markers win"** over setlist.fm, the jerrybase dataset and alignment. We need to know, show by show, what the adjudicator's corrected structure actually rests on, and whether it is an explicit marker written by the taper.

Read-only work. Do not run llama, do not edit anything except your output file.

## Input

Your batch is a list of show slugs (given below). For each slug read `/Users/shawn/.llama-harness/piece2/packets/<slug>.md`. A packet has: deterministic facts (what llama shipped, the adjudicator's target breaks, what llama's own description parser produced), the adjudicator's verdict text, the selected recording's description (HTML stripped, truncated at 5000 chars), and the shipped track list with filenames.

If a packet is not enough to decide, you may read the full evidence bundle `/Users/shawn/.llama-harness/t3/bundles/<slug>.md` (large: setlist.fm, sibling descriptions). Do so only when needed.

"Break after track N" means track N is the last track of the earlier set.

## Definitions

**Explicit taper marker** = text written by the taper on THIS recording (its description, its filenames, or its track titles) that names a set or the encore: `Set 1`, `Set II`, `2nd set`, `Set Two:`, `Encore:`, `E:`, `Disc 2 (Set 2)`, `(start of Set II)`, `s2t01`/`set2` in filenames, a track titled `Set 2 intro`, an HTML-wrapped `<div>SET 1</div>`. A disc boundary alone (`Disc 2:`, `d2t01`) is **not** an explicit set marker. Track numbering restarting at 1, or a blank line between song groups, is **not** explicit either. Those are inferences.

## Output

Write one JSON object per line (JSONL) to `/Users/shawn/.llama-harness/piece2/out/<BATCH>.jsonl`, one line per slug in your batch, with these keys:

- `slug`
- `primary`: the ONE evidence kind the adjudicator's target structure mainly rests on. One of:
  `desc-set-header` (a `Set N`/`Set II` line or line-start header in the description), `desc-encore-only` (only an encore marker; no numbered-set marker; the target is about the encore boundary), `desc-inline-marker` (a set/encore marker mid-line or in a parenthetical, e.g. `9. Oakland (start of Set II)`), `desc-disc-with-set` (`Disc N (Set M)` or `Disc 2 - Set 2`), `desc-disc-only`, `desc-numbering-restart`, `desc-blank-line`, `filename-set`, `filename-disc-only`, `track-title-set-label` (a track title such as `Set 2 intro`, `Encore break`), `sibling-description` (another recording's description), `setlist.fm`, `jerrybase`, `durations-or-listening`, `review`, `other`.
- `also`: list of other evidence kinds from the same vocabulary that agree with the target (may be empty).
- `taper_explicit`: `"yes"` if an explicit taper marker on THIS recording supports EVERY break in the target (numbered breaks and the encore boundary), `"partial"` if it supports some of them, `"no"` if none.
- `marker_quote`: up to two short verbatim quotes of the marker text (or filename pattern), `""` if none.
- `lost_to`: what made llama ship the wrong structure, judged from the facts and verdict. One of: `setlistfm-unlabelled` (setlist.fm's single unlabelled set won), `setlistfm-mislabelled` (setlist.fm labelled sets but differently, e.g. a named encore as a set), `jerrybase-anchoring`, `alignment` (the right parse was used but alignment put breaks in the wrong place or lost them), `parser-missed-marker` (llama's parse of the description lacks set labels the description has; compare the facts' `set labels` with the description), `llm-alignment`, `no-marker-anywhere` (there was nothing explicit to lose), `other`.
- `target_matches_marker`: `"yes"` / `"no"` / `"n/a"`: do the adjudicator's target breaks fall exactly where the explicit marker puts them? If `no`, say why in `note`.
- `note`: at most one sentence, only if something is unusual (renumbering edit, target disagrees with the taper, ambiguous marker, a marker form not in the vocabulary).

Be literal and conservative: if you are unsure whether a marker is explicit, say `partial` or `no` and explain in `note`.

## Finishing

After the last line is written, touch `/Users/shawn/.llama-harness/piece2/out/<BATCH>.done`. Then reply with: the line count you wrote, a count of `primary` values, a count of `taper_explicit` values, a count of `lost_to` values, and any marker forms you saw that the vocabulary did not cover (with one example slug each). Return this as text; do not write a summary file.
