TASK QUALITY: CHANGES REQUESTED

Reviewer: code quality only (a separate reviewer covers spec compliance).
Verdict is CHANGES REQUESTED on one Important finding; everything else is Minor.
The task is fundamentally sound and the test work is above average.

## Checks I ran (beyond reading the diff)

- **Independently re-ran 4 of the report's 14 mutants** against
  `test_show_cmd.py` + `test_cli.py`. All four CAUGHT, each by exactly the
  predicted test, each as the *sole* failure:
  - M13 (excluded filename column unpadded) → `test_tracks_listing_shows_the_excluded_section`,
    failing at the predicted assertion (`assert 19 == 21`).
  - M1 (`dropped` clause unconditional) → `test_no_dropped_clause_when_nothing_was_dropped`
    (`recording: gd73  (1 tracks, 0 dropped)`).
  - M5 (`e['duration_sec']` for `e.get(...)`) → `test_excluded_section_survives_a_show_json_written_before_duration_sec`
    (`KeyError('duration_sec')`, exit 1).
  - M3 (`+` on every row) → `test_tracks_listing_marks_a_re_admitted_track`
    (`'   2.+ set …'.startswith('   2.  set ')` False).
  Each mutant was applied via an exact-anchor replace, reverted with
  `git checkout --`, and the file's SHA re-compared to the pre-mutation value
  (`d0a26a6d…`) — RESTORED OK on all four. `git status --porcelain` is empty.
  **The mutation table's claims hold where I checked them.**
- **Comment-accuracy verification against source** (this repo treats a stale
  comment as a defect, so I checked both new factual claims):
  - "Junk drops such files" — `junk.py:133-134` appends reason `missing duration`
    when `length_seconds(...)` is `None`. ✅ accurate.
  - "package.py re-probes the real duration from the downloaded file at package
    time" — `package.py:52` `real = read_duration(dest)`, `:57`
    `duration_sec=real if real is not None else t.duration_sec`. ✅ accurate.
- **`_MARK_COL` 17→18 derivation** — recomputed and verified against live
  `_format_tracks` output: `'   1.  set 1      - Bertha…'`, index 18 holds the
  mark. 2+2+1+1+5+6+1 = 18. ✅ the comment's arithmetic is right.
- **Callers of the shared helper** (named risk: `_format_tracks` is shared with
  the interactive picker) — exactly two production call sites, `cli.py:1563`
  (`show --tracks`) and `cli.py:1297` (`_pick_excludes`); both pass a real
  `Show`, whose `excluded_files` has `default_factory=list`, so a pre-feature
  `show.json` loads as `[]`. No third caller. ✅
- **Pathological rendering probe** — drove `_format_tracks` directly with a
  56-char LMA filename, a filename containing a space, an empty `reasons`
  list and a `None` duration. Output recorded under findings 3 and 4.
- **Read-only guarantee** — the diff is print-only; no write path touched. ✅

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

**1. `cli.py:1281` — the `+` legend asserts something the codebase's own
comment says is false. (plan-mandated text)**

```python
lines.append("  + = re-admitted by operator (the junk filter had dropped it)")
```

`models.py:167-172`, written by Task 1, documents the opposite in as many words:

```
# True when the operator named this file in overrides.include -- not
# necessarily that the junk filter would otherwise have dropped it; the
# stamp is `filename in overrides.include`, and filter_files' return
# shape does not expose which re-admitted names were actually junk.
```

The state is reachable and silent: `gather.py:842` warns only for include
entries matching **no kept file**, so an `include` entry naming a file the junk
filter kept anyway stamps `included=True`, emits no warning, and prints a `+`
whose legend tells the operator the filter had dropped it. The parenthetical is
the only part of the row that is not derivable from the data.

This string comes from the brief, so I am labelling it plan-mandated — but the
brief does not get to grade its own work, and the spec (§4) specifies only
"a legend line emitted only when at least one track carries it", not this
wording. In a repo whose standard is that an inaccurate comment is a real
defect, an inaccurate *operator-facing* string is worse.

**Remedy:** `"  + = re-admitted past the junk filter by overrides.include"`, or
simply drop the parenthetical. One-line change, no test churn beyond
`test_tracks_listing_marks_a_re_admitted_track`'s
`assert "+ = re-admitted by operator" in r.output`.

