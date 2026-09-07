# `overrides.include` — re-admitting a file the junk filter dropped

**Date:** 2026-09-07
**Status:** Approved design, pending implementation plan

## The bug this comes from

`delmccouryband-1969-08-08` ships without its opening `Introduction`.
Diagnosis confirmed 2026-09-06 against the show's own `show.json`: the file
`dm1969-08-08t13.mp3` (37 s) sits in `excluded_files` with reason
`implausibly short`. The tape's median track is 175.5 s, so the duration arm's
floor is `0.25 x 175.5 = 43.9 s`; the shortest **kept** track is 44.0 s. The
introduction lost by a tenth of a second.

**The operator has no recourse.** `overrides.exclude` is one-directional: it
only ever *removes* (`gather.py:842-849`, reason `operator-excluded`), and
`--unexclude` merely undoes an entry in that list. Nothing re-admits a file the
junk filter dropped. An operator who can see the track on the archive.org item
page has no supported way to keep it — and no CLI surface even *shows* what was
dropped: `Show.excluded_files` is written to `show.json` and read back by
nothing (`excluded` appears nowhere in `cli.py`'s display paths).

## Explicit non-goal: do not loosen the junk constants

`SHORT_FRACTION_OF_MEDIAN` 0.25 / `MIN_PLAUSIBLE_SEC` 90 / `MIN_MEDIAN_SAMPLE`
5 were swept over 2,030 cached items, and the amputation they fixed — 11 of 38
Minutemen tracks shipped at coverage 1.00 with **no review flag** — is a far
worse failure than an occasional dropped introduction. Retuning them
invalidates that measurement. A per-show override is auditable and reversible;
a constant change is neither. This spec adds the override and leaves
`junk.py`'s thresholds exactly where they are.

## Decisions taken (owner, 2026-09-07)

1. **Dropped files are shown inside the track listing**, not behind a separate
   flag — the operator wants an obvious visual cue that a track went missing
   whenever they look at a show.
2. **Excluded rows are addressed by `x`-handles or by filename** (`x1`,
   `x2`, …), numbered within the excluded list. Not bare integers: the same
   integer would mean a play-order track under `--exclude` and an excluded file
   under `--include`, in one output.
3. **Provenance lives in `show.json`, not the manifest.** `ManifestTrack`
   carries neither `title_source` nor `matched` today; it stays lean and the
   llama<->emcee contract is untouched.
4. **Every exclusion reason is re-admittable, with no refusals.** `--include`
   is the single undo for any reason a file is missing, `operator-excluded` and
   `duplicate-listing` included. The consequence was raised and accepted:
   re-admitting a `duplicate-listing` row ships that recording twice. It is an
   explicit, per-show, visible operator act, and the excluded table names the
   reason next to the handle.

## 1. Data model

- **`Overrides.include: list[str]`** — source filenames re-admitted *after*
  junk filtering. Durable across every redo, like `exclude`.
- **`Track.included: bool = False`** — stamped in `run_gather` immediately
  before the `Show(...)` construction (`gather.py:1124`), from
  `t.filename in overrides.include`. Stamped late on purpose: no intermediate
  track rebuild between `resolve_titles` and `Show(...)` can drop it.
- **`ManifestTrack` unchanged** (decision 3).

`Overrides` is a persisted state artifact and stays **permissive**
(`extra="forbid"` was deliberately not extended to it) — an `overrides.json`
written by an older llama, with no `include` key, must keep loading.

## 2. Where re-admission happens

`filter_files` grows a keyword-only `readmit: frozenset[str] = frozenset()`.
Re-admission is applied **inside** it, **after** `_keep_and_exclude` **and
after** `_dedupe_duplicate_listings`, **before** the play-order derivation.
Re-admitted entries move from `excluded` back into `kept`.

The position is load-bearing three times over:

- **After `_keep_and_exclude`** — the duration floor is the median of files
  passing every *other* arm, computed in that function. A re-admitted 37 s
  track therefore cannot lower the floor and license further junk. This
  preserves the two-pass invariant documented at `junk.py:104-107`.
- **After `_dedupe_duplicate_listings`** — otherwise a re-admitted
  `duplicate-listing` row would be immediately re-dropped by dedupe,
  contradicting decision 4.
- **Before the ordering block** (`junk.py:227-236`) — play order is then
  derived over the final kept set, so the re-admitted file lands in its correct
  slot, and may correctly flip `order_source` from `filename` to `track-tags`
  if its tag completes the set. The alternative (re-admitting in `gather` after
  `filter_files` returns) would force a reimplementation of that ordering logic
  at the call site, where it can drift from the original.

**Consequence of that last point, deliberate:** order is derived over the final
kept set, so re-admitting a file that carries **no track tag** drops the whole
recording out of `track-tags` ordering back to `filename` ordering — the
`all(n is not None)` test at `junk.py:232` fails once the untagged file is in
`kept`. That is the honest price of deriving order once over the final set
instead of splicing a file into an order derived without it. It is pinned by
test rather than worked around.

**`readmit` names the winning format's files only.** `filter_files` picks the
first format whose *kept* set is non-empty, and `excluded` covers only that
format. A `include` entry naming a file in a losing format matches nothing and
logs the same `matched no file` warning `exclude` already emits.

In `run_gather`, `read_overrides(show_ws)` moves **above** the `filter_files`
call (it only reads the show directory; it has no dependency on `md`):

```python
overrides = read_overrides(show_ws)
kept, excluded, ordering = filter_files(
    md.get("files", []), want_format=want, readmit=frozenset(overrides.include))
```

`_recover_format_titles` continues to run on the post-`filter_files` `kept`, so
a re-admitted file participates in title recovery like any other track.

**Precedence.** The existing `overrides.exclude` block (`gather.py:842-849`)
runs *after* and is untouched, so a file appearing in **both** lists is
**excluded** — a defined answer, with a warning logged. The CLI (§3) makes that
state unreachable by construction; this rule exists only for a hand-mangled
`overrides.json`.

## 3. CLI

`llama fix <name> --include <handle|filename>` — repeatable, accepts
comma-lists, redoes from `gather`. Same shape as `--exclude`.

- **`_resolve_include_tokens(show_ws, tokens)`** mirrors
  `_resolve_exclude_tokens`: expand comma groups, map an `xN` token to
  `show.excluded_files[N-1]["filename"]`, pass anything else through as a
  filename. Resolving a handle needs `show.json` (same error text as the
  numeric path); an out-of-range handle raises `LlamaError` naming how many
  excluded files there are.
- **The two override lists stay mutually exclusive by construction.**
  `--include` on a row whose reason is `operator-excluded` *removes that
  filename from `overrides.exclude`* rather than appending to
  `overrides.include` — that is the `--unexclude` case, which decision 4 folds
  in. Symmetrically, `--exclude` on a currently-included file removes it from
  `overrides.include`. `--unexclude` remains as the precise spelling and is
  unchanged.
- **Refuses to combine with `--suggest-titles`** in one invocation, for the
  same reason `--exclude` already does (`cli.py:2337-2352`): re-admitting a
  file renumbers tracks before the proposal's numbering would apply.
- **`--exclude` and `--include` together is allowed** — both resolve against
  the current `show.json` before any redo runs, so neither sees the other's
  renumbering. Naming the *same* file in both in one invocation is an error.
- `_edit_overrides` grows `add_include=()` / `rm_include=()` alongside the
  existing `add_exclude`/`rm_exclude`, applying the mutual-exclusion rule above.

## 4. Display

All three changes are in `cli.py`.

- **`_format_tracks` gains an `excluded (N):` section**, so it renders under
  `llama show --tracks` *and* inside the interactive `[e]xclude` picker, which
  shares the helper:

  ```
  excluded (3):
    x1  dm1969-08-08t13.mp3       0:37  implausibly short
    x2  FOLLOW-ME @BYPIKENO.mp3   1:12  filename convention mismatch
    x3  dm1969-08-08t07.mp3       4:02  duplicate-listing
  ```

- **A `+` marker on re-admitted tracks**, in its own one-character column
  beside the existing `?`/`-` match marks (which mean something orthogonal),
  with a legend line emitted only when at least one track carries it.
- **`recording: <id>  (24 tracks, 3 dropped)`** — the `dropped` clause appears
  on the always-visible line whenever `excluded_files` is non-empty, so the cue
  does not depend on `--tracks`.
- **`overrides:` line prints `include=[...]`** alongside the existing
  `exclude=[...]`, in both `_print_show_entry` and `_print_show_json`.

**Deliberate scope cut:** no new interactive `[i]nclude` verb in the triage
walkthrough. The picker gains the excluded *listing* as context; its prompt
still accepts play-order track numbers only.

## 5. Downstream effects

- A re-admitted track runs the ordinary title cascade and will usually land
  `title_source="unresolved"`, raising the existing `unresolved track titles`
  hold — which self-clears on re-gather once the title is resolved. **No new
  review flag**: the operator asked for this file explicitly.
- A `missing duration` re-admit carries `duration_sec=None` through gather and
  prints `?`. `package.py:52` re-probes the real duration from the downloaded
  file, so the delivered manifest is correct. This falsifies the comment at
  `cli.py:1248-1249` asserting the duration `?` cannot co-occur with the match
  marker — that comment is corrected as part of this work.
- Gather-time consumers that read durations (`align`, `siblings`'
  duration-sequence matching) see `None` for such a track. Accepted: it affects
  only the one operator-forced file.

## 6. Testing

- **`junk.filter_files(readmit=...)`**: re-admits from each arm
  (`implausibly short`, `filename convention mismatch`, `derivative of unknown
  original`, `unknown provenance`, `missing duration`, `duplicate-listing`);
  the re-admitted file leaves `excluded`; an unknown filename is a no-op; the
  median floor is unchanged by a re-admission (pin it with a tape where a
  re-admitted short file *would* have moved the floor); play order is
  re-derived, including the `filename` -> `track-tags` flip case.
- **gather**: `overrides.include` re-admits end to end; `Track.included` is
  stamped on exactly the re-admitted tracks; a file in both lists is excluded
  and warns; an `include` entry matching no file warns.
- **cli**: `x`-handle resolution and its out-of-range error; missing
  `show.json` error; `--include` on an `operator-excluded` row edits
  `overrides.exclude` not `overrides.include`; `--exclude` on an included file
  removes it from `overrides.include`; same file in both flags errors; the
  `--suggest-titles` refusal; the three display changes; `--include` routes to
  `redo --from gather`.
- **docs**: `README.md`, `docs/workflow.md` (`llama fix` reference), and
  `CLAUDE.md`'s `overrides.json` paragraph.

## Out of scope

- Loosening any junk constant (see the non-goal above).
- An interactive `[i]nclude` verb in `llama triage`.
- Recording operator re-admission in the delivered manifest.
- Re-admitting a file that belongs to a *losing* audio format.

## Corrections made during implementation (2026-09-07)

This section is appended, not edited in place, so the text above stays the
record of what was actually approved. Three places diverge from what
shipped, settled across four review rounds:

1. **Section 4's depicted excluded-table layout is superseded.** The
   filename was padded to the widest in the set, which made every row as
   long as the worst one — a measured 121 characters on a real-length LMA
   filename. Shipped layout puts the duration before the filename, leaves
   the filename unpadded, and never truncates it, because `--include`
   accepts the filename verbatim so a truncated one is unusable for the
   purpose the listing serves. It now matches the track row's own
   documented "duration before filename" convention three lines above it.
2. **Section 3's prose says an `xN` token maps to
   `show.excluded_files[N-1]["filename"]`. The implementation deliberately
   goes through `cli._excluded_handles` instead**, so the handle an
   operator reads in `show --tracks` and the handle the resolver means
   come from one producer and cannot drift.
3. **Section 3 mentions an `rm_include=()` parameter on `_edit_overrides`;
   it was deliberately omitted.** No caller needs it — `--exclude` on an
   included file is expressed through `add_exclude`, which the include-list
   filter already honours — and two independent reviewers ruled that
   deriving the removal inside `_edit_overrides` is what "the two lists
   stay mutually exclusive **by construction**" actually asks for, since a
   parameter the caller must remember to pass is a caller obligation rather
   than a construction.
