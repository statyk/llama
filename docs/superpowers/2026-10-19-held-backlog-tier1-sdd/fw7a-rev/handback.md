VERDICT: APPROVED

Reviewer fw7a-rev (Opus). Reviewed 9d5884b..c255ca7 (19af9de, 2686bec, c255ca7) in a git-archive snapshot of c255ca7; no worktree files changed, no commits.

## Spec compliance
| Brief item | Status | Where |
|---|---|---|
| 1. refusal tests the same stripped form adoption uses, via one helper | ✅ | siblings.py:303-304 (`_adopted_form`), used at :306 (`proposed`) and :310 (refusal) |
| 1. `is_placeholder_text`/`is_real_title`/`hygienic_title` unchanged | ✅ | not in diff |
| 1. test `tmp >` and `Track 02 >` decline with `sibling title fails hygiene` | ✅ | test_siblings.py:1080-1090 |
| 2. `_date_flags(..., *, day_unknown: dict[str, str])` required kw-only, callers updated | ✅ | vet_research.py:158, :173 (`day_unknown.values()`), :271-272, :284; test_stage_vet.py:514-519. Only callers in the tree (grep). |
| 3a. ordering pinned exactly | ✅ | test_stage_vet.py:739 (mismatched → day-00 → yearless; matches code order) |
| 3b. `0/5/08` → `2008-05-00` | ✅ | test_stage_vet.py:752 — pins `day_unknown_date` (the 16b ledger's pin, orch-r2 ledger:66) and `normalize_date(...) is None`; the brief's "normalize_date" wording was loose, the implementer pinned both and said so |
| 3c. first-surface-text de-dup | ✅ | test_stage_vet.py:758 |
| Commit subjects verbatim | ✅ | all three match |
| Nothing extra changed | ✅ | |
| Do-not-retune names | ✅ | no Global Constraints name in any +/- line |

## Findings
Critical: none. Important: none.

Minor (all pre-existing, outside the brief's scope, same drift class as item 1 — for the deferred list, not this task):
- M-a siblings.py:309: `hygienic_title(t, ...)` still tests the RAW donor title. Measured: `hygienic_title("Foo: >")` is True but the shipped form `Foo:` is rejected by hygiene (`endswith(":")`), so a donor `Foo: >` would be adopted as `Foo:`. Fix: pass `_adopted_form(t)` to `hygienic_title` as well (function untouched); note it also makes the `MAX_TITLE_LEN` check see a 2-char-shorter string — a trivial loosening to accept or reject explicitly; add a `Foo: >` decline test.
- M-b siblings.py:303-304: `_adopted_form` is not a fixpoint. `tmp > >` ships `tmp >`, and `is_placeholder_text("tmp >")` is False, so it is still adopted (with a trailing marker). Refusal and shipping now agree, as the brief asked; the residue is the shipped form itself. Fix (later, it changes shipped titles): strip to a fixpoint. Real-world likelihood very low.
- M-c siblings.py:303: helper is a nested def redefined per loop iteration; a module-level `_adopted_form` would be the house idiom. Cosmetic.
- M-d test_siblings.py:1080: the `Track 02 >` param is not a mutation witness (raw `is_placeholder_text("Track 02 >")` is already True). Disclosed by the implementer; harmless extra pin.

Implementer's handback (fw7a-impl) claims verified: suite count, M1 caught by `[tmp >]` only, no behaviour found wrong. Its "already refused by some other clause" is in fact the same raw `is_placeholder_text` call.

## Mutation spot-check (MROOT under $TMPDIR, per-mutant rsync copy, PYTHONPATH shadowing proven per mutant, private PYTHONPYCACHEPREFIX; predictions logged before flipping)
| mutant | predicted test | caught by |
|---|---|---|
| M1 refusal back to `is_placeholder_text(t.strip())` | test_a_donor_placeholder_with_a_trailing_segue_mark_still_fails_hygiene[tmp >] (and `[Track 02 >]` passes) | caught by [tmp >] only, as predicted (1 failed, 53 passed) |
| M2 `day_unknown.setdefault(du, text)` → `day_unknown[du] = text` (not in brief) | test_day00_entries_dedupe_on_the_first_surface_text | caught by it (1 failed, 91 passed) |
| M3 day-00 loop moved after the yearless loop (not in brief) | test_date_flags_order_is_mismatched_then_day_unknown_then_yearless | caught by it, plus pre-existing test_16b_day00_flag_uses_the_surface_text_and_orders_before_yearless (2 failed) |

## Suite (snapshot of c255ca7)
3798 passed, 1 skipped, 8 deselected, 26 warnings in 117.24s
