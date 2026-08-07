# Title-fold and structure overrides — design

Two independent but adjacent changes, both surfaced by one held show
(`gratefuldead-1990-03-29`):

- **A.** A general `-in'`/`-ing` fold at the matching layer, replacing per-song
  alias patching.
- **B.** Operator controls for show structure: an encore override, and a
  per-track "didn't match" cue in `show --tracks`.

A third topic — a rating ceiling in `winnow` with a downloads/reviews escape
hatch — was explicitly deferred. It changes *which shows llama picks* rather than
how it reports or corrects them, and it needs a measurement pass against llama's
own candidate pools rather than the whole archive. Evidence lives in
`docs/2026-08-07-lma-census.md`; do not fold it into this work.

## Motivating failure

`gratefuldead-1990-03-29` was held with:

    jerrybase set closer 'Turn On Your Lovelight' is not at a set break

The flag names the wrong song. jerrybase, setlist.fm and the LMA description all
agree Lovelight closes set 2. The actual defect is on the **encore**: jerrybase
records `Knockin' On Heaven's Door`, the taper tagged `Knocking On Heaven's
Door`, and `fuzzy_title_eq`'s three tiers (exact, subphrase, spacing-insensitive)
cover neither direction of the g-drop. So `_closer_candidates` returned `[]`.

`anchor_breaks` is **all-or-nothing** — it succeeds only if every closer matches.
Measured against the real show:

    closer 'Promised Land'             -> [6]    ok
    closer 'Turn On Your Lovelight'    -> [15]   ok
    closer "Knockin' On Heaven's Door" -> []     FAIL
    anchor_breaks(...)                 -> None

Two closers anchored **exactly**; one orthographic miss discarded both. Anchoring
declined, which is precisely the condition under which the closer tripwire is
allowed to speak — so it spoke, found Lovelight legitimately at track 16 against
`set_breaks=[7]`, and raised the hard flag.

Counterfactual, same code, apostrophe restored on track 17: anchoring resolves to
`set_breaks [7, 16]` with track 17 labelled `encore`. **The correcting mechanism
was one character from working, and its failure is what let the tripwire fire.**

The same gap also cost the setlist.fm alignment — coverage 0.882, with
`Knockin' on Heaven's Door` sitting in `structure.conflicts` as an unmatched
item. The missing break and the inability to repair it are one defect hit twice.

### Scale

Of 17,957 set rows in the vendored jerrybase index, **1,000 (5.6%)** carry a
closer containing a g-dropped word: `Good Lovin'` (437), `Going Down the Road
Feelin' Bad` (220), `Knockin' on Heaven's Door` (193), `Truckin'` (59), `Dancin'
In The Streets` (25). Each is a coin flip on the taper's spelling. jerrybase
itself carries both spellings of one song (`Going Down the Road Feelin' Bad` ×220
vs `Goin' Down The Road Feelin' Bad` ×10), so the two forms demonstrably coexist
in the ground truth.

---

# A. The `-in'`/`-ing` fold — **TABLED 2026-08-07, NOT IMPLEMENTED**

**Status: tabled at Shawn's direction. Implemented as `aa7ff5f`, then reverted
in `366df8a`. B shipped without it.** Do not implement A1 below as written — the
measurement in A5 refutes it. If A is revived, start from A5's alternative.

## A1. Fold before normalization, signalled by the apostrophe

**Rejected design (what was originally filed):** fold the *normalized* forms,
`knockin` <-> `knocking`. This is unsafe. `norm_title` strips punctuation, so by
then the apostrophe is gone and the fold must guess from word shape. Measured
collisions it would manufacture:

    sing -> sin     thing -> thin     wing -> win     king -> kin

Each lands on a real word, and `Sin City`, `Sing Me Back Home`, `The Thing` and
`King Bee` are all real LMA titles. Do not resurrect this design.

**Chosen design:** rewrite `in'` -> `ing` *while the apostrophe still exists*,
i.e. before `norm_title` runs, inside `fuzzy_norm_title`. This is structurally
identical to the `&` -> `and` fold already on the line above, and is there for
the same reason: `norm_title`'s punctuation strip destroys the signal.

```python
_IN_APOSTROPHE = re.compile(r"in'(?=\s|$|[^A-Za-z])")

def fuzzy_norm_title(title, aliases=None):
    folded = _IN_APOSTROPHE.sub("ing", title.replace("&", " and "))
    norm = norm_title(folded)
    return (aliases or {}).get(norm, norm)
```

The lookahead keeps the rewrite to word-final `in'`, so an interior apostrophe
is untouched.

Verified before adoption:

| input pair | result |
|---|---|
| `Knockin' On Heaven's Door` / `Knocking On Heaven's Door` | both -> `knocking on heavens door` |
| `Truckin'` / `Trucking` | both -> `trucking` |
| `Doin' That Rag` / `Doing That Rag` | match |
| `Playin' In The Band` / `Playing In The Band` | match |
| `Sin City`, `Sing Me Back Home`, `The Thing`, `King Bee` | unchanged — no apostrophe, no fold |

