# Pre-registration: footnote-marker strip in `build_canonical` — predicted no-op on matching

**Status:** pre-registration only. No implementation exists yet. Registered
by a **third party** (a registrar agent) who did **not** author the
prediction below and is not implementing or testing it. This document
records the prediction, its stated mechanism, and its abort condition
*before* the change is made, against a named commit, so the record cannot
later be edited to fit the outcome.

**Registered at:** Mon Aug 31 17:47:05 EDT 2026 (from `date`, not inferred).

## Commit this registration is pinned to

Registered against commit `5261f8beaac06e6d4575c7e6f330bba2c6517511`.

Verified to exist in this repository:

```
$ git cat-file -e 5261f8beaac06e6d4575c7e6f330bba2c6517511 && echo "COMMIT EXISTS"
COMMIT EXISTS
```

```
$ git log -1 --format='%h %ci %s' 5261f8beaac06e6d4575c7e6f330bba2c6517511
5261f8b 2026-08-31 17:44:10 -0400 fix(cli): task-7 review round 1 - I1/I2/M4/M6/M7/M8/M9/M10/M11
```

At the time of registration, this repository's `HEAD` (branch
`title-correspondence`, working tree in
`/Users/shawn/projects/llama/.worktrees/title-correspondence`) was exactly
this commit, and `git status` reported a clean working tree — nothing
uncommitted, nothing staged. This registration file is the only change
being committed on top of it.

## The prediction (authored by the orchestrator, not by this registrar)

> **Prediction:** stripping trailing footnote markers from canonical item
> titles will change **only track `title` text**, on tracks whose canonical
> item genuinely carried a trailing marker. It will NOT move any of:
> `matched`, `set`, `title_source`, set breaks, coverage, or alignment
> output — on any show in the cached library.
>
> **Stated mechanism:** `structure.fuzzy_norm_title` already discards these
> characters before any comparison, so two canonical items differing only
> by trailing markers already normalize to the same string. Matching
> therefore cannot observe the strip.
>
> **Abort condition, registered in advance:** if ANY of `matched`, `set`,
> `title_source`, set breaks, coverage, or alignment output moves on any
> show, the run stops and escalates rather than being ruled on locally.
> That would mean the markers ARE load-bearing in matching, which is a
> different change than the one authorized.

## Independent reproduction of the supplied evidence

The orchestrator reported that every marked/unmarked pair normalizes
identically under `structure.fuzzy_norm_title`. This registrar re-ran the
exact command independently, using the worktree's own venv
(`./.venv/bin/python`, not a bare `python`, per the project's own warning
that a bare interpreter in a worktree can import the wrong checkout):

```
$ cd /Users/shawn/projects/llama/.worktrees/title-correspondence
$ ./.venv/bin/python -c "
from llama.structure import fuzzy_norm_title as f
pairs=[('Get Me Outta This City # %','Get Me Outta This City'),
('High Lonesome Sound * # \$','High Lonesome Sound'),
('Polly Put The Kettle On * ^','Polly Put The Kettle On'),
('Steep Grade Sharp Curves *','Steep Grade Sharp Curves'),
('Tear Down The Grand Ole Opry @','Tear Down The Grand Ole Opry'),
('Countdown to Happy New Year - Auld Lang Syne # %','Countdown to Happy New Year - Auld Lang Syne')]
for a,b in pairs: print(repr(a),'|',repr(f(a)),'|',repr(f(b)),'| EQUAL:',f(a)==f(b))
"
```

Actual output observed by this registrar (verbatim):

```
'Get Me Outta This City # %' | 'get me outta this city' | 'get me outta this city' | EQUAL: True
'High Lonesome Sound * # $' | 'high lonesome sound' | 'high lonesome sound' | EQUAL: True
'Polly Put The Kettle On * ^' | 'polly put the kettle on' | 'polly put the kettle on' | EQUAL: True
'Steep Grade Sharp Curves *' | 'steep grade sharp curves' | 'steep grade sharp curves' | EQUAL: True
'Tear Down The Grand Ole Opry @' | 'tear down the grand ole opry' | 'tear down the grand ole opry' | EQUAL: True
'Countdown to Happy New Year - Auld Lang Syne # %' | 'countdown to happy new year auld lang syne' | 'countdown to happy new year auld lang syne' | EQUAL: True
```

**Result: this registrar's independently reproduced output AGREES with the
claim.** All six pairs normalize to identical strings (`EQUAL: True` in
every row); no disagreement was observed.

## What does not yet exist at this commit

This is the "the test does not yet exist at this commit" clause — the part
that makes the pre-registration meaningful rather than a description of
work already done.

1. No test named for footnote-marker stripping exists in the `llama`
   package at this commit:

   ```
   $ grep -rni "footnote" packages/llama
   packages/llama/tests/test_structure.py:841:    # "#  [9:41]" is a footnote marker glued to a duration - stripping the
   packages/llama/tests/test_setlist.py:473:    # then stop"): a leading footnote-number marker before "w/" ("1. w/
   packages/llama/src/llama/setlist.py:248:    # carry a leading footnote-number marker before "w/" ("1. w/ Donna Jean
   packages/llama/src/llama/structure.py:758:    # behind a footnote marker like "#", which `setlist._is_junk_title` does
   ```

   All four hits are comments referencing "footnote" in unrelated contexts
   (a duration-parsing comment, a leading-marker comment in `setlist.py`,
   and a comment in `structure.py`). None is a test function, and none
   concerns stripping trailing footnote markers from canonical item titles
   in `build_canonical`.

   A broader search for test functions named after marker-stripping also
   turned up nothing relevant to this change (checked via
   `grep -rn "def test.*footnote\|def test.*marker" packages/llama/tests`
   — the matches are all about segue markers, encore markers, disc
   markers, and session markers, none about footnote-strip cleaning in
   `build_canonical`).

2. `build_canonical` does not yet strip trailing footnote markers from
   canonical item titles at this commit. Its source
   (`packages/llama/src/llama/stages/gather.py:500`) was read directly:
   after ranking parses, its only cleaning-pass calls are

   ```python
   canonical = _strip_head_banner(canonical, metadata_norms)
   canonical = _drop_artist_items(canonical, artist)
   ```

   — a head-banner strip and an artist-item drop. There is no call to any
   marker-stripping helper, and no `#`/`*`/`%`/`^`/`$`/`@` trailing-marker
   regex appears anywhere in `build_canonical` or its docstring at this
   commit. The docstring's own description of the cleaning pass
   ("head-banner-stripped and artist-item-dropped") does not mention
   footnote markers at all.

## Registrar's role and disclaimer

This registrar performed **no implementation** of the described change,
ran **no test suite** (no code was changed, so none was warranted), and
expresses **no opinion** on whether the prediction is correct or will hold
once the change is made. Its sole function was to (a) verify the facts
that are checkable right now — the commit's existence and identity, the
absence of a pre-existing test or implementation, and the
`fuzzy_norm_title` behavior on the supplied pairs — and (b) record the
prediction, its mechanism, and its abort condition durably and
verbatim, timestamped against the named commit, before any implementation
work begins.
