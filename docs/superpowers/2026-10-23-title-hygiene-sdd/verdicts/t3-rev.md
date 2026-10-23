### Spec Compliance
- ✅ Spec compliant (against the brief; one plan-mandated item below needs a ruling)
  - `Cleaner`, `drop_leading_artist_items`, `read_parse`, `DescRead` and `read_desc_list` match the brief's signatures (desc_list.py:69-188 in the diff).
  - Exemptions match spec (ii):
    - Truncated header lines are exempt by construction: `_parsed_lines` mirrors `parse_setlist`'s preprocessing and truncation exactly. I compared it with setlist.py:480-512 and probed both the truncation branch and the `_RECOVER_FLOOR` branch.
    - `_NOISE` lines and header-only marker lines are exempt when they yield 0 items (diff :161).
    - The lines of removed items are exempt (diff :157).
    - Every other line must yield exactly 1 item, judged by `_emit_items([line])`. A per-line call never trips the enumerated `_NUM_PREFIX` strip, because `_enumerated_prefix` needs at least 3 lines (setlist.py:284).
  - The empty numbered line makes both readers inadmissible (diff :137, using reader (i)'s own `_EMPTY_NUMBERED`/`_lines`).
  - (i) is preferred (diff :186). Blocks and boundaries follow the brief (diff :117-124).
  - The artist drop applies only to the leading run (diff :76-89).
  - Protected names: the diff edits none of them. It only adds imports of setlist privates that the brief allows. `git diff main -- packages/llama/src/llama/setlist.py` prints 0 lines (checked).
  - All nine brief tests are present, plus six more.
  - `RRE_DESC` is verbatim: I checked it against `~/.llama/cache/md_rre2004-04-09.shnf.json` and it is equal.
- ⚠️ Cannot verify from diff:
  - The pin literals in `test_parse_setlist_unchanged` were "generated on main". This is consistent with setlist.py being byte-identical to main, but I did not regenerate them.
  - The full-suite run reported `26 warnings`. `test_desc_list.py` alone runs clean (34 passed, no warnings), so they come from elsewhere and are probably pre-existing. The report does not say.

### Strengths
- The per-line check is structurally sound:
  - Lines come from an exact mirror of `parse_setlist`'s own preprocessing and truncation.
  - The sum check (diff :142) ties per-line attribution to the real parse.
  - A mirror that drifts fails safe: it returns "per-line count disagrees", which is inadmissible, never a wrong list.
- `drop_leading_artist_items`' removals are mapped back into `removed` correctly. They are a prefix of the kept items: `kept[:len(cleaned)-len(dropped)]`, diff :154. The leading-artist test reaches this path for real: the `Railroad Earth` line above `Disc 1: Set 1:` survives truncation (the parse has 25 items with `Railroad Earth` first), so the drop in `read_parse` is what removes it.
- The tests exercise real `parse_setlist` behaviour with no mocks. They pin the reason strings and cover the inline-marker split (`Deal E: Ripple`), the 0-item prose line, cleaner/report disagreement, and (ii) being used when (i) is admissible but not count-matched.
- The real-case excerpt is verbatim, and setlist.py is untouched.

### Issues
#### Critical (Must Fix)
None.

#### Important (Should Fix)
1. **Plan-mandated: a partly removed multi-item line is exempt, and its leftover fragment enters the list.** desc_list.py diff :157 (`exempt = {line_of[i] for i in removed ...}`), pinned at test_desc_list.py diff :266-269 (`raws == ("Boulder CO", "Bertha", ...)`).
   - Spec (ii) exempts "the banner or artist lines the cleaning removes". It makes (ii) inadmissible for "a line that yields several items" precisely so that a multi-item line never feeds positional entries.
   - Exempting a line when only some of its items were removed admits exactly that: a fragment of a split line, at the head of the list.
   - This is reachable with gather's real cleaner. `_strip_head_banner` (gather.py:599) strips a prefix of items "up to the last metadata item", which can end in the middle of a `,`-split banner line. The fragment left behind is by construction not metadata or chatter, so check 1's `banner` class need not catch it, and it sits in front of every real entry. Only count-match and the shift checks then stand between it and a shifted fill.
   - The implementer followed the brief's test as written (Step 1 requires this case to be admissible) and flagged it.
   - Fix (needs an orchestrator ruling, since it changes the brief's test): exempt a line only when ALL of its items are in `removed`, e.g. `exempt = {k for k in range(len(lines)) if counts[k] and all(i in removed for i in items_of_line[k])}`. Then the brief's case returns `"line yields 2 items: Fox Theatre, Boulder CO"`, and only the `{0, 1}` variant stays admissible.

#### Minor (Nice to Have)
1. **Spec question: (ii) bypasses (i)'s contiguity guard.** desc_list.py diff :186.
   - Probe: `1. A song\n2. B song\n4. D song` with `n_tracks=3` gives `numbered="non-contiguous at 4"` but `used=parse` with `('A song','B song','D song')`. The plan calls this "the alabamashakes-2012-01-13 / delmccouryband-2004-06-12 shape", and the spec says contiguity "is there to catch blank or missing entries".
   - Likewise, a restart at 1 with no header (plan reading R16, (i) inadmissible) is used via (ii).
   - This follows the spec literally: (ii) is defined by per-line yields only, with no numbering. On the two cited real shows it does no harm: I probed both against the cache and both are `empty entry` for both readers, so the explicit both-inadmissible rule covers them.
   - But on any numbered list that (ii) also parses one item per line, (i)'s gap and restart rejection is overridden.
   - Suggest putting it to the operator at Checkpoint A beside R16. One option: when (i)'s reason is `non-contiguous`, (ii) is not used. That would cost the legitimate unlabeled-disc restart, so it is a ruling, not a fix. At minimum, the gate should count shows where `used.reader == "parse"` while `numbered` is `non-contiguous…`.
2. **The report's claim that compensating mis-attribution "cannot arise" is false, though the outcome is safe.**
   - Under the enumerated vote, a numbered line one character over `MAX_TITLE_LEN` yields 0 items alone but 1 in the document. That is an addition, not only a removal.
   - Probe: `1 Bertha\n2 Deal\n03 <80×A>\n04 3:45` gives per-line `[1,1,0,1]`, sum 3, equal to the parse's 3, but misattributed.
   - The 0-item line is then non-exempt, so the result is `line yields 0 items …`, which is inadmissible. So the effect is conservative.
   - Worth a one-line comment at diff :142 saying the sum check does not prove attribution, and the per-line rule backstops it.
3. **No test covers the `_RECOVER_FLOOR` branch of `_parsed_lines`** (diff :103-106).
   - I probed it and it works: `Grateful Dead\nBertha\nDeal\nSugaree\nJack Straw\nLoser\nEncore:\nRipple` gives 6 raws and `("encore",)`.
   - A mirror bug there would only cost yield (the sum check fails), but a pin is cheap: assert `_emit_items([l for l in _parsed_lines(d)])[0] == parse_setlist(d).items` for a truncating case and a recovering case.
4. **Header-shaped and decoration lines that yield an item become entries.** Examples: `CD 2:`, `=====` and `----` each give an entry, e.g. `('Bertha','Deal','CD 2:','Ripple')`. This is `parse_setlist`'s output, so it is faithful to "parse_setlist's own items". Check 1's `header`/`no alnum` classes will decline these shows rather than mis-fill, so it costs yield only. Worth a gate count; no code change in this task.
5. **The cleaner's report is checked only by length** (diff :151), and out-of-range indices are silently ignored (diff :157, `0 <= i < len(line_of)`). A cleaner that removes item 2 but reports `{0}` passes and exempts the wrong line. The contract is internal (Task 11 supplies the only real cleaner), so this is low risk. Optionally treat any out-of-range index as "cleaner count disagrees".
6. **Small duplication.** `_is_marker` (diff :112-114) duplicates the three-regex predicate inlined in `_parsed_lines` (diff :100); `_parsed_lines` could call it. Also, `_lines(desc)` at diff :137 does not get the `desc or ""` guard that the next two lines use.

### Assessment
**Task quality:** Approved (implementation; Important 1 is plan-mandated and goes to the orchestrator for a ruling, not back to the implementer as written)
**Reasoning:** Reader (ii) mirrors `parse_setlist` faithfully, fails safe on drift, leaves setlist.py untouched, and the tests pin real behaviour. The two substantive concerns are the partly removed banner line (Important 1) and (ii) overriding (i)'s contiguity rejection (Minor 1). Both are at plan or spec level and need a ruling, not an implementation correction.
