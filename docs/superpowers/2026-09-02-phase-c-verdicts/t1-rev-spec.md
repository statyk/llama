# Task 1 — SPEC COMPLIANCE review (sibling title transfer, `filter_files` duplicate-listing dedupe)

# SPEC ✅ (with one Important finding against the tests and two Minor findings)

Reviewed `98d752a..852e47d` (`f943909` impl+tests, `852e47d` sweep script).
All mutation work done on a copy at
`/private/tmp/.../scratchpad/workc/t1-rev-spec`; the worktree at
`/Users/shawn/projects/llama/.worktrees/sibling-transfer` was never modified
(verified `git status --porcelain` empty, HEAD still `852e47d`).

---

## Shadowing proof (mandatory step 2) — and a correction to the run recipe

**`./.venv/bin/pytest` from a copied tree DOES NOT test the copy.** The venv's
console-script shebang is an absolute path:

```
$ head -1 <copy>/.venv/bin/pytest
#!/Users/shawn/projects/llama/.worktrees/sibling-transfer/.venv/bin/python3.14
```

so it runs the *worktree's* interpreter, gets the *worktree's* `site-packages`,
and resolves the un-sed'd `_editable_impl_llama_radio.pth` back to the worktree
source. Proven by a probe test printing `sys.path` from inside pytest:

```
P: /Users/shawn/projects/llama/.worktrees/sibling-transfer/.venv/lib/python3.14/site-packages
P: /Users/shawn/projects/llama/.worktrees/sibling-transfer/packages/llama/src
```