**Collision surface is essentially nil**: a token is rewritten only where the
source explicitly spells the dropped g, and it is rewritten to that same word's
spelled-out form.

**Accepted residual gap:** a taper who writes `Knockin` with *no* apostrophe
still will not match. Catching that requires exactly the unsafe blanket fold
above. This is a ruled-on limitation, not a TODO.

## A2. Why `fuzzy_norm_title` and not `fuzzy_title_eq`

`fuzzy_norm_title` feeds four call sites: `align()` (via `fuzzy_title_eq`),
`_closer_candidates`, `title_components`, and `contains_sequence`.

Placing the fold in `fuzzy_title_eq` instead would repair the closer match but
**not** `contains_sequence`, which does raw containment over normalized text with
no equality call. `winnow`'s setlist constraints would still miss `Truckin'` in a
description spelled `Trucking` — re-creating, one layer over, the exact class of
bug `contains_sequence` was shipped to fix (`bad5d4c`).

`normalize_song` / `DEFAULT_ALIASES` stay untouched, per the standing rule:
folding there would also move `grouping`, `vet_research`, `brief` and setlist.fm
artist matching, two of which generate holds, and none of which was measured.

## A3. Existing per-song patches stay

`DEFAULT_ALIASES` carries **four** entries for one song (`gdtrfb`,
`going down the road feeling bad`, `going down the road feelin bad`,
`goin down the road feelin bad` -> `goin down the road feeling bad`), and
`GD_SHORTHAND` has `throwin stones -> throwing stones`. These are hand-written
g-drop patches, and they cover the **apostrophe-less** spellings the fold
deliberately cannot reach. Keep them all. The fold's value is that *new* songs
stop needing them.

## A4. Validation (required, not optional)

Same discipline as `_NEVER_EQUAL`, whose floor was validated exhaustively against
the closer vocabulary:

1. **Vocabulary sweep.** Over the 564 distinct jerrybase closers plus the local
   corpus titles, find every pair that becomes equal *only* under the fold.
   Confirm each is one song under two spellings. Any genuine cross-song pair is
   recorded in `_NEVER_EQUAL`. Expectation is zero — the sweep is what converts
   that expectation into evidence.
2. **Corpus acceptance run.** No show's set structure may change except
   `gratefuldead-1990-03-29`, which must go from held to
   `set_breaks [7, 16]` with track 17 labelled `encore`.

A "no pairs found" result is only believable if the sweep can return non-empty at
all: run it against a known-positive case first.

## A5. Why A1 is wrong, measured — and the direction that is not

A1 shipped, passed spec review, and was **refuted by measurement at the real call
site**. Recorded here in full because the naive fold is an attractive nuisance:
it looks obviously correct, and the reasoning that kills it is not visible from
the code.

**The error in A1's premise.** A1 calls the apostrophe-less taper spelling
(`Truckin`, no apostrophe) an "accepted residual gap" that "**still** will not
match." That word *still* is false. It matched **before**. `norm_title` strips
apostrophes, so jerrybase's `Truckin'` and a taper's `Truckin` both already
normalized to `truckin`. A1 moves the canonical form to `trucking` and
**orphans** the bare spelling. A1 does not add matches; it trades one partition
of the three spellings for another.

**Measurement.** `anchor_breaks` outcome over the **535 cached shows that carry a
jerrybase event**, comparing designs against pre-change behaviour:

| design | anchors gained | anchors **lost** | anchors changed |
|---|---:|---:|---:|
| A1 (`in'` -> `ing`, pre-normalization) | 4 | **5** | 2 |
| A5 alternative (`ing` -> `in`, post-normalization) | 4 | **0** | 0 |

