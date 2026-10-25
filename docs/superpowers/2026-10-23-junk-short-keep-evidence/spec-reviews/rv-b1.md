Foundation: SOUND -- the diagnosis (short-only drops are mostly real show content, the tag separates junk, positional overrides re-point silently on insertion) checks out against the code and the R' harness outputs; the defects are in interfaces and in the migration's version-skew story, not in the premise.

- **[Critical] A pre-change binary silently ignores, then deletes, the migrated filename keys**
  - Where: 4.3 "When. Once, after the new code is installed and before the first gather under it. The guard in 4.1 enforces the order."
  - Problem: The 4.1 guard protects only new code from legacy files. Nothing protects migrated files from old code. `Overrides` is a plain `BaseModel` (pydantic's default `extra="ignore"`), so a v2.17 binary reads a migrated `overrides.json` as having no title, break or encore overrides. Its gather then ships without the operator's corrections and raises no error. Every old-binary `_edit_overrides` call re-dumps the model and so drops `titles_by_file`/`breaks_after`/`encore_after_file`. That includes an unrelated edit such as `fix --set-venue` or `--exclude`.
  - Evidence: models.py:204-217 (no `model_config`); cli.py:1393-1446 (`read_overrides` -> `model_copy` -> `write_artifact(show_ws.overrides, data)`). The installed CLI is a signed release binary, `/Users/shawn/.local/bin/llama` (Mach-O, installed 2026-10-23 18:41, so v2.17). The migration script runs from the repo venv. So the two binaries will coexist from merge until the next release is cut and installed.
  - Failure scenario: The branch merges and `python scripts/rekey_overrides.py --apply` runs from `.venv`. The operator then runs `llama triage` or `llama fix gratefuldead-... --set-venue ...` from `~/.local/bin`. That show's 3,203-title share of re-keyed data is dropped from `overrides.json`, and the redo ships `unresolved`/tag titles where the operator's titles were. 4.3's undo now refuses, because the file is no longer byte-identical to the migration's output. Recovery means hand-merging `overrides.pre-rekey.json`. A `while true; do llama run resume --all` loop on the old binary does the gather half of this unattended.
  - Setup and likelihood: The merge-then-release gap that every release so far has had, plus any old-binary command touching one of 606 shows. Likely unless the procedure forbids it.
  - Suggested fix: Make old binaries fail loudly on a migrated file. The migration writes a tombstone the v2.17 model rejects (e.g. `"set_breaks": ["rekeyed"]`, which fails `list[int]`), and the new model accepts and ignores it. Also state the order: stop any sweep loop, install the new release binary and verify `llama --version`, then migrate, with the script refusing to `--apply` unless the `llama` on PATH reports the new version. This adds one sentinel value, one check and a runbook paragraph.

- **[Important] `set_breaks: []` (structure override, no breaks) has no defined mapping, and the guard's "non-empty" lets it through**
  - Where: 4.1 "Gather refuses a show whose `overrides.json` still has a non-empty legacy key"; 4.3 "with the legacy keys removed and the filename keys added"; 4.2 "`--untitled`".
  - Problem: Gather treats `set_breaks is not None` as the structure-override path. So `[]` means "forced single set, alignment skipped", which is not the same as "no override". The spec never says whether `breaks_after` is `list | None` with `[]` meaningful, how the migration maps `[]`, whether new gather still honours a legacy `[]`, or what `--untitled` (which writes `set_breaks=[]`) now writes.
  - Evidence: gather.py:1658 and 1982 (`overrides.set_breaks is not None or ...`); cli.py:1819 (`--untitled` writes `set_breaks=[]`). Library: `delmccouryband-2008-05-24/overrides.json` has 18 titles plus `"set_breaks": []`, and its show.json has every track in set "1".
  - Failure scenario: The migration maps titles and "removes the legacy keys", so `set_breaks: []` becomes absent and `breaks_after` is unset. The next gather runs alignment, may relabel sets or raise a low-confidence or structure flag, and loses the operator's flattening. An implementer reading "non-empty" literally might instead leave `[]` in place for a future `--untitled` show. New gather then either keeps honouring a legacy key, which the spec says it never does, or ignores it.
  - Setup and likelihood: 1 show today, and every future `--untitled` show. Certain on that show.
  - Suggested fix: Define `breaks_after: list[str] | None`, where `[]` is a valid override. The migration maps `[] -> []`. The guard's legacy test is `titles` non-empty, or `set_breaks is not None`, or `encore_after is not None`. `--untitled` writes `breaks_after=[]`. Add a test on the delmccoury shape. This is a few lines of definition.

- **[Important] The staleness guard recomputes "what gather keeps" differently from gather, so it permanently refuses positional edits on protected shows**
  - Where: 4.2 "every positional translation applies the staleness guard `--suggest-titles` already has (C1): the filename list `show.json` holds must equal what the current metadata and overrides keep"; 2.4 "Every other `filter_files` caller uses the default: siblings, `select_recording`, `best_donor`, corroboration."
  - Problem: The C1 guard recomputes `kept` as `filter_files(..., readmit=include)` minus `exclude`, with the default keyword. The count-match protection runs only inside `gather.title_inputs`. On a show where the protection fired, show.json lacks the untagged files and the recomputation has them, so the guard always reports "stale" and tells the operator to run `llama redo --from gather`. That redo reproduces the same mismatch. The spec's caller list also omits three other places that run the lossless-format filter for the selected recording: `lossless_titles._lossless_map` (slice C's stem bijection against `recovery_basis`), gather.py:1338 (the 2b "format sibling tagged" note), and `correspondence.sibling_item_durations`.
  - Evidence: cli.py:2853-2895 (`kept, _, _ = filter_files(...)`, then `if kept_names != track_names: ... run llama redo ... --from gather`); lossless_titles.py:117-128; gather.py:1333-1338.
  - Failure scenario: On `ratdog-2007-08-12`, `fix --set-title 5=...`, `--set-breaks` or `--set-encore` refuse forever, and the printed remedy does nothing. On the same 3 shows, slice C sees an mp3 basis without the untagged files and a FLAC set with them, so the bijection fails and C declines silently.
  - Setup and likelihood: The 3 protection shows today, plus every future one; certain whenever the operator edits them.
  - Suggested fix: Either drop the guard for single-number writers, or have it call the same helper that computes `title_inputs`' final kept list. Dropping is cheaper and arguably right: a number translated through show.json is exactly the file the operator saw in `show --tracks`, the resolver already refuses a key whose file is not kept, and `--exclude N` has never had the guard (cli.py:1489-1509). In either case, name every lossless-format caller that must receive `keep_untagged_short`.

