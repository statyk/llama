# Junk-title drop: library replay against the 2026-11-13 baseline

Measured 2026-11-14 04:31 EST, library quiescent (no llama/emcee/bulk_apply/reapply/run-resume
process, no launchd/cron job). Read-only on `~/.llama`; arms and reports live under
`~/.llama-harness/junk-tag-drop/` (not committed). Spec: `docs/superpowers/specs/2026-11-13-junk-tag-drop-design.md`,
"Acceptance". Baseline: `docs/superpowers/2026-11-13-junk-tag-drop-evidence/drops.tsv`.

## Commands and commit

| step | command | exit | time |
|---|---|---|---|
| check | `git -C /Users/shawn/projects/llama diff --quiet a03fc04e HEAD -- packages scripts` | 0 | |
| check | `/Users/shawn/projects/llama/.venv/bin/python -c "import llama; print(llama.__file__)"` → `/Users/shawn/projects/llama/packages/llama/src/llama/__init__.py` | 0 | |
| base arm | `/Users/shawn/projects/llama/.venv/bin/python /Users/shawn/projects/llama/scripts/replay_holds.py run --all --out ~/.llama-harness/junk-tag-drop/base.json` | 0 | 37 s |
| cand arm | `./.venv/bin/python scripts/replay_holds.py run --all --out ~/.llama-harness/junk-tag-drop/cand.json` (worktree, clean tree at `6bc767f9`) | 0 | 37 s |
| holds | `./.venv/bin/python scripts/replay_holds.py compare ~/.llama-harness/junk-tag-drop/base.json ~/.llama-harness/junk-tag-drop/cand.json --out ~/.llama-harness/junk-tag-drop/compare` | 0 | |
| baseline | `./.venv/bin/python scripts/junk_drop_measure.py compare --base ~/.llama-harness/junk-tag-drop/base.json --cand ~/.llama-harness/junk-tag-drop/cand.json --baseline docs/superpowers/2026-11-13-junk-tag-drop-evidence/drops.tsv --shows ~/.llama/shows --out ~/.llama-harness/junk-tag-drop/measure` | 0 | |

The two arms ran concurrently. Base arm `sha` is `b616264c…-dirty`: the main checkout's
HEAD, whose only dirt is an untracked `.playwright-mcp/` (nothing under `packages` or
`scripts`); its `packages`/`scripts` equal `a03fc04e`. Candidate arm `sha` is
`6bc767f97ac6e702e1d00321826f36b45d207fc8`. Both arms share config fingerprint `3f1af9a8…2757`
and root `/Users/shawn/.llama`. Base reproduction: 95/95 held non-needs-LLM shows; briefing
guard 2/2; drift 0 shows.

Copied here from `~/.llama-harness/junk-tag-drop/measure/`: `summary.md`, `differences.tsv`,
`vocabulary.txt`, `kept_track_deltas.tsv`, `override_keys.tsv`.

## Counts: candidate vs baseline

| | baseline | candidate | delta |
|---|---|---|---|
| drop rows | 960 | 968 | +8 |
| shows with a drop | 699 | 709 | +10 |
| rule A rows / shows | 508 / 374 | 521 / 387 | +13 / +13 |
| rule B rows / shows | 431 / 359 | 426 / 360 | -5 / +1 |
| rule C rows / shows | 21 / 21 | 21 / 21 | 0 |
| held rows / shows | 19 / 19 | 19 / 19 | 0 |

+8 rows = 33 candidate-only - 25 baseline-only (below).

## Coverage

Base arm 3935 shows, candidate arm 3935 shows (both `--all`), 3935 in both. Baseline slugs absent
from the candidate arm: 0; from the base arm: 0. Rows with empty `filenames` (skipped by the
kept-track comparison): 2 in each arm. Coverage is complete at the show level; the one gap
is inside the needs-LLM rows (category `needs-llm-row` below), where the replay does not
reach every drop the baseline counted.

## Reconciliation against the spec's expected deltas

**Candidate-only drops: 33.**