Concrete evidence this is not theoretical: with the sentinel planted in the
copy (`"duplicate-listing"` -> `"SENTINEL-REASON"`), `./.venv/bin/pytest
packages/llama/tests/test_junk.py -q` reported **22 passed** — a false
"mutation did not break anything". The same sentinel, run as
`./.venv/bin/python -m pytest` (which honours the copy's `pyvenv.cfg` and the
sed'd `.pth` files), went red:

```
>       assert dropped["reasons"] == ["duplicate-listing"]
E       AssertionError: assert ['SENTINEL-REASON'] == ['duplicate-listing']
packages/llama/tests/test_junk.py:227: AssertionError
1 failed, 21 passed
```

**Every mutation result below was produced with `./.venv/bin/python -m pytest`
from the copy's root, with `find <copy> -name __pycache__ -prune -exec rm -rf
{} +` before each run**, and after restoring a pristine `junk.py` byte-diffed
against `git show HEAD:packages/llama/src/llama/junk.py` (`PRISTINE RESTORED =
HEAD`). Pristine full suite from the copy: `1560 passed, 7 deselected`.

Note for future reviewers: the implementer's own mutation run was inside the
worktree, where `./.venv/bin/pytest` *is* correct — its result was valid, just
unverified. It is now independently re-verified (M1 below).

---

## Requirement-by-requirement

| # | Requirement (brief) | Verdict | Location |
|---|---|---|---|
| R1 | Collapse duplicate listings inside `filter_files` | **met** | `junk.py:145-172` (`_dedupe_duplicate_listings`), called `junk.py:212-213` |
| R2 | Runs **after** `_keep_and_exclude` for the **winning** format | **met** | call sits immediately after `matched, kept, excluded = chosen or fallback ...` (`junk.py:210-212`) — operates on the winner's kept set only |
| R3 | Key = `(basename, round(duration or 0))` | **met** | `junk.py:158-159`: `base = f["name"].rsplit("/",1)[-1]`; `key = (base, round(length_seconds(f.get("length")) or 0))` |
| R4 | Keep first copy unless a later dup carries a title the kept one lacks (then swap) | **met** | `junk.py:165-171`, `if not incumbent_title and candidate_title:` swap, else drop candidate. Titles compared `str(...or "").strip()`, so a blank/whitespace title does not count as "carries a title" |
| R5 | Excluded reason exactly `duplicate-listing` | **met** | `junk.py:168, 171` — literal `["duplicate-listing"]`, pinned by test (sentinel proof above) |
| R6 | Play-order derivation runs on the **deduped** list | **met in code, NOT PINNED** | dedupe at `junk.py:212` precedes the `orig_tracks`/`nums`/ordering block at `junk.py:215-224`. See Finding 1 |
| R7 | Step-1 test: one file kept, `clean_tag_titles` == `["Alpha"]` (title string, not count) | **met** | `test_junk.py:210-227` `test_duplicate_listing_keeps_the_titled_copy` |
| R8 | Step-1 test: dropped copy in `excluded` with reason `duplicate-listing` | **met** | `test_junk.py:226-227` |
| R9 | Step-1 test: same basename, 180 vs 420 -> both kept | **met** | `test_junk.py:230-239` `test_same_basename_different_duration_both_kept` |
| R10 | Step-1 test: clean item byte-identical through `filter_files` | **met** | `test_junk.py:242-252` — asserts kept names AND object **identity** (`f is by_name[f["name"]]`), which is what makes it mutation-sensitive |
| R11 | Step 2: recorded pre-fix failure | **met** | report §"Step 2", `assert 2 == 1`; independently reproduced by mutation M2 below |
| R12 | Step 3: full suite green | **met** | 1560 passed / 7 deselected, reproduced from the copy |
| R13 | Sweep script: walk `~/.llama/cache/md_*.json`, old vs new `filter_files` per item/format, print identifier / before+after counts / dropped names | **met** | `scripts/dedupe_sweep.py:60-73` (`load_items`), `:100-118` (both filters, print row with identifier, fmt, before=, after=, dropped=, added=) |
| R14 | Sweep run + committed + summary in commit message | **met** | `852e47d` message carries the summary line, both changed rows, the 24 spot checks, and the mutation result |
| R15 | Sweep result reproducible: exactly one changed item, `ymsb2005-12-31.flac16`, 56->28 | **met, independently reproduced** | see below |
| R16 | Every changed item is a same-basename/same-duration collapse; >=10 spot-checked and recorded | **met** | 24 pairs recorded in report + commit message; `added=[]` on both rows (verified: 2 occurrences of `added=[]`, i.e. every changed row) |
| R17 | No library show's kept set changes except the named duplicate-listing item | **met, and stronger than claimed** | see below |
| R18 | YAGNI — nothing beyond scope | **met** | 3 files, +210/-0. `junk.py`: one function + two wiring lines. `test_junk.py`: 3 tests + 1 import. `dedupe_sweep.py`: required by Step 4. No config, no CLI, no new constants, no unrelated refactor |

### Sweep reproduced independently

```
$ ./.venv/bin/python scripts/dedupe_sweep.py
ymsb2005-12-31.flac16   mp3    before=56  after=28  dropped=[...28 prefixed .mp3...]  added=[]
ymsb2005-12-31.flac16   flac   before=56  after=28  dropped=[...28 prefixed .flac...] added=[]
# items=968 item/format pairs=1936 changed pairs=2 changed items=1
```

Matches the implementer's numbers exactly. `ls ~/.llama/cache/md_*.json | wc -l`
= 968, so no items were silently skipped. The script loads OLD behaviour from
real git history (`git show 98d752ab...:junk.py` + `importlib`), not a
reimplementation — I confirmed by reading `_load_old_junk`
(`dedupe_sweep.py:41-52`); this is the right design and removes the usual
"paraphrased baseline" hazard.

### Library impact (R17)

Of 89 shows in `~/.llama/shows`, exactly one (`yondermountainstringband-2005-12-31`)
references the changed identifier at all, and its **selected** recording is
`ymsb2005-12-31.flac16.wav` — a *different* item, unchanged by the sweep. So no
library show's own kept set changes; the changed item is a sibling/donor
recording, which is precisely the item this phase exists to harvest titles
from. R17 holds strictly.

---

## Findings

**Finding 1 — Important (against the tests, not the code): R6 ("play-order
derivation runs on the deduped list") is not pinned by any test.**
Mutation M5 relocated the dedupe to *after* the ordering block and the entire
suite stayed green (`1560 passed`). This is not an academic difference — on the
real corpus item it changes observable output. The prefixed duplicates in
`ymsb2005-12-31.flac16` carry **no `track` tag** while their top-level twins
do, so:
- dedupe-before-ordering (shipped): `nums` all present & unique ->
  `ordering["order_source"] == "track-tags"` (verified live on the cached item);
- dedupe-after-ordering (M5): `nums` contains `None` for the 28 prefixed copies
  -> falls back to `"filename"`.
The shipped behaviour is the correct one; the gap is that nothing would catch a
future refactor moving the call. This is the same class as the four hollow pins
from the previous phase. Suggested fix (cheap): extend
`test_duplicate_listing_keeps_the_titled_copy` — or add one test — where the
titled top-level copies carry `track` tags and the prefixed dups do not, then
assert `ordering["order_source"] == "track-tags"`. That assertion is red under
M5 and green as shipped.

**Finding 2 — Minor: the swap can leave `kept` out of name order while
`ordering["order_source"]` still reports `"filename"`.**
`_keep_and_exclude` name-sorts `kept`; `_dedupe_duplicate_listings` preserves
*first-seen key* order and then substitutes the later titled object into that
slot. When the prefixed copy sorts before an unrelated file that itself sorts
before the top-level twin, the survivor inherits the prefixed copy's slot.
Reproduced on the shipped code:

```python
files = [mp3("band0/band1t02.mp3"), mp3("band1t01.mp3", l="240.0"),
         mp3("band1t02.mp3", title="Beta")]
filter_files(files) -> kept ['band1t02.mp3', 'band1t01.mp3'], order_source 'filename'
```

`filter_files`'s own docstring promises "kept in canonical play order", and the
filename path assumes name-sorted input. Corpus incidence is **0 of 968**
(the sweep compares ordered name lists and found no such case), and the brief
did not ask for a re-sort — hence Minor, not Important. A one-line
`kept.sort(key=lambda f: f["name"])` after dedupe would close it; flagging
rather than requiring, since it is out of the brief's stated scope.

**Finding 3 — Minor: files with no parsable `length` collapse on basename
alone.** `round(length_seconds(...) or 0)` maps both "missing" and "zero
duration" to key component `0`, so two same-basename files with no length are
treated as duplicates. This is literally what the brief specifies
(`round(duration or 0)`), so it is compliance-correct — recording it only so
the choice is a known one rather than an accident.

**No Critical findings. No spec deviations.**

---

## Mutation evidence

Protocol for every entry: restore pristine `junk.py` (byte-identical to HEAD),
`find <copy> -name __pycache__ -prune -exec rm -rf {} +`, apply mutation, run
`./.venv/bin/python -m pytest ...` from the copy root, purge again.

### M0 — sentinel (shadowing proof)
Command: `sed -i '' 's/"duplicate-listing"/"SENTINEL-REASON"/g' packages/llama/src/llama/junk.py`
Red test: **`packages/llama/tests/test_junk.py::test_duplicate_listing_keeps_the_titled_copy`**
```
>       assert dropped["reasons"] == ["duplicate-listing"]
E       AssertionError: assert ['SENTINEL-REASON'] == ['duplicate-listing']
E         At index 0 diff: 'SENTINEL-REASON' != 'duplicate-listing'
packages/llama/tests/test_junk.py:227: AssertionError
1 failed, 21 passed
```
(Same sentinel under `./.venv/bin/pytest`: 22 passed — the shadowing false
negative documented above.)

### M1 — THE NAMED MUTATION: invert the tagged-copy preference
Command: `sed -i '' 's/if not incumbent_title and candidate_title:/if incumbent_title and not candidate_title:/' packages/llama/src/llama/junk.py`
Run: `./.venv/bin/python -m pytest packages/llama/tests -q`
Red test: **`packages/llama/tests/test_junk.py::test_duplicate_listing_keeps_the_titled_copy`**
```
        kept, excluded, _ = filter_files(files)
        assert len(kept) == 1
>       assert clean_tag_titles(kept) == ["Alpha"]
E       AssertionError: assert [''] == ['Alpha']
E         At index 0 diff: '' != 'Alpha'
packages/llama/tests/test_junk.py:225: AssertionError
1 failed, 1157 passed, 7 deselected
```
**Exactly the required signature**: the failure is a *title-string* mismatch
(`['']` vs `['Alpha']`) on line 225, and `assert len(kept) == 1` on line 224
passed — proving a count-based test would have stayed green. Acceptance
criterion satisfied, independently of the implementer's run.

### M2 — delete the dedupe wiring entirely (probe for a hollow pin)
Command: removed both lines `kept, dup_excluded = _dedupe_duplicate_listings(kept)` / `excluded = excluded + dup_excluded` from `filter_files`
Run: `./.venv/bin/python -m pytest packages/llama/tests scripts packages/herder/tests packages/emcee/tests -q`
Red test: **`test_junk.py::test_duplicate_listing_keeps_the_titled_copy`**
```
>       assert len(kept) == 1
E       AssertionError: assert 2 == 1
packages/llama/tests/test_junk.py:224: AssertionError
1 failed, 1559 passed, 7 deselected
```
Independently reproduces the implementer's Step-2 baseline failure. **Not** a
hollow pin — deletion is caught.

### M3 — "both kept" test: drop duration from the key
Command: `sed -i '' 's/key = (base, round(length_seconds(f.get("length")) or 0))/key = (base, 0)/'`
Red test: **`test_junk.py::test_same_basename_different_duration_both_kept`**
```
>       assert {f["name"] for f in kept} == {"band1t01.mp3", "band99/band1t01.mp3"}
E       AssertionError: assert {'band1t01.mp3'} == {'band1t01.mp...band1t01.mp3'}
E         Extra items in the right set: 'band99/band1t01.mp3'
1 failed, 1195 passed, 7 deselected
```
Not hollow — the 180/420 test can fail.

### M4 — "clean item byte-identical" test: return copies instead of the same objects
Command: `sed -i '' 's/return \[winners\[k\] for k in order\], excluded/return [dict(winners[k]) for k in order], excluded/'`
Red test: **`test_junk.py::test_clean_item_byte_identical_through_filter_files`**
```
>           assert f is by_name[f["name"]]
E           AssertionError: assert {'name': 'gd73-06-10d1t01.mp3', ...} is {'name': 'gd73-06-10d1t01.mp3', ...}
1 failed, 1195 passed, 7 deselected
```
Not hollow — the identity assertion (not just the name list) is what pins it,
and it fires.

### M5 — move the dedupe to AFTER play-order derivation
Command: relocated both dedupe lines to sit immediately before `return kept, excluded, ordering`
Run: `./.venv/bin/python -m pytest packages/llama/tests scripts packages/emcee/tests packages/herder/tests -q`
Result: **MUTATION DID NOT BREAK ANYTHING** — `1560 passed, 7 deselected`.
This is Finding 1 (Important). Live evidence that the mutation is behavioural,
not inert: on `~/.llama/cache/md_ymsb2005-12-31.flac16.json` the shipped code
yields `ordering == {'order_source': 'track-tags', 'reordered': False, 'format':
'VBR MP3'}` because the prefixed duplicates carry no `track` tag and are gone
before `nums` is computed; under M5 the `None`s survive into `nums` and the
ordering silently degrades to `filename`.

---

## Summary

Every requirement in the brief is met by the shipped code, the named acceptance
mutation kills exactly the intended test with exactly the intended
title-string signature, and none of the three new tests is hollow (M2/M3/M4
each turn one red). The sweep is independently reproducible — 968 items, 1
changed item, `ymsb2005-12-31.flac16` 56->28, `added=[]` — and no library
show's selected recording is affected. The one Important finding is a missing
pin on R6, not a defect in the shipped behaviour.
