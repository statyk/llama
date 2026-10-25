# Task 16 implementer handback (t16-impl, Opus)

## Status: BLOCKED (one unsanctioned expectation change). Nothing committed.

Everything in the brief is built and its new tests are green. The Step 4 dry run turned up a THIRD
existing test whose expectation changes. The plan expected exactly two, so per the rules I have not
edited it and have not committed. The suite has exactly one failure: that test.

**The blocker:** `packages/llama/tests/test_reapply.py::test_cli_reapply_names_form` (line ~371)
asserts `  re-deliver with: llama deliver gratefuldead-1973-06-10`. It runs on the fixture library's
own `config.toml`, which has **no `delivery_path`**. The brief's interface bullet says "With
`delivery_path` None no hint is printed", so that assertion now fails. Spec 5.5 says only "suppressed
for a voiced destination"; the None rule comes from the plan/brief, and Step 4 did not list this test.
So the brief contradicts itself (interface bullet vs. the dry-run list).
The controller needs to pick one:
  (a) keep "no delivery_path -> no hint" and amend `test_cli_reapply_names_form`: give it a config with
      a `delivery_path` whose station copy is missing or unvoiced, or drop its hint assertion. The new
      parametrised `test_reapply_hint_suppressed_for_a_voiced_destination` already covers the
      missing, unvoiced, voiced, unreadable and no-delivery_path cases. Or
  (b) print the hint when `delivery_path` is None. That is a one-line change in
      `_echo_redeliver_hint`, and the new test's "no delivery_path" case flips to expect it.
I recommend (a): with no delivery_path, llama cannot check whether the copy is voiced, and every
ambiguity resolves toward not inviting a re-delivery.

Uncommitted changes are in the worktree, all on the files the brief names (`git diff --stat`: 7 files).

## Built, per interface bullet

- **`deliver` selector refusal.** `--replace-voiced` with any selector (`other_selector`) prints
  `--replace-voiced takes one named show, never a selector` to stderr and exits 1. This happens before
  `_setup()` and before the "not both" check. Single-name `--replace-voiced` is unchanged.
  `_deliver_batch` lost its `replace_voiced` parameter, along with its now-unreachable
  `(voiced: DJ script/audio will be discarded)` marks. It calls `_deliver_one(config, ledger, e, dest)`,
  so no batch path can replace a voiced copy.
- **`_destination_is_voiced(out) -> bool`.** It now sits on a new `_read_destination_manifest(out) -> dict | None`:
  - `FileNotFoundError` (the manifest or `out` is missing) returns None, which reads as unvoiced (False).
  - Any other `OSError` or a `ValueError` (invalid JSON, a decode error) raises `LlamaError`.
  - A non-object raises `LlamaError` with the detail `not a JSON object: list`.
  - The message is verbatim: `refusing to deliver <out.name>: cannot read <out>/manifest.json (<error>); check the station copy by hand`.

  `_deliver_one` reads it once, under the show lock, and lets it propagate: a single name exits 1 with
  nothing copied, purged or recorded. `_deliver_batch`'s preflight catches it per show: it echoes the
  message to stderr, marks the row `  (refused: destination manifest unreadable)`, skips the show in
  the delivery loop and carries on.
- **Changed track list.** `_deliver_one` compares the destination manifest's track `filename` list,
  in order (`_track_filenames`), with the package manifest's. If the destination is readable,
  unvoiced and the lists differ, it copies through `_replace_destination` (atomic, wholesale) instead
  of the merging `copytree`. A `tracks` field that is not a list of objects also counts as "differs"
  (toward replacing; covered by an extra test). A missing destination manifest keeps today's merge.
  A voiced destination still refuses without the flag, before the gate.
- **`reapply` hint.** Both `re-deliver with` sites (names form and `--from-list`) now go through the new
  `_echo_redeliver_hint(config, slug)`:
  - `delivery_path` None: nothing is printed;
  - unreadable destination: `  <unreadable message>`;
  - voiced: nothing is printed;
  - otherwise, the old hint.
- **`scripts/replay_holds.py`.** `_is_voiced` returns `bool | None`: it catches the `LlamaError` and
  returns None. `_state_label` maps None to `unreadable`. `_taper_changes` now calls `_state_label`
  for a delivered row instead of open-coding the voiced check. `_title_changes`' fixed state tuple
  gained `"unreadable"`, so an unreadable show is listed rather than silently dropped from
  `title_changes.txt`. As a side effect, its summary line gains `unreadable N`; no test pins that line.