- **[Important] "Same treatment as `Track.included`" leads an implementer to stamp `short_kept` too late, which makes the coverage clause inert**
  - Where: 2.5 "Gather stamps `Track.short_kept: bool = False`. ... the same treatment as `Track.included`"; 3 "`and not t.short_kept`" in the same comprehension.
  - Problem: `included` is stamped at the end of `compute_gather`, after alignment, taper, jerrybase and every coverage computation. A `short_kept` stamped in the same place is always False when `_songish_coverage` runs, from `align()`, `apply_llm_alignment` or the taper's coverage check. The unit test 6(f) names ("`short_kept` in `_songish_coverage`") passes anyway, because it builds Tracks by hand. The R' harness measured the intended behaviour through a filename-keyed global, so it cannot catch this either.
  - Evidence: gather.py:2007-2010 (`t.included = t.filename in forced`, after structure); structure.py:1129, 1186-1188, 1253; harness `spec/dump_rp.py` `cov()` (filters on `KEPT` by filename).
  - Failure scenario: The candidate arm shows about 43 extra `low-confidence structure alignment` holds, which are the ones section 3 says it removes. Acceptance 6(a) would catch it as a count difference, but only after a full arm run, and only if nobody "explains" it away.
  - Setup and likelihood: Moderate. The spec points at exactly this idiom.
  - Suggested fix: Say that `short_kept` is set when the Track is built, inside `resolve_titles` from `ordering["short_kept"]`, before any alignment. Add a gather-level test in which a short-kept unmatched track does not lower coverage.

- **[Important] Briefing reuse "over the tracks that are not `short_kept`, matched by filename" leaves `set_breaks` undefined, and the 1,377 figure was measured without most of `briefing_reusable`**
  - Where: 5.2 "change `replay.briefing_reusable` to compare the broadcast fields over the tracks that are not `short_kept`, matched by filename ... 1,377 of 1,533 changed shows keep their briefing".
  - Problem: `briefing_reusable` also compares `o.set_breaks != n.set_breaks`, and those are positional ints. Any track inserted before a break changes them, so a literal implementation reuses almost no multi-set briefing. The harness behind 1,377 compared only title, set and segue on the matched tracks. It never ran `set_breaks`, date, venue, city, narration or `briefing_guard`, so the figure is an upper bound and the bulk apply's LLM sizing rests on it. The spec also does not say whether this branch implements the change: 6(f) has no test for it, and 5 says "planned separately".
  - Evidence: replay.py:240-262; `~/.llama-harness/piece45/spec/m6_final.py` (`same = [(title,set,segue)...]` only).
  - Failure scenario: The implementer keeps the `set_breaks` leg. Most of about 1,000 delivered Dead shows (two sets plus encore, a restored `Drums`/`St. Stephen` in set 2) then need a fresh brief: around 1,000 extra `brief` calls on the 5x plan, against a plan sized for 156.
  - Setup and likelihood: Likely whenever the leg is copied literally.
  - Suggested fix: Define the comparison as the per-track tuples over matched non-`short_kept` tracks, plus the break-after filenames, plus the show-level fields and the guard. State which branch owns the change, and re-measure the 1,377 with the real function. This adds one sentence and one replay run.

