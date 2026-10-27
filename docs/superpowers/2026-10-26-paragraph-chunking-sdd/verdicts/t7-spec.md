# Task 7 spec-compliance review (2cb14e34..675d16e5)

Done well: the prompt sentence is the brief's text verbatim, in the specified place (after "...no separate show intro or set-break segments.", before `{{encore_note}}`), as guidance beside the segment description rather than a fifth hard rule; the four hard rules are untouched. The unescape sits inside the retry loop, before `script_guard`, on every `set_intros` value and on `outro` via `model_copy` (new dict, no mutation). `rephrase_segment` unescapes before `.strip()`. All five requested tests exist and assert the specific things the brief names, including the set_intros case. Mutation evidence has predictions stated before each run and plausible observations (A, A2, B).

### Spec Compliance
- ✅ Spec compliant.
  - scriptwrite.md: paragraph guidance, escaped `\n\n`, "never a raw line break" (kept on one line) — matches spec s.1 and Acceptance.
  - rephrase.md: rule bullet "Keep the blank lines between paragraphs, written as \n\n inside the JSON string." — matches.
  - scriptwrite.py: `_unescape_breaks` (literal backslash-n -> "\n", any occurrence, as spec s.1 says "any literal `\n` sequence"); call sites as the Interfaces block specifies.
  - No code re-inserts breaks after a rephrase (spec s.1) — none added.
  - Nothing extra: no other files, no other behaviour changes.
- Named risks checked outside the diff (one focused check each):
  1. Risk: template rendering might interpret or mangle the literal `\n\n` in the prompt. Checked `herder/tasks.py` `render` (plain `str.replace` of `{{key}}`) and `emcee/prompts/__init__.py` (`read_text`): the two-character escape reaches the model unchanged.
  2. Risk: a voiced field left un-unescaped (e.g. `context`). Checked `process.py` lines ~205-215: only `outro` and `set_intros` values are voiced segments; `context` is only rendered into dj-notes.md. Coverage is complete for spoken text.
- ⚠️ Cannot verify from diff: the end-to-end Acceptance items (notes contain paragraph breaks, no invalid-JSON retries in a real run) belong to the operator listening check, not this task.

### Issues (spec only)
#### Critical (Must Fix)
None.
#### Important (Should Fix)
None.
#### Minor (Nice to Have)
- `packages/emcee/src/emcee/prompts/scriptwrite.md` (new lines 40-43): the test pins "never a raw line break" as a contiguous substring, so a future re-wrap of the prompt could break it; the implementer flagged this themself. Cosmetic, no action needed for this task.

### Assessment
**Spec compliance:** Approved

No tests run by the reviewer (no doubt arose that the implementer's reported runs, 1017 passed / 1 deselected, do not answer).