- **`scripts/short_keep_probe.py voiced-precheck --list L [--config C] SLUG`.** Read-only. It prints
  `  ok: ...` / `  FAIL: ...` lines, then `voiced-precheck <slug>: pass` or `N check(s) failed`. Exit 0
  only when all checks pass, else 1. The checks:
  - the slug is in the list, with at least one file;
  - the destination is voiced. It uses deliver's own `_destination_is_voiced`; an unreadable copy
    fails with deliver's message, and a missing `delivery_path` fails;
  - every listed source file is in the library `show.json` with `short_kept` true. Each failure names
    the file: `not in show.json` or `short_kept is not set`;
  - `package/manifest.json` exists, has a track list, and has as many tracks as `show.json`.

  An unreadable `show.json`, list or config is also a failed check (exit 1), not a crash. Note that
  the list's entries include 9 non-`music` kinds (7 `spoken`, plus `mixed-with-tuning` and
  `music-fragment`). The check requires every listed file, as spec 5.5 says.

## Dry run (Step 4): every existing test whose expectation changes

Full suite with the implementation and the new tests, before editing any existing test:
`3 failed, 5273 passed, 1 skipped, 8 deselected`
1. `test_deliver_cmd.py::test_unparseable_destination_manifest_is_not_voiced`: reversed by spec 5.5
   ("Any other read error, or a malformed manifest, refuses the show"). Expected; deleted. It is
   replaced by `test_unreadable_destination_manifest_refuses_the_show`.
2. `test_deliver_cmd.py::test_batch_replace_voiced_marks_only_voiced_and_replaces_it`: spec 5.5
   ("deliver itself refuses --replace-voiced whenever any batch selector is given"). Expected;
   rewritten as `test_batch_replace_voiced_is_refused_and_a_single_name_replaces`: the batch is
   refused and the tree is byte-identical, then a single-name replace un-voices it.
3. `test_reapply.py::test_cli_reapply_names_form`: **NOT in the plan's list -> BLOCKED** (above). Not edited.

One more deliberate choice. `_deliver_batch`'s note `(pass --replace-voiced to replace them)` now
points at a refused path, since a batch with the flag is refused. I kept the text so that
`test_batch_without_flag_notes_how_many_will_be_refused` stays unchanged, rather than make a fourth
unsanctioned change. Suggested reword, for the controller to decide:
`(re-deliver each by name with --replace-voiced)`.

## RED / GREEN

RED (new tests, before implementing):
`./.venv/bin/python -m pytest -q -p no:cacheprovider packages/llama/tests/test_deliver_cmd.py packages/llama/tests/test_reapply.py scripts/test_replay_holds.py scripts/test_short_keep_probe.py -k "<the new tests>"`
-> `21 failed, 6 passed`. The 6 passes are the pins: single-name replace, missing manifest, unchanged
overlay, voiced refuses, and reapply's unvoiced/missing hint cases. The failures were the intended ones:
- the selector cases returned exit 0 with `no matching shows`;
- `_setup reached`;
- the unreadable cases delivered;
- `voiced-precheck` was an invalid choice;
- and so on.

I then added two selector parameters that match the voiced show (`--state delivered`,
`--artist "Grateful Dead"`), where today's code would actually replace it.
`test_destination_without_a_usable_track_list_is_replaced` was added after GREEN and not run against
the old code. By reading, the old code merges, so the stale file would survive and the test would fail.

GREEN: the same command gives `29 passed`. `test_deliver_cmd.py` alone gives `53 passed`.
Full suite, final: `./.venv/bin/python -m pytest -q -p no:cacheprovider`
-> `1 failed, 5275 passed, 1 skipped, 8 deselected, 26 warnings in 41.70s` (the failure is the blocker).
`llama.__file__` resolves inside this worktree.

## Files changed (uncommitted)
- packages/llama/src/llama/cli.py
- packages/llama/tests/test_deliver_cmd.py
- packages/llama/tests/test_reapply.py
- scripts/replay_holds.py
- scripts/short_keep_probe.py
- scripts/test_replay_holds.py
- scripts/test_short_keep_probe.py

## Concerns
- The blocker above. The commit (`feat(deliver): --replace-voiced takes one name; unreadable
  destinations refuse; changed track lists replace`) is waiting on the controller's ruling.
