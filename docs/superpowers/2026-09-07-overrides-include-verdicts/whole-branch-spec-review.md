# Spec-compliance review — branch `overrides-include` (18 commits, base `e1fecb9`)

Test command run: `./.venv/bin/python -m pytest -q` from the repo root →
**1968 passed, 7 deselected** (matches the stated baseline). `llama.__file__`
resolves to `/Users/shawn/projects/llama/packages/llama/src/llama/__init__.py`.
No file changed; `git status --porcelain` empty at finish.

## Verdict

The approved design is **implemented essentially in full**. One
**Important** unrecorded defect at a cross-task seam, one **Important**
spec claim that is false and whose §6 test was silently skipped, and six
Minor items. **No Critical findings.**

---

## 1. Requirement-by-requirement

### Decisions taken (§ "Decisions taken")

| # | Requirement | Verdict | Evidence |
|---|---|---|---|
| 1 | Dropped files shown inside the track listing, not behind a flag | IMPLEMENTED | `cli.py:1337-1352` (`excluded (N):` inside `_format_tracks`); reachable from `show --tracks` (`cli.py:1629`) and the `[e]xclude` picker (`cli.py:1362-1363`) |
| 2 | Addressed by `x`-handles or filename, numbered within the excluded list | IMPLEMENTED | `cli.py:1292-1300` (`_excluded_handles`), `cli.py:1247-1276` (`_resolve_include_tokens`) |
| 3 | Provenance in `show.json`, not the manifest | IMPLEMENTED | `models.py:167-173` (`Track.included`); `ManifestTrack` (`models.py`) unchanged — verified no new field |
| 4 | Every exclusion reason re-admittable, no refusals | IMPLEMENTED | `junk.py:250-259` filters only on membership in `excluded`, never on reason; pinned `test_junk.py::test_readmit_of_a_duplicate_listing_ships_the_track_twice` |

### §1 Data model

| Requirement | Verdict | Evidence |
|---|---|---|
| `Overrides.include: list[str]`, durable across redo | IMPLEMENTED | `models.py:205`; read in `gather.py:838-841`; `test_models.py::test_overrides_include_defaults_empty_and_survives_an_old_file` |
| `Track.included: bool = False`, stamped from `t.filename in overrides.include` immediately before `Show(...)` | IMPLEMENTED | `gather.py:1183-1188`, `Show(...)` at `gather.py:1190`; `models.py:167-173` |
| `ManifestTrack` unchanged | IMPLEMENTED | verified — no diff to `class ManifestTrack` |
| `Overrides` stays permissive (no `extra="forbid"`) | IMPLEMENTED | `models.py:200` plain `BaseModel`; the only `model_config` in the file is `populate_by_name` at `:280` |
| *(unstated in §1)* `excluded_files` entries gain `duration_sec` | **DEVIATED (Minor, undocumented)** | `junk.py:138-139`, `:173-178`, `gather.py:895-896`, `models.py:190`. Required by §4's table, but neither §1 nor any correction records the persisted-shape change. See finding M1. |

### §2 Where re-admission happens