### Minor (Nice to Have)

**2. `cli.py:1292` — the hint is the only one in the file that is not
copy-pasteable, and it lands in the wrong place for the picker.**

```python
lines.append(f"  re-admit one with: llama fix <show> --include {handles[0][0]}")
```

Every neighbouring hint interpolates the real slug: `cli.py:1561`
(`llama fix {entry.slug} --overrule`) and `cli.py:2385`
(`llama fix {entry.slug} --exclude ...`). This one prints a literal `<show>`
because `_format_tracks` receives only the `Show` model, which has no slug.

Sharper problem: because the helper is shared, `_pick_excludes` (`cli.py:1296-1301`)
now prints this hint — plus the `x`-handles — immediately above a prompt that
accepts **play-order integers only**. The operator is shown two token
vocabularies at the input point and told about a command the prompt will not
take. Spec §4 sanctions the excluded *listing* in the picker; it does not
sanction the hint.

**Remedy:** move the hint out of `_format_tracks` into `_print_show_entry`,
where `entry.slug` is in scope, matching `cli.py:1561`. That fixes both halves
at once. If you do this, add finding 6's picker test first — otherwise nothing
stops the *listing* following the hint out of the shared helper.

**3. `cli.py:1284,1288` — the excluded section inverts the column principle
recorded 20 lines above it, and one long filename widens every row.**

`cli.py:1265-1266`, in the same function:

```
# duration before filename so a long filename can print in full without
# misaligning the numeric column.
```

The excluded rows do the opposite: filename first, padded to
`max(len(e["filename"]) …)`. Measured, with one real-shaped LMA filename among
three entries:

```
   x1  gd1973-06-10.aud.vernon.motb0031.101223.flac16.d1t01.mp3    1:12  derivative of unknown original, unknown provenance
   x2  FOLLOW-ME @BYPIKENO.mp3                                        ?  
   x3  s.mp3                                                       0:12  implausibly short
```

121 characters on the first row, and the two short-named entries carry ~50
columns of padding they did not cause. Spec §4's worked example fixes this
column order, so this is a spec-shaped tradeoff rather than an implementer
slip — I am flagging it for the human, not asking the implementer to override
the spec unilaterally.

**Remedy (if taken):** duration before filename in the excluded rows too, which
removes the need to pad at all and matches the track rows. Alternative, cheaper:
leave the order and bound the pad (`min(width, 40)`) without truncating the
name.

**4. `cli.py:1290` — an empty or absent `reasons` list emits a row with trailing
whitespace.** Visible in the `x2` row above (`… ?  ` — the line ends in two
spaces). `e.get("reasons", [])` is the defensive read that makes this reachable
on a hand-mangled `show.json`; no current producer emits an empty `reasons`
(`junk.py:138` only appends when `reasons` is truthy). **Remedy:** `.rstrip()`
the assembled row.

**5. `cli.py:1609` — `--json` bypasses the "single producer" it was written to
establish.**

```python
data["excluded"] = s.excluded_files if s is not None else None
```

The entries carry no `handle`, so a scripted consumer that reads `--json` and
then calls `fix --include xN` must re-derive the 1-based numbering itself —
which is exactly the second, drifting producer `_excluded_handles`'s docstring
(`cli.py:1245-1248`) exists to prevent. **Remedy:**
`data["excluded"] = [{**e, "handle": h} for h, e in _excluded_handles(s)]`,
which makes the docstring's claim literally true and costs one line.