- The batch note's text (above).
- The new per-test `permission` case skips itself if run as a user that ignores file modes (root).
- An unvoiced destination with extra non-llama files and a changed track list now loses those files
  (wholesale replace). That is the spec's intent ("keeps no old-numbered copies").

---

# Update (t16-impl2): the two parent rulings, applied

## Status: DONE. Commit e539653.

**Ruling 1, option (a).** I amended `test_reapply.py::test_cli_reapply_names_form`. It now runs on a
config that is the fixture library's own plus `delivery_path = <tmp>/station`. That station copy is
missing, which reads as unvoiced, so the hint is still expected. The change is tied to the Task 16
interface bullet "With `delivery_path` None no hint is printed". That None case stays pinned by
`test_reapply_hint_suppressed_for_a_voiced_destination[no delivery_path]`.

**Final dry-run list.** Three existing tests had expectations moved by spec or plan clauses. One more
had its pinned text updated under ruling 2:
1. `test_unparseable_destination_manifest_is_not_voiced`: spec 5.5, malformed manifest refuses. Deleted;
   replaced by `test_unreadable_destination_manifest_refuses_the_show`.
2. `test_batch_replace_voiced_marks_only_voiced_and_replaces_it`: spec 5.5, selector refusal. Rewritten
   as `test_batch_replace_voiced_is_refused_and_a_single_name_replaces`.
3. `test_cli_reapply_names_form`: the plan's Task 16 interface bullet (no delivery_path, no hint).
   Its config gained a `delivery_path`, per parent ruling (a).
4. `test_batch_without_flag_notes_how_many_will_be_refused`: its pinned note text was updated per
   parent ruling 2 (spec 5.5 selector refusal).

**Ruling 2.** The batch preflight note now reads `note: N destination(s) already voiced by emcee will
be refused (re-deliver each by name with --replace-voiced)`. Test 4 above is updated to match. I also
reworded the `--replace-voiced` option help, which pins nothing, so it now ends "...; one named show
only, never a selector".

**Grep for `--replace-voiced` / `replace_voiced`** over packages/, scripts/, README*, and docs/ outside
docs/superpowers/. Each hit:
- `packages/llama/src/llama/cli.py`:
  - the batch note: **fixed** (above);
  - the option help: **reworded** (above);
  - the `_deliver_one` refusal `(pass --replace-voiced to replace it with a fresh, unvoiced copy)`:
    **left as is**. It is the per-show message, singular "it", pinned verbatim by
    `test_redeliver_over_voiced_is_refused_and_changes_nothing`. In a batch run the same line prints
    per refused show, and following it there now gets the selector refusal, so nothing can be replaced
    in bulk. Flag it if you want a batch-specific wording;
  - the rest are the code itself, the new refusal string and docstrings. None recommends a batch.
- `scripts/short_keep_probe.py:21,777`: the new voiced-precheck docs, which already say single-name.
- `packages/emcee/src/emcee/station.py:312`, `packages/emcee/src/emcee/cli.py:119,964`: describe the
  swap directories and moves surviving a re-delivery. None recommends a batch; no change.
- `README.md:500`: "survive a `llama deliver --replace-voiced`". Not a batch recommendation; no change.
- `CLAUDE.md` (not mine, Task 23), report only:
  - line 71: "`llama deliver <name>` (refuses to overwrite an emcee-voiced destination unless
    `--replace-voiced`...; a batch confirmation marks or counts the voiced destinations". The "marks"
    part described the removed `(voiced: DJ script/audio will be discarded)` mark. A batch now only
    counts voiced copies (with the new note) and marks unreadable ones `(refused: destination manifest
    unreadable)`; `--replace-voiced` is single-name only.
  - line 309: "it refuses an emcee-voiced destination unless `--replace-voiced`". Still true; could add
    "(single name only)".

**Suite:** `./.venv/bin/python -m pytest -q -p no:cacheprovider` -> `5276 passed, 1 skipped, 8 deselected,
26 warnings in 40.26s`. `llama.__file__` resolves inside the worktree.

**Commit:** e539653 `feat(deliver): --replace-voiced takes one name; unreadable destinations refuse; changed
track lists replace`. The test command is in the message, along with the attribution trailer.

**Remaining concern:** only the `_deliver_one` per-show wording in batch context (above).
