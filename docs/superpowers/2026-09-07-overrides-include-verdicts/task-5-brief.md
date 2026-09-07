### Task 5: documentation

**Files:**
- Modify: `README.md:150-152` (the `llama fix` example block), `:180-195` (the three resolutions)
- Modify: `docs/workflow.md:281` (the Correct row), `:594-596` (the `fix` flag table), `:613` (the `--suggest-titles` refusal sentence)
- Modify: `CLAUDE.md:49` (the `llama fix` command summary), `:196` (the overrides paragraph), `:242` (the `--suggest-titles` refusal)

- [ ] **Step 1: README**

After the `--exclude` example at `README.md:150`, add:

```
    llama fix 1973-06-10 --include x1         # re-admit a file the junk filter dropped
                                              # (x-handles come from `llama show ... --tracks`)
```

In the "Correct the data" bullet (around `README.md:183`), append a sentence:

> The reverse also works: `llama show <s> --tracks` lists every file the junk
> filter dropped with an `x`-handle, and `llama fix <s> --include x1` puts one
> back — the junk thresholds are measured and stay put, so a wrongly-dropped
> track is fixed per show, not by loosening the filter.

- [ ] **Step 2: `docs/workflow.md`**

Add a row to the `fix` flag table, directly under the `--unexclude` row:

```
| `--unexclude FILE\|N` | remove from `overrides.exclude` | gather |
| `--include xN\|FILE` (repeatable, comma groups) | add to `overrides.include` — re-admit a file the junk filter dropped; on a row whose reason is `operator-excluded` it un-excludes instead | gather |
```

In the Correct row at `:281`, after the `--unexclude` parenthetical, add
`; --include xN re-admits a file the junk filter dropped`.

At `:613`, change `--exclude`/`--unexclude` to
`--exclude`/`--unexclude`/`--include`.

Add a short subsection under the `fix` reference:

```markdown
#### Seeing what was dropped

`llama show <show> --tracks` ends with an `excluded (N):` section — one line per
file the junk filter removed, with an `x`-handle, its duration and the reasons.
A re-admitted track carries a `+` in the track table. The count also appears on
the always-visible `recording:` line (`(24 tracks, 3 dropped)`).

No exclusion reason is refused: re-admitting a `duplicate-listing` row will ship
that recording twice. The reason is printed next to the handle so the choice is
made with it in view.
```

- [ ] **Step 3: `CLAUDE.md`**

At `:49`, extend the `fix` flag list from `--exclude`/`--unexclude` to
`--exclude`/`--unexclude`/`--include`.

In the `overrides.json` paragraph at `:196`, after the `--exclude`/`--unexclude`
clause, add:

> and `--include xN|FILE` (`overrides.include`), which re-admits a file the junk
> filter dropped — applied inside `filter_files` after the junk arms and after
> duplicate-listing dedupe but **before** play-order derivation, so the floor
> cannot move and order is derived over the final set (a re-admitted file with
> no track tag reverts the recording to filename order). A file in both lists is
> excluded; the CLI keeps the lists mutually exclusive so that never happens
> through it. `--include` on an `operator-excluded` row un-excludes instead.
> **Do not loosen the junk constants instead** — this override is why they
> stay put.

At `:242`, add `--include` to the `--suggest-titles` refusal list.

- [ ] **Step 4: Verify the docs match the code**

```bash
./.venv/bin/python -m pytest -q
./.venv/bin/python -m llama fix --help
```

Expected: suite green; `--include`'s help text in the CLI output matches what
the docs describe.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/workflow.md CLAUDE.md
git commit -m "docs: llama fix --include and the excluded-files listing"
```

---

## Verification checklist (run before declaring the feature done)

- [ ] `./.venv/bin/python -m pytest -q` — whole suite green, and the count is
      higher than the pre-feature baseline by the number of tests added.
- [ ] `./.venv/bin/python -c "import llama; print(llama.__file__)"` resolves
      inside the tree you edited.
- [ ] `git grep -n "SHORT_FRACTION_OF_MEDIAN\|MIN_PLAUSIBLE_SEC\|MIN_MEDIAN_SAMPLE"`
      shows the values unchanged (0.25 / 90.0 / 5).
- [ ] `git grep -n "class ManifestTrack" -A 8` shows no new field.
- [ ] Manual smoke on a real workspace, if one is available:
      `llama show <a show with excluded files> --tracks` prints the
      `excluded (N):` section, and `llama fix <show> --include x1` writes
      `overrides.include` and redoes from gather.
