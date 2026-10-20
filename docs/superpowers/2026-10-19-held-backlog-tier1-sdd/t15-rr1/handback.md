### Finding Verdicts

- **[Important] `date_flags_raw` was not "the flags that loop would have produced without the window" (missing yearless, wrong placeholder text, non-empty on adoption)**: ADDRESSED. `_date_flags` (vet_research.py:132-150) is the old flag loop moved into a helper unchanged: it returns `[]` when `adopted is not None`, emits the placeholder text when `placeholder`, otherwise `wrong date:`, then the yearless month/day arm. `grounding_flags` calls it twice (vet_research.py:194-195): with `mismatched_raw` into a local named `date_flags_raw`, and with the windowed `mismatched` into `flags`. That covers (a), (b) and (c). The return signature is unchanged (`tuple[list[str], str | None, list[str]]`, line 150). The flags output is the same as before: same order (full dates, then yearless) and same adoption guard. The local's name now matches the parameter in plan Task 16 (`right_show_gate(..., *, date_flags_raw)`). The ruling's test exists: `test_4b_raw_date_flags_keep_what_the_window_hides_and_yearless_mismatches` (test_stage_vet.py:500-512) shows the helper keeps the yearless mismatch and the window-hidden adjacent date, uses the placeholder text, and returns `[]` on adoption. Its end-to-end part, with the own full date asserted, shows the yearless flag survives while the adjacent date is windowed out. The fix report names the covering tests and shows their output: test_stage_vet.py + test_prompts.py, 62 passed; full suite 3638 passed.
- **[Minor] vet_research.md item 1: re-wrap the ragged short line "entry: split segue chains", wording unchanged**: ADDRESSED. The short line is gone, and the wording is byte-identical apart from line breaks (checked against the diff). The re-wrap left a new ragged spot, listed below.

### New Breakage in the Fix Diff

- Minor: packages/llama/src/llama/prompts/vet_research.md:14 is now 94 characters ("Exclude songs mentioned only as context — other nights, studio versions, tour statistics,"). The rest of the file runs to 70-79, and the 37-character line after it ("comparisons to other performances.") makes it ragged again. This is cosmetic only. A 4-line re-flow at about 78 columns fixes it with no wording change.
- Minor, informational: no test can observe whether `date_flags_raw` is fed `mismatched_raw` (vet_research.py:194), because the local is unused until Task 16. The helper is pinned, but swapping in windowed `mismatched` would survive the suite. Task 16's tests must pin it, for example a gate that declines when the only wrong date is the one the window hides. Expected for a hand-off local; not blocking.

### Out-of-Scope Observations

None.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