| Requirement | Verdict | Evidence |
|---|---|---|
| `filter_files` grows keyword-only `readmit: frozenset[str] = frozenset()` | IMPLEMENTED | `junk.py:182-185` |
| Applied after `_keep_and_exclude` (floor cannot move) | IMPLEMENTED | `junk.py:250` sits after `:230`; pinned `test_junk.py::test_readmit_does_not_move_the_duration_floor` (uses provenance-arm drops, so the test is actually sensitive — the earlier duration-arm version was not) |
| Applied after `_dedupe_duplicate_listings` | IMPLEMENTED | `junk.py:233-234` then `:250`; pinned by the duplicate-listing test above |
| Applied before the ordering block | IMPLEMENTED | `junk.py:259` precedes `:261-278` |
| Re-admitted entries move `excluded` → `kept` | IMPLEMENTED | `junk.py:256-259`; `test_readmit_returns_an_excluded_file_to_kept` |
| Consequence: an untagged re-admit reverts the tape to `filename` order, "pinned by test" | IMPLEMENTED | `test_junk.py::test_readmitting_an_untagged_file_falls_back_to_filename_order` |
| "may correctly flip `order_source` from `filename` to `track-tags` if its tag completes the set" | **DEVIATED — the claim is FALSE** | see finding **I2** |
| `readmit` names the winning format's files only; a losing-format entry warns `matched no file` | IMPLEMENTED (partially pinned) | `junk.py:252` (`f.get("format") == matched`), warning at `gather.py:842-843`. Only the *absent-name* case is pinned (`test_stage_gather.py::test_gather_warns_when_an_include_entry_matches_no_file`); the losing-format case is not — but the arm is unmutable in practice, since `excluded` only ever holds winning-format entries. |
| `read_overrides` hoisted above `filter_files`, snippet shape | IMPLEMENTED | `gather.py:834-841`, exactly the spec's call shape |
| Precedence: a file in both lists is **excluded**, with a warning | IMPLEMENTED | `gather.py:888-894`; pinned `test_stage_gather.py::test_exclude_wins_when_a_file_is_in_both_override_lists` |
| "`_recover_format_titles` continues to run on the post-`filter_files` `kept`" | **REVERSED by correction 5 — correctly** | `gather.py:883-884` (`recovery_basis`) |

### §3 CLI

| Requirement | Verdict | Evidence |
|---|---|---|
| `--include`, repeatable, comma-lists, redoes from `gather` | IMPLEMENTED | `cli.py:2371-2377` (option), `:2520` (`did_files`), `:2605` (stage selection); `test_fix.py::test_include_is_repeatable`, `::test_include_by_filename_and_comma_group`, `::test_include_by_handle_writes_overrides_include` (asserts `stages == ["gather"]`) |
| `_resolve_include_tokens` mirrors `_resolve_exclude_tokens`; `xN` → excluded filename | IMPLEMENTED (via `_excluded_handles`, per correction 2) | `cli.py:1250-1276`; `test_fix.py::test_include_handle_is_the_one_show_tracks_printed` reads the handle out of real `show --tracks` output and feeds it back |
| Handle resolution needs `show.json`, "same error text as the numeric path" | IMPLEMENTED, text adapted | `cli.py:1259-1260` — "resolving an **x-handle** needs show.json; reference the file by name instead" vs `:1232` "resolving a **track number** …". Not byte-identical; see finding M4. |
| Out-of-range handle raises `LlamaError` naming the count | IMPLEMENTED | `cli.py:1270-1272`; `test_fix.py::test_out_of_range_handle_errors` pins the whole message |
| `--include` on an `operator-excluded` row edits `overrides.exclude`, not `overrides.include` | IMPLEMENTED | `cli.py:2549-2557`; `test_fix.py::test_include_of_an_operator_excluded_file_unexcludes_it` (asserts `ov.include == []`, the half that actually bites) |
| `--exclude` on a currently-included file removes it from `overrides.include` | IMPLEMENTED | `cli.py:1191-1194`; `test_fix.py::test_excluding_an_included_file_removes_it_from_include` |
| Refuses to combine with `--suggest-titles` | IMPLEMENTED | `cli.py:2452`, message `:2467-2477`; `test_fix.py::test_include_refuses_to_combine_with_suggest_titles` pins the message *and* the remedy naming `--include` |
| `--exclude` + `--include` together allowed; same file in both is an error | IMPLEMENTED | `cli.py:2544-2548`; `test_fix.py::test_exclude_and_include_of_different_files_both_apply`, `::test_same_file_in_both_flags_errors` |
| `_edit_overrides` grows `add_include` / `rm_include` | IMPLEMENTED with `rm_include` deliberately omitted | `cli.py:1170-1197`; recorded as **correction 3** |

### §4 Display