- `parts-split`: 31, matching the spec's "~31 extra drops from `junk.parts` splitting". All are
  bracketed/punctuated intros and crowd/tuning tags: `(Intro)`, `[Intro]`, `Intro,`, `intro,`,
  `~intro~`, `/-intro`, `Intro /`, `intro *`, `(intro)`, `[intro]`, `crowd)`, `[crowd]`,
  `(crowd)`, `(Crowd)`, `(crowd noise)`, `***crowd noise***`, `Crowd~`, `/-crowd`, `(tuning)`,
  `Crowd + Tuning`. (rows in `differences.tsv`)
- `edge-run`: 2, the extra B drops from edge runs: `radiators-1996-02-17` `rad1996-02-17D1T02.mp3`
  `Introduction`; `radiators-2010-07-03` `rads2010-07-03d1T02.mp3` `Intro`.
- `title-differs`: 0. `not-in-show.json`: 0. `other`: 0.

**Baseline-only drops: 25.**

- `operator-include`: 2, as expected: `billystrings-2017-07-15` `bs2017-07-15t01.mp3`,
  `cubensis-2011-01-22` `cubensis2011-01-22-16bit-set1t01.mp3`.
- `arrowed`: 0. The 26 arrowed titles keep in the candidate as in the baseline: no candidate
  drop has a title containing `>`.
