Foundation: SOUND -- the diagnosis (the short arm drops real show content, and the tag separates junk from music) holds against rp_files.jsonl and the arms; the defects below are in the migration's safety envelope and the interfaces, not in the premise.

- **[Critical] Old binaries silently ignore and then erase the new filename keys (version skew)**
  - Where: 4.1 "The legacy guard ... So no gather under the new code can ever apply a stale number"; 4.3 "When. Once, after the new code is installed"
  - Problem: the guard protects only against the NEW code reading OLD keys. The reverse direction is not covered. Any v2.17-or-earlier `llama` reading a migrated `overrides.json` silently drops `titles_by_file`/`breaks_after`/`encore_after_file`. Its `fix`/triage then rewrites the file without them.
  - Evidence: `Overrides` has no `extra="forbid"` (models.py:204-217, as CLAUDE.md says, deliberately permissive), and `read_model` is a plain `model_validate_json` (workspace.py:47-48). Measured with the repo venv: `Overrides.model_validate({"titles_by_file": {"a.mp3": "x"}})` returns an empty model. `_edit_overrides` (cli.py:1393-1446) does a model_copy plus `write_artifact` of the whole model, so any old-binary `fix --set-venue/--exclude/--narration` or triage edit writes the file back with the new keys gone. `~/.local/bin/llama` is a 17 MB release binary, and the operator's sweep loop and `fix`/triage run from PATH.
  - Failure scenario: the operator runs `scripts/rekey_overrides.py --apply` from the repo venv (the only place a `scripts/` file can run) while PATH still holds v2.17. A later `llama fix <show> --set-venue …` or triage edit on any of the 606 shows wipes that show's override titles and forced structure from `overrides.json`. Meanwhile, any old-binary `redo`, `reapply` or sweep gather ships the show with cascade titles and computed set breaks, and nothing is flagged. Undo then refuses, because the file differs, so recovery means hand-copying `overrides.pre-rekey.json`, and nobody would know to do it. The same skew silently corrupts any replay arm run at an older sha against the migrated library, including the acceptance (a) base arm at `e37f670` if it runs after the migration, `-prev` arms, and `title_hygiene_probe.py dump`.
  - Setup and likelihood: you only need a migration run before the release binary is upgraded, or the sweep loop left running. This is likely: pieces 1-3 were merged well before their bulk apply, and the spec never says which binary is current.
  - Suggested fix: store the filename mapping under the legacy key names with filename-typed values (`titles: {filename: title}`, `set_breaks: [filename]`, `encore_after: filename`; legacy = a key or value that parses as an int). v2.17's model then rejects the file loudly (measured: all three raise `ValidationError`) instead of dropping it. Also add an ordered step list to 4.3: stop the sweep loop, upgrade the PATH binary, run the base arm, then migrate. Optionally make the migration a `llama` subcommand so the migrator and the reader are the same artifact. Cost: the field names change and the guard becomes type-based; the order is a few lines of text.

- **[Important] Every positional writer's staleness guard recomputes `kept` without the count-match protection, so protected shows refuse forever**
  - Where: 4.2 "every positional translation applies the staleness guard `--suggest-titles` already has (C1): the filename list `show.json` holds must equal what the current metadata and overrides keep"; 2.4 "Every other `filter_files` caller uses the default"
  - Problem: the existing C1 guard recomputes kept as `filter_files(..., readmit=include)` minus `exclude` (cli.py:2853-2890). Under this spec, gather's final kept list on a protected tape comes from a second `filter_files(keep_untagged_short=False)` pass decided by the description counts. The guard reproduces neither, and the spec extends it to every positional writer. The guard's own comment records the same defect class, found once already for `readmit`.
  - Evidence: cli.py:2861-2867 comment ("a recomputation without it is one file short ... the C1 guard below then declines forever"); spec 2.4 "Where it runs" lists only gather call sites.
  - Failure scenario: `belafleckandtheflecktones-2003-06-08` is held for `unresolved track titles` in arm_final, and the protection drops 4 of its files. `fix --suggest-titles`, `--set-title N=`, `--untitled` and triage `[t]`/`[u]` all refuse with "show.json is stale ... run `llama redo … --from gather` first". The redo writes the same show.json, so the refusal never clears. The same goes for `ratdog-2007-08-12` and `stevekimockband-2005-10-27`, and any future protected tape.
  - Setup and likelihood: certain on the 3 measured shows (one of them held) and on any future protected show.
  - Suggested fix: name one shared function, gather's "final kept list" (filter, protection, exclude), and require every guard and recomputation to call it. Alternatively remove the protection (see the protection Minor). The spec should also say whether the guard compares against overrides before or after the invocation's own edits (`fix --include X --set-title N=` in one call).