| Requirement | Verdict | Evidence |
|---|---|---|
| `_format_tracks` gains an `excluded (N):` section; renders under `--tracks` **and** in the `[e]xclude` picker | IMPLEMENTED | `cli.py:1337-1352`; picker pinned `test_triage.py::test_exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint` |
| Depicted layout (padded filename first) | **superseded by correction 1** — shipped puts duration first, filename unpadded and never truncated | `cli.py:1350-1352`; `test_show_cmd.py::test_excluded_rows_align_regardless_of_filename_length` pins the columns and the *exact* row length (a `len(short) < len(long)` check was measured to survive re-padding) |
| `+` marker in its own one-character column, legend only when used | IMPLEMENTED | `cli.py:1322-1327`, legend `:1330-1336`; `test_show_cmd.py::test_tracks_listing_marks_a_re_admitted_track` (whole-prefix, so an unmarked row must carry a space), `::test_no_re_admitted_legend_when_no_track_was_re_admitted` |
| `recording: … (N tracks, M dropped)` whenever `excluded_files` non-empty | IMPLEMENTED | `cli.py:1593-1594`; `::test_dropped_count_shows_without_the_tracks_flag`, `::test_no_dropped_clause_when_nothing_was_dropped` (pins the whole line, catching the ", 0 dropped" mutation) |
| `overrides:` line prints `include=[…]` in both `_print_show_entry` and `_print_show_json` | IMPLEMENTED | `cli.py:1604-1605`, `:1677`; `::test_overrides_line_and_json_carry_include` |
| Deliberate scope cut: no `[i]nclude` verb in triage | HONOURED | `RESOLVE_PROMPT` (`cli.py:1386`) untouched in the diff; pinned negatively by the triage test above |

### §5 Downstream effects

| Requirement | Verdict | Evidence |
|---|---|---|
| Re-admitted track runs the ordinary cascade, usually `unresolved`; **no new review flag** | IMPLEMENTED | no `review_flags` change anywhere in the diff; `titles.py:299-306` cascade unchanged |
| `missing duration` re-admit carries `duration_sec=None` and prints `?` | IMPLEMENTED, **unpinned end to end** | `titles.py:308` (`length_seconds(f.get("length"))`), `_fmt_dur` at `cli.py:1287`. No test re-admits a `missing duration` file through gather. See M5. |
| The `cli.py:1248-1249` comment is corrected | IMPLEMENTED | `cli.py:1305-1309` |
| `align`/`siblings` see `None` for such a track — accepted | IMPLEMENTED (no code needed) | — |

### §6 Testing / docs

Covered: junk-layer re-admission across four arms, floor invariance, play
order, gather end-to-end (`test_stage_gather.py` 8 new tests), all four CLI
behaviours, all four display changes, and all three doc files
(`README.md:152-153,190-194`, `docs/workflow.md:281,597,637-666`,
`CLAUDE.md:202-212,251-254`).

Gaps: the `filename → track-tags` flip case (finding **I2**), the
`derivative of unknown original` and `missing duration` arms (finding **M3**),
and the `missing duration` display path (**M5**).

### Out of scope — nothing was built anyway

| Item | Verdict |
|---|---|
| Loosening any junk constant | CLEAN — `junk.py:66,69,70` still `0.25 / 5 / 90.0`; the diff of `junk.py` touches no constant |
| Interactive `[i]nclude` verb in `llama triage` | CLEAN — `RESOLVE_PROMPT`/`_UNRESOLVED` prompts untouched; no `"i"` branch added |
| Recording re-admission in the delivered manifest | CLEAN — `ManifestTrack` unchanged, `stages/package.py` untouched by the diff, `included` appears only in `models.py:173` |
| Re-admitting a losing-format file | CLEAN — `junk.py:252` scopes `by_name` to `matched`, and `excluded` only ever holds winning-format rows |

### Global constraints — all hold

- `SHORT_FRACTION_OF_MEDIAN = 0.25` (`junk.py:66`), `MIN_MEDIAN_SAMPLE = 5` (`:69`), `MIN_PLAUSIBLE_SEC = 90.0` (`:70`) — unchanged.
- `ManifestTrack` — no new field.
- `Overrides` (`models.py:200`) — plain `BaseModel`, no `extra="forbid"`.

