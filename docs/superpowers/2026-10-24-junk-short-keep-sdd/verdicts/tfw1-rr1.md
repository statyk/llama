# tfw1-rr1: re-review of FW1 fix round 1 (bcfeef4..1bcccd1)

### Finding Verdicts

- **C-1 (Critical): in groups with no `_vbr` copy, name order kept the stale, misplaced copy** — ADDRESSED.
  - `packages/llama/src/llama/junk.py:409-425`: `_derivative_preference` returns `(vbr != PREFER_VBR_DERIVATIVE, stale, name)`, where `stale` means the copy's stem differs from its original's stem. This is the reviewer's key exactly.
  - Pinned on the real gd1984 capture by `test_format_choice_and_derivatives.py::test_gd1984_stale_copies_lose_to_the_copies_named_after_their_originals`. It asserts track 1 is `d1t01`, U.S. Blues (`d2t11`) is last, Scarlet (`d2t01`) follows `d1t10`, and both stale copies are `duplicate derivative`.
  - gd1985 is pinned by `test_gd1985_baby_blue_stays_the_encore`.
  - Check I ran on the 23 non-`_vbr` groups in `m1b_group_shapes-r1.json`: in **23 of 23**, the kept copy's stem equals its original's.
  - Check I ran on all 1,947 plain+`_vbr` groups the dedupe collapses in the cache: every one is a plain copy named after its original plus `<orig>_vbr`. So no stale-plain/`_vbr` mix exists for step 1 to decide wrongly.
  - The cache has no group of three or more copies (`m1b` shapes: 1,947 pairs plus 23 non-`_vbr` pairs).
  - The fixtures' `files` entries match `~/.llama/cache/md_<id>.json` field for field (slim capture shape, the same 191 and 117 names).
- **I-1 (Important): the copy choice ignored `overrides.exclude`, so excluding the winning copy silently lost the song** — ADDRESSED.
  - The fix is the preferred one. `gather.py:1055-1057` passes `frozenset(overrides.exclude)` into `filter_files`, which forwards it as `exclude` → `_choose_format(avoid)` → `_dedupe_derivatives(kept, avoid)` (`junk.py:578-579`, `:494`).
  - An avoided name is left out of grouping and of the drop check (`junk.py:450`, `:456-457`). It stays in the filter's `kept`, and `final_kept` drops it as `operator-excluded` (`gather.py:1066-1074`).
  - The legacy `else` arm never reads `exclude` (`junk.py:580-598`). That is pinned against the v2.17.0 model by `test_the_exclude_pass_through_leaves_the_legacy_filter_alone`.
  - Play order is unchanged. The avoided copy now enters `nums` from `kept`, where bcfeef4 put it in `order_nums` from `deriv_dropped`, so the multiset of track numbers is the same.
  - Other pins: `test_an_operator_exclude_of_the_plain_copy_keeps_the_vbr`, and `test_sci_ships_the_same_songs_at_either_preference` (the same 25 originals at both values, no `matched no file` warning).
  - The preference comment was corrected (`junk.py:398-405`), but see N-2.
  - Re-measure: `m2_changed-r1.json`, `m2_summary-r1.json` and `m3_changed-r1.json` are byte-identical to r0.
    - 23 shows change and 414 `duplicate derivative` drops.
    - 0 shows with other drops, 0 with adds, 0 losing a song.
    - The same 20 selection changes.
  - `m2-r1` shows no `exclude ... matched no file` warnings. The 10 `include` warnings come from pre-existing entries on db2003-08-15, db2003-11-28 and sci01-08-01.

Covering tests: the fix report names the six new tests and gives RED (5 failed / 17 passed on bcfeef4, each with its reason), GREEN (140 passed over the three junk test files), the full suite (5394 passed, 1 skipped, 8 deselected), and three mutants each failing exactly its predicted tests. I did not re-run them: nothing in the code raised a doubt that those runs leave open.

### New Breakage in the Fix Diff

- **N-1 (Minor, latent). The running-time format choice now double-counts an operator-excluded duplicate copy.**
  - Where: `junk.py:494-500`. `secs = _kept_running_time(fmt_kept)` runs after `_dedupe_derivatives(fmt_kept, avoid)`, and an avoided copy is never dropped.
  - Effect: when the operator has excluded one copy of a doubled pair, both copies count toward that format's time, where bcfeef4 counted the song once. This breaks the docstring's own invariant at `junk.py:483-484` ("a format listed twice must not win on its doubled time").
  - It only matters when two or more formats are configured (`flac`: `Flac`, `24bit Flac`) and the excluded copies are derivatives in one of those formats. The library is `mp3`, a single format, so no measured show is affected. This is the implementer's concern 2.
  - Suggested fix: compute `secs` over `fmt_kept` without avoided files that share an `original` with a non-avoided kept file.
  - Do not subtract every excluded file. That could flip the format away from the one the operator's filename-keyed overrides were written against.
  - Not blocking.
- **N-2 (Minor, documentation). The comment on `PREFER_VBR_DERIVATIVE` overclaims.**
  - Where: `junk.py:402-403`, "Set True to keep the `_vbr` copy instead; nothing else needs to change."
  - Why it is wrong: with the flip, sci1999-12-31 ships 5 short songs twice. Its `overrides.include` names the plain short copies, which the flip drops as duplicates, and `include` re-admits a dropped duplicate as the brief requires. The test docstring (`test_format_choice_and_derivatives.py`, `test_sci_ships_the_same_songs_at_either_preference`) says so. This is the implementer's concern 1.
  - The comment should say that a flip must revisit `include` entries naming the plain copy. That is the deferred M-2 territory.
  - A code-level option for M-2: treat an `include`d copy like an avoided one, preferred as the winner. The operator's explicit choice would then never be dropped, and the other copy would go. That would make the flip a true one-line change.
  - Not blocking while the flip is off.

No Critical or Important breakage:
- `short_keep=False` is untouched, and `_dedupe_duplicate_listings` is untouched.
- The `readmit` block and the ordering block are unchanged.
- `ordering["short_kept"]` never names a dedupe-dropped copy. It can name an avoided, operator-excluded copy, but that was already true at bcfeef4 for any excluded non-duplicate. Its readers are membership tests over final tracks (`gather.py:1413`, `titles.py:537`), so it is harmless.
- `select_recording.py:63` and `gather.py:254` call `filter_files` without `exclude`. That is correct, since overrides are per selected show. The count per original is the same either way.

### Out-of-Scope Observations

- Implementer concern 1 (a `_vbr` flip doubles 5 sci songs via includes): real, as N-2 above. It belongs with M-2 and should be resolved before anyone flips the constant.
- Implementer concern 2: the format choice counts excluded copies in general, not only duplicates. That was already true before this fix and is defensible: the operator's excludes are keyed to the format chosen when they were written, so counting them stays stable. Only the duplicate double-count (N-1) is new.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage. Two Minor notes (N-1, N-2) go to the ledger for Checkpoint C / M-2.

Checks run (log: `$D/tfw1-rr1/tfw1-rr1.log`):
- `cmp` of the r0 and r1 measurement outputs.
- The 23/23 stem check on the non-`_vbr` groups.
- The 1,947-pair shape check on the `_vbr` groups.
- Read-only `filter_files` runs on the cache items mp1988-01-30.sbd, wd2013-07-05, deadco2022-07-10 and ttb2022-07-08.
- A fixture-versus-cache field comparison.
- `llama.__file__` resolves inside the worktree.
