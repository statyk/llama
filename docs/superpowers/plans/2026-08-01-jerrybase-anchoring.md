# Plan — jerrybase break anchoring (evidence-triggered + fuzzy-matched)

Spec: `docs/superpowers/specs/2026-08-01-jerrybase-anchoring-design.md`
Branch: `jerrybase-anchoring` (worktree, own `.venv`)
Baseline: `32fbf12`, 1177 passed / 7 deselected

Five tasks. Tasks 1–2 are pure additions with no behaviour change; task 3
switches the trigger; task 4 updates the two tests whose premise the new
contract invalidates; task 5 is docs. Run `./.venv/bin/pytest -q` (the
worktree's own venv — the repo-root `.venv` imports llama from the *main*
checkout and will silently test the wrong source).

---

## Task 1 — title-matching helpers in `structure.py`

**File:** `packages/llama/src/llama/structure.py` (+ `tests/test_structure.py`)

Add below the existing `norm_title` definition (anchor: the line
`return normalize_song(_STRUCTURE_PREFIX.sub("", title))`):

```python
# Interior segue separators. A merged track ("China Cat > I Know You Rider")
# is several songs; its *closer* is the last component.
_SEGUE_SEP = re.compile(r"\s*(?:->|>|→)\s*")


def fuzzy_norm_title(title: str) -> str:
    """norm_title with "&" folded to "and" first.

    `normalize_song`'s punctuation strip deletes "&" outright, so
    "Me & My Uncle" and "Me and My Uncle" normalize differently today. Folding
    before the strip collapses them. Kept separate from `normalize_song` on
    purpose: folding there would change `align()` coverage for every show at
    once, which is a later phase's decision.
    """
    return norm_title(title.replace("&", " and "))


def title_components(title: str) -> list[str]:
    """Normalized components of a possibly-merged track title, in order.

    Trailing separators produce no empty component, so a dangling ">" stays a
    segue marker rather than becoming a phantom song.
    """
    parts = [p.strip() for p in _SEGUE_SEP.split(title) if p.strip()]
    return [fuzzy_norm_title(p) for p in parts] or [fuzzy_norm_title(title)]


def _is_subphrase(short: str, long: str) -> bool:
    ws, wl = short.split(), long.split()
    if len(ws) < 2 or len(ws) >= len(wl):
        return False
    return any(wl[i:i + len(ws)] == ws for i in range(len(wl) - len(ws) + 1))


def fuzzy_title_eq(a: str, b: str) -> bool:
    """Equality for already-normalized titles, tolerating subtitles and
    parentheticals ("Mississippi Half Step" vs "... Uptown Toodeloo").

    The 2-word floor on the shorter side is deliberate: single-word shorthand
    ("Scarlet", "Help", "Estimated") is a hardcoded table's job, not a general
    rule's — a 1-word rule would match "Dew" to "Morning Dew" and to anything
    else containing the word.
    """
    return a == b or _is_subphrase(a, b) or _is_subphrase(b, a)
```

**Tests** (`tests/test_structure.py`): `&` folding both directions;
`title_components` on `"China Cat Sunflower > I Know You Rider"`, on a plain
title, and on a trailing `"Truckin >"`; `fuzzy_title_eq` accepts a 2+-word
subphrase both ways and **rejects** a single-word one (`Scarlet` vs
`Scarlet Begonias`); unrelated titles reject.

**No caller changes in this task.** Full suite must still be 1177.

---

## Task 2 — fuzzy, repeat-tolerant `anchor_breaks` + encore guard

**File:** `packages/llama/src/llama/jerrybase.py` (+ `tests/test_jerrybase.py`)

Import site (anchor: `from llama.structure import norm_title`) becomes:

```python
from llama.structure import fuzzy_norm_title, fuzzy_title_eq, norm_title, title_components
```

Add a shared candidate finder and rewrite `anchor_breaks`. Keep the existing
docstring shape and the per-track-set-names return type — only the matching and
the ambiguity handling change.

```python
def _closer_candidates(tracks: list[Track], closer: str) -> list[int]:
    """Track indices whose closing song matches `closer`.

    A merged track closes on its last component. Exact matches win outright:
    when any candidate matches exactly, fuzzy candidates are discarded, so
    "Not Fade Away" prefers the track actually called that over one called
    "Not Fade Away Chant".
    """
    target = fuzzy_norm_title(closer)
    exact = [i for i, t in enumerate(tracks) if title_components(t.title)[-1] == target]
    if exact:
        return exact
    return [i for i, t in enumerate(tracks)
            if fuzzy_title_eq(title_components(t.title)[-1], target)]
```

`anchor_breaks(tracks, event, aligned_sets=None)`:

1. Build `cands = [_closer_candidates(tracks, st.closer) for st in event.sets]`;
   if any is empty, return `None` (unchanged: a missing closer still fails).