- **[Important] The re-delivery of "only the 37" is stated as a list, not a mechanism, and the list drifts while emcee keeps voicing**
  - Where: 5.3 "The 37 voiced shows where the rule restores music are approved for `deliver --replace-voiced`"; "Delivered unvoiced shows are re-delivered".
  - Problem: `deliver` accepts batch selectors (`--state`, `--profile`, `--artist`, `--run`) together with `--replace-voiced`. A batch run with that flag discards voicing on every voiced destination it selects, including the 28 minor shows, and voicing cannot be restored. The 65-voiced / 1,026-unvoiced split is also a snapshot. Any `emcee run` between now and the apply voices more of the 1,534. Those shows then sit outside both lists: refused at re-delivery, which is safe, but their restored music never airs and nobody is told.
  - Evidence: cli.py:2451-2505 (selectors plus `replace_voiced`, passed to `_deliver_batch`); the 37 rows in `voiced-severe-final.json`.
  - Failure scenario: A wave runs `llama deliver --state delivered --replace-voiced --yes` "to be safe". Then 28 minor shows lose paid TTS. Alternatively, emcee voices 50 more changed shows before the apply, and their restorations go missing without anyone noticing.
  - Setup and likelihood: Plausible across a multi-wave bulk apply over ~1,100 shows.
  - Suggested fix: Bind the mechanism. `--replace-voiced` is used only per name, from the 37-slug file. At apply time the voiced set is recomputed and any newly voiced changed show goes back to the operator. Either `emcee run` is held on change-list shows until re-delivery, or the plan accepts the drift and lists it.

- **[Minor] The migration's consistency checks do not cover `exclude`/`include`**
  - Where: 4.3 step 1, "These checks prove the stored positions and the stored `show.json` agree."
  - Problem: The checks prove the titles and breaks match show.json numerically. They do not prove that show.json was gathered under the current `exclude`/`include`. A `fix --exclude ... --no-run` (or a hand edit) leaves positions that match a stale show.json, while the operator may have meant post-exclusion numbering.
  - Evidence: The spec's checks; `m4_migrate.py` checks the same set. My read-only check over the 606 found that operator-excluded entries in show.json equal `overrides.exclude` ∩ files, and that no `include` is left un-applied: 0 mismatches.
  - Failure scenario: In a future window between `--no-run` and the migration, the re-key is applied against a show.json the overrides no longer describe.
  - Setup and likelihood: Rare, with 0 cases today.
  - Suggested fix: Add the refusal "show.json's operator-excluded set, or its `included` tracks, disagree with `overrides.json`". It costs about 5 lines and refuses 0 shows today. Separately, delete or rename the backup after a successful `--undo`, so that a later re-migration backs up the then-current file.

- **[Minor] The 2.3 separator list reads as splitting on every hyphen**
  - Where: 2.3 "split into parts on `/ , & + ; and - > ~ |` (including ` - `, `-->`)".
  - Problem: The harness splits on ` - `, `--+` and `-?>`, never on a bare `-` (`rprime.py` `SPLIT`). Read literally, the spec splits `re-tune`, `warm-up`, `cut-in`, `fade-in` and `sound-check` into a non-junk part (`re`, `warm`, `cut`), so those are kept.
  - Evidence: rprime.py:9.
  - Failure scenario: A `re-tune` file is kept; the fallout is one short tuning clip airing.
  - Setup and likelihood: Depends on the implementer's reading.
  - Suggested fix: List the exact separators and say that a bare intra-word hyphen is not one. Use the regex from `rprime.py` as the reference.