---

## 2. Findings

### Important

**I1 — `--suggest-titles` / triage `[t]` permanently declines on any show with an effective `overrides.include`, with a wrong diagnosis and a futile remedy.**

`_propose_titles_for_show` rebuilds `kept` from item metadata and applies
**only** `overrides.exclude`:

```
cli.py:2284    kept, _, _ = filter_files(ia.metadata(show.identifier).get("files", []), want_format=want)
cli.py:2285-87 if entry.overrides.exclude: … kept = [f for f in kept if f["name"] not in drop]
```

There is no `readmit=frozenset(entry.overrides.include)`, and no
include-side filter. `gather`, by contrast, *does* re-admit
(`gather.py:838-841`), so `show.tracks` contains the re-admitted file and this
recomputed `kept` does not. The C1 staleness guard immediately below then
fires:

```
cli.py:2304-2311  if kept_names != track_names: … "show.json is stale relative to
                  overrides.json (N files kept, N+1 tracks on disk) - run
                  `llama redo <slug> --from gather` first"
```

Reproduced (probe run outside the repo, since removed): a 24-track show plus
one re-admitted track yields exactly
`show.json is stale relative to overrides.json (24 files kept, 25 tracks on disk) - run llama redo … --from gather first`,
exit 0, no table, nothing written.

Why this matters rather than being cosmetic: the prescribed remedy cannot
work. `redo --from gather` re-derives the *same* show.json, including the
re-admitted track, so the comparison fails identically on every retry —
`--suggest-titles` and triage's `[t] suggest titles` (same helper via
`_propose_and_confirm_titles`, `cli.py:2341`) are permanently unavailable on
such a show, and the operator is told their state is stale when it is not.
Spec §5's own first bullet says a re-admitted track "will usually land
`title_source="unresolved"`, raising the existing `unresolved track titles`
hold" — i.e. this feature routinely delivers shows into precisely the hold
whose title-proposal resolution it then disables.

Classification: an **oversight**, not an undocumented decision. Nothing in the
spec, the plan, or the corrections section mentions `_propose_titles_for_show`;
the branch's five tasks are `junk` / `gather` / display / `fix` / docs, and
this call site belongs to none of them, so it fell between them. Note the
irony that the *same-invocation* refusal (§3) was implemented and tested —
the cross-invocation case was not considered. Two candidate fixes: pass
`readmit=frozenset(entry.overrides.include)` at `cli.py:2284` (mirrors
gather), or, at minimum, make the guard's message distinguish "your tape
carries an operator re-admission" from genuine staleness.

**I2 — §2's `filename → track-tags` flip claim is false, and §6's test for it was silently skipped.**

Spec §2 asserts a re-admitted file "may correctly flip `order_source` from
`filename` to `track-tags` if its tag completes the set", and §6 asks for a
test of "the `filename` -> `track-tags` flip case". No such test exists
(the only order test in that direction is
`test_readmitting_an_untagged_file_falls_back_to_filename_order`, which pins
the *opposite* flip).

It could not have been written as described. The ordering gate is
`if kept and all(n is not None for n in nums) and len(set(nums)) == len(nums)`
(`junk.py:275`), evaluated over `kept`; re-admission only ever **adds** to
`kept` (`junk.py:257`). Both predicates are monotone-decreasing under
insertion, so a `kept` that was on the `filename` branch cannot be moved onto
the `track-tags` branch by adding a file — a missing tag stays missing, a
duplicate stays duplicated. Verified empirically: on a tape whose tag "gap"
is the junk-dropped file, `order_source` is `track-tags` **both** before and
after re-admission (the gap never affected it). The only reachable flip is the
degenerate one — `kept` empty before the re-admission (an all-junk tape),
where `if kept` is false — which is not the mechanism §2 describes.