**6. Coverage: nothing pins the excluded listing's presence in `_pick_excludes`.**
Spec §4 requires it there ("The picker gains the excluded *listing* as
context"), and the implementer's own concern 4 notes the gap. Today it holds by
construction (shared helper), but that is precisely what finding 2's remedy
would start unpicking. **Remedy:** one test driving the picker's rendering and
asserting an `excluded (N):` line reaches the prompt.

**7. `test_show_cmd.py:392` — one whole-output negative survived the sweep.**

```python
assert "excluded (2):" not in r.output
```

in `test_dropped_count_shows_without_the_tracks_flag`. This is the exact form
the three rewrites moved away from, and the file's own comments
(`test_show_cmd.py:352-356`, `:395-400`) explain why. It is **safe today** —
a pytest tmp_path cannot contain `(2):` — so this is consistency, not a live
defect. **Remedy:**
`assert not any(ln.startswith("excluded (") for ln in r.output.splitlines())`,
matching `test_no_excluded_section_when_nothing_was_filtered`.

## ⚠️ Cannot verify from diff

- **`_excluded_handles` is single-*producer* but not yet double-*consumer*.**
  It has exactly one production consumer today (`cli.py:1282`); grep confirms
  nothing else in `packages/` numbers `x`-handles, so the "single producer"
  half is real. But its docstring claims it is "consumed by both the `--tracks`
  listing and `fix --include`'s token resolver", and spec §3 describes that
  resolver as mapping "an `xN` token to `show.excluded_files[N-1]["filename"]`"
  — i.e. indexing the list *directly*. If Task 4 follows the spec literally,
  the docstring becomes false and the seam this task was asked to create goes
  unused. **Controller: require Task 4's `_resolve_include_tokens` to consume
  `_excluded_handles`, or amend the docstring.**
- Whether the `dropped` count and the `+` column render correctly against a
  real gathered show with a genuine junk exclusion — all tests here construct
  `excluded_files` by hand. Task 2's gather tests presumably cover the
  producing side; I did not cross-check them.

## Strengths

- **The tmp_path defect class was found, diagnosed correctly, and escaped —
  not merely worked around.** The report's analysis is right: `assert "dropped"
  not in r.output` was matching the test's own name inside the pytest temp
  directory printed on the `path:` line. Each rewrite is scoped to a line
  (`startswith("excluded (")`, `startswith("  + = ")`, an exact
  `recording:` line), and each carries a comment recording *why* the
  whole-output form is wrong. That comment is the part that keeps the fix from
  regressing.
- **The three brief-supplied assertions the implementer strengthened were all
  genuinely weak, and the replacements are strictly better.**
  `spam.split() == ["x1", "spam.mp3", "1:12", …]` pins handle and entry on the
  *same row*, which the brief's `"x1" in r.output and "spam.mp3" in r.output`
  could not — and handle/entry mis-pairing is the exact failure
  `_excluded_handles`-as-single-producer exists to prevent.
  `intro.startswith("   1.+ set ")` / `dew.startswith("   2.  set ")` pins the
  marker to a fixed column *and* pins what an unmarked row carries there, which
  `"2.+" not in dew` did not.
- **The four tests added beyond the brief each close a real hole**, most
  notably `test_excluded_section_survives_a_show_json_written_before_duration_sec`
  — the `e.get` requirement was stated in the constraints and pinned by nothing
  in the brief. I confirmed by mutation that it is the sole test standing
  between the code and a `KeyError` on a pre-feature `show.json`.
- **The mutation table is honest about its own near-miss.** The note on mutant
  14 vs 7 — first `if handles: → if True:` variant caught by `ValueError` from
  `max()` on an empty sequence, i.e. caught for the wrong reason, re-run as a
  crash-free variant — is exactly the discipline
  `mutation-scoring-needs-a-prediction` asks for, applied against the
  implementer's own interest.
- **`_MARK_COL` was corrected rather than the column reverted**, and the three
  collateral `test_cli.py` fixed-offset tests all key off the constant, so the
  layout change needed one edit rather than three. The rewritten derivation
  comment is accurate and says *why* the number moved.
- **The `+` was kept in its own column rather than folded into `_MARK`**, with
  an added comment stating the orthogonality — the constraint most likely to be
  "simplified" away by a future reader.
- **Both pre-existing in-loop comments were preserved** where the brief's
  replacement body would have deleted them, including the "duration before
  filename" one and the `sibling-format` width measurement. Given this repo's
  standard on measurement-recording comments, noticing that was the right call.
- Defensive reads are real and correct: `e.get("duration_sec")`,
  `e.get("reasons", [])`, `if s is not None` on both `--json` fields, and the
  `if handles:` guard that keeps `max()` off an empty sequence.

## Assessment

**Task quality:** Needs fixes — finding 1 only. The Minors are polish and a
seam note for Task 4.

**Reasoning:** The rendering, the guards and the defensive reads are correct and
genuinely pinned — I verified four of the fourteen mutation claims myself and
all four held, by the predicted test, as the sole failure. The one thing I would
block on is a user-facing string that states as fact something the model's own
docstring says is not necessarily true, in a repo whose explicit standard is
that such claims are defects.