- **[Important] The voiced re-delivery step names no mechanism, and `deliver`'s only multi-show path replaces every voiced destination in the selection**
  - Where: 5.3 "The 37 voiced shows where the rule restores music are approved for `deliver --replace-voiced`"; Stakes (b) "Only the 37 shows the operator approved are in scope"
  - Problem: `deliver` takes one name or a selector, with no list input. `_deliver_batch` with `--replace-voiced` marks, then replaces, every voiced destination in the selection, whether or not the rule changed it. The spec leaves the bulk-apply author to invent the restriction on an irreversible surface. Shows that are "delivered, unvoiced" when the list is made can be voiced by `emcee run` before the apply.
  - Evidence: cli.py:2449-2505 (name XOR selectors) and cli.py:2415-2446 (`voiced` collected over all of `kept`, then `replace_voiced` passed to every `_deliver_one`).
  - Failure scenario: the apply runs `llama deliver --state delivered --replace-voiced --yes` (or `--profile gd`) to cover the 37 plus the 1,026 unvoiced in one pass. It discards paid voicing on the 28 minor voiced shows and on every unchanged voiced show in the selection.
  - Setup and likelihood: plausible whenever a batch is used for ~1,060 re-deliveries, and nothing in the spec forbids it.
  - Suggested fix: add one rule to 5.3. `--replace-voiced` is used only as 37 single-name invocations generated from `voiced-severe-final.json`, each checking membership before it runs. The unvoiced batch never passes `--replace-voiced`, so `_deliver_one`'s refusal protects any show voiced since the list was made. Cost: two sentences.

- **[Important] `set_breaks: []` is meaningful operator data, and the spec's "non-empty" wording and new fields lose it**
  - Where: 4.1 "Gather refuses a show whose `overrides.json` still has a non-empty legacy key"; 4.3 "Per show with a non-empty legacy key"; 4.1 Fields `breaks_after: [filename]`
  - Problem: gather takes the structure-override path on `set_breaks is not None` (gather.py:1658), so `[]` means "operator forced a single set, skip alignment". `--untitled` writes exactly that (cli.py:1819). The spec doesn't say whether `breaks_after: []` keeps that meaning, and "non-empty" lets a legacy `[]` slip past both the guard and the migration.
  - Evidence: `delmccouryband-2008-05-24/overrides.json` has `"set_breaks": []` plus 18 titles (library read). harness m4_migrate.py:15 treats `sb is not None` as a positional key, unlike the spec text.
  - Failure scenario: an implementer maps "empty" as "absent". The delmccoury show, and every future `--untitled` show, silently loses its forced structure, re-aligns, and may ship a different set structure or re-hold.
  - Setup and likelihood: 1 show today, plus every future `--untitled`.
  - Suggested fix: state presence semantics explicitly. `breaks_after` is `None | list` with `[]` meaning override-on. The migration and the guard key on "present", not "non-empty", and a test pins `set_breaks: []` → `breaks_after: []`.