- **[Minor] The non-performance terms `radio` and `DJ` "matched anywhere" hit real song titles in this library's cache**
  - Where: 2.3 test 1, "`radio`, `DJ`/`DJ's` ... matched anywhere in the tag".
  - Problem: The cache holds tags such as `Mohammed's Radio` (40), `Radio Blues` (34), `Jesus on the Radio`, `Midwest Gospel Radio >`, `Border Radio`, `Car Radio`, plus `DJ Logic / Jam` (a sit-in musician). Any of them, short on its tape, is dropped as non-performance. That reproduces today's behaviour, so it is no regression, but the operator's rule says to omit as little as possible.
  - Evidence: `grep` of `~/.llama-harness/piece45/dump.jsonl` titles.
  - Failure scenario: A two-minute `Jesus on the Radio` on a long-jam tape stays dropped, and the show keeps its hole.
  - Setup and likelihood: Rare (0 among today's 34 non-performance drops).
  - Suggested fix: Record it as an accepted limitation under 7, or anchor `radio`/`DJ` to a qualifier (`radio ad|spot|promo|broadcast|interview|talk`, `DJ talk|rap|intro`). Premise 3's sweep would size it.

- **[Minor] The protection and the interior test ignore operator `include`/`exclude`**
  - Where: 2.4, "dropped together when an admissible list has exactly as many entries as the final kept list *without* them", "Untagged files in the leading or trailing run drop".
  - Problem: The second `filter_files(..., keep_untagged_short=False)` still applies `readmit`. An untagged candidate the operator has `--include`d therefore comes straight back, so the final count is the "with" count, D does not fire, and the protection quietly does nothing. It is also unstated whether such a file counts as a candidate. Interior/edge is decided inside `_keep_and_exclude`, before readmission and before operator exclusion, so an operator-excluded first track can leave an "interior" untagged file at the edge.
  - Evidence: junk.py:256-266 (readmit runs after the arms); gather.py:1124-1135 (exclusion runs after the filter).
  - Failure scenario: An operator-included untagged interior file on a D-count tape: D titles are lost and the show holds.
  - Setup and likelihood: Rare.
  - Suggested fix: State that operator-included files are never protection candidates, and accept the pre-exclusion interior test as a documented limitation. This is two sentences.

- **[Minor] The "tag" definition matches neither `_track_number` nor the tag rung**
  - Where: 2.2, "its own `title`, else its original's `title` (the same rule `_track_number` uses ...)".
  - Problem: `_track_number` always takes the original's tag for a derivative; it is not "own, else original". The tag rung (`clean_tag_titles`) reads only the file's own `title`. So 42 of the 3,547 short-only drops are "tagged" only through their original, e.g. `ALO2013-08-01d3T04.mp3` <- `Eulogy for Jerry Garcia >` and `builttospill-1997-10-13 1-001 start.mp3` <- `October 1997 / early all-ages show`. These are kept even at a tape edge and ship `""`/`unresolved` unless format recovery fires.
  - Evidence: junk.py:83-88; titles.py:236; count from `dump.jsonl`.
  - Failure scenario: Extra edge files are kept and extra holds appear; the spec counts only the 12 placeholder-tagged files.
  - Setup and likelihood: 42 files today; the worst case is a hold.
  - Suggested fix: Fix the parenthetical and add the 42 to 2.2's "Consequence" (or define the tag as the one the tag rung will ship).

- **[Minor] The residual spam path under strict surface (c) is not written down**
  - Where: 2.3, "It means a spam clip that happens to match the item's naming convention still drops".
  - Problem: The tripwire catches only spam-shaped tags. A short clip that follows the item's naming convention and carries a song tag is now admitted. The canonical spam file is tagged `Morning Dew` (section 7), so a song tag is the real spam shape, and today the short arm would have dropped such a clip.
  - Evidence: Section 7's spam example; junk.py:122-124.
  - Failure scenario: A spam upload named `gd73-06-10d3t09.mp3`, tagged as a song and 60 s long, airs.
  - Setup and likelihood: Very rare (0 of 3,547), but this is a strict surface.
  - Suggested fix: Add it to section 7's accepted limitations in one line. Optionally, require a kept short file's track tag, when present, to fall within the tape's track-number sequence.

- **[Minor] Fix behaviour is undefined when `--exclude`/triage exclusion names a file that carries a filename key**
  - Where: 4.1, "A key naming a file not in the final kept list raises `LlamaError` ... `fix`'s unit rolls an edit back on it."
  - Problem: Excluding a titled file, or a break or encore file, now fails only after the redo starts, with a gather error. Nothing says whether `fix` should refuse up front or drop the title key itself. A break key must not be dropped silently, because sets would merge.
  - Evidence: Spec 4.1; cli.py:1393-1446.
  - Failure scenario: `fix X --exclude 7` on a show with a title on 7 rolls back with a resolver message, and the operator has to work out the two-flag combination.
  - Setup and likelihood: Occasional; recoverable.
  - Suggested fix: Have `fix` refuse up front, before any work, and name the key and the `--clear-*` flag that resolves it.

- **[Minor] The apply lists must be generated after the migration; the scratch re-key should be the migration's own code**
  - Where: 5.1, "The replay harness applies the same re-key to its scratch copy when it meets legacy keys".
  - Problem: `input_digests` includes `overrides.json` (replay.py:104). Any list a pre-migration arm produces has stale digests for the 606 re-keyed shows, so `reapply --from-list` skips them all as changed. The R' harness's re-key (`dump_rp._install_rekey`) is also a separate algorithm without the refusal checks.
  - Evidence: replay.py:89-104; `spec/dump_rp.py:80-110`.
  - Failure scenario: The apply run skips 606 rows, and a wave has to be re-run.
  - Setup and likelihood: Likely if the arms run before the migration.
  - Suggested fix: Say that the apply-list arm runs after the migration, and that the harness's scratch re-key imports `rekey_overrides`' mapping function.

- **[Minor] Counts that disagree inside the spec**
  - Where: Why, "untagged 197", against 2.4's "99 interior, 37 edge"; 5.2's "1,534 shows the rule changes" against "1,377 of 1,533".
  - Problem: Under ruling 3, 58 census-"untagged" files are now tagged (timestamped `moe` banter, `tmp`, `d1t01`, `Track 9`, `42`, `7-11`; 20 of them at an edge), which accounts for the 197 vs 136 gap. 1,533 is 1,534 minus the one held no-file show. Neither is explained, and the "12 placeholder-tagged" figure undercounts the 58.
  - Evidence: `spec/rp_files.jsonl` (`tagged` False, `rp_tagged` True: 58); m6_out.txt.
  - Failure scenario: An acceptance reader cannot reconcile the numbers in 6(a).
  - Setup and likelihood: Certain, but cosmetic.
  - Suggested fix: Add one sentence for each.

- **[Minor] The apply side-effects on the 15 newly-held delivered shows and the 28 minor voiced shows are not stated**
  - Where: 5.3, "Delivered unvoiced shows are re-delivered"; "A minor show may be re-gathered in the library."
  - Problem: 15 delivered shows become held (m3_final: added by state, delivered 15). The deliver gate refuses them, so the station keeps the old copy with the hole while the library says held. Re-packaging the 28 minor voiced shows re-downloads their purged audio, and nothing ever purges it again because those shows are never delivered.
  - Evidence: m3_final.txt; CLAUDE.md deliver/purge section.
  - Failure scenario: Wasted downloads, and the library and station diverge on 43 shows.
  - Setup and likelihood: Certain, but low cost.
  - Suggested fix: State that the 28 are skipped (not re-packaged) until the re-voice-later decision, and that the 15 go through triage before re-delivery.

### Unverified premises
1. **No pre-change llama touches `~/.llama` after the migration.** Contradicted by the setup unless the procedure enforces it: `~/.local/bin/llama` is a release binary and the script runs from `.venv`. Cheapest test: `which -a llama; llama --version; pgrep -fl "llama run"` immediately before `--apply`.
2. **1,377 briefings are reusable.** Measured with title, set and segue only. Test: run the changed `replay.briefing_reusable`, including `set_breaks` and `briefing_guard`, over the candidate arm's changed shows.
3. **Section 3's 43-of-46 removal survives in shipped code.** It depends on where `short_kept` is stamped. Test: a gather-level fixture with an unmatched short-kept track and an asserted coverage.
4. **The protection's 3 shows are all of its blast radius.** True for the filter. Unmeasured for slice C and for the C1 guard (finding 3). Test: on the candidate arm, list the shows where `lossless_titles` returns `NO_LOSSLESS` but did not at base.
5. **Spec premise 5 (no other positional key).** My grep found `Overrides.titles/set_breaks/encore_after` read only in gather, cli (fix/triage/show/`_edit_overrides`), scripts/replay_holds.py, taper_probe.py and title_hygiene_probe.py. That matches the spec, so this premise is confirmed and needs no test.
6. **Transmitter tolerates re-delivered shows inside its lead window.** Its code re-plans on "package changed" and refuses only when an on-air show's encode is missing (pipeline.py:235-290). This looks fine. Cheapest test: none beyond spacing re-delivery waves, so that shows inside the current lead window are delivered last.

TOTAL: 16 findings (1 Critical, 5 Important, 10 Minor)