2. Resolve right-to-left instead of demanding a unique hit: `pos[-1] =
   cands[-1][-1]`; for each earlier set take the **latest** candidate strictly
   below the following set's chosen position, returning `None` if none exists.
   (This is what rescues a PITB sandwich or a twice-played Good Lovin'.)
3. Keep the existing strictly-increasing check and the empty-`positions` guard.
4. Keep the existing index→set-name walk verbatim.
5. Encore guard, last: if `aligned_sets` is given and no set in `event.sets` is
   named `"encore"`, copy the aligned labels back over the **trailing run** of
   tracks that `aligned_sets` labels `"encore"`. Never invent a label the
   alignment did not already produce.

**No filler push.** Measurement attributed 157 of 159 disagreements to it and
the stored library is self-inconsistent about boundary filler; it is not in this
design.

**Tests** — new: `&` fold matches a closer; 2+-word subphrase matches; merged
track matched on its last component; exact-first prefers the exact track over a
longer fuzzy one; a twice-played closer resolves to the latest occurrence before
the next closer; still `None` when no candidate sits below its successor; encore
guard preserves a trailing aligned encore when the event has no encore set, and
does **not** interfere when the event does have one.

**Rewrite** `test_anchor_breaks_none_when_closer_ambiguous` (tracks
`["A", "C", "B", "C"]`, one closer `C`): under the repeat rule this now anchors
on the *last* `C`. Turn it into a positive assertion of that, and keep a
distinct negative case for the genuine failure mode.
`test_anchor_breaks_none_when_out_of_order` must keep passing unchanged.

---

## Task 3 — trigger anchoring on jerrybase's own evidence

**File:** `packages/llama/src/llama/stages/gather.py` (+ `tests/test_stage_gather.py`)

Anchor: the block beginning `result = align(tracks, canonical)` and the line
`if canonical.items and result.coverage < structure_cfg.align_coverage_threshold:`.

Restructure so anchoring is attempted whenever a single event is in hand and
wins whenever it succeeds; the coverage gate survives only as the trigger for
the **LLM realignment fallback and the low-confidence flag**:

```python
result = align(tracks, canonical)
alignment = "deterministic"
anchored = (jerrybase.anchor_breaks(tracks, event, aligned_sets=result.sets)
            if event is not None else None)
if anchored is not None:
    # Jerrybase closers are ground truth for break placement, so anchoring
    # wins outright rather than waiting for alignment to look bad. Measured
    # over 756 shows with evidence: +148 newly anchor, 0 disagree with the
    # shows that already anchored.
    result = result.model_copy(update={"sets": anchored})
    alignment = "jerrybase"
    notes.append("set breaks anchored from jerrybase")
elif canonical.items and result.coverage < structure_cfg.align_coverage_threshold:
    ... existing LLM fallback + "low-confidence structure alignment" flag,
        unchanged, minus the now-dead inner anchoring attempt ...
```

Note the dropped `canonical.items` precondition on anchoring: a tape with no
usable setlist parse can now still be structured from jerrybase.

Everything downstream is unchanged — in particular the closer tripwire's
`if event is not None and alignment != "jerrybase":` guard already suppresses
`closer_contradictions` for anchored shows, which is now the common case.

**Tests** — new: with the gd73 fixture aligning confidently (breaks `[3, 5]`)
and jerrybase closers `China Cat Sunflower`/`Eyes of the World`/`Johnny B.
Goode`, anchoring now runs *despite* high coverage and moves the breaks to
`[2, 5]` with `alignment == "jerrybase"`; and a no-setlist-parse tape still
anchors when the closers are present.
`test_gather_anchoring_rescues_low_confidence_without_llm` must keep passing.

---

## Task 4 — fuzzy `closer_contradictions`, and the tests it invalidates

**File:** `packages/llama/src/llama/jerrybase.py` (+ both test files)

Replace `closer_contradictions`'s raw-equality hit-finding (anchor:
`target = norm_title(st.closer)` / the `hits = [t for t in tracks ...]`
comprehension) with `_closer_candidates`, keeping every other behaviour: no
hits → soft note; more than one → ignored as ambiguous; exactly one → the
"not at a set break" position check.

**`test_gather_confident_but_contradicted_break_flags` premise is now wrong.**
Its closers are all real gd73 titles, so anchoring succeeds and *corrects* the
breaks instead of flagging them — which is the entire point of this change.
Rewrite it as two tests:

- anchoring succeeds → breaks corrected, no `set break` flag, and
  `alignment == "jerrybase"`;
- one closer absent so anchoring fails → the tripwire still fires exactly as
  before (this is the case the tripwire now exists for).

Sanity-check the other jerrybase gather tests rather than assuming: the venue
tests and `test_gather_set_count_ignores_encore` should be unaffected (the last
one only because the encore guard restores the tape's trailing encore, so the
numbered-set count still matches — assert that explicitly).

---

## Task 5 — docs

- `CLAUDE.md`, jerrybase bullet: it currently reads "gather uses it after
  alignment as a tripwire … and a deterministic break-anchoring corrector".
  State that anchoring is attempted whenever there is single-event evidence and
  wins when it succeeds, that closer matching tolerates `&`, subtitles and
  merged tracks, and that the tripwire now only speaks when anchoring fails.
- `config.py` config-init template: annotate `align_coverage_threshold = 0.8`
  to say it gates the LLM realignment fallback and the low-confidence flag —
  **not** jerrybase anchoring. Update the `[jerrybase]` comment's
  "all-or-nothing by design" note in `JerrybaseConfig` if it now misleads.
- No config schema change, no new dependency, no manifest change.

---

## Done when

- `./.venv/bin/pytest -q` green, with the new tests, from the worktree venv.
- `python3 anchor_variants.py` in `~/projects/llama-setlist-analysis/` still
  reports the agreed profile, and the same rule re-scored **against the real
  llama implementation** reproduces 385 → 533 with 0 disagreements.
- Both corpora re-measured (the non-Dead corpus has 0 jerrybase rows, so its
  result must be *identical* to baseline — that is the regression check).