- **[Important] The migration's undo depends on the mutable `show.json`, so it refuses exactly when a rollback would be needed**
  - Where: 4.3 Undo "only when the current file is byte-identical to what the migration writes from that backup. That output is deterministic."
  - Problem: "what the migration writes" maps backup positions through `show.json` (4.3 step 2). Any new-code gather rewrites `show.json` with inserted tracks, so after the bulk apply the recomputation differs, or fails its own checks, and undo refuses every re-gathered show. The output is deterministic only until the first gather.
  - Evidence: spec 4.3 steps 1-2. 5.1 puts the bulk apply (a re-gather of 1,534 shows) right after the migration.
  - Failure scenario: a problem found after the bulk apply means going back to the old binary. Undo refuses about 600 shows, which leaves them in the new format that old code silently ignores (the Critical above).
  - Setup and likelihood: only on a rollback, but that is the case undo exists for.
  - Suggested fix: at `--apply`, record the sha256 of the bytes written (in the backup's sidecar or the summary file). Undo compares the current file to that hash, independent of `show.json`. Also say plainly that undo only makes sense together with reinstalling the old binary. Cost: a few lines. Alternatively drop undo and keep the backup as the recovery path.

- **[Important] The spam tripwire checks only the tag, but the measured spam shape carries its marker in the filename**
  - Where: 2.3 "AUTHOR'S CALL, a spam-shape tripwire. A tag containing a URL ... It means a spam clip that happens to match the item's naming convention still drops (strict surface (c))."
  - Problem: the canonical spam file is `FOLLOW-ME @BYPIKENO.mp3`, tagged `Morning Dew` (spec 7). A convention-matching short spam clip with a song-shaped tag passes a tag-only tripwire, and the short arm (today's secondary net for it) now keeps it. The safety claim the spec makes for the tripwire is not delivered. Word-bounding is also undefined: 2.1's "No ... 'follow' ... exists" is false as a substring (`mountaingoats-2017-06-02` `14_banterJohnFollowsHisFingers…` / `(Banter) John follows his fingers`) and true only word-bounded.
  - Evidence: spec 7 first bullet; the rp_files.jsonl scan (1 substring hit, a real banter clip).
  - Failure scenario: a short convention-matching clip `gd73-06-10d3t09 follow @xyz.mp3` tagged `Morning Dew` is kept and airs.
  - Setup and likelihood: hypothetical (0 in the library), but this is the strict surface the tripwire claims to cover.
  - Suggested fix: apply the tripwire to the filename stem and the tag, and define every term as word-bounded and case-insensitive, `@handle` included. Re-measure (expected 0). Cost: one line.

- **[Minor] Stamping `short_kept` "like `Track.included`" puts it after alignment, which makes the coverage clause inert**
  - Where: 2.5 "Gather stamps `Track.short_kept` ... the same treatment as `Track.included`"; 3 "`and not t.short_kept`"
  - Problem: `included` is stamped after `align()`/LLM alignment (gather.py:2007-2010; align at 1670). An implementer copying that placement leaves `short_kept` False whenever `_songish_coverage` runs. The harness excluded by filename at compare time, so it never tested the placement.
  - Evidence: gather.py:1998-2010; dump_rp.py:66-72.
  - Failure scenario: about 43 of the measured clears do not happen; acceptance (a) would catch it, but only late.
  - Setup and likelihood: likely if the analogy is followed literally.
  - Suggested fix: say that the stamp happens where the cascade builds `Track`s (before `align`, `apply_llm_alignment` and the taper), and add a gather-level test, not only a `_songish_coverage` unit test.

- **[Minor] As written, the migration's break check refuses titles-only shows**
  - Where: 4.3 step 1 "`show.json`'s `set_breaks` is not exactly `sorted(set_breaks ∪ {encore_after})`"
  - Problem: when both structure keys are absent, the right side is `[]`, so every titles-only show with real aligned breaks is refused. The measured "0 refused" applied the check only when a structure key is present (m4_migrate.py:31-35).
  - Failure scenario: hundreds of titles-only shows are refused, which is the safe direction but blocks the bulk apply.
  - Suggested fix: "when `set_breaks` or `encore_after` is present".

- **[Minor] Definitions an implementer must guess in 2.2-2.3**
  - Where: 2.2 "(the same rule `_track_number` uses for the track tag)"; 2.3 "Every part is a junk part"; the 2.3 table
  - Problem: (i) `_track_number` always uses a derivative's original's tag, never its own (junk.py:86), so "the same rule" is false and the spec's own "own, else original's" wording is the one to keep. (ii) A tag that cleans to no parts (`d1t01` once the disc stem is stripped) makes `all([])` true, so it drops, contradicting 2.2's "kept". rprime.py:57 guards this with `ps and`. (iii) The table is not the measured function. rprime.py's regex also matches `disk`, `tape|side|disc|reel … break`, `tuning break`, `tunin'`, `walk-in/out/off music`, `set one/two` tuning, `encore break II`, and so on. Tests built "on every example named in 2.3" can pass while the shipped vocabulary differs from the measured 651+34.
  - Suggested fix: make rprime.py's `LEAD`/`TIME_PAREN`/`SPLIT`/`JUNK_PART`/`NONPERF` normative (ported verbatim), state that empty parts are not junk, and add a corpus test that every measured `drop-junk` stays dropped and every `keep` stays kept.

- **[Minor] The protection mostly drops files for nothing, and its handling of operator-included candidates is undefined**
  - Where: 2.4 "Measured: it drops 6 files in 3 shows ... and so keeps ratdog's 19 `desc-position` titles"
  - Problem: in arm_final, `belafleckandtheflecktones-2003-06-08` (4 files dropped) still has 0 `desc-position` titles and stays held as needs-llm. `stevekimockband-2005-10-27` (1 file, 118 s) is fully tagged with 0 `desc-position`. So 5 of the 6 dropped files protect nothing, which cuts against "omitting real show content is worse". `drop_final.json` also lists 12 operator-included untagged files. The spec doesn't say whether these count among "them", and the choice flips them between `readmitted` (reduced standing, counted in coverage) and `short_kept` (full standing, not counted).
  - Suggested fix: either fire only when the tape without them has an unresolved song-like track for D to fill, or drop the protection, `fix --exclude` the one ratdog file, and document the limitation. Dropping it also removes the keyword threading and the guard replication in the Important finding above. State that operator-included names are not candidates.

- **[Minor] Re-gathering the 28 minor voiced shows costs a full re-download and leaves the library and station copies diverged**
  - Where: 5.3 "A minor show may be re-gathered in the library. Its station copy is left alone."
  - Problem: library audio was purged at delivery, so re-packaging re-downloads the whole show, which then sits undeliverable (deliver refuses voiced) with nothing gained. The spec also doesn't say what happens to the 15 delivered and 16 packaged shows the apply turns into holds: the station copy keeps airing the old version until the hold is resolved.
  - Suggested fix: leave the 28 out of the bulk apply until they are re-voiced (a removal), and add one line on held-after-apply delivered shows.

- **[Minor] The `briefing_reusable` change is undefined for `set_breaks`, and its ownership is unclear**
  - Where: 5.2 "change `replay.briefing_reusable` to compare the broadcast fields over the tracks that are not `short_kept`, matched by filename"
  - Problem: `set_breaks` is an index list (replay.py:251), and an insertion shifts it, so it has to be compared as filenames too. m6_final.py's 1,377 never compared `set_breaks` or date/venue/city. The spec also doesn't say whether this branch or the bulk-apply branch implements it and the reapply extension, and 6(f) tests neither.
  - Suggested fix: specify "breaks compared as the filename after which each falls", name the owning branch, and add a test if it is this one.

- **[Minor] A dangling filename key deadlocks the show**
  - Where: 4.1 "A key naming a file not in the final kept list raises `LlamaError`"
  - Problem: when a metadata cache refresh removes a keyed file, gather raises, and the staleness guard then refuses the `--clear-title N` that would fix it (show.json and the recomputed kept list differ). Separately, `fix --exclude N` on a track that carries an override title fails its own redo.
  - Suggested fix: `--exclude` removes keys on the file it excludes and prints that; document the cache-refresh case as a hand-edit (rare).

- **[Minor] Measurement claims that do not match the harness outputs**
  - Where: 2.3 "no sibling or canonical labels any of them a song"; 6(e) "1 S loss ... plus 1-track reversions"
  - Problem: four `drop-junk` rows carry `sib_label: sib-split` with song titles, for example `gratefuldead-1984-04-17 01Tuning.mp3` (sibling: Jack Straw) and `philleshandfriends-2005-12-04` `Warm Up` (U.S. Blues). The behaviour is the same as today. m3_final.txt also lists `belafleckandtheflecktones-2003-04-12` losing 2 positional fills, not 1, among 9 shows with losses.
  - Suggested fix: reword both claims so acceptance (e) is not blocked by its own expectation.

- **[Minor] The interior test runs before dedupe, re-admission and operator exclusion**
  - Where: 2.4 "Play order is derived the way `filter_files` derives it ... over the kept files, the tagged short files 2.3 keeps, and the untagged candidates"
  - Problem: a file that is interior only because of an operator-excluded neighbour is kept, and the order mode (tags vs filename) can differ between the interior check's set and the final set.
  - Suggested fix: document it as a limitation (rare; the replay showed 0 reorders of existing files).

### Unverified premises
- The operator approved all 37 voiced re-deliveries. The "re-voice?" column in `voiced-severe-review.md` is blank in the evidence copy. Cheapest test: point to the written ruling 8 record.
- Which binary runs the migration and the bulk apply, and whether the PATH binary is upgraded first. Cheapest test: write the ordered runbook into 4.3 and 5.
- The candidate arm reproduces R'. The harness implemented neither the spam tripwire nor filename junk except through the fixed `drop_final.json` list, and it applied the protection as a global name list rather than through the description condition. Cheapest test: the spec's 8.1, per show.
- `transmitter` tolerates the 37 `--replace-voiced` swaps of possibly-planned shows. pipeline.py:254-290 re-plans "package changed"/"no longer eligible" but raises `LayoutError` if the show is already on air with its encode missing. Cheapest test: run `transmitter status`/plan for the 37 slugs before swapping, and skip any that are inside the current horizon.
- The download cost is affordable (spec 8.6). Cheapest test: as stated there.

TOTAL: 16 findings (1 Critical, 6 Important, 9 Minor)
