### Spec Compliance

- ✅ Spec compliant. Every item of Task 2 is present, nothing extra.
  - `CAUTIONS_PREFIX`, `ARCHIVE_PREFIX`: site.py:99-100, values as briefed; pinned at test_site.py:206-208.
  - `archive_link`: site.py:103-105. Non-str and missing are guarded; the prefix ends in `/`, so `archive.org.evil.test` fails (test_site.py:215-222).
  - `parse_briefing`: site.py:108-159. Line-based; `# ` dropped (:141-142); cut at the lowered prefix (:135-136); `## ` opens a section (:137-140); `- ` collects a `ul` (:146-151); blank ends a paragraph (:143-145); text joins with a space (via :121, :157); `**` removed (:134); empty sections omitted (:159).
  - `build_notes` adds `sections` (site.py:183); `briefing` is unchanged (:182).
  - Brief's `test_notes_carry_sections_and_keep_the_briefing` was done as the brief's own stub says, by extending `test_notes_from_a_package` (test_site.py:76-77). Not a deviation.
  - Global constraints: no imports added, nothing 3.12-only, transmitter still imports neither llama nor emcee. No page rendering in this diff, so escaping is out of scope here (Task 9/10).
- ⚠️ Cannot verify from diff: `render_show_page` still reads `notes["briefing"]` (site.py:195, seen in a grep), expected until Task 9. Task 9/10 must render `{"ul": [...]}`/`{"p": ...}` as text, and use `archive_link`, which nothing calls yet.

Named risks and checks run:
- Literal drifts from llama: read packages/llama/src/llama/stages/brief.py:91-104. It emits `# Briefing: …`, `## <heading>`, a body line or `- ` lines, and `## Cautions for the scriptwriter` last. The parser handles every shape it emits; the prefix matches.
- Spec's parser paragraph: read docs/superpowers/specs/2026-11-01-player-design.md:269-283. Matches; "the raw marks no longer appear" is met for everything brief.py emits.
- Branches the tests leave out, run read-only against the worktree's `transmitter`:
  - `A\n\nB` -> two `p`.
  - `A\n- x\nB\n- y` -> p, ul, p, ul, in order.
  - `A\n## H\nB` -> flushed into the right sections.
  - `## **Cautions** x` -> cut, since `**` is stripped before the check.
  - CRLF -> clean.
  - `## Cautionary tales` -> kept, not cut.
- List aliasing: `items`/`para` are rebound, never cleared in place, so a published `ul` cannot be mutated later (site.py:125, :151, :155).

### Strengths

- Stripping `**` before the cautions check (site.py:134-135) makes a bolded heading cut correctly, a case the brief did not call out.
- `{"heading": None}` is created lazily by `ensure()`, so a title-only or blank briefing gives `[]`, and a `## ` heading right after the title gets no phantom null section.
- `test_notes_from_a_package` has teeth: its fixture briefing is non-empty, so a `"sections": []` mutant fails at test_site.py:77.
- `archive_link` is typed defensively, and `None`/`""` are both tested.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- test_site.py:184-216: nothing exercises the mid-section transitions (text then `- `, `- ` then text; site.py:148-150, :154-156), two paragraphs in one section (:143-145), or text directly followed by `## ` (the `flush()` at :138). They behaved correctly when run by hand (above), but deleting either inner `if` leaves the suite green by reading (not run). brief.py's real output separates most of these with blank lines, so low production exposure; one mixed-block test would close it.
- site.py:148-150, :154-156: these re-implement `flush()`'s two appends inline. After `ensure()`, calling `flush()` in both branches would give the same result with less code. No behaviour change.
- site.py:141-142: a `# ` line does not end a paragraph, so `A\n# mid\nB` becomes `A B`. Unreachable from brief.py unless LLM text carries it; the brief is silent.
- site.py:152-157: a wrapped bullet (`- a\n  wrapped`) becomes a `ul` then a separate `p`, and `### Sub` stays as text with its raw marks. Neither is emitted by brief.py's template. They could only come from a newline inside an LLM field, which I did not measure (no production data read).
- Implementer's note confirmed: a blank line between bullets merges them into one `ul` (`- x\n\n- y`). Consistent with the brief ("`- ` lines collect into one `ul`"), and brief.py never emits it. Not a defect.

### Assessment

**Task quality:** Approved

**Reasoning:** The parser matches the brief and spec on every shape llama's renderer emits, including the case-insensitive cut, and `archive_link` is a correct literal prefix check. Remaining items are a test-coverage gap on mixed blocks and small tidying, none blocking.