- `needs-llm-row`: 23 (not named in the spec's expectations; explained). Every one is a show
  that is `needs-llm` in both arms: the replay stops at the gather LLM touchpoint, so a
  baseline drop there is not reached. In 5 of them (`antibalasmusic-2003-06-13`,
  `kungfuband-2013-06-14`, `lettuce-2008-08-06`, `soulive-2009-04-16`,
  `tedeschitrucksband-2016-01-17`; blank candidate title in `differences.tsv`) the file is
  not in the arm's `filenames` at all; in the other 18 it is kept. These are the
  `--with-gather-llm` shows the rollout reports as their own wave; the replay cannot measure
  their drops without an LLM call. Slugs: antibalasmusic-2003-06-13,
  campervanbeethoven-2003-02-28, derektrucksband-2000-03-15, derektrucksband-2005-04-08,
  discobiscuits-2008-07-18, discobiscuits-2010-09-11, greatamericantaxi-2009-11-03,
  kungfuband-2013-06-14, lettuce-2008-08-06, lettuce-2011-01-18, lettuce-2014-12-06,
  moe-2005-03-04, moe-2005-03-05, moe-2008-06-15, radiators-2005-12-02, soulive-2009-04-16,
  tedeschitrucksband-2016-01-17, umphreysmcgee-2006-03-10, umphreysmcgee-2006-08-20,
  umphreysmcgee-2010-02-09, yondermountainstringband-2002-04-20,
  yondermountainstringband-2004-02-21, yondermountainstringband-2005-12-30. (76 needs-LLM
  shows still carry at least one candidate drop, on rows the replay did reach.)
- `not-in-arm`: 0. `title-differs`: 0. `not-kept`: 0. `other`: 0.

Arithmetic: rule A +13 = 13 A parts-split; rule B -5 = 18 B parts-split + 2 edge-run - 2
operator includes - 23 needs-llm-row.

## Vocabulary

`vocabulary.txt` is empty: zero candidate drops have a part outside the operator's vocabulary
(`junk_drop_measure.py` exit 0).

## Holds added or cleared between the arms

From `compare/holds_delta.txt`: 0 cleared, 18 added. All 18 added holds are
`junk-title drop held for review:` flags (17 delivered, 1 voiced: `gratefuldead-1969-03-01`).
The 19th held drop (`greatamericantaxi-2007-08-05`) is on a show that is `needs-llm` in both
arms, so it is not a hold delta.

**Other than junk-drop flags: no hold added, no hold cleared.** `flags.txt` lists 0 flag
families; newly cleared 0.

One outcome change that is not a hold flag, a finding:

- `darkstarorchestra-2009-05-24`: base `needs-brief`, candidate `structure-changed` (would be
  `needs-brief`). Cause: the rule-B drop of `dso2009-05-24d1t01.mp3` `tuning/intro` (also in
  the baseline). `structure_changed.txt` compares sets/segues by position, so the 9-track
  stored show vs 8 kept tracks reads as index 9 `old 1 → new null`; no kept track's set or
  segue changed. It is the one row of `compare/structure_changed_list.json`, i.e. it would go
  through `reapply --from-list … --allow-structure-change`. `taper_cleared.txt` lists the same
  show (removed flags: none).

Every other outcome change carries a junk drop: clean → clean-changed 602, clean →
newly-held 17, clean-changed → newly-held 1; no show changed outcome without a drop.

## Kept-track deltas

`kept_track_deltas.tsv`: 3 rows, all segue losses on the kept track right before a drop
(`adjacent_to_drop` True), as expected:

| slug | file | title | segue base → cand |
|---|---|---|---|
| jackiegreene-2011-12-31 | jg2011-12-31-d2t08.mp3 | New Speedway Boogie > … > New Speedway Boogie | True → False |
| smashingpumpkins-2007-07-28 | tsp2007-07-28d3t07.mp3 | Heavy Metal Machine | True → False |
| umphreysmcgee-2004-10-01 | um2004-10-01d3t4.mp3 | Soul Food I^^ | True → False |

**Set changes on kept tracks: 0. Title changes on kept tracks: 0.**

## Override keys naming a dropped file

`override_keys.tsv`: 13 rows, all `encore_after` (spec expected 12; the 13th is
`moe-2002-06-22` `moe2002-06-22d4t03.mp3` `/-crowd`, a parts-split extra). Checked against
each show's stored track order: in every row the last kept file before the dropped one is in
the set before the encore and the next kept file is `encore`, so the key moved to the last
kept file before the drop.

| slug | dropped file | set before → after | last kept before (set) | next kept (set) |
|---|---|---|---|---|
| derektrucksband-2005-04-09 | dtb2005-04-09d2t09.mp3 | 2 → encore | d2t08 (2) | d2t10 (encore) |
| derektrucksband-2008-11-02 | DTB20081102set2t10.mp3 | 2 → encore | set2t09 (2) | set2t11 (encore) |
| gomez-2006-10-06 | gomez2006-10-06_mxl603_d2t04_crowd.mp3 | 1 → encore | d2t03 (1) | d2t05 (encore) |
| moe-2002-06-22 | moe2002-06-22d4t03.mp3 | 2 → encore | d4t02 (2) | d4t04 (encore) |
| mountaingoats-2012-01-31 | MtnGoats18.mp3 | 1 → encore | MtnGoats17 (1) | MtnGoats19 (encore) |
| railroadearth-2005-02-18 | RRE2005-02-18d02t11.mp3 | 2 → encore | d02t10 (2) | d02t12 (encore) |
| railroadearth-2006-02-18 | rre2006-02-18d3t06.oktava.mp3 | 2 → encore | d3t05 (2) | d3t07 (encore) |
| railroadearth-2006-03-11 | rre2006-03-11d3t04.mp3 | 2 → encore | d3t03 (2) | d3t05 (encore) |
| railroadearth-2007-09-29 | rre2007-09-29d3t05.mp3 | 2 → encore | d3t04 (2) | d3t06 (encore) |
| railroadearth-2008-02-01 | RRE2008-02-01d03t07.mp3 | 2 → encore | d03t06 (2) | d03t08 (encore) |
| railroadearth-2009-01-15 | rre2009-01-15.at4041.t16.mp3 | 2 → encore | t15 (2) | t17 (encore) |
| soundtribesector9-2007-03-15 | sts92007-03-15-d2t08.mp3 | 2 → encore | d2t07 (2) | d2t09 (encore) |
| umphreysmcgee-2008-10-31 | um2008-10-31d3_t03.mp3 | 2 → encore | d3_t02 (2) | d3_t04 (encore) |

## Drops whose final title differs from show.json (non-tag rungs)

None. `differences.tsv` has 0 `title-differs` rows, and a direct check of all 968 candidate
drops found every drop's final title equal to that file's `show.json` title (all 968
`show.json` files readable). `darkstarorchestra-2014-07-31`, the named test case: the
candidate drops `dso2014-07-31d1t01.mp3` and `dso2014-07-31d2t01.mp3`, both `Tuning` in
`show.json` (title overrides) and in the baseline; `dso2014-07-31d2t02.mp3` keeps as
`China Cat->`. No cascade rung renamed a song to a vocabulary word in this library.