Identical gains — the same four shows, including both `gd1990-03-29` tapes that
motivated the work. A1's five losses are all on `Good Lovin'`, the single most
common closer in the vocabulary (437 rows), because tapers routinely write
`Good Lovin`. Two further shows silently move their encore boundary.

A vocabulary-wide proxy (every title x every closer over 612 items / 26,434
titles) had shown 24 titles lost vs 21 gained — roughly a wash. That proxy
*understated* the harm: at the call site the losses land on shows that were
anchoring correctly. **Do not judge a matching change by vocabulary-wide pair
counts; judge it by outcomes at the call site.**

**The alternative, if A is revived.** Canonicalize toward the g-*dropped* form,
post-normalization: fold word-final `ing` -> `in`, so `Trucking` joins the
`{Truckin', Truckin}` class that already existed. This is **purely additive** by
construction — it only ever merges a new spelling *into* an existing class,
never moves a class — which is a far stronger safety property than A1's
collision argument.

Guard: fold only when the stem is >= 4 characters, plus a blocklist. Stems of 3
are where the real collisions live (`sing`/`sin`, `king`/`kin`, `wing`/`win`,
`ring`/`rin`); at length 4 the only English collision found is `thing`/`thin`,
which the blocklist covers. That exception set is enumerable, and A4's sweep is
what validates it rather than this paragraph.

**Unmeasured, and required before reviving A:** this compares closer matching and
anchoring only. `fuzzy_norm_title` also feeds `align()` and `contains_sequence`.
The additive property is an argument for those call sites, not yet a measurement.

---

# B. Structure overrides

## B1. Encore override — narrow, not general

Considered and rejected: replacing `set_breaks` with general per-track set
labels. It expresses any structure, but costs a migration path for existing
`overrides.json` files for a case nobody has hit, and is far more verbose to
type. YAGNI.

**Chosen:** `Overrides.encore_after: int | None`, using the **same convention as
`set_breaks`** — the track number the encore falls *after*.

For `gratefuldead-1990-03-29`: `set_breaks: [7], encore_after: 16` gives tracks
1-7 = `"1"`, 8-16 = `"2"`, 17 = `"encore"`.

Semantics:

- `encore_after` **implies a break there**. `show.set_breaks` becomes
  `sorted(set(set_breaks or []) | {encore_after})`, so the operator does not list
  16 twice.
- `_sets_from_breaks(n_tracks, breaks, encore_after=None)` gains the parameter:
  numbered labels exactly as today, then every track past `encore_after`
  relabelled `encore`.
- `encore_after` may be set with `set_breaks` absent (a one-set show plus
  encore).
- Validation: `1 <= encore_after < len(tracks)`, and `> max(set_breaks)` when
  both are present. Out of range raises `LlamaError`, matching the existing
  `set_breaks` behaviour.

**This is what stops the override path tripping `structure_guard`.** Today
`_sets_from_breaks` emits numbered labels only, so `--set-breaks 7,16` labels
track 17 `"3"`; `expected_set_count` excludes encores while the override's three
numbered sets do not, and the guard fires `structure has 3 sets but jerrybase
shows 2`. It trades one hold for another. With track 17 labelled `encore`,
`actual` counts 2 against jerrybase's 2 and the guard passes.

**CLI:** `--set-encore N` / `--clear-encore` on `llama fix`, help text *"the
encore begins after track N (same convention as --set-breaks)"*. Redoes from
`gather`, like every other structure flag, and the hold self-clears if the
re-gather no longer reproduces it.

## B2. Per-track "didn't match" cue

**Why the existing column does not cover this:** `_format_tracks` prints
`title_source`, which says where a title *came from*, not whether it *matched*.
Track 17 read `tags` — the most ordinary value in the vocabulary — while matching
nothing. The two are orthogonal and the display carries only the first, which is
why the sole symptom was a hold naming a different song.

**The data already exists and is discarded.** `AlignResult.matched: list[bool]`
is computed per track by both `align()` and `apply_llm_alignment()`, consumed
only to derive coverage, and dropped — `Track` has no such field, so `show.json`
never carries it.

- Add `Track.matched: bool | None = None`.
- `gather` populates it from `AlignResult.matched`.
- **`None` means unknown, not matched.** On the override path
  (`overrides.set_breaks` set) `align()` never runs and coverage is forced to
  1.0, so there is no per-track match data. Rendering unknown as "matched" would
  assert something never measured.
- `_format_tracks` gains a one-character flag column: `?` = no setlist match,
  space = matched, `-` = unknown. ASCII, not Unicode — this is a fixed-width
  terminal table. A legend line prints only when a `?` appears.

One renderer change covers all three surfaces: `show --tracks` (`cli.py:841`),
`_pick_excludes` (`cli.py:642`), and `triage`.

**Not in the manifest.** `ManifestTrack` (`models.py:235`) is a separate,
deliberately narrower model, and emcee reads `manifest["tracks"]` as plain dicts
keyed on `title`/`set`. `matched` stays on `Track`/`show.json` only — the package
contract and emcee are untouched, and no manifest version bump is needed.

**Explicitly out of scope:** this surfaces tracks with no *item*. It does not
surface items with no *track* — the documented coverage gap where a partial
recording scores ~1.0 while missing half the show. Opposite direction; a track
column structurally cannot display an item that has no track. That needs its own
affordance.

## B3. Interaction between A and B

Independent, and both are wanted:

- A removes the *need* for an override on this particular show — the closer
  matches, anchoring resolves natively.
- B1 covers every other cause of anchoring declining, where no title fix exists.
- B2 would have made the original defect visible in one glance instead of
  presenting as a hold naming an unrelated song.

## B4. Testing

**A:** unit tests on the fold, including the four verified pairs and the four
no-apostrophe non-matches; the vocabulary sweep as a test; a
`gratefuldead-1990-03-29` regression asserting the encore closer matches and
`anchor_breaks` returns `[7, 16]` with a labelled encore.

**B:** `gather` tests for `encore_after` label generation, the implied break, the
range/ordering validation errors, and `structure_guard` passing where it
previously fired; a CLI test for `--set-encore` / `--clear-encore` including the
redo-from-`gather` path; renderer tests for all three cue states, `None`
included.

**Standing gate:** the full suite (1416 green at `2882773`) must stay green, and
the corpus acceptance run in A4 is a release gate, not a nice-to-have.