Classification: a **spec error that was neither corrected nor flagged**. Four
of the five corrections were written for smaller divergences than this; this
one left a §6 test item unbuilt with no record. It is not a code defect —
`junk.py`'s behaviour is right — but by this branch's own standard ("a
requirement satisfied by code nothing would catch regressing is not
implemented"), a spec sentence describing behaviour that cannot occur should
have become correction 6.

### Minor

**M1 — `excluded_files` entries gained a `duration_sec` key with no data-model or correction entry.**
`junk.py:138-139`, `:173-178`, `gather.py:895-896`, `models.py:190`. This is a
change to a *persisted* artifact's shape, and §1 ("Data model") lists three
items, none of them this. It is required by §4's table and is handled
defensively on read (`e.get('duration_sec')`, `cli.py:1351`, pinned by
`test_show_cmd.py::test_excluded_section_survives_a_show_json_written_before_duration_sec`),
so the risk is nil — but the corrections section is where the branch records
exactly this class of thing. Undocumented decision, not an oversight.

**M2 — two display surfaces beyond §4, neither spec'd nor recorded.**
(a) `data["excluded"] = s.excluded_files` in `_print_show_json`
(`cli.py:1685`); (b) the `re-admit one with: llama fix <slug> --include x1`
hint (`cli.py:1637-1640`). Both were in the plan (Task 3 Step 3/4), so they
are deliberate, and (b) was moved from `_format_tracks` to `_print_show_entry`
during implementation so it carries the real slug and stays out of the
`[e]xclude` picker (commit `eb1e278`) — a good change, well tested
(`test_triage.py::test_exclude_picker_lists_the_dropped_files_but_not_the_re_admit_hint`).
§4 says "All three changes are in `cli.py`" and then lists four; there are
now six. Undocumented decision.

**M3 — §6's arm enumeration is only two-thirds covered.**
§6 asks for a `readmit` test "from each arm (`implausibly short`, `filename
convention mismatch`, `derivative of unknown original`, `unknown provenance`,
`missing duration`, `duplicate-listing`)". Covered: `implausibly short`
(`test_readmit_lands_in_filename_play_order`), `filename convention mismatch`
+ `unknown provenance` (`test_readmit_returns_an_excluded_file_to_kept`,
`test_readmit_does_not_move_the_duration_floor`), `duplicate-listing`
(`test_readmit_of_a_duplicate_listing_ships_the_track_twice`). Not covered:
**`derivative of unknown original`** and **`missing duration`**. The
re-admission code is reason-agnostic (`junk.py:256-257` matches on filename
only), so the gap is low-risk, but it is a literal §6 item.

**M4 — the x-handle `show.json` error text is not "the same error text as the numeric path".**
`cli.py:1259-1260` vs `cli.py:1232`: "resolving an x-handle needs show.json"
vs "resolving a track number needs show.json". Adapting the noun is clearly
the better reading of the spec's intent — telling an operator who typed `x1`
that "resolving a track number" failed would be wrong. Flagged only because
it is a literal §3 phrase and no correction records the adaptation.

**M5 — §5's `missing duration` re-admit path is unpinned end to end.**
No test re-admits a file excluded for `missing duration` through `gather` and
observes `duration_sec=None` reaching a track row as `?`. The corrected
comment at `cli.py:1305-1309` now asserts `?` "appears only on a track the
operator re-admitted via overrides.include" — a claim about the track table
that only the *excluded* table's `?` is tested for
(`test_excluded_section_survives_a_show_json_written_before_duration_sec`).

**M6 — `ordering["readmitted"]`'s populated content is pinned only through gather.**
`junk.py:250-259, 268-269, 275-278`. The junk-layer tests assert
`"readmitted": []` in four `ordering ==` comparisons and
`order == base_order` for the no-op case, but no junk test asserts
`ordering["readmitted"] == ["<name>"]` after a real re-admission. Correction
5's crucial "filter on what was ACTUALLY re-admitted, never on the request"
rule *is* pinned, but only at the consumer
(`test_stage_gather.py::test_including_a_file_that_was_never_dropped_keeps_its_vote`).
A mutation that made `readmitted` mirror the request rather than the result
would be caught, so this is completeness rather than exposure.

### Nothing found at Critical level.

---

## 3. Seams between commits — examined, and clean except I1

- **`x`-handle producer/consumer.** One producer (`cli.py:1292-1300`), three
  consumers (`_format_tracks` `:1337`, the hint `:1638`, the resolver
  `:1268-1269`). Correction 2's whole point, and it is pinned by an
  end-to-end round trip through real CLI output
  (`test_fix.py::test_include_handle_is_the_one_show_tracks_printed`), not by
  a unit assertion on either side. Clean.
- **`excluded_files` entry shape.** Three producers (`junk.py:138`, `:174`,
  `:178`, `gather.py:895`) all emit `{filename, reasons, duration_sec}`;
  four consumers (`cli.py:1300`, `:1350-1352`, `:1593`, `:2552-2553`) read
  `e["filename"]` (always present) and `.get()` everything else. Legacy rows
  are pinned on both the display side and the `fix` routing side
  (`test_fix.py::test_include_reads_a_pre_feature_excluded_row`). Clean.
- **The two `kept`-derived bases in `gather.py`.** `recovery_basis:884` is
  pre-exclusion (matching the pre-existing guard's rationale),
  `tag_gate_basis:953` is post-exclusion; both subtract `readmitted:883`.
  I checked they cannot be collapsed: `test_readmission_does_not_stop_the_track_number_strip`
  is exactly the case where reusing `recovery_basis` lets operator-excluded
  files vote. The two deliberately-uncarved consumers
  (`fetch_siblings:944`, `build_canonical`'s `target_count=len(kept)`) do use
  the full `kept`, as correction 5 rules. Also checked the other four
  `clean_tag_titles` call sites (`titles.py:241`, `correspondence.py:310`,
  `select_recording.py:69`, `gather.py:204`) — all operate on a *different*
  tape (a sibling donor, or a pre-gather candidate) where overrides do not
  apply. Clean.
- **Display/CLI split.** `_format_tracks` is shared by `show --tracks` and
  `_pick_excludes` (`cli.py:1362-1363`); the slug-bearing hint is correctly
  outside it. Note `_format_tracks` now *requires* its argument to carry
  `excluded_files` — the one existing caller with a `SimpleNamespace` was
  updated (`test_show_cmd.py:112-113`), and both real callers pass a `Show`.
  Clean.
- **The `+` column shifted every track row by one character.** `_MARK_COL`
  17 → 18 in `test_cli.py:161-169`, with the arithmetic re-derived in the
  comment. I checked for other consumers that parse `_format_tracks` output
  positionally — `_pick_excludes` parses the operator's *reply*, not the
  table — and found none. Clean.
- **`fix`'s new unconditional `read_model(sws.show, Show)` at `cli.py:2552`.**
  I checked whether this newly crashes `fix --exclude <filename>` on a show
  with no `show.json` (a path that previously did not need it). It does not:
  the pre-existing guard at `cli.py:2530-2532` exits first. Verified by probe
  (`no show.json in … (state: selected)`, exit 1). Clean.

## 4. Notes on process, not defects

- The corrections section did its job on the five things it covers; each of
  the five is verifiable in the shipped code and pinned by a named test
  (correction 5's two bases are pinned by four tests across
  `test_stage_gather.py` and `test_titles.py`). The finding class the prompt
  anticipated — a departure that was *not* reasoned about — is exactly what
  I1 and I2 are.
- Test quality on this branch is unusually high: several tests carry a
  recorded measurement of the mutation that defeated their previous form
  (`test_readmit_does_not_move_the_duration_floor`,
  `test_excluded_rows_align_regardless_of_filename_length`,
  `test_gather_leaves_ordinary_tracks_unmarked`,
  `test_a_filename_that_merely_starts_like_a_handle_is_a_filename`). The
  gaps I list under M3/M5/M6 are omissions of coverage, not weak assertions.
