# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Implemented. The full pipeline (interpret through package) works offline
against the `fake` LLM backend and real archive.org fixtures; see
`docs/superpowers/plans/2026-07-14-llama.md` for the task-by-task
implementation plan this was built from. The approved design spec is
`docs/superpowers/specs/2026-07-14-llama-design.md`.
The repo also holds `transmitter` (playout, phases 1-3; not a released/signed
binary — `.github/workflows/release.yml` has no transmitter) and `antenna/`
(a Cloudflare Worker + static player).

## Commands

- Setup: `python3 -m venv .venv && source .venv/bin/activate && pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`
- Test: `pytest -q` (offline, deterministic). Single test: `pytest packages/llama/tests/test_setlist.py::test_parses_sets_segues_and_confidence -q`
  **In a git worktree, give the worktree its own `.venv` and run `./.venv/bin/pytest`.**
  The repo-root `.venv` installs llama editable against the *main* checkout, so a
  bare `pytest` from a worktree collects the worktree's tests but imports the main
  checkout's source — it silently tests the wrong code and still passes.
  **And never run a `.venv/bin/*` console script from a COPY of the tree.** `pytest`, `pip`, `llama`, `emcee` and `transmitter` are all shebanged with an absolute path to the original venv's interpreter, so from a copy they act on the original: `.venv/bin/pytest` tests the worktree instead of the copy (so a mutation you applied does nothing and the suite stays green), and `.venv/bin/pip install -e` reinstalls into the worktree's venv and repoints its `_editable_impl_*.pth` at your copy — poisoning every other process using that worktree, invisibly to `git status`. Use `python -m <tool>`, or shadow with `PYTHONPATH`. To check: `./.venv/bin/python -c "import llama; print(llama.__file__)"` must resolve inside the tree you meant to test.
- Live tests (real archive.org, no LLM): `pytest -m live -q`
- Refresh a fixture: `python scripts/capture_fixture.py <identifier>`
- Stitch a playlist into one mp3: `python3 scripts/stitch_m3u.py <playlist.m3u>`
  (standalone, stdlib-only, needs ffmpeg/ffprobe; stream-copies uniform mp3
  input and re-encodes otherwise, writing ID3 chapters per entry and pulling
  tags from a sibling `manifest.json` when there is one). `scripts` is in
  pytest `testpaths`, so its tests run under plain `pytest -q`.
  `python scripts/backfill_voiced_by.py [--station-root P] [--apply]` is a
  one-off (imports emcee): it fills `dj_audio.presenter` on packages voiced
  before emcee recorded it, by whole-word matching each presenter's `name`
  in the script text — exactly one match writes, zero or several leave `?`.
  Dry run unless `--apply`.
  `python scripts/backfill_tts_record.py [--station-root P] [--apply]` is a
  one-off (imports emcee): it fills `dj_audio.tts` on packages voiced before
  emcee recorded it, for the operator-vouched presenters in its `BACKFILL`
  table only (`phil` voxtral, `jamesbrown` mlx_audio), with `voice:
  "unknown"` (the clone hash is never recomputed). Dry run unless `--apply`.
  `python scripts/purge_delivered_audio.py [--config P] [--dest P] [--apply]`
  is a one-off (imports llama): it applies deliver's audio purge, same
  verification, to shows delivered before deliver did it. Dry run unless
  `--apply`.
- Run (llama, acquisition): `llama get "..."`, `llama get --profile <name>`,
  `llama get` takes `--wait/--no-wait`, `--max-wait <dur>` and `--no-pacing`
  (also on `run approve`/`run resume`): when the claude_cli backend refuses
  because a usage window is exhausted, the run pauses at the show boundary
  rather than failing every remaining show — sleeping until the reset the
  refusal names, or checkpointing the session as `paused` when the wait
  exceeds `--max-wait` (default 6h). Resuming costs nothing for shows already
  packaged: stage-level `should_run` skips them.
  `llama artists "..."`, `llama status` (shows only, one row per show so it pipes — sessions
  needing attention are `llama run list`'s; `--by-run` for
  session rollups), `llama show <name>` (read-only), `llama pipeline`
  (static stage/state teaching command), `llama pacing` (read-only:
  the usage meters, the learned per-show cost, how many shows fit
  before the reset, and the verdict — `would proceed`, or
  `would pause: <reason>`), `llama triage` (interactive
  held-show walkthrough -- `[t] suggest titles`, offered only on a hold
  flagged "unresolved track titles", proposes a full set of titles from
  the setlist correspondence and writes them all on confirmation;
  `[i]nclude dropped`, offered only when the show has `excluded_files`,
  re-admits by x-handle or filename and shares `fix --include`'s
  operator-excluded routing via `_split_include_targets`; each edit is one
  unit like `fix`'s -- a failure prints `error: …` (no "updated" line: those print only after the unit succeeds), restores the show and
  returns to the same show's prompt -- except `changed by another command`, which re-captures the view, then re-resolves, and re-prints the show before its prompt, so a retry works -- and Ctrl-C ends the walkthrough after the
  restore), `llama
  fix <name> <edit-flags>` (overrides/hold editor, auto-redoes;
  `--suggest-titles` is the same title-proposal resolution, one
  invocation, one confirmation, refuses to combine with
  `--exclude`/`--unexclude`/`--include`). **One unit (2026-10-21):** `fix`, triage's edits and `redo` (single and batch, per show) each run as one unit under the show lock. `fix` and triage ask any prompts first with no lock held, then take the lock and refuse with `changed by another command; run it again` if `overrides.json`/`show.json` changed since (or `the show was removed`). `redo` shows nothing, so it reads the show once it holds the lock: it waits behind another writer rather than refusing, and refuses only a show removed meanwhile. Each unit snapshots every file outside `package/audio/` into `<show>/.txn/`, then does the work. Any exception, including Ctrl-C, restores those files byte-identical and removes new audio. A single `fix`/`redo` then exits 1 with the error. A stale `.txn/` (SIGKILL) is deleted, never restored, by the next unit. With no `show.json`, `fix` still accepts `--set-venue`/`--set-city`/`--set-date`, the three `--clear-*` flags (`--clear-title` by filename only) and filename `--exclude`/`--unexclude`; a positional `--set-title`/`--set-breaks`/`--set-encore`, `--suggest-titles` or a track-number `--clear-title` needs `show.json` (piece 4: a number means `show.json`'s numbering). Every other flag refuses and names `llama redo <show> --from gather`, which is also the repair for any show left part-way. `--no-run` validates nothing: a later redo that refuses the overrides rolls back and names the field.
  `llama redo <name> --from <stage>` (one unit, above),
  `llama deliver <name>` (refuses to overwrite an emcee-voiced destination
  unless `--replace-voiced`, which replaces the destination wholesale and
  discards its DJ script and audio, takes ONE named show and refuses with any batch
  selector (`--held`, `--state`, …); a selector batch refuses a voiced destination and
  names the by-name route; after a successful copy it **purges the library's
  `package/audio/*`** — only once `catalog.purge_package_audio` verifies the
  station copy holds every manifest track at the same size and as a different
  file (a hardlink or a `delivery_path` inside the library deletes nothing);
  a skipped or partial purge only warns. **A purged (delivered) show no longer re-downloads (bulk-apply, strict station reuse):** `llama redo <name> --from package`, `reapply` and any `fix`/`triage` auto-redo of a delivered show re-package by copying audio from the STATION copy (pairing by index + title + `source.identifier`, each file length-checked) and REFUSE rather than download: `<slug>: station copy does not pair: <detail>` / `<slug>: station copy unreadable: <detail>` (details `no copy pairs`, `a different recording`, `<file> has no metadata length`, `<file> failed its length check`, `no delivery_path in config`), then the hint `  if the station copy cannot be fixed: re-run this one show with --allow-download`. `--allow-download` (ONE named show only, on `reapply`/`redo`/`fix`; with a selector or list: `--allow-download takes one named show`) downloads whatever no copy pairs. `redo`/`fix`/triage check the station before any LLM spend, so with the station unreadable every such edit of a delivered show refuses up front (nothing spent, the unit rolls back), even one whose re-gather would end held: triage held delivered shows with the station mounted. A newly kept file the station never held downloads alone (per-show line `audio reused N, downloaded 1`). A redo `--from select` of a delivered show is not strict (it re-selects the recording). The verification also requires the station manifest's `tracks` to
  equal the library's (same-size files are not the same package: a retag
  keeps sizes) and flushes each station file to disk (`F_FULLFSYNC`) before
  the first delete. A voiced-destination refusal is checked BEFORE the gate,
  so a purged show is not sent to re-package only to be refused anyway.
  **Awaiting fix (bulk-apply):** a show whose LIBRARY campaign record is awaiting fix (an unreadable record included) is refused by `deliver`, by name and in every selector; a STATION copy carrying `awaiting_fix` whose library show has been processed is not refused but always replaced wholesale on delivery, which clears the mark: `refusing to deliver <slug>: awaiting fix (marked <marked_at>: <reason>)` then `  re-process it first: llama reapply <slug> --allow-structure-change` (` --with-gather-llm` appended when the slug is on the frozen needs-LLM list) or `  re-process it first: llama redo <slug> --from select`; a batch line ends `  (refused: awaiting fix)`. `llama deliver --fixed` is the selector for shows re-processed since their station copy was marked (always replaced wholesale, which clears the mark). On a voiced marked destination `--replace-voiced` refuses when the re-processed show equals the voiced copy: `refusing to replace <slug>: the re-processed show equals the voiced station copy; keep the voicing with: llama clear-mark <slug>`
  **Piece 4:** `_destination_is_voiced` treats only a missing manifest as unvoiced,
  and any other read error or a malformed manifest refuses that show (a batch
  preflight marks it refused and continues); an unvoiced destination whose track
  list differs from the package's is replaced wholesale (`_replace_destination`),
  so no old-numbered file survives beside the new manifest; `reapply`'s
  `re-deliver with` hint is suppressed for a voiced destination),
  `llama clear-mark <slug> [--accept-change]` (one named show; clears a VOICED station copy's `awaiting_fix` without re-delivery, printing `mark cleared; the voicing is kept`: refused unless the show's campaign record is processed after `marked_at`, it is not held, the library manifest's sha256 equals the record's, and the library and station manifests are equal as raw JSON on `source.identifier`, venue, city, date, the track list (filenames, durations), titles, set labels, segues and set breaks; `--accept-change` clears despite a difference, then the library keeps its audio; an emcee process running refuses; spec `docs/superpowers/specs/2026-10-25-bulk-apply-design.md`),
  `llama status --awaiting-fix` (selector: marked and not yet fixed; the status row carries an `awaiting-fix` mark),
  `llama rm <name>`, `llama suppress`/
  `llama unsuppress <performance-id>`, `llama run list/approve/resume/rm`
  (session namespace; a run that lost shows to a failure ends
  `incomplete`, not `complete`, so it stays on `run list`'s attention list
  — with the per-show reasons recorded in `session.json` — until a
  `run resume` finishes cleanly; `run list` prints those reasons indented
  under the session row, and `--no-flags` drops them for one line per
  session, like `status --no-flags`; a run another process is working shows as
  `running`, derived and never written). **`llama run resume --all`** is the
  unattended sweep (spec `docs/superpowers/specs/2026-10-21-download-retry-and-run-sweep-design.md`
  §6): one pass, then exit; a positional session plus `--all` is an error. Eligible:
  `paused` past its `resume_after` (or with none) and `incomplete`, either with no
  recorded failures or only `download`/`archive` ones; a run with no `session.json`
  reads `incomplete` and is eligible when its `request.json` has `auto: true` or no
  `auto` key. Skipped, one line each: `running`, `paused until HH:MM`, `awaiting
  approval`, `needs attention` (any `transport`/`llm`/`rate-limited`/`other`
  failure, so a loop never re-spends on a run that fails the same way every time;
  no `criteria.json` and no `request.json`; an `auto: false` request in ANY state,
  i.e. an interactive `get` that may have stopped before a prompt; a human-gated
  run — `request.json` records `human_gate` (the profile's, `false` for a query
  run) and a profile request written before that loads its profile, an unloadable
  one counting as gated; a malformed or non-string `updated_at`, skipped rather
  than crashing the sort — the sweep makes no human decisions, operator ruling
  2026-10-21); `complete` runs are not listed. Oldest
  `updated_at` first, one at a time, always `--auto`, **`--no-wait` by default**
  (unlike plain `run resume`: a usage pause checkpoints `paused` instead of napping
  inside the loop; `--max-wait`/`--no-pacing` pass through). A run that ends `paused`
  stops the sweep (the window is account-wide) and the rest print `not reached:
  <id>`. Per-run results: the run's state, `running` (turned live since the listing),
  `gone` (removed since), or `error: <msg>`; the summary lists each. Exit 0 only when
  every resumed run ended `complete` (`running`/`gone` don't count against it) or
  nothing was eligible (`nothing to resume`); else 1. **Crash marker:** an exception
  escaping a swept run (a non-zero `typer.Exit` included, as `exit <code>`) writes
  `incomplete` with one run-level failure `{show: null, kind: "other", error: <msg>}`
  while the run lock is still held; `run list` prints it under `(run)` and the next
  sweep skips the run as `needs attention`. `KeyboardInterrupt` stops the sweep and
  records nothing. Operator loop: `while true; do llama run resume --all; sleep 600;
  done`. `llama get`'s `no matching artists found` now marks the run `complete`. A
  run that cannot be locked prints `run <id> is in progress in another process` (or
  `run <id> no longer exists`) and exits 1. Shows/sessions are addressed by name or unique
  substring; paths still work. `llama config init` seeds a commented config
  of the baked-in defaults (config values replace defaults; nothing
  merges). **An unknown key in `config.toml` is now an ERROR, not a silent
  drop** (`extra="forbid"`, 2026-09-07): a typo'd knob used to parse to its
  default and leave the operator's edit with no effect and no message. It is
  set on a shared strict base because pydantic does NOT propagate
  `model_config` to nested models — on `Config` alone every section below it
  stays permissive, which is most of the value. Mapping KEYS stay free-form
  (task names under `[llm.*]`, backend names under `[llm.tiers.*]`); only
  their values are strict. `herder`'s `TaskConfig` is deliberately left
  permissive (cross-package blast radius), and so are the PERSISTED state
  artifacts — `Criteria`/`criteria.json`, `session.json`, `show.json`, the
  manifest — where permissiveness is load-bearing forward compatibility:
  strictness there would break `llama run resume` on run dirs written by a
  different version, which is the thing T6b exists to protect. emcee has the
  same treatment on its own six models via its own base (it must never import
  llama). No `voice`/`presenter` commands — that's emcee's job now.
- Run (held-backlog tooling; spec
  `docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md`):
  `llama reapply <show>...` / `--from-list <list> [--dry-run]` re-processes shows in
  place in EVERY state (held, briefed, packaged, delivered; bulk-apply Task 9 built what piece 4 filed as spec 5.2) with exactly the replay harness's computation
  (`llama/reapply.py`, `llama.replay`): gather LLM-free from the cache (a stored
  alignment of `"llm"` is needs-llm), vet from the stored `vetting.json`
  extraction (none = needs-llm, nothing written), the stored briefing reused
  when `briefing_reusable` holds (else one fresh brief task of up to two
  attempts, its only LLM work), then package. **It holds the show lock from the
  still-held check through the last write and writes `show.json` LAST as the
  commit marker**: until then the show is still held, so a failure part-way
  leaves it on every held list and a re-run completes it. It never writes
  `reviews.json`/`provenance.json`/`research.md`/the ledger and **never
  delivers**: a delivered show that cleared prints `re-deliver with: llama
  deliver <name>` (piece 4: not for a voiced destination, and an unreadable one prints
  deliver's refusal instead). A held outcome whose replay changed shipped fields (and ran
  no brief) drops the now-stale briefing (`drop:brief`; `briefing.md` alone
  counts), so the eventual `fix --overrule` regenerates it rather than shipping
  it unchecked. A show whose replay is structure-changed is refused unless
  `--allow-structure-change` (names form and `--from-list` alike; the row is
  `skipped: structure changed`, retryable); the dry-run predicts that skip
  (`would: <slug> -> skipped: structure changed`; names form `-> dry-run:
  skipped: structure changed`) and counts no brief or download for it, and the
  `--from-list` dry-run's summary line counts `downloads` (incl. purged-audio
  re-downloads). `--from-list` takes a `predicted_list.json` and refuses it
  whole unless its `sha` equals `replay.code_identity()` and its
  `config_fingerprint` the running config's; **a `-dirty` identity is refused on
  either side**. A row whose `input_digests` changed since the harness ran is
  skipped. Batch state is `<root>/reapply/<sha256(list bytes)[:16]>/`
  (`list.json`, append-only `progress.jsonl`; outside `runs/`): re-running the
  same list resumes, skipping rows with `retryable: false`. A pacing gate (list
  form only) runs before each show's lock; a pause or `RateLimited` prints the
  resume command; `STOP_AFTER_LLM_FAILURES = 3` consecutive LLM failures stop
  the batch. **The learned per-show EWMA cannot size this batch (spec
  "Re-processing cost"): the gate still pauses at a ceiling but cannot project a
  show's cost, so size waves from the pilot's `meter: 5h A% -> B%` lines, not
  `llama pacing`.**
  **Bulk-apply additions** (spec `docs/superpowers/specs/2026-10-25-bulk-apply-design.md`, plan `docs/superpowers/plans/2026-10-26-bulk-apply.md`): outcomes `label-only` (only `title_source`/`structure.alignment` changed: `show.json` only) and `unchanged` join the old ones, plus `skipped: processed` (the show's campaign record already holds a processed stamp) and `skipped: re-selection (llama redo <slug> --from select)` (the replay would pick another recording; reapply never re-selects). A delivered show re-uses the station copy's audio and refuses rather than downloads (strict station reuse, `deliver` bullet; `--allow-download`, one named show). A marked, unvoiced delivered show that comes out unchanged is still re-packaged so `deliver --fixed` can re-deliver it. `--with-gather-llm` also re-processes a show whose replay needs gather's own LLM touchpoints (`extract_setlist`, `align_structure`; never research; a dry run never calls them). List form only: `--seven-day-ceiling <pct>` (pause when the weekly meter passes it, overriding `[pacing] seven_day_ceiling`) and `--stop-at-points <n>` (stop once the 5-hour meter has moved n points in one window: a trial block; the printed resume line repeats it; reset instants within `herder.usage.RESET_JITTER_S` (120 s) count as one window, because `/usage` prints the same reset a minute early now and then, and `trial-report` applies the same rule). Every list batch takes a per-batch snapshot `<root>/reapply/<hash>/snapshot/` (undo: `bulk_apply.py restore`, plan Appendix B).
- `scripts/bulk_apply.py` (the bulk-apply campaign's operator script; run from the PINNED worktree by path, `<worktree>/.venv/bin/python <worktree>/scripts/bulk_apply.py <sub>`, never with its venv activated: its dev `llama` reports `0.1.0` and the version gate refuses; `CAMPAIGN_MIN_VERSION = "2.20.0"` in `llama/campaign_gate.py` is the release llama and emcee ship together at, correct it first if the release takes another number; any refused gate exits 2). Runbook: plan `docs/superpowers/plans/2026-10-26-bulk-apply.md` Appendix A, undo Appendix B. Subcommands: `pin --tag T [--replace]` (pin the campaign to a release tag's commit), `arm --out F` (the replay arm, behind the version and pin gates), `snapshot --slugs F` / `seal <snap>` / `restore <snap> [--slugs F] [--apply]` (whole-show snapshots for the re-selections and the wave undo; dry run unless `--apply`), `backfill --base B --verdicts D [--rehold-verdicts D] [--apply]` (the overrule backfill), `freeze --arm F` (the frozen needs-LLM list), `reselect-check --source F [--write]` (the verified re-selection list, re-checked read-only), `mark --arm F [--apply]` (the station marking batch; backs up every station manifest first), `unmark --batch DIR [--apply]` (its reversal), `lists --arm F [--profile P] [--state S] [--slugs F] [--kind fresh|reuse|needs-llm|label-only|held] [--include-voiced] [--famous F] [--limit N] [--out F | --counts]` (wave lists), `wave-check --list F`, `spot-check --batch DIR [--n N] [--seed S]`, `revoice-list --arm F --emcee-status F [--backend B]` (the ranked re-voice list for voiced marked shows), `trial-report --block <shape>-<kind>=DIR … --queue F --weekly-share PCT [--shape S=P,P]`. **Backfill bases:** today's rule (a not-held show that was newly held under the pre-piece-4 code and whose verdict ruled a flag `spurious`/`flag-spurious` or listed it in `overrule_if_reheld_on`) plus the Checkpoint A rules (a) a `fix` verdict records every still-listed structure/closer/venue/city flag, (b) a rehold-verdict `decision: overrule` (`--rehold-verdicts ~/.llama-harness/t3/rehold-verdicts`) records every still-listed base flag but `titles` and the research-wrong/right-show-wrong rulings (it covers `research-song`; `escalate` stays listed), (c) a delivered show with no verdict records every base flag, (d) `overrule_if_reheld_on` entries the base arm did not raise; each recorded overrule's `note` names its basis (measured at Checkpoint A2, 3497e77e: 195 considered, 494 recorded, 21 listed, 187 of 195 fully covered). **Marking reasons (five):** `changed by the held-backlog fixes: <fields>`; `replay needs an LLM call: <needs_llm>`; `stored briefing fails today's guard`; `recording re-selection: <stored> -> <pick>`; `newly held by today's checks: <flag kinds>` (an arm row newly held with no visible change, not label-only and not processed; Checkpoint B). `lists`, `mark` and `wave-check` refuse an unmounted or empty station root. `mark` refuses a `reselections.json` older than its arm: `reselections.json predates the arm; re-run: bulk_apply.py reselect-check --write`. `rekey_overrides.py --restore` is RETIRED from the backfill's first write on (the bulk apply's writes postdate its snapshot): `refusing to restore: the bulk apply retired this rollback at <at> (<by>); its writes postdate the snapshot: use scripts/bulk_apply.py restore`.
- **Bulk-apply open gaps** (plan "Open gaps"): a delivered show whose station copy is gone or permanently unpaired refuses strict reuse every time (route: by-name `--allow-download`); a paired source whose cached metadata has no length refuses (`<file> has no metadata length`) on every strict re-package (same route; how many is unmeasured); newly held shows with no visible change are listed by `lists` (`kind == held`) so the apply writes their hold, and Checkpoint B's fifth marking reason now marks them (88 packaged, 1 delivered measured at Checkpoint B2; mark plan 2640 = 2551 + 89 at f1f447db); `clear-mark` and `--replace-voiced`'s refusal compare raw-JSON durations, so a re-read duration off in the last digit needs `--accept-change`; SMB/NFS rename atomicity of the station mark is unmeasured; the station-mark residual window (an emcee write landing between `write_mark`'s last byte check and its rename is overwritten undetected; the per-write `emcee_running()` check is the guard); the marking rule cannot reach processed needs-LLM shows after a later gather change.
- `llama fix <show> --untitled` / triage `[u]`: offered only when EVERY track is
  `unresolved`; lists filenames, then ONE confirmation writes `Untitled (track
  N)` titles, `narration=vague`, `set_breaks=[]`, clears any
  `overrides.encore_after`, redoes from `gather`, overrules any remaining flag
  and continues from `brief`. It refuses every other edit flag. Route for a
  delivered all-`Track NN` tape (`eotoband-2007-10-09`): `llama redo <show>
  --from gather` (2b demotes the tags), `llama fix <show> --untitled`, `llama
  deliver <show>`.
- `scripts/replay_holds.py run --out <arm.json> [--held|--all|--slugs F]`
  replays holds read-only under THIS tree's code (use that tree's own
  interpreter; it exits 2 unless `llama.__file__` is inside the tree, and
  refuses an `--out` or `--scratch` overlapping the library; put output outside
  `~/.llama`, e.g. `~/.llama-harness`). `compare <base> <cand> --out <dir>
  [--no-repro-gate]` writes the reports in `replay_holds.OUTPUT_FILES`,
  including `predicted_list.json`, `structure_changed_list.json` (hand-check
  each, then apply with `reapply --from-list <it> --allow-structure-change`) and
  `pilot_list.json`; it exits 2 when the arms differ (digests, config
  fingerprint, setlist.fm configuration, show set) and 3 below 99% baseline
  reproduction (`--no-repro-gate` skips only that, for `-prev` arms). **Every
  list carries the arm's `sha`, `config_fingerprint` and per-row digests; that
  is what ties it to the code that predicted it** (editing a list changes its
  batch dir; do it before any apply).
- `scripts/replay_holds.py run --strip-title-overrides` replays each show with
  `overrides.titles` removed (the fresh-get title view; add
  `--strip-structure-overrides` too for the full fresh-get view, which is what
  piece 3's acceptance used). Like the structure strip it works on a scratch
  copy, stamps the arm and writes no apply lists. `--disable-slices slice5,slice4`
  (comma list; names outside `title_hygiene.ENABLED_SLICES` are refused) turns
  title-hygiene slices off for that run and stamps `disabled_slices` on the arm,
  so a slice's effect is a candidate arm against the same arm with it off.
  `scripts/title_hygiene_probe.py dump|gate|parity|packets` is the read-only
  piece-3 probe (spec Acceptance): `dump` runs the UNWIRED `title_inputs` +
  `title_cascade` on two views and so measures PRE-WIRING trees only (e.g.
  89fd787; on a wired tree gate 0 measures nothing and fails by design); `gate`
  tabulates `dump.jsonl` into the Checkpoint A table; `parity` compares a wired
  fresh-get arm's titles with the dump; `packets` writes the hand-check packets
  from a `compare` directory. Run it with the tree's own interpreter, output
  outside `~/.llama` (it refuses an overlapping `--out`).
- Piece 4 tooling (spec `docs/superpowers/specs/2026-10-23-junk-short-keep-design.md`).
  `scripts/short_keep_probe.py arms|repro|packets|score|sibvocab|reuse-check|voiced-precheck`
  (read-only, tree's own interpreter, output outside `~/.llama`): `arms --base --cand
  --ref-dir --out` is the acceptance tallies and the `BLOCKS MERGE` lines; `repro --pre
  --post --out` is the post-migration self-check (refuses, comparing nothing, an arm with no
  replayable row or two arms of different roots); `packets`/`score` the hand-check packet and
  its bar; `sibvocab` the sibling-vocabulary look; `reuse-check` how well audio re-use covers
  the delivered shows; `voiced-precheck --list <voiced-severe-final.json> <slug>` the check
  before one `deliver <slug> --replace-voiced` (exit 0 only when all pass).
  `scripts/replay_holds.py run --rekey-overrides` replays a LEGACY library with each
  `overrides.json` re-keyed onto `show.json`'s filenames (imports the migration's own
  `rekey_raw`; measurement only, stamps the arm `overrides_rekeyed`).
  `scripts/rekey_overrides.py [--snapshot | --apply | --restore <snapshot-dir>]` is the
  one-off positional-overrides migration (no option = dry run; never gathers); run it from
  the MAIN checkout as `/Users/shawn/projects/llama/.venv/bin/python scripts/rekey_overrides.py`
  with that venv NOT activated (its dev `llama` reports `0.1.0` and `--apply`'s version gate
  refuses it). Runbook in the piece-4 bullet. `--restore` is retired once the bulk apply writes (see the `scripts/bulk_apply.py` bullet).
- `notes.json` (written by gather, and by vet for 4a; `reapply` rewrites it):
  operator notes. **They never reach the briefing LLM** (`run_brief` passes the
  whole `show.json`, so a note there would); only `llama show` and triage read
  them, and each gather replaces the file.
- Run (emcee, station-side, post-`llama deliver`): `emcee run` (scan
  `[station] root` and voice every not-yet-broadcast-ready package;
  it prints a plan on stderr (new / re-voice by reason / repair, the exact clip count, presenter and TTS per group) and asks `Proceed? [y/N]` before ANY LLM or TTS spend; `--yes`/`-y` skips the question; with no TTY and no `--yes` it prints the plan and exits 1. A pending package with missing track audio is skipped (`re-deliver from llama`), not voiced, whatever else is wrong with it. **An agent (no TTY) runs `emcee run --dry-run`, shows the plan, and passes `--yes` only after the operator approves**; the `--yes` run re-scans, so keep the gap short;
  `--profile <name>` (repeatable) limits it to packages whose EFFECTIVE profile (move > artist rule > llama's) is one of those, `--assigned` to packages whose effective profile has its OWN
  `[assign.profiles.<name>]` entry (not those falling to `[assign] default`
  or the house voice), `--dry-run` lists what
  would be voiced and by whom — an explicit assignment prints `<id>`, the
  default `<id> (default)`, none `house`; a pinned presenter's row also shows
  `[<backend> <model>]`, an unloadable presenter file
  `[invalid presenters/<id>.toml]`, a failed TTS resolution
  `[unresolved: …]`),
  `emcee voice <package>` (script + voice + assemble one package —
  a path, or a name/unique substring under `[station] root`, overridable
  with `--station-root`, exact name beating substring hits;
  `--fresh <clip-stem>` deletes just that cached clip, but since emcee
  re-scripts on every call, a real LLM's regenerated text usually
  invalidates every clip's cache too — in practice `--fresh` normally
  re-renders every clip, not just the named one; `--force` re-synthesizes
  all of them unconditionally), `emcee status` (default: a summary by profile, ending in `voiced on`, the voiced packages by recorded TTS backend; `--list`/`-l`
  gives the per-package table (a header row unless `--no-header`) of ready/pending/unsupported/`error` with a TTS column (the recorded backend, `?` = no usable record, `(now: <backend>)` when the presenter now resolves to a different backend, `(now: new model)` when only the model moved, `(now: unresolved)` when it cannot resolve; models are in `--json`; the voice hash is not compared; display only, drift never changes readiness) and a short reasons column (`unvoiced`, `no script`, `no m3u`, `N clips missing`, `N of M audio missing`; blank for `awaiting-fix`; `--json` keeps the full text), `--profile`,
  `--state`, `--tts BACKEND` (`none` = voiced, no record) and `--drifted` filter and switch to that table on their own, `--json` is
  always per-show and adds `tts_now`/`tts_drifted`; `station.scan` checks packages on `SCAN_WORKERS = 16` threads and reads each manifest once, output unchanged; a `--profile` no package carries prints a `note:` rather
  than looking like an empty queue; the voicing presenter is the
  recorded `dj_audio.presenter` — null is the house narrator, an absent key
  means voiced before it was recorded and shows `?`), `emcee move <show> <profile>|--delivered|--clear`, `emcee move --list` (one-off profile moves in `<emcee root>/moves.json`, keyed by `source.performance_id`; flock + atomic write; a move to an unassigned profile other than the delivered one is refused), `emcee say <text-file>` (ad-hoc
  narration: text file in, MP3 out, no package/script/LLM — voice via
  `--clone`/`--voice`/`--presenter` else the house `[tts] voice`, bed via
  `--bed`/`--bed-gain`/`--no-bed` else the package rules, chunking ON by
  default like `[tts] chunk`; `--no-chunk` without a bed is the one render
  that is not loudness-normalized), `emcee presenter add/edit/list/show/remove`
  (`presenters/<id>.toml`; `edit` changes any field with set/`--clear-*`
  flags, `--transcribe` drafts `voice_clone_text` on the mlx-audio server's
  STT model and writes it only on confirmation; `voice_clone` is stored as an
  absolute path), `emcee config init`.
- Read-only scheduler views (no lock, never write; `schedule` uses `load_epoch`, so with no
  `epoch.json` it previews from a provisional in-memory epoch and says so):
  `transmitter schedule [--days 7] [--clock FILE] [--library eligible|delivered]` (the persisted
  plan from now, then what the scheduler would append: per block its nominal/actual start and slip,
  shows with `~` on estimated lengths, fill cause, station breaks, MISS, degraded, bent rules and
  missing announcement audio, then a summary; a block entered mid-way, i.e. the phase-1 cutover or
  a fresh run after an outage, may record a MISS on its first show: only with a clock file, and only when the plan's end lands outside that block's window),
  `transmitter library` (eligible shows by profile with count/median/p10/p90, the interstitial
  pool, ineligible packages by first reason incl. `awaiting fix from llama`). `status` reads
  persisted rows, the clock files and the interstitials folder only: clock source, current/next block, misses and
  fill minutes by cause for the last and next 24 h, bends, degraded blocks, missing announcement
  audio; none of it alerts. `packages/transmitter/scripts/probe_estimates.py --config <config.toml> --time-one SLUG` prints an ineligible
  package's reasons (or `not found`). `transmitter announcements [--days 8] [--clock FILE] [--export DIR]` lists
  the announcements the clock needs and writes `ann-<id>.txt` for the missing ones; voice them on
  the Mac with `emcee say` into `<station root>/interstitials` (`id-*.mp3` are station IDs).
  Clock: `<TRANSMITTER_ROOT>/clock.toml` + `clock.last-good.toml`; edit a draft and check it with
  `schedule --clock draft.toml` first. `plan` and `render` share a non-waiting plan lock
  (`PlanLocked`). Runbook: `docs/playout-setup.md` 7.2-7.3.
- Run (transmitter, playout on hugo — phases 1-3): `transmitter run` (service
  loop: plan/render once the lead drops below `low_water_hours`, and keep
  filling until it is back at `lead_hours`; publish + prune every minute;
  `--once` runs one tick), `transmitter plan|render|publish|status`,
  `transmitter fallback render <loop> [--notice <file>]`, `transmitter config
  init`, `transmitter offair on --reason … | off` and `transmitter budget
  [--raise-to <usd>]` (`offair` and `budget --raise-to` write `state/` directly,
  bypassing the publish lock, the guard and the PUT budget); `transmitter status` also shows the cost guard, kill switch,
  off-air flag and active alerts. Production runs the SYSTEM unit
  `packages/transmitter/systemd/transmitter@.service` (`Type=notify`,
  `WatchdogSec=45min`, env file `/etc/transmitter/<user>.env`), so it is
  `sudo systemctl … transmitter@<user>` with no `--user`. hugo's alerts:
  `[alerts]` in config.toml; `SMTP_USERNAME`/`SMTP_PASSWORD`/`NTFY_TOKEN` in the
  env file; dedupe in `~/.transmitter/alerts.json`; the dead-clock check fetches
  `<site_url>/live.m3u8`. **The dead-clock check and the relay run on a daemon
  monitor thread** (`monitor.py`) every 60 s, off the service tick, with its own
  get-only R2 reader (never writes, never touches `guard-cache.json`, never pings
  the watchdog); `monitor-stalled` (level, sent at once) fires from the main tick
  when its last pass is over 5 min old; `run --once` checks once on the main
  thread and does not relay; the plan step pings the watchdog after each show
  analysis (`Station.frames_of`). **Alert gate:** every-minute alert keys
  (antenna `GATED_KEYS`, transmitter `GATED_CODES`) send only after `GATE` = 3
  consecutive failing observations (antenna: minutes; transmitter: ticks, or
  monitor passes for `dead-clock-check`); spend/off-air keys and one-shot keys are
  never gated, and two antenna raise sites (the metronome stall branch of
  `metronome-down`, `guard-unknown` after an unblock) send at once. **Relay:**
  antenna appends each invocation's sent alerts to `state/alert-relay.json` (a
  ring of 50, stream + seq) after the email; hugo's monitor thread relays them to
  its ntfy (cursor `~/.transmitter/alert-relay-cursor.json`, `RELAY_MAX_AGE_S` 1 h);
  the Worker sends no ntfy. State in `~/.transmitter/` (`TRANSMITTER_ROOT`); R2 keys from
  `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`. Tests:
  `packages/transmitter/tests_transmitter/` (a package, NOT `tests/`: llama's
  test modules are top-level and emcee's are the `tests` package, so the name
  would collide); ffmpeg-dependent tests skip without ffmpeg;
  `packages/transmitter/scripts/test-in-debian12.sh` runs them on hugo's
  Python 3.11 + ffmpeg 5.1 (needs docker). Container spike:
  `python -m transmitter.spike build|serve <dir>`.
- antenna (cron-only Cloudflare Worker + static player): `cd antenna && npm
  ci && npm test` (vitest in the Workers runtime via
  `@cloudflare/vitest-plugin`; `npm test` first checks `src/pages.ts` is fresh,
  `npm run pages` regenerates it), `npx wrangler deploy` (run `--dry-run`
  first; `--var` overrides for the verification items; see the runbook),
  `ANTENNA_BUCKET=<bucket> npm run deploy:assets`. Secrets go in with
  `wrangler secret put`: `CF_ACCOUNT_ID`, `CF_ZONE_ID`, `CF_ANALYTICS_TOKEN`,
  `CF_WAF_TOKEN`, `ALERT_EMAIL_FROM`,
  `ALERT_EMAIL_TO` (the Worker sends no ntfy; an existing deploy deletes its old
  `NTFY_URL`/`NTFY_TOKEN` secrets); `BILLING_ANNIVERSARY_DAY` is a committed var. The committed
  `send_email` binding `ALERT_EMAIL` is unrestricted, the destination exists
  only as the `ALERT_EMAIL_TO` secret: never put `account_id` or an address in
  `wrangler.jsonc` (a test enforces this). Cloud setup and the phase-1/2
  verification checklists: `docs/playout-setup.md`. The metronome's switch is the var `METRONOME` (`"on"` enables it; rollback `npx wrangler deploy --var METRONOME:off`, then commit `"off"`): `docs/playout-setup.md` section 9.

## What this is

Two Python CLIs — `llama` and `emcee` — that together carry an archive.org
Live Music Archive (LMA) recording all the way to air (the playout side,
`transmitter` + `antenna/`, is described at the end of this section). They ship as separate
signed binaries and know nothing of each other's internals; the only
contract between them is the delivered package on disk. Usage tilts heavily
toward Grateful Dead shows (two sets + encore).

`llama` finds concerts on the LMA, winnows them for quality, researches the
specific performance online, and emits a self-contained "show package"
(verified audio, m3u, manifest v3 with track titles/set breaks, vetted
research + reviews digest, and a required neutral vetted `briefing` for
scriptwriters) for an automated in-house radio station. `brief` is llama's
sole text stage — llama does not write DJ scripts, has no presenters, no
TTS, and no `[tts]`/presenter config. Its `deliver` gate is just: packaged,
not held for review, and every manifest track's audio file present on disk
— plus it refuses an emcee-voiced destination unless `--replace-voiced` (single
name only). After delivering it drops the library's own copy of the audio (the
station copy is the one that airs; archive.org is the re-fetch source), so
a delivered show in `~/.llama/shows/` normally has an empty `package/audio/`.

`emcee` (dist name `llama-emcee`, bare CLI `emcee`) is station-side and runs
**after** `llama deliver` — it operates on the delivered-packages folder
(`[station] root`), never on llama's own library. "Not broadcast-ready" IS
the work predicate: `emcee run` scans the station root and voices every
package that isn't yet broadcast-ready, no separate state file needed.
The one exception to the package-shaped rule is `emcee say`, which voices
an arbitrary text file to an MP3 — no package, no manifest, no LLM call —
reusing the same voice/bed resolution and `audio.render_speech_mp3`
renderer as the DJ clips.
emcee owns presenters (`presenters/<id>.toml`: name/sex/character +
`voice` XOR `voice_clone`), the script LLM task and its own factual guard,
`speech_text` normalization, TTS (hosted Mistral Voxtral by default,
ElevenLabs as an opt-in alternative, and a free local `mlx_audio` backend
over mlx-audio's server; a presenter may pin any of the three with `tts`, and
clones are voiced on voxtral or mlx_audio, never elevenlabs), instrumental
beds, the per-segment render cache, and
assembling `dj-audio/`/`broadcast.m3u`. Its `[assign]` config maps a llama
profile name to a presenter + on-air title, keyed off the
effective profile (`manifest["source"]["profile"]`, which llama stamps on every
package it delivers, unless a move or `[assign.artists]` rule overrides it). emcee writes `dj-notes.md`, `dj-audio/`, and `broadcast.m3u`
straight into the package directory llama delivered, and rewrites the
manifest's `dj_notes`/`dj_audio` blocks in place (llama writes both as
`null` — they are emcee-written passthrough blocks in the shared manifest
model). emcee never imports llama.

**Single-writer station, no lock.** Unlike llama (parallel-safe via flock,
below), emcee assumes exactly one `emcee run` at a time against a given
station root — it takes no lock. Overlapping runs can't corrupt a package
(unique-temp + atomic rename everywhere, in both tools), but they *will*
double LLM/TTS spend by voicing the same pending package twice
concurrently. Don't fan out `emcee run` the way llama's workspace tolerates
concurrent `llama get`s.

LLM model choice is tiered (low/medium/high; haiku/sonnet/opus on claude_cli,
gemini-flash/sonnet-5/opus-5 on openrouter): medium by default, high for
llama's interpret/deep_research/brief and emcee's scriptwrite, low for
vet_research,
overridable per task via `[llm.<task>]` `tier`/`model` or per backend via
`[llm.tiers.<backend>]`; a failed validation's final retry escalates one
tier (pins never escalate).

`transmitter` (dist `llama-transmitter`, CLI `transmitter`) is the playout
side, reading the station root (over NFS on hugo) and never importing llama or
emcee (enforced by `test_no_llama_or_emcee_imports.py`). The stream is a
function of the wall clock: segment N is AAC frames [441N, 441N+441) of one
frame line whose frame 0 sits at the epoch, d = 10.24 s exactly; each show is
encoded once (ffmpeg native `aac`, ADTS) and cut by counting frames, never by
ffmpeg cut points. Segments go to R2 in ascending N and `state/horizon.json`
only advances past confirmed PUTs: before the horizon PUT a batch persists
its candidate `last` as the local `publish.json` `high_water`
(`state.PublishState`), so a crash between the PUT and the save cannot let
`plan_step` re-plan keys R2 may already list; the horizon is never rewritten
below that mark (a batch under it is a "horizon held" — and `fallback render`
likewise defers its horizon rewrite, the next publish batch carrying the
version). `service.HeldTracker` alerts `horizon-held` after
`HELD_ALERT_AFTER = 3` consecutive `publish_all` passes ending held, since
each pass re-sends the same batch and spends PUT budget. Publish, prune and
`fallback render` share a non-waiting flock (`publish.publish_lock`): when it
is held they raise `PublishLocked`: `run` holds it only during its
once-a-minute publish/prune step, so a manual `transmitter publish` while the
service runs normally succeeds (serialized, spending PUTs from the same
budget) and exits 1 with `error: ...` only when it overlaps that step, while
`run`'s own step just logs a warning and retries next tick. `antenna/` is a
cron-only Worker (no routes, `workers_dev = false`) that rewrites `live.m3u8`
at every grid boundary, plus the static player; listeners only ever fetch
cache-served R2 objects. Its clock bounds its own spend
(`antenna/src/clock.ts`): `MAX_PUTS = 10` per invocation, a horizon whose `d`
is not 10.24 is refused (`horizon-refused`, nothing written), and
`LOOP_SECONDS` is clamped to 75 (`loop-clamped`). Off-air (from
`state/offair.json`, or a horizon more than 24 h stale) plays the notice from
the fallback, so transmitter publishes NOTHING — no segment, no horizon — until
`fallback render` has recorded a fallback version in the workspace: every
publish pass alerts `no fallback rendered` instead (gated: after 3 consecutive ticks; the fallback check sits before the
first PUT, since segment files are dropped only after a horizon PUT and would
otherwise be re-PUT every tick), and prune likewise refuses to rewrite the
horizon (`stopped: no-fallback`, before any delete) if `fallback.json` is lost
later. Every horizon therefore names a fallback (publish, prune and `fallback
render` are its only writers). If the named fallback is unusable in R2 anyway
(its `index.json` deleted by hand, or `len < 1`), off-air writes an
ENDLIST-only playlist (no notice; players stop) and logs
`offair-without-fallback` once per invocation; the WAF kill switch remains the
hard stop (`docs/playout-setup.md` section 4 step 4).
**Cost guard (phase 2).** It runs first in every antenna invocation
(`antenna/src/guard.ts`), evaluating when its last attempt is 15 min old (or at once after a raise) through
the account-scoped GraphQL API, pricing through the allowances plus the $5
base and projecting each meter from the last 3 h. The `tripped` latch sets at
actual >= 90% or projected >= 100% of `MONTHLY_BUDGET_USD`, and also when blind
(no reading for 6 h). `blocked = tripped OR offair` is reconciled every
invocation (ENDLIST playlist, off-air `index.html`, the kill-switch WAF rule
found by its description) with etag-conditional PUTs so a trip is never lost;
an unreadable state means the invocation writes nothing. Alerts go out after
the last playlist write, and the clock line logs `guardMs`. VLC needs
stop/play at a fallback-to-live switch of a fresh run
(`EXT-X-DISCONTINUITY-SEQUENCE` restarts at 0): a documented limitation. The
spend bounds above (`MAX_PUTS = 10` etc.) are unchanged. **Playlist
hold-back:** live playlists list `PLAYLIST_WINDOW` 16 segments, ending
`PLAYLIST_LOOKAHEAD` 12 past the one airing, with `EXT-X-START` and
`EXT-X-SERVER-CONTROL:HOLD-BACK` at 122.88 s (`PLAYLIST_HOLD_BACK` 12), so
players sit at the wall clock with ~123 s of runway against a late cron fire.
Keep lookahead = hold-back (hugo's dead-clock check dates the playlist by its
own hold-back); a lookahead alone adds no runway. Phase-2 SDD record:
`docs/superpowers/2026-10-12-playout-phase2-sdd/`.

**The metronome** (`antenna/src/metronome{,-core,-engine}.ts`; spec `docs/superpowers/specs/2026-10-14-antenna-metronome-design.md`). With the var `METRONOME` exactly `"on"`, one SQLite-backed Durable Object (`Metronome`, `idFromName("metronome")`, binding `METRONOME_DO`, migration v1 `new_sqlite_classes`) writes `live.m3u8` from an alarm re-armed at every boundary + 25 ms. It works under a 15-minute lease that cron renews every minute over RPC (`renew(play | hold | null)`), carrying the guard's verdict, the horizon and the fallback. The object never reads R2 and never decides blocked. It accepts a blocked lease or a hold unconditionally, and an unblocked one only when it is strictly newer by `verdictAt`; it computes expiry on its own clock. Cron's own loop runs only as the fallback, raising `metronome-down`: when renew throws or times out (15 s), when a play lease is not accepted or not written, or when two consecutive renews find the chain stalled for over 30 s. Its own spend bounds:
- at most 10 PUTs and at most 12 alarms per rolling minute;
- a 5 s bound on each PUT;
- a fixed 8-key storage set;
- the chain ticks only while the playlist is live (never blocked, held or expired).

Anything but `"on"` is the rollback: cron's loop exactly as before, and the object deletes its alarm. The cost guard prices three DO meters (requests, duration in GB-s, rows written); while the switch is `"on"`, an empty recent DO window is a failed reading. Tests: `antenna/test/metronome*.test.ts` and `clock-metronome.test.ts`. **`@cloudflare/vitest-plugin` 1.4.0 does not isolate DO storage per test**, so DO tests `reset()` after each test. Real alarms fire on time in tests, so leases put `now` mid-segment. Rollout and rollback: `docs/playout-setup.md` section 9.

transmitter must stay Python 3.11-compatible (hugo is Debian 12: Python 3.11,
ffmpeg 5.1); the Debian-12 script above is the gate for that. Design:
`docs/superpowers/specs/2026-10-09-playout-design.md` (phases 1–3 built; the
full player is phase 4).
**Scheduler (phase 3; spec `docs/superpowers/specs/2026-10-25-scheduler-design.md`, measurement
`docs/superpowers/2026-10-25-scheduler-measurement/evidence.md`).** Append-only: it extends the
persisted plan from its end, never rewriting a row, and pieces are shows plus one-clip
interstitials (announcements, station IDs) from `[interstitials] dir` (absolute; default
`<station root>/interstitials`). The clock file is strict; an invalid one alerts `clock` and
planning continues on `clock.last-good.toml`, else a daily 00:00 open block with a ±12 h window. Announcement ids are
a hash of the rendered text, so template edits retire voiced clips; missing audio degrades
two-block, one-block, station ID, gap. `aired.jsonl` (append-only rotation history, backfilled
from `plan.jsonl`) refuses appends on an epoch mismatch (alert `history`). A package manifest
with a non-null `awaiting_fix` is not airable. Plan and render run under the plan lock. Plan
rows tolerate scheduler fields (`4fa87a7`/`af46d72`, the oldest safe rollback once the scheduler
has run).

## Architecture (from the spec — the short version)

- **Staged pipeline over an on-disk workspace** (default `~/.llama/`):
  interpret → search (wide net) → winnow (quality gate + optional human gate)
  → select-recording → gather → research → vet (grounding check) →
  brief (always on) → package. Every stage reads/writes plain files;
  run-level artifacts live in a per-run directory, show-level artifacts in a
  canonical `shows/<slug>/` library (one dir per performance, reused across
  runs); stages write outputs only on success and are individually
  re-runnable (`llama redo <show> --from <stage>`). `brief` is llama's sole
  text stage — it emits a neutral vetted briefing (`briefing.md`/
  `briefing.json`) for scriptwriters — no flag, no config gate, factually
  guarded (retry-once-then-hold), and stamped with the `narration`
  directive from `overrides.json`. The show-package contract is **manifest
  v3**: a required `briefing` block (`file`, `json`, `narration`, `vetted`)
  alongside the existing fields; `package` copies both briefing files into
  `package/` and hard-fails if a show has no briefing artifacts. The
  manifest model also carries `dj_notes`/`dj_audio` fields, which llama
  always writes as `null` — they are **emcee-written passthrough blocks**,
  filled in station-side after delivery; llama itself never populates them.
  `stages/synthesize.py` (the in-house DJ script/voice path) was cut
  entirely in this split — scriptwriting and voicing moved wholesale to
  `emcee` (umbrella spec:
  `docs/superpowers/specs/2026-07-28-split-architecture-design.md`).
- **Parallel-safe workspace:** multiple `llama` processes may run concurrently
  against one local `~/.llama/`. Coordination is advisory `fcntl.flock`
  (`packages/llama/src/llama/locks.py`) at two scopes — a short **ledger lock**
  (`ledger.jsonl.lock`) around every ledger mutation, and a long **per-show
  lock** (`shows/<slug>/.lock`) around `process_show` and every single-show
  mutator (`redo`/`fix`/`deliver`/`rm`). Locks auto-release on
  process death (no stale-lock reaping). Same-performance runs serialize
  (first builds, others wait and reuse); independent shows run fully in
  parallel. Readers (`show`/`status`/winnow dedup) never lock. All atomic
  writes use unique temp names. POSIX-only; non-POSIX degrades to no-op
  locking. **`emcee` does not share this locking scheme** — see emcee's
  bullet below.
  **Run lock (third scope, spec §4):** the commands that work a run — `get`,
  `run resume`, `run approve`, the run-level `redo --run <id> --from search|winnow`
  and `run rm` — take an exclusive flock on `runs/<id>/.lock` exactly once, at
  command entry, held to exit, **never inside `_execute`** (`locks.run_lock`). Lock
  order is **run ⊃ show ⊃ ledger**; `process_show` stays lock-free. A held lock means
  live: all but `get` try non-blocking and refuse. `get` on a dir it just created
  locks blocking (only a reader's probe can hold a fresh dir's lock, briefly);
  `get --name <existing>` refuses a live run. The helper never creates a missing run
  dir (`RunMissing`), and after acquiring checks the locked fd is still
  `run_dir/.lock` (inode and device) — that check is what stops a fresh `get` whose
  dir was removed under it from working an unlocked dir. `run rm` holds the lock
  through `rmtree`. Readers (`run list`, `status --by-run`, `--json`) probe with
  `run_is_live`: a non-blocking acquire released at once, no `O_CREAT`, and report
  `running`. **Rollout caveat:** a run started by a pre-v2.14 binary holds no lock and
  is invisible to the sweep; don't sweep while one is going. **Known limitations:**
  a lock attempt landing inside `run rm`'s `rmtree` recreates `.lock`, so `rm` fails
  and leaves a `.lock`-only dir, listed as needs attention (a second `run rm`
  removes it); a `run list` probe colliding with a resume starting that instant makes
  the resume refuse; the milliseconds between a fresh `get` creating its dir and
  locking it are unguarded against `run rm`. None of the remaining windows can
  produce two workers.
  **Download cap:** at most `download_slots.DOWNLOAD_SLOTS = 8` concurrent audio
  downloads per workspace, across processes, via flock slot files
  `<root>/.download-slots/0..7.lock` (non-blocking polls with jitter; one `waiting
  for a download slot` line per file; the slot is held for one attempt and released
  before any inter-attempt sleep; module constant, not config). **Known limitation:**
  not FIFO — with more than 8 downloading processes a waiter may wait until a
  holder's show finishes downloading.
- **`overrides.json`:** the one durable, app-edited per-show input —
  excluded source-track filenames, `narration` (`full`/`vague`), and
  metadata corrections (`venue`, `city`, `date`, `titles`: track#→forced
  title, `set_breaks`: track numbers a break falls after, numbered-sets-only,
  `encore_after`: track number past which every remaining track relabels
  "encore") — that survive every `redo`. `gather` drops excluded files (reason
  `operator-excluded`), forces `venue`/`city`/`date`/track titles/set
  breaks when their fields are set (bypassing structure alignment entirely
  for `set_breaks`/`encore_after`; `encore_after` must exceed every
  `set_breaks` entry), and `brief` reads `narration=vague` to write a
  briefing that names no songs and asserts no set structure (the LLM's own
  opinion of `narration` is never trusted — stamped from `overrides.json`
  after generation); `show.json` stays purely derived and is never itself
  hand-edited. **Piece 4:** `titles`, `set_breaks` and `encore_after` are STORED as
  filenames under the same key names (`{"<file>": "<title>"}`, `["<file>", ...]`,
  `"<file>"`); the "track#" wording above and the `fix`/triage flags are the
  OPERATOR syntax: a number means `show.json`'s numbering (what `show --tracks`
  shows), translated through `show.json` (see the piece-4 bullet). `llama show` is strictly read-only; `llama fix <show>
  <edit-flags>` (flag-driven, single show, auto-runs the correct redo) and
  `llama triage` (interactive walkthrough over held shows, default
  `--held`) are the only ways to edit it — `--exclude`/`--unexclude`
  (filename or track number, `--tracks` on `show` lists them) and
  `--set-venue`/`--set-city`/`--set-date`/`--set-title N=…`/`--set-breaks`/
  `--set-encore` (plus their `--clear-*` counterparts) all redo from
  `gather`, and a hold **self-clears** whenever the re-gather no longer
  reproduces the flag that caused it (gather recomputes
  `needs_review`/`review_flags` from scratch every run). `--exclude`/
  `--unexclude` are joined by **`--include xN|FILE`** (`overrides.include`),
  which re-admits a file the junk filter dropped and redoes from `gather`
  like the other two — applied inside
  `filter_files` after the junk arms and after duplicate-listing dedupe and the derivative dedupe (an included copy wins its group) but
  **before** play-order derivation, so the floor cannot move and order is
  derived over the final set (a re-admitted file with no track tag reverts
  the recording to filename order). A file in both lists is excluded; the
  CLI keeps the lists mutually exclusive so that never happens through it.
  `--include` on an `operator-excluded` row un-excludes instead. **Do not
  loosen the junk constants instead** — this override is why they stay put.
  A hold flagged "unresolved track titles" additionally gets **`--suggest-titles`**
  (`fix`) / **`[t] suggest titles`** (`triage`, same helper, offered only
  under that flag): both build a canonical setlist via
  `build_canonical(..., provider=None)` — deliberately **not** the same
  call `gather` itself makes: `run_gather` passes gather's real provider
  (`gather.py:616-618`), and `provider=None` is precisely what stops this
  CLI-side proposal path from ever firing the `extract_setlist` LLM
  fallback. The difference is benign, not weaker — an unrankable setlist
  yields an infeasible proposal rather than a silently worse one — and
  then render a per-track proposal table, for tracks the DP can propose
  for, via the correspondence DP (`llama/correspondence.py` —
  **proposal-only, never auto-adopted**; unanchored monotone
  correspondence measured 45-52% wrong, so a human confirmation is the
  only thing standing between a proposed title and adoption). **The DP is
  gated by an accountability guard that declines rather than renders**
  (`correspondence._unaccounted` / `_contradicts_forced_gaps`): each
  maximal run of still-`unresolved` tracks — the only adoptable ones —
  must be **count-forced between anchors**, exactly as `setlist-gap`
  requires, and the DP's own solution must not contradict a forced gap.
  Both checks are exact structural counts, never a margin/score/coverage
  threshold; they reuse `structure.anchor_spans`/`gap_span`/
  `unresolved_runs`, extracted from `adopt_gap_titles` so the silent rung
  and the confirmed one cannot drift apart on what an anchor is. What
  they do NOT share is the `_hygienic` veto — an operator reads this
  table — which is the command's whole residual value over `setlist-gap`.
  **Consequence, deliberate and load-bearing: a WHOLLY UNTAGGED tape is
  no longer proposable at all**, since nothing anchors the setlist to it.
  That is the population this feature was aimed at, and the M3 gate
  measured it 13-of-22 wrong via a uniform off-by-one with nothing in the
  table saying so. **A whole-tape count comparison cannot substitute for
  the per-run one**: `yondermountainstringband-2005-12-31` (declines) and
  `trampledbyturtles-2007-07-20` (renders, correctly) are both 24
  song-like tracks against 23 canonical items — measured, don't retry it.
  On
  confirmation, the proposed titles for still-`unresolved` tracks are
  written into `overrides.titles` at once (a filler row gets no proposal
  and stays `(unresolved - hand-edit)`; a track that already carries a
  title is never overwritten), then redo from `gather` like every other
  metadata edit. `--suggest-titles` refuses to combine with
  `--exclude`/`--unexclude`/`--include` in the same `fix` invocation (any
  of the three renumbers tracks before the proposal's numbering would
  apply), and an
  explicit `--set-title N="..."` on the same invocation always wins over
  the proposal for that track. On a multi-set show,
  `--set-encore` must be combined with `--set-breaks` to keep set labelling
  correct — the override path skips alignment entirely rather than layering
  on it, so `--set-encore` alone flattens every set into `"1"`. Any
  structure override (`--set-breaks` and/or `--set-encore`) takes that same
  path and loses every segue regardless — combining the flags fixes set
  labelling but does not bring segues back. The other
  two gate-2 resolutions: **accept-vague** (`fix
  --narration vague` → redo from `brief`, regenerating the briefing and
  package too, clears the hold immediately), and **overrule** (`fix
  --overrule` → redo from `package`, clears the hold without touching
  overrides).
- **`overrules` in `overrides.json`** (bulk-apply, spec "Overrules persist"): `Overrides.overrules: list[Overrule] = []`, each `{identifier, kind, subject, flag, source, at}` (`subject` a list of strings or null; `source` `fix`|`triage`|`untitled`|`backfill`; the optional `note` names the basis, mostly on backfill records). `fix --overrule`, triage's overrule and `fix --untitled` record every flag they clear; `overrules.flag_key` maps a flag to its kind and subject (first match wins, table in the plan's Contracts; `duration mismatch on …` is not overrulable). Gather/vet/brief then turn a flag matching a rule (same `identifier` = the show's `source.identifier`, same kind, equal subject; `titles` matches when the new unresolved set is a subset) into the operator note `overruled: <flag>` in `notes.json` instead of a hold; any non-matching flag still holds. A re-selection makes every record on the old identifier inert (never deleted). `source: backfill` records come from `bulk_apply.py backfill`. 2.18.0's `fix` drops the key, which is why the campaign installs the new release first.
- **`awaiting_fix` and `campaign.json`** (bulk-apply; spec `docs/superpowers/specs/2026-10-25-bulk-apply-design.md`, "The `awaiting_fix` contract" and "The library side"): a STATION manifest may carry top-level `awaiting_fix: {reason, marked_at}` (absent or null = none), written only by `llama/station_mark.py` as a raw-JSON read-modify-write under the show lock (never llama's `Manifest` model, which has no such field; library packages never carry it). Any non-null value means not to be voiced and not to be aired. Per-show `<show>/campaign.json` is `{marks: [{at, reason, start_stage: gather|select, batch}], processed: {at, digests, manifest_sha256}|null, clears: [{at, outcome: equal|change accepted}]}`; a show is AWAITING FIX when `marks` is non-empty and `processed` is null or older than the last mark; an UNREADABLE record counts as awaiting (`status` shows it, `deliver` refuses `<slug>: cannot read campaign.json (<error>); check it by hand`, `reapply` fails the row retryably). `<show>/reuse-anchor.json` (`{identifier, tracks: [{filename, title}], written_at}`) is the pre-commit `show.json` track list that strict station reuse pairs against after a held outcome rewrote `show.json`. emcee has an `awaiting-fix` state: `emcee status` reason `awaiting fix from llama: <reason>` (`emcee status --state awaiting-fix`), `emcee run` prints `skip <slug>: awaiting fix from llama`, `emcee voice` and `run` refuse `awaiting fix from llama (<reason>); re-deliver from llama first`; a malformed mark (non-null, no usable `reason`) reads `awaiting fix from llama` / `awaiting fix from llama; re-deliver from llama first`; emcee's manifest rewrite preserves the field. transmitter treats a non-null `awaiting_fix` as not airable (see the scheduler paragraph). Marking refuses while an `emcee` process runs.
- **App-managed instead of hand-edited:** `llama profile artists <name>
  [--set "A, B, C"]` views or re-pins a profile's pinned artist roster.
  Between this, `llama fix`/`llama triage`, and `overrides.json`,
  `config.toml` remains the only file this design expects a human to
  hand-edit — for llama. (emcee has its own equivalent: `emcee presenter
  add/list/show/remove` manages `presenters/<id>.toml`, and its
  `[assign]` config table is the one thing a human hand-edits there.)
- **Tier 1 held-backlog guards** (deterministic, no LLM; spec
  `docs/superpowers/specs/2026-10-19-held-backlog-guard-fixes-design.md` as
  amended by the plan's "Recorded at Checkpoint B-F" blocks,
  `docs/superpowers/plans/2026-10-19-held-backlog-tier1.md`; evidence:
  `docs/superpowers/2026-10-19-held-backlog-tier1-evidence.md`).
  Each removes false holds only where the harness can enumerate the
  effect, and **sits beside the protected predicate, never loosening it**
  (`is_real_title`, `_TRACK_NUM_PREFIX`, `_STRUCTURE_PREFIX` untouched).
  A show whose gather
  would reach an LLM call is needs-LLM and stays held. 1a: a blank jerrybase
  venue is no evidence. 1b: `venues_equivalent` folds spelling and
  `cities_compatible` is the shared city predicate (metro table fixed a
  priori). 1c: on a single-event date only, a same-city name difference ships
  the selected recording's venue and notes jerrybase's. 1d: gather holds
  `recordings of this date disagree on city` when the selected venue is not
  `venues_equivalent` to the vote's and the cities conflict (an operator
  venue/city override suppresses it); step 1 checks cities only for pairs 1b
  newly made equivalent (`_venues_equivalent_pre1b` is the frozen old rule). 2a:
  `accept_short_tags` adopts a still-`unresolved` short tag only when a parse
  that is not the selected recording's own description names the same item
  (cross-source or it does not count). 2b: `placeholders.py` demotes placeholder
  tags (`Track 01`, `tmp`, timestamps, filename residue, one string or the
  item's title on every track) to `unresolved` at the tag rung, never into the
  positional `setlist` rung; the real song `2:22` is a known false demotion. 2c:
  `_GLUED_NUM_PREFIX` strips a glued track number only under the
  `_ENUMERATED_MIN_FILES`/ `_ENUMERATED_MIN_COVERAGE` vote. 2d:
  `_JOINED_NUM_PREFIX` (`^\d{1,3}[-_](?=[^\d\s])`) strips a
  hyphen/underscore-joined track number (`01-Hell In A Bucket`, `01_Song`) under
  the same vote, once, note `stripped joined track number:`; a `7-Up`-style
  title on an enumerated tape is an accepted loss like `100 Years`; `1.02 - `
  and `1-002` forms are not covered. 3a: `normalize_briefing` drops empty sets
  on generation and reuse. 3b: `known_song` is a superset of the old matcher
  (segue components, brief-local `E:` prefix, one trailing parenthetical; no
  fuzzy matching); the parts of a comma-merged title also count, ONLY when every
  top-level comma part ends in its own parenthetical (`Stay With Me (tease),
  Girl Named Sandoz (tease)`) -- a comma inside one title never splits. 3c:
  set-count and ordinal claims are ignored when qualified (`_NOT_SHOW_WIDE`),
  negated or scoped; both set-count regexes' `of` lookahead stops at the
  briefing-field newline, the vague branch's too (operator ruling 2026-10-20).
  4a: `right_show_gate` turns
  `unknown song` flags into a note at `RIGHT_SHOW_MIN_TAPE_FRACTION = 0.5`
  (stays 0.5) and `RIGHT_SHOW_MIN_ASSERTED = 4`, needs 2b and the show's own
  date, and reads date flags before 4b. 4b: an asserted date within
  `ADJACENT_DAY_WINDOW = 1` day of the show's own is context. 4c:
  `normalize_date` range-checks and reads a slash form day-first only when the
  swap is the valid one; `day_unknown_date` keeps a day-`00` date flagging. 4d:
  prompt wording, unmeasured offline; `reapply` never re-extracts, so it
  changes nothing in the backlog. 5a: `evidence_sets` counts numbered sets only,
  except `encore_lost` keeps the flag. 5c.1: a closer is not hard-flagged when
  only `is_filler` tracks follow it (`filler_tail_closers` makes it a note).
  5c.3: a leading-parenthetical fold is a fallback tier of closer matching.
  **5c.2 (numbered-set anchoring when only the encore closer is missing) was
  built, measured wrong on 5 structures and DROPPED at Checkpoint F: do not
  re-add it.**
  **Venue tie-break** (`gather.venue_tie_break`, spec `2026-10-21-held-backlog-small-fixes-design.md` slice B): on a tied grouping vote (raw strings, counted as `grouping._make_candidate` counts) the selected recording's own stripped venue ships, with `sel_city or vote_city`. It applies only when the two strings are `venues_equivalent` (measured 2026-10-21: 58 of 234 ties were not equivalent, e.g. "9:30 Club" vs "Nightclub", where the selected string was no better; those ship the vote, including ~20 unfolded spellings of one venue such as `1st`/`First Avenue`), never under an operator venue override, and only when its city is blank or `cities_compatible` with the vote's, and only in the arms that ship the vote unflagged: no event, unflagged 1a, and step 1 when the selected string passes step 1's full test. It never adds or removes a flag, `venue_source` stays `item`, and `provenance.json` is unchanged.
- **The taper's set/encore markers win** (held-backlog part 1, piece 2; spec `docs/superpowers/specs/2026-10-22-taper-set-markers-design.md`, plan `docs/superpowers/plans/2026-10-22-taper-set-markers.md`, acceptance `docs/superpowers/2026-10-22-taper-set-markers-evidence/acceptance.md`, SDD record `docs/superpowers/2026-10-22-taper-set-markers-sdd/`). `llama/taper.py` (`read_taper_structure` / `place_taper_structure` / `decide_taper`), called by `compute_gather` after step 1 and jerrybase anchoring, which stay the reference for every "was" note. It reads the selected recording's description, else its `notes` when the description has no marker at all (lineage lines place no boundary because they match no track); `parse_setlist` is untouched. Recognised, worded forms only: `Set 1-3`/`one-three`/`I-III`, the ordinals, `Disc N (Set M)`-style joins, a header plus a trailing `(duration|time)` annotation (Checkpoint A), the disc-and-set shapes (`Set 1 Disc 1`, `Disc/Set1`, `Disk 1: Set 1`, `CD1 Set 1`), inline mid-line `Set II:`/`E:`, and encore lines (`Encore`/`Encores`/`ENC`/`E`, `Encore 1:`). It asserts a structure only for two or three consecutive numbered sets, with or without an encore. **Whole-or-nothing:** the taper owns the whole structure with every boundary placed exactly (one track matches each side's boundary song, only filler between, no merged track across, no title repeated across the boundary; never a score or margin) or owns nothing and the show is computed as today. With no encore marker the last set runs to the end of the tape. Vetoes (each owns nothing; attributions in the spec): encore-like text, or an `_ENCORE_MARKER` track title, with no recognised encore marker; set-like text the reader does not recognise (llama-db, Checkpoint A2); ruling (d) keep today's encore (operator, Checkpoint A: no taper encore marker and step 1 has an encore after the last taper break); B4, a numbered step-1 break before the LATEST hit of set 1's first song within set 1's window (llama-db, acceptance defect, `stevekimockband-2000-03-31`); G1, no taper encore marker while today's path would reach the LLM branch (llama-db reading of (d)). **Ownership ships the taper's labels and skips `align_structure`;** jerrybase set-count and closer disagreements become operator notes (`notes.json`, never `conflicts`) and the `set breaks anchored from jerrybase` entry and `merge_conflicts` are dropped; segues and `matched` still come from step 1; the low-confidence flag is kept only when today's path would reach the LLM branch and align() coverage of the taper's items is also under the threshold. Fields: `StructureInfo.taper_owned` (persisted, permissive, absent on old dirs; `alignment` becomes `"taper"` only when the breaks differ from step 1 at song level, with a "was ..." note) and on `GatherResult` `taper_owned`, `taper` (the `TaperDecision`, None on the override path) and `step1_alignment`. **Replay relaxation:** a stored-`llm` show is replayable only when `gathered.taper_owned` (`replay.py`); any other stored-`llm` show stays needs-LLM. **Accepted limitations:** D1, on an owned show whose step 1 is in today's LLM branch the segues the LLM would have restored are lost (143 over 36 shows after G1, operator ruling (c)); an encore the taper did not mark folds into the last set without a hold because the jerrybase closer flag is a note (`furthur-2012-07-08`); an owned low-confidence hold on a correct structure (3 delivered shows); G1 costs `greenskybluegrass-2013-05-04` and `soulive-2001-12-15` a correct taper structure. Harness: `scripts/replay_holds.py run --strip-structure-overrides` replays override shows as if unoverridden (writes no apply lists); `compare` writes `taper_cleared.txt` and `taper_changes.txt` (tiers: songs moved, labels renamed, filler labels only, segues changed, provenance only, needs-llm not owned, unreplayable, stored-llm moved; keep the `segues changed` rows out of non-held re-processing); `scripts/taper_probe.py gate|forms|delta|score` is the read-only yield, form, delta and score probe.
- **Title hygiene** (held-backlog part 1, piece 3; spec `docs/superpowers/specs/2026-10-22-title-hygiene-design.md`, plan `docs/superpowers/plans/2026-10-23-title-hygiene.md`, acceptance `docs/superpowers/2026-10-22-title-hygiene-evidence/acceptance.md` (the (d) table and the measured bar), SDD record `docs/superpowers/2026-10-23-title-hygiene-sdd/`; Checkpoint A/B rulings: `orch-r1/checkpoint-a-rulings.md`, `orch-r2/checkpoint-b-rulings.md` there). Fills unnamed tracks from sources that earn trust and stops the positional rungs shipping junk or shifted titles. `compute_gather` is now two calls: `gather.title_inputs` (the prelude) and `gather.title_cascade` (tag layer through 2a, new slices at their places, each behind `enabled_slices`; `enabled=frozenset()` reproduces the pre-piece-3 title block exactly, gate 0 on 3983/3983 shows). New modules `desc_list.py` (readers, cleaning), `title_hygiene.py` (checks, D, S plan, slice 4), `lossless_titles.py` (C), `title_cosmetics.py` (slice 5); `title_hygiene.ENABLED_SLICES` is all five. **D (slice 2):** `title_source` `desc-position` (always tautological, in `structure.TAUTOLOGICAL_TITLE_SOURCES`; 13 characters fits the `show --tracks` column) fills `unresolved` tracks from the SELECTED recording's own description, by position, when an admissible list's entry count equals the kept track count; after setlist-gap, 2a and slice 4, before `align()`; never touches a resolved track or an override; may fill a 2b-demoted position. Reader (i) reads contiguous numbered blocks (a restart at 1 only after a recognised set/disc or encore header, R16); reader (ii) takes `parse_setlist` items only when every contributing raw line yields exactly one (may admit a list (i) rejected as non-contiguous, Checkpoint A (a)); (i) wins; neither reads a run-on line. **Slice 1, the gate** (`title_hygiene.judge`): check 1 (candidate hygiene after `desc_list` cleaning; never `is_junk_tag`), check 2 (no adjacent duplicate), check 3 (tape agreement, D only), written durations, the agreement check (`AGREEMENT_FLOOR`; not a shift detector). Header, annotation, filename, timestamp, over-length, first-entry `metadata_norms` and `is_junk_title` failures decline every fill that rung would make on the show; only slot placeholders, a later `metadata_norms` hit and a `Filler:` entry decline per track; checks 2 and 3, durations, agreement and the untagged checks are show-level. A declined track stays `unresolved` (the hold catches it); notes go to `notes.json`. New check-1 shapes apply to S and D only; setlist-gap and sibling-align keep `hygienic_title`. **S by canonical source, and Q1:** `plan_setlist_rung` (modes `none`, `today`, `chosen`, `untagged`, `deferred`, `gated`; read it) decides where the whole-tape `setlist` rung fires; with a `chosen` canonical and a count-matched list it is D's job. **Q1: S never fills a wholly untagged tape** (`title_hygiene.wholly_untagged`, under `siblings.MIN_ANCHORS` independent titles); D may, under `block_size_mismatch` and `sibling_disagreement` (inert without evidence). `INDEPENDENT_SOURCES` is a new set; `siblings.INDEPENDENT_TITLE_SOURCES` is unchanged and must never be extended. **C (slice 3):** per-track lossless titles from the same archive item at the TAG LAYER (`lossless_titles.apply_lossless`, before `resolve_titles`), only where `_recover_format_titles`' first gate excluded the item (recovery constants untouched), on the filename-stem bijection, stamped `sibling-format` per track. C1 fills a blank, placeholder or non-real, non-2a-shaped delivered tag with a real, hygienic lossless one that agrees with the same-position list entry or canonical item, or else when `MIN_ANCHORS` comparison stems agree and none disagrees; one target failing all three declines every C1 fill on the show. C2 replaces a real (or 2a-shaped) delivered tag only when the lossless one agrees with the ONE reference (list, else canonical) and the delivered one does not. Never taken: a wholly `[...]` lossless tag, one ending `:`, the delivered title plus only `@ ^ * #`. Show-level skip when two or more lossless tags match the reference at +-1 but not their own position. **C-1, the shifted delivered tag set** (Checkpoint B ruling 1): if two or more delivered real tags disagree with the reference at their own position but agree at +-1, AND at least 2 of those signature positions were themselves confirmed by C with a lossless tag (the 2026-10-23 narrowing, 3751735), C's confirmed changes stand and every other delivered real, non-filler tag not agreeing at its own position is demoted to blank, with the one note `lossless titles: shifted delivered tag set; unconfirmed tags demoted: tracks ...`; every later rung (sibling-align, setlist-gap, 2a, slice 4, D, deferred S) sees it as `unresolved`; it never touches an `overrides.titles` position (`_without_override_positions`). It demotes on `darkstarorchestra-2014-07-31` only (fresh-get view, #3; on the as-is view #3 is an operator override); the signature also holds on `lettuce-2002-07-13` and two `tedeschitrucksband` shows (2019-02-15, 2020-01-15), where every unconfirmed tag already agrees at its own position, so nothing is demoted. **Slice 4** (`title_hygiene.confirm_short_tags`): 2a's relaxation for a short real tag (`J`, `420`, `M80`) failing `is_real_title`: accepted when its core equals the WHOLE entry at the same position of the taper's count-matched list, an independent neighbour within `SHORT_TAG_WINDOW` agrees and none disagrees, a core of at least `STEM_SUBSTRING_MIN` characters is not a substring of the file stem, and 2a's `is_junk_tag`/`metadata_norms` veto still holds (`12.28.99`, `2:22` stay out); runs before D. **Slice 5** (`title_cosmetics.cosmetic_strip`): a pass on the FINAL titles of sources `tags`, `sibling-format`, `setlist`, `setlist-gap`, `desc-position`, `sibling-align`, after every flag and set label, before `Show` is built (leading `m:ss`, embedded `dNtN` stems, `.wav`/`.flac` tails, and per Checkpoint B ruling 5 a leading `<artist> - `, `Encore- ` and a trailing ` H2`; a strip that edits inside a bracket pair is declined, M-6). It never touches an `override` or `unresolved` track, **never strips `E: ` or set markers** (`S2:`, `set1:`) and never `4:20 Polka`, `8 Cylinders`, `1 Samuel 15:23`. **Q2, self-filled tapes ship:** when every song-like track is `desc-position` and D passed every check (`title_hygiene.is_self_filled`, `GatherResult.self_filled`), gather makes no `align_structure` call and raises no `low-confidence structure alignment` on the not-owned branch; a tape with ANY independent song-like title keeps today's coverage rule. The taper never owns a self-filled tape (`taper._counts`; pinned by a test). **Replay relaxation:** a stored-`llm` show is also replayable when `gathered.self_filled` (`replay.py`); `ShowReplay` gains `self_filled`, a `desc-position` count and the per-row `cascade` record (also on needs-LLM rows). **Fixed constants** (do not retune): `AGREEMENT_FLOOR` 0.5, `WRITTEN_DURATION_MIN_SHARE` 0.5, `WRITTEN_DURATION_TOL_SEC` 15, `WRITTEN_DURATION_TOL_FRAC` 0.10, `SHORT_CORE_LETTERS` 3, `SHORT_TAG_WINDOW` 2, `STEM_SUBSTRING_MIN` 2, `_DISC_INDEX`/`_SET_INDEX`, `desc_list._ENTRY_LEADER`; the 2c/2d vote constants, `siblings.MIN_ANCHORS`, `is_real_title`, `_TRACK_NUM_PREFIX`'s `\d{1,3}`, `_STRUCTURE_PREFIX` and `placeholders.py` are untouched. **Dropped at Checkpoint A:** nothing (ruling 1); P1 and P2 were fixed. Checkpoint B ruling 5 extended slice 5 (artist prefix, `Encore- `, ` H2`, M-6), D's cleaning (a leading `--> `, trailing `^`/`$`, a duration glued after `)`) and M-1 (`title_hygiene._LONE_MARKER`). Shipped C titles lose a trailing taper segue/footnote marker (Checkpoint A (h), `desc_list._TRAIL_MARKERS`). **Measured** (acceptance at `c49cdd1`, 3983 shows): holds cleared 7 as-is / 40 fresh-get, added 14 / 15, each in the (d) table; 0 of 900 changed tracks (fills, replacements and slice-5 strips) hand-checked wrong, zero shifted shows; slice 1 holds one good S show (`lotus-2010-06-10`). **Accepted limitations:** (C-1) an uncorroborated shifted delivered set (fewer than 2 C-confirmed signature positions) ships as tagged, as before the fix wave. (C2 and coverage) C2 raises no flag of its own; it moves alignment coverage both ways (measured: 1 hold added, 6 as-is / 9 fresh-get low-confidence holds removed). The one hold added, `kinggizzardandthelizardwizard-2022-10-22` (two right `(part one)` titles drop coverage 12/13 to 10/13, under 0.8), is an accepted cost (operator ruling 2026-10-23). GY!BE `12-28-99` (`godspeedyoublackemperor-2011-03-15`: tag and description agree, the file is mostly another piece). The untagged residual (an untagged tape with no disc structure, no tagged sibling and no written durations can hide a coincidental shift; the spec's sample had 0 such failures, gate R12 0 bad in 8 residual shows). `w/ ...` survives in a count-forced setlist-gap run. The anchor-span limitation on `fix --suggest-titles`/triage `[t]` (`structure.anchor_spans` treats `desc-position` as anchors). P3: 2 false agreement holds, GY!BE 2000-10-30/31 (setlist.fm aliases vs `12.28.99`). P4: `elliottsmith-1997-05-15`, a junk header-fragment tag drives agreement. (g) `rosehilldrive-2008-12-31` `07-8th Wonder` (`desc_list._ENTRY_LEADER` does not cut a leader followed by a digit). `deadandcompany-2016-07-15` ships a shifted-tag delivery (piece-5 class, untouched). Abbreviations shipping the taper's wording (`MRG` via C2, `newmastersounds-2009-06-06` #5; `O` via slice 4, `mymorningjacket-2006-06-04` #14; Checkpoint B ruling 6). Reader gaps that cost holds, not accuracy (a bare trailing `N` line read as a disc label, `lotus-2010-06-10`; a disc header carrying a duration, `railroadearth-2007-01-28`; Checkpoint B ruling 7). The `1 Samuel 15:23` trailing-time edge (R19 strips it; Checkpoint A ruled not to gate). `E: ` kept by slice 5. Delivered-tag conflicts piece 3 does not touch (`greenskybluegrass-2013-05-04` #11/#16). Harness: `scripts/replay_holds.py run --strip-title-overrides`/`--disable-slices` and `scripts/title_hygiene_probe.py` (above, Commands).
- **Junk short-keep** (held-backlog part 1, piece 4; spec `docs/superpowers/specs/2026-10-23-junk-short-keep-design.md`, plan `docs/superpowers/plans/2026-10-24-junk-short-keep.md`, acceptance `docs/superpowers/2026-10-23-junk-short-keep-evidence/acceptance.md` (Checkpoints A-C and the operator's rulings verbatim), SDD record `docs/superpowers/2026-10-24-junk-short-keep-sdd/` (README, ledgers, `verdicts/`, `mutation.md`)). **The rule** is in the Domain gotchas (`junk._apply_short_rule`, `short_keep: bool = True` on `filter_files`, `False` reproducing v2.17.0). **Filename-valued overrides:** `Overrides` parses both forms (`titles: dict[str, str]`, `set_breaks: list[int | str] | None`, `encore_after: int | str | None`), and ONE resolver (`override_keys.resolve_positions`, called by `compute_gather`, so gather, redo, reapply and replay all pass through it) maps filenames onto the final kept list; it refuses with `LlamaError` a legacy (track-number) file (`overrides.json uses track-number keys; run the migration`), a mixed file, and a filename key whose file is not kept (one message names every such key). "Legacy" is v2.17.0's own pydantic lax-int test (`"7"`, `" 7"`, `"07"`, `"7_0"`, `true`, `2.0` are all legacy; a real filename has an extension), pinned against the vendored v2.17.0 model; that model rejects every migrated file with a `ValidationError`, so an old binary or sweep loop fails LOUDLY library-wide. **Writers** (`fix` flags, `--suggest-titles`, `--untitled`, triage) take track numbers meaning `show.json`'s numbering, translate through `show.json`, and refuse a legacy file before any prompt; their staleness check (one shared helper that returns gather's final kept list) refuses with `re-gather under the new rule first (llama redo <show> --from gather)` on any show the rule changed until it is re-gathered (so triage held shows AFTER the bulk apply); `fix --exclude` refuses up front on a file carrying a title, break or encore key and names the `--clear-*` flag; `--clear-title` also takes a filename and the three `--clear-*` flags skip the staleness check, so a dangling key is cleared with `fix`, never by hand; `set_breaks: []` (forced no breaks) is preserved exactly. **Briefing reuse** (`replay.briefing_reusable`): drops the `short_kept` files on both sides, keys each break by the last remaining file at or before it, and (Task 15a, operator ruling at Checkpoint B) refuses a stored briefing that mentions a RESTORED file by name or uses exclusion/absence wording (`_RESTORED_WORDING`, matched on punctuation-normalised copies, bounded negation windows; it only ever refuses MORE): measured 100% regeneration on today's library, because `run_brief` hands the LLM `excluded_files` and the briefing then claims the piece is absent. **Audio reuse** (`audio_reuse.py`, spec 5.4): re-packaging a show whose track list changed moves `package/audio/*` aside into `<show>/.audio-aside/` (put back on a failed unit, deleted on success), pairs the library and station copies to source files BY INDEX against the current `show.json` (same length, same title at every index, AND the manifest's `source.identifier` equal to `show.json`'s; file names repeat across archive items), and reuses a file only when `audio.read_duration` is within `DURATION_TOLERANCE_S` of the source's cached length (library before station); anything else downloads as before. It runs in `redo`, `fix`/triage auto-redos and `reapply`; reapply's path extended to packaged and delivered shows (spec 5.2) is now BUILT (bulk-apply; see the `reapply` bullet). **Deliver:** see the `deliver` bullet (selector refusal, unreadable destinations, a changed track list replaces). **Format choice and doubled derivatives** (FW1, operator rulings 2026-10-25): the winning format is the one with the greatest kept running time (Domain gotchas), and within it `_dedupe_derivatives` keeps at most one derivative per `original` across all kept files (dropped copies: reason `duplicate derivative`); `PREFER_VBR_DERIVATIVE = False` keeps the plain `X.mp3` (the newer file in 2017 of 2017 measured pairs), an `include`d copy wins its group, an `exclude`d copy is never the kept one, and in non-`_vbr` groups the copy named after its original wins (newest 23/23). **Do not flip it to `_vbr` without a duration tie-break first:** the truncated copy is the `_vbr` one in all 13 library / 48 cache duration-mismatched pairs. **Segue donor** (FW3, FW4; unfreezes `blend_segues`' pooling): when setlist.fm wins the canonical, the donor is ranked only among LMA parses carrying at least one segue; `_drop_dangling_segues` (G5) clears a donor item's segue followed by an entry that BEGINS with a `_FILLER` word (`_leads_with_filler`; `is_filler`/`_FILLER` untouched) or by nothing; and `donor_segues` takes a track's segue from the donor's own alignment by position wherever it matches (pooling is the fallback), adding a mark only when the track is not the last AND its SHIPPED set equals the next track's or its title ends in `>`/`->`, skipped when the LLM `align_structure` branch won. **Migration** (`scripts/rekey_overrides.py`, `REKEY_MIN_VERSION = "2.18.0"`; spec 4.3 and plan Appendices A-C are the runbooks): dry run (checks every show, prints each refusal with its v2.17.0 repair route) -> `--snapshot` (verified whole-library copy of everything outside `package/audio/`, `manifest.json` written last) -> install the new release -> `--apply` (per show under the show lock: byte-equal re-check against the snapshot, raw-JSON map of the three keys only, durable write, `rekey-applied.json`) -> post-migration self-check (`short_keep_probe.py repro`) -> restart the sweep loop; `--restore <snapshot-dir>` is the wholesale rollback (empties `package/audio/` first unless the snapshot's manifest is byte-equal, restores every file, deletes files written since, lists the reapply batches, runs created since and station destinations whose manifest changed since (re-delivered or re-voiced); it refuses while a show created after the snapshot exists, on a failing hash, and when `rekey-applied.json` names ANOTHER snapshot or cannot be read). **Process-check limitation:** `--snapshot`/`--apply`/`--restore` refuse while a `llama` process runs, but a sweep loop typed at an interactive prompt and sleeping between passes is INVISIBLE to the check (it prints a note): stop the loop by hand first. A show `--restore` lists as re-delivered only because emcee re-voiced its manifest in place (an mtime test) needs no `--replace-voiced`. **Accepted limitations and filed follow-ups** (full list: spec section 7 and the SDD README): an NFA/crowd-chant tag stays kept (operator, Checkpoint B; pinned by `test_a_not_fade_away_crowd_chant_is_kept_operator_ruling`); typo'd, pluralised or annotated crowd/tuning tags outside the library are kept; a destination with audio but no `manifest.json` still merges (operator, "Leave it"); `ratdog-2007-08-12` and `derektrucksband-2004-11-20` hold after losing positional titles; the 2 re-selections that orphan overrides (`gratefuldead-1970-05-06`, `gratefuldead-1985-11-10`) are fixed by hand after the bulk apply and the 20 GD re-selections re-gather at the apply; segue classes B (run-on chosen descriptions, `parse_setlist`'s merge) and C (`blend_segues` exact-title `Space`/`Jam`) are unfixed, as are the LLM `align_structure` branch (item 2 does not apply, and pooled marks still feed `correspondence._merge_legal` and the prompt), an in-track flow into a non-filler solo (`warrenzevon-1994-02-07` #15) and 4 real gains declined under a wrong shipped set label (upstream); a `_vbr` preference flip needs a duration tie-break; FW2 M2 (a both-excluded pair counted twice in a format's running time, latent). **The bulk apply of pieces 1-4 is the `scripts/bulk_apply.py` campaign (Commands)** (needs the migration done, the self-check passed, apply lists built from `migration-post.json`; no e37f670 arm may run after the migration); the 28 voiced-minor shows stay out and refuse positional edits until re-gathered; the 37 voiced-severe shows re-deliver one named `deliver <slug> --replace-voiced` then `emcee voice <slug>` each, after `voiced-precheck`.
- **Two modes:** one-off queries, and standing criteria profiles for recurring
  segments, deduped against the on-disk show library ∪ a `ledger.jsonl`
  history keyed by performance identity (artist + date + venue), not
  archive.org item id — winnow skips anything already in the library or
  logged played/rejected. A date carrying two performances (early/late show)
  splits at grouping time into one show per jerrybase event, keyed
  `collection/date/eN` (e1 = first show); single-event dates and dates with
  no jerrybase data are unchanged. There is deliberately NO ledger migration
  and NO legacy-id compatibility for pre-split `collection/date` rows — purge
  and re-run. Run names auto-unique: a same-day collision gets a `-2`/`-3`
  suffix instead of silently resuming the earlier run.
- **LLM layer:** lives in the shared `herder` package (`packages/herder/`),
  used by both llama and emcee — task registries and prompts stay per-app.
  Provider abstraction with two capabilities — `complete`
  (schema-validated, no tools) and `research` (needs web search). Dev backend
  shells out to headless `claude -p`; `openrouter` is the HTTP alternative
  (opt-in, needs `OPENROUTER_API_KEY`, research via the web plugin); a `fake`
  backend serves tests.
  A usage-window refusal is classified as `herder.limits.RateLimited` (measured
  signature: `You've hit your session limit · resets 11:10am (America/New_York)`),
  carrying the reset instant parsed from the message itself — so pausing needs no
  access to Claude Code's internal state. It is excluded from
  `_with_transport_retry`, which would otherwise spend three more calls against
  an empty window. Every failed `claude -p` is captured whole under
  `~/.llama/llm-failures/`; the 7-day refusal's wording is still unobserved and
  that capture is how it will be learned.
  **Pacing has two halves.** *Reactive* (phase 1): the refusal above pauses the
  run. *Proactive* (phase 2): a live meter read decides, BEFORE spending
  anything, whether the window can finish the next unit of work. The meter is
  `claude -p "/usage"` via `herder.usage` — a live `GET /api/oauth/usage`, zero
  tokens, NOT an inference call, so it is affordable at every show boundary;
  `~/.claude.json`'s cached utilization is deliberately not read (it was
  measured serving an already-expired window). The meter subprocess gets
  `stdin=DEVNULL`: a headless `claude -p` reads a non-tty stdin as prompt
  input, and an inherited one swallowed an operator's `while read` loop. What a show costs is learned
  from the meter across show boundaries and persisted as an EWMA in
  `pacing-state.json` (`llama.pacing_state`) — **a show records a boundary only if
  an LLM provider was invoked during its `process_show` call**, so a resume that
  merely re-downloads and re-packages (the sweep's population) cannot fold
  near-zero deltas into the EWMA — and `pacing.decide()` turns a
  reading plus that estimate into `Proceed` or `PauseUntil`. Gates sit at the
  top of `_execute` (pre-flight, before the opening burst), before each
  show's lock, and — since T6b — ahead of `run_interpret` at both of its
  in-run call sites (`_get_query`, and `run resume`'s criteria-less
  re-interpret branch). `llama pacing` prints the same picture read-only. `--no-pacing`
  opts out of both halves; a failed meter read degrades to the reactive
  backstop alone and says so.
  **Three boundaries on what that pause guarantee covers, all confirmed in
  review:** **(a) it is `claude_cli`-specific.**
  `packages/herder/src/herder/openrouter.py:37` raises a plain `HerderError` on
  any non-200 response, so an HTTP 429 on the `openrouter` backend is still
  retried three times by `_with_transport_retry` like any other transient
  failure and then fails the show — nothing recognizes an openrouter response
  as a usage-window exhaustion, and `openrouter.py` was deliberately left
  untouched. **(b) `_execute`'s run-level catch covers three stages, not four —
  and `run_interpret`, the fourth, has a catch of its own.** Phase 2
  closed phase 1's per-show-only gap: `cli._execute` wraps `run_discover`,
  `run_search` and `run_winnow` in an `except RateLimited` arm — which must
  stay above any `except HerderError`, since it subclasses it — that
  checkpoints the session `paused` with a `resume_after` instead of exiting 1.
  The resume is recoverable but not cheap: those stages gate on `should_run` at
  WHOLE-STAGE granularity, so the interrupted one re-runs from the top. That
  arm does **not** cover `run_interpret`, which runs outside `_execute`
  entirely. **`interpret` and `discover` are DIFFERENT stages and both exist** —
  the phrase `interpret (run_discover)`, inherited from phase 1's spec, conflated
  them and is the origin of every muddle about what this catch covers; read the
  call sites, not the phrase (`_PIPELINE_RUN_STAGES` is a third, different
  triple that excludes `discover`). **T6b is BUILT**, and `run_interpret` is
  covered by `cli._interpret_with_pause` instead: the pre-flight gate runs
  BEFORE interpret is paid for, and a refusal on the call itself parks the
  session `paused` rather than exiting 1. Both halves apply at both in-run
  call sites — `_get_query` and `run resume`'s criteria-less re-interpret
  branch — because a resume that died on a limit would be the same defect on
  the one command that exists to recover from it, and an account-wide meter
  reading that passed can still be followed by a refusal. What made the
  checkpoint worth writing is the resumability design, not the catch:
  `run_interpret` writes `criteria.json` only on success, so `_get_query`
  persists the raw query and the flags stamped onto criteria as
  `runs/<id>/request.json` at run-claim time, before any LLM call, and
  `run resume` re-interprets from it whenever a session has a request but no
  criteria (`iter_sessions` reads that request too, so a run parked at
  interpret still lists its query).
  **`request.json` is a MODE-AGNOSTIC invocation record (2026-09-07), and
  `--plan` survives a pause in both modes.** It carries an explicit
  `mode: "query"|"profile"` — never inferred from which of `query`/`profile`
  is set, since a reader that infers eventually meets a run where both or
  neither is populated and picks silently — and a MISSING `mode` reads as
  `"query"`, because every artifact written before the field existed was one
  by construction. `_get_profile` writes the record too; without it a
  `--plan` profile run parked by the run-level catch resumed with
  `plan=False` and performed a full acquisition, from the recovery path the
  CLI itself prints, and profiles are the unattended recurring path.
  `run resume` replays the persisted `plan` as
  `bool(req.get("plan")) and not ws.shortlist.exists()`: `--plan` means "stop
  AT the shortlist", so the directive is SATISFIED once one exists — replaying
  it unconditionally is worse than dropping it, because the artifact carries
  `plan: true` for the life of the run and every later resume would re-park
  the session forever, including the one `run approve` recommends.
  **Five readers, not three** (`run_resume`, `_interpret_with_pause`,
  `iter_sessions`, `_by_run_rollup`, and `sessions.sweep_verdict` for `run
  resume --all`, which reads `auto` and `human_gate`); `_by_run_rollup` was
  missed twice in two consecutive features, so check every one when adding a
  key or a reader, and keep a missing key readable (old run dirs). The three SWEEP
  readers go through `sessions.read_request()`, which treats an unreadable or
  non-object file as "no request" so one bad file cannot blind the whole
  triage listing — **`run_resume`'s two reads deliberately do NOT**, because
  there a malformed request must fail loudly rather than silently resume with
  `plan=False`. That asymmetry is pinned by a test asserting the exception
  TYPE (rerouting still exits non-zero, via a downstream `KeyError`), because
  `read_request`'s docstring names the sweep call sites and "unify the
  readers" is the signposted next cleanup. `--no-pacing` restores the pre-pacing
  behaviour here as it does at every other site, though what that MEANS
  differs per site and only two of them literally re-raise: this catch and
  `_execute`'s run-level one do, the per-show loop records a per-show
  failure instead, and the pre-flight gate simply never reads a meter (a
  missing reading proceeds). Note `profile add`
  DOES call `run_interpret`, against a scratch workspace with no session to
  park — so **that one call site still exits 1**, and it is the only
  `run_interpret` call the pause guarantee does not reach; it is `llama get
  --profile`, which reads stored criteria, that never calls it at all.
  **(c) all four pause sites honour
  `--wait`** — the pre-flight gate, the reactive run-level catch above, the
  interpret catch, and the per-show
  loop, through one shared `_render_pause`. This was T7b and is BUILT; the
  asymmetry that preceded it (run-level sites checkpointing even when the wait
  fit inside `--max-wait`, so `llama get --wait` shortly before a reset exited
  having done nothing) is gone. Two things about the run-level sites remain
  worth knowing: after a nap they **re-decide** rather than proceed — the
  pre-flight re-reads the meter, the catch re-runs the stages — because the
  meter is account-wide and the reset may have moved; and they sleep **at most
  once**, since nothing can change between naps at a site where no work has
  completed. That guard is load-bearing rather than tidy: a `when` already in
  the past makes `sleep_until` return without sleeping, so without it the
  second pause is a HOT spin, not a nap — and no sleep-budget guard in a test
  can see it (it hangs rather than failing).
  Set/segue structure is performance-level: gather builds
  a canonical setlist from every recording's description plus setlist.fm
  (optional, key via `SETLISTFM_API_KEY` or `[setlistfm] api_key`; absent key
  = best-effort LMA-only) and aligns it onto the chosen recording's tracks
  (`structure.py`), falling back to the `align_structure` LLM touchpoint for
  messy alignments. Structure evidence for the Garcia universe also comes from
  a vendored, offline jerrybase-derived dataset
  (`packages/llama/src/llama/data/set_breaks.csv`, GPL-3.0 from deadstream; refresh via
  `scripts/refresh_jerrybase.py`): gather uses it after alignment as a
  tripwire (multi-event dates, venue mismatch, contradicted set breaks, wrong
  set count) and a deterministic break-anchoring corrector, never as a setlist
  source (`[jerrybase] enabled`, default on). **Anchoring runs on its own
  evidence and wins whenever it resolves** — it is not gated on
  `align_coverage_threshold`, which now only triggers the LLM realignment
  fallback and the low-confidence flag. Closers match merged tracks on their
  last component and tolerate `&`/`and` and dropped subtitles; a repeated
  closer resolves to its latest occurrence before the next set's closer; a
  trailing encore jerrybase has no row for is preserved, not absorbed. The
  closer tripwire only speaks when anchoring declines. Design:
  `docs/superpowers/specs/2026-08-01-jerrybase-anchoring-design.md`.
  **`align()` matches fuzzily, at the matching layer only**: it normalizes both
  the track and the setlist item at compare time via `fuzzy_norm_title`
  (bypassing the precomputed `SetlistItem.normalized`), folding `&`→`and`, and
  curly apostrophes (`’`/`‘`) to `'` (`structure.fold_curly_apostrophes`, also
  applied by vet_research's and brief's song matchers on both sides),
  tolerating dropped subtitles, matching merged tracks as consecutive runs, and
  dropping credit-only parentheticals. **`songs.normalize_song` and
  `DEFAULT_ALIASES` are deliberately NOT part of this** — folding there would
  also move `grouping`/`vet_research`/`brief`/`setlistfm`, two of which generate
  holds, so don't "simplify" it down a layer. Dead-canon shorthand
  (`songs.GD_SHORTHAND`: `scarlet`→`scarlet begonias`, `chinacat`, …) is
  **gated on artist family** — `jerrybase.is_family_artist`, derived from the
  vendored CSV's own artist keys plus a small extras set — because `scarlet`,
  `help`, `dew`, `eyes` and `saint` are ordinary English words off-family; the
  jerrybase closer path applies it ungated since an event only exists for
  artists in the dataset. `structure._NEVER_EQUAL` blocklists subphrase pairs
  that are genuinely different songs (`It's All Over Now` vs `… Baby Blue`).
  Design: `docs/superpowers/specs/2026-08-01-fuzzy-title-matching-design.md`.
  **`align()`'s lookahead window defaults to 8** (raised from 3), paired with a
  **tail-exhaustion guard** — `structure._tail_guard_declines`, constants
  `TAIL_GUARD_ITEMS=3` / `TRACKS_REMAINING=3` / `MAX_SKIP=6`. `j` advances only
  on a match, so without the guard one far-ahead match can consume the last
  canonical item, exhaust the two-pointer walk and mislabel a show's whole
  tail. The guard declines a hit landing in the final few items while many
  tracks remain unprocessed. **`MAX_SKIP >= lookahead` makes the guard
  structurally unreachable** — that is why it is inert at the old default of 3,
  and `test_align_default_lookahead_is_8` deliberately pins the shipped value
  (reverting it fails that test plus one gather fixture). `TRACKS_REMAINING` is
  measured INERT on both corpora and kept anyway: it is the only thing
  protecting a legitimate tail match on a short tape — do not "simplify" it
  away; its comment records the measurement. Evidence for the change lives in
  `docs/superpowers/2026-08-03-tail-guard-sanity-check.md` and
  `2026-08-04-tail-guard-family-sample.md`.
  **Known gap, filed not fixed:** coverage is matched-tracks over
  song-like-tracks and never inspects UNMATCHED ITEMS, so a partial recording
  can score ~1.0 while missing half the show; `select_recording`'s completeness
  is RELATIVE (best sibling), not absolute.
  Nine named touchpoints (one
  per file under `packages/llama/src/llama/prompts/` — `synthesize` is gone,
  emcee has its own separate `scriptwrite` prompt), each with a Pydantic
  output schema. LLM calls live only at stage boundaries — everything else
  is deterministic.
- **emcee (station-side voicing), architecture:** `emcee run`/`emcee status`
  scan `[station] root` for delivered packages (`packages/emcee/src/emcee/
  station.py`; scans skip dot-prefixed dirs, which are llama's replace-swap
  siblings); `readiness()` computes the same "broadcast-ready" signal
  llama used to (script present, DJ audio present, `broadcast.m3u` present,
  every manifest track's audio on disk, and, since 2026-10-16, the profile check: the voiced profile (`dj_audio.profile`, else, for a legacy block, `source.profile`) equals the EFFECTIVE profile, `station.effective_profile` = a `moves.json` move > an `[assign.artists]` rule > `source.profile`; transmitter deliberately does not mirror this leg) — but as emcee's own derived,
  never-stored state (`ready`/`pending`, plus `unsupported` for a pre-v3
  manifest), not llama's. There is no separate work-queue file: "not
  broadcast-ready" *is* the predicate `emcee run` sweeps on.
  `process.py:process_package` orchestrates one package: resolve the
  package ONCE (`resolve_voicing`: effective profile, then `resolve_assignment(config, profile)`
  against `[assign]`, then `resolve_tts`) and pass that `Voicing` through → `scriptwrite.py` (script LLM task + `script_guard`,
  emcee's own port of llama's old `factual_guard`, persona-styled when a
  presenter is assigned, byte-for-byte neutral otherwise) → render
  `dj-notes.md` → TTS via a `SpeechProvider` (`packages/emcee/src/emcee/tts/`:
  `voxtral` default, `elevenlabs` alternative, `fake` for tests; same
  per-segment cache, `[tts] chunk`, and `[tts] bed` instrumental-bed mixing
  llama used to have) → assemble `broadcast.m3u` → atomically rewrite the
  manifest's `dj_notes`/`dj_audio` blocks last (`dj_audio` records `presenter`, `profile`, `profile_source` and `tts` (`backend`/`model`/`voice`); the last three are required in `DJAudioBlock`, so a legacy block must never be round-tripped through the model: update it as a raw dict), in place, in the package
  directory llama delivered (`package_io.py:rewrite_manifest`).
  Chunked clips are packed by paragraph at `[tts] chunk_chars` (default 250; a chunk never ends inside a sentence) and exact-silence gaps are filled with the clip's own room tone (`[tts] room_tone`, default on); the scriptwriter writes paragraphs.
  Chunked and bed-active clips are loudness-normalized per chunk/segment
  before the gap and the bed mix (`tts/loudness.py`: −20 dBFS speech-active,
  −1 dBFS peak ceiling, ±10 dB clamp; module constants, no config), because
  Voxtral returns every call at its own level; the unchunked no-bed path ships
  the provider's MP3 untouched and is not normalized.
  **`moves.json` is never read leniently**: unreadable or malformed is a hard error for `run`/`voice`/`status`/`move`, and so is a missing file while any package records `profile_source: "move"`.
  Everything else in a package is llama-owned and read-only from emcee's side.
  A Voxtral content-filter refusal (403 `guardrail_violation`) is `SpeechBlocked`:
  emcee narrows it to the sentence, rewords just that segment with the small
  `rephrase` task (2 attempts, gated by `rephrase_problems` + `script_guard`),
  and re-voices only that segment (the task has its own `[llm.rephrase]` config key and does not inherit scriptwrite's backend); on the chunked path a blocked
  multi-sentence chunk is narrowed to its sentence and, when every sentence
  passes alone, falls back to its passing takes; with `[tts] chunk = false` a
  block that exists only across sentences fails with "re-run with `[tts] chunk = true`". Blocks are deterministic
  (measured 7/7), so they are never retried identically; transport errors, 429
  and 5xx get one retry.
  **Per-presenter TTS pinning + the local `mlx_audio` backend**
  (`docs/superpowers/specs/2026-10-12-local-tts-presenter-pinning-design.md`).
  A presenter's `tts` pins its backend; an unpinned presenter inherits
  `[tts] backend` — EXCEPT that a presenter never inherits `mlx_audio` (a
  resolution error, `pin tts explicitly`), so moving the house voice never
  moves a presenter. `tts/resolve.py:resolve_tts` is pure and runs before any
  spend; `speech_provider_for(config, resolution, *, voice, clone_ref,
  clone_text)` takes no defaults, so no call site can fall back to `[tts]
  backend` or drop the transcript. Hosted keys/models live in
  `[tts.voxtral]`/`[tts.elevenlabs]` (legacy `[tts] api_key`/`model` still mean
  the HOUSE hosted backend's; the env var still wins). `tts/mlx_audio.py` is
  clone-only, sends `ref_audio` as an ABSOLUTE path (the server reads it from
  its own cwd) plus `ref_text` (`voice_clone_text`), always requests WAV, and
  never falls back. Every mlx clip passes the per-model runaway guard
  (`tts/calibration.py`: `max_tokens` capped in proportion to the text, the
  duration checked; `CALIBRATED_MODELS` holds MEASURED entries only, and an
  uncalibrated model is a resolution error). The quality layer
  (`tts/quality.py`) owns the ONE re-synthesis; a second guard or
  verification failure is a `SpeechDefect` that fails the package. Optional
  transcript verification (`[tts.verify] backends`, `tts/verify.py`) fails only
  gross mismatches and never re-verifies cached clips. `preflight()` runs in
  `cli._process_one` before the `--fresh` unlink, the manifest clear and any
  LLM spend: a no-op on hosted providers, one fixed sentence on mlx, and the
  STT path end to end when verification applies (hosted: the bundled
  `emcee/data/preflight_en.wav`). Evidence: `docs/superpowers/2026-10-12-mlx-audio-probe.md`
  and `…-mlx-audio-calibration.md` (adding a model means a calibration run,
  `scripts/mlx_audio_calibrate.py`). Runbook: README "Local TTS on this Mac".
  `presenters.py` manages `presenters/<id>.toml` (`emcee presenter
  add/edit/list/show/remove`) — the same TOML shape llama's presenters used to
  have (`name`/`sex`/`character` + exactly one of `voice`/`voice_clone`,
  optional `bed` override, plus the optional `tts`/`tts_model`/`voice_clone_text` pin; strict — an unknown key is a load error). emcee never imports llama (enforced by
  `packages/emcee/tests/test_no_llama_imports.py`) — its only input is the
  delivered package directory's files.
- **Quality philosophy:** the LMA is a completist archive. Winnowing demands
  evidence a show is well received by people who were *not* there (LMA reviews
  are heavily attendance-biased). Suspicious output (unresolved track titles,
  duration mismatches, low-confidence setlist parse, a briefing contradicting
  the setlist, a long show with zero set breaks, research asserting songs or
  dates that don't belong to the show) marks a show `needs-review` rather
  than shipping; `--auto` runs skip such shows.

## Domain gotchas

- archive.org items contain junk: `gd73-06-10.sbd.hollister.174.sbeok.shnf`
  (the canonical test fixture) includes a spam file `FOLLOW-ME @BYPIKENO.mp3`
  that would play on air if file lists were trusted. Filter to originals (or
  derivatives of originals) matching the item's dominant filename convention
  with plausible durations.
  **"Plausible duration" is RELATIVE to the tape, never absolute.** The floor is
  `junk.SHORT_FRACTION_OF_MEDIAN` (0.25) × that tape's own median track length,
  falling back to `MIN_PLAUSIBLE_SEC` (90 s) only below `MIN_MEDIAN_SAMPLE` (5)
  usable durations. The old absolute 90 s floor sat *above* the median track
  length of short-song bands and amputated them: `minutemen1983-03-09` has 38
  audio files matching a 38-song description one-for-one, 27 of them under 90 s,
  so llama kept 11 tracks, aligned at coverage **1.00**, and shipped a
  29%-complete show with **no review flag** — the tape was whole and the filter
  made it partial. The two-pass structure in `_keep_and_exclude` is load-bearing:
  the median is taken over files passing every OTHER junk arm, so an item padded
  with spam clips cannot drag the threshold down and license itself. The 0.25/90/5
  constants were measured over 2,030 cached items (see the comment above them) and
  are the same do-not-retune class as the tail-guard constants.
  **The floor is unchanged, but the short arm no longer drops by duration alone**
  (piece 4, spec `docs/superpowers/specs/2026-10-23-junk-short-keep-design.md`). A file
  whose ONLY drop reason is `implausibly short` is KEPT unless it trips the spam
  tripwire (`junk.short_is_spam`: URL, `www.`, a domain, `@name` in the filename stem
  or either tag; bare `follow`/`download`/`subscribe` in the stem only, `follow me/us`
  in a tag; reason `spam-shaped name or tag`), its cleaned tag is wholly junk
  (`junk.short_tag_is_junk`: tuning, silence, fades, crowd noise, broadcast and
  non-performance material, every part of the tag junk, so `intro/tuning` is kept), or
  its duration is zero. An UNTAGGED short file is kept only when interior (a kept file
  before and after it in play order); edge files and a wholly junk filename stem drop.
  A leaked timestamp or a placeholder (`tmp`, `Track 9`) counts as tagged. The kept
  files are `ordering["short_kept"]` and `Track.short_kept`, and
  `structure._songish_coverage` ignores them (`and not t.short_kept`), so a restored
  `Jam >` neither lowers nor raises coverage. The operator's 239 hand `include`s of
  short files are why none of this loosens the floor constants; an `include` of a file
  the rule now keeps re-admits nothing. `show --tracks` and triage `[i]` still read
  `implausibly short` for the files that stay dropped.
- **Downloads fall back across archive.org servers** (`IAClient.download_file`,
  spec §1; constants module-level in `ia_client.py`, none in config). archive.org
  throttles each connection, so a struggling server is answered by switching, not by
  waiting. Candidates, in order: the redirect URL, then `https://<server><dir>/<file>`
  for each of the item's cached `workable_servers`, or `d1` then `d2` only when that
  list is missing or empty (de-duplicated; a `d1`/`d2` absent from a non-empty list
  is marked not workable). Metadata trouble degrades to fewer candidates or no size
  check, never a crash. Own timeouts (connect `DOWNLOAD_CONNECT_TIMEOUT_S` 10 s,
  stall `DOWNLOAD_STALL_TIMEOUT_S` 20 s; `_get` keeps the client's); there is **no
  total-time bound on a transfer** (normal rate is 50-100 KB/s). First pass: one
  attempt per candidate with a 1-4 s random sleep, never cut short; then repeat
  attempts over candidates whose last error was retryable, until a monotonic
  `DOWNLOAD_DEADLINE_S` (60 s) counted from the end of the first pass (slot wait
  excluded). Retryable: 5xx/429/408 and transport errors; other 4xx moves on but is
  not repeated; `Retry-After` is ignored. **Trickle switch:** throughput below
  `TRICKLE_FLOOR_BPS` (10 KB/s) over `TRICKLE_WINDOW_S` (30 s) abandons that
  candidate once per file, and the next asks `Range: bytes=<held>-`; only a `206`
  whose `Content-Range` starts at that offset (and total matches `size`) is
  appended, anything else (incl. `416`) discards the `.part` and restarts from byte
  0. Continuation needs an md5; with size alone the `.part` is discarded. A stale
  `.part` from a killed process is never continued. **Integrity is over the whole
  finished file, however many servers it came from:** md5 (else byte count equal to
  `size`) before the rename; a mismatch deletes the `.part`, moves on, and that copy
  is not tried again. Exhaustion raises `IADownloadError(IAError)` whose text keeps
  the `download of <filename>` prefix and names every URL tried. **Known
  limitations:** the last non-abandoned candidate is never abandoned, so a server
  dribbling just above the stall timeout holds its slot until it finishes; a file
  whose every copy fails the integrity check (removed or darked item, stale cached
  md5) fails as `download` on every sweep pass, so the sweep keeps listing it and
  exits 1 until cleared by hand.
- **Failure records carry `kind` and `at`** (`sessions.failure_record`, spec §3).
  `kind`, first match wins: `RateLimited` → `rate-limited` (recorded only under
  `--no-pacing`); `TaskFailed` → `llm`; herder `ResearchNotSupported` → `other`;
  any other `HerderError` → `transport`; `IADownloadError` → `download`; any other
  `IAError` → `archive`; else `other`. The order is load-bearing (several subclass
  `HerderError`). `at` is the UTC ISO time. The sweep re-spends only on `download`
  and `archive`. A per-show `LlamaError` (e.g. gather refusing the show's overrides) is a per-show failure of kind `other`, not a run abort. The records are persisted state and stay permissive: a legacy
  record without `kind` reads as `download` when `error` starts with `download of `,
  else `other` (`failure_kind`).
- Track filenames (`gd73-06-10d1t04.mp3`) don't carry song titles; disc/track
  numbering doesn't map to sets. Titles resolve via cascade: recovered-format
  tags → own tags → setlist parsed from the item description → **sibling
  recordings of the same performance (`sibling-align`)** → **setlist-gap** →
  unresolved, with `title_source` recording which fired. Never guess — flag
  unresolved.
  **`setlist-gap`** fills a run of unresolved tracks ONLY when it is
  count-forced (the gap's canonical-item count exactly equals its file count,
  so no shift can hide in it) and anchored by tracks that independently
  matched, plus per-title hygiene; trailing-edge runs are declined outright.
  Measured on 960 cached items it adopts ONCE, so treat it as a slow-burn
  asset: the candidate population (17 items) skews 16:1 toward non-Dead acts,
  where a taper tagging all but a couple of songs is common.
  **Both tautological rungs are excluded from alignment evidence.** A title
  taken from the canonical setlist IS that item's own text, so `align()`
  matching it back is circular — `structure.TAUTOLOGICAL_TITLE_SOURCES`
  (`setlist-gap`, `setlist`) is filtered out of `_songish_coverage`, and those
  tracks carry `matched=None`, not `True`. Without this a mis-adoption raises
  coverage and suppresses the very `low-confidence structure alignment` flag
  that would have caught it.
  **`sibling-align` (v2.4.0) replaced a positional rung, and the old one was
  dangerous.** It aligns the target's tracks against a **tagged sibling
  recording of the same performance** on the *duration sequence*
  (`packages/llama/src/llama/siblings.py`, pure; IO stays in `gather`),
  tolerating merges, splits and filler. The rung it replaced required the
  sibling's track count to equal the target's **exactly** and then transferred
  **by position** — so it declined usable donors, and when it did fire on a
  shifted sibling it shipped the whole tape rotated one song over (pinned by a
  backward mutation in `test_siblings.py`). Adoption is intersected with the
  **unresolved set at application time**, so a real tape tag is never
  overwritten.
  **Three-band anchor-reproduction guard**, of the target's own surviving tags
  ("anchors") that the alignment reproduces: **>= AUTO (0.80)** adopts
  automatically; **FLOOR (0.50) .. AUTO**, or fewer than **MIN_ANCHORS (2)**,
  routes to an operator proposal; **< FLOOR** declines with a show-note. The
  anchor-count clause is evaluated **first** — below `MIN_ANCHORS` the ratio is
  not a measurement, and `declined`'s error basis was never measured there.
  On top of the ratio sits **shape C+**: a run of fills is adopted only when
  agreeing anchors **bracket it on both sides** (`structure.gap_span`'s rule
  reused verbatim, not reimplemented) **and** the span is count-forced; an
  unbracketed run declines **alone** rather than sinking the pair.
  **C+ gates the automatic band and NEVER the proposal display** — applied to
  the renderer it shows a wholly untagged tape nothing, destroying the case the
  work exists for. Do not unify those paths.
  `sibling-align` is deliberately **NOT** in `TAUTOLOGICAL_TITLE_SOURCES`:
  another taper's text assigned by durations is cross-source evidence, not the
  item's own text. Operator-path adoptions land as `override`.
  **The four constants are do-not-retune** and cite
  `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`, which also records
  the honest limits: C+ is **quantified-cost insurance, not measured
  necessity** (it blocks ~28.7 correct titles per error prevented, over a
  population 4x more error-prone), the automatic library yield is **1 track**,
  and the localised-slide class is **real at 136 pairs** but is selected away by
  donor ordering rather than caught by C+. Reviewer verdicts:
  `docs/superpowers/2026-09-02-phase-c-verdicts/`.
  **"Recovered-format tags" is `title_source="sibling-format"`** (the literal
  string a manifest carries), produced by `gather._recover_format_titles` via
  `titles.sibling_format_titles`. Its defining property, and the thing that
  makes it a *different* rung from the "sibling recordings" one four words
  later: the tags come from a **different-format copy of the SAME archive.org
  item** — the FLAC originals beside the MP3 derivatives — matched by a
  **filename-stem bijection** (anything less than a bijection declines rather
  than guessing by position). It is read straight out of cached item metadata:
  **no download, no tag parsing**. The "sibling" rung, by contrast, is a
  *different item* — another taper's recording of the same performance.
  Recovery fires only when the delivered format's `title_fraction` is
  **< 0.5** (`gather._RECOVER_BELOW`) and the other format's clears **>= 0.9**
  (`_RECOVER_SIBLING_ABOVE`). Those two are the values the spec's 166-item
  measurement was taken at and were **not** independently swept — changing
  them invalidates it, the same do-not-retune class as the tail guard's
  constants above. **Recovery is
  wholesale, not gap-filling**: when it fires, the delivered format's own
  tags are not consulted at all, and a recovered title that is still
  unusable falls through to the setlist/sibling cascade rather than back to
  the bad tags. `titles.clean_tag_titles` (the recording-level cleaner;
  `clean_tag_title` remains the per-string one) gates the
  leading-track-number strip on whether the *recording* looks enumerated
  (`>=3` numbered files and `>=80%` coverage) — the `\d{1,3}` bound in
  `titles._TRACK_NUM_PREFIX` is what protects `1952 Vincent Black Lightning`
  and a bare `2001`, and must never be widened to `\d+`. The gate's
  destructive mode — a real numeric title tagged without its own track number
  on an enumerated tape (`100 Years` → `Years`) — is an **accepted, ruled-on
  gap**, pinned by test not fixed; do not tighten the gate.
  `FORMAT_BY_AUDIO`'s values are ordered
  preference tuples, tried in order, never unioned (a
  union would keep every track of a both-formats item twice). The winner is
  the format whose **kept** files have the GREATEST TOTAL RUNNING TIME, the
  list's order breaking ties only (piece 4, operator ruling 2026-10-25; it
  replaced "the first format whose kept set is non-empty", which let a lone
  61 s `Flac` file beat a whole show in `24bit Flac`) — decided *after* junk
  filtering and both dedupes, because one corpus item's every `Flac` entry is
  junk while 15 clean tracks sit under `24bit Flac`; when no format survives
  filtering, the first with any audio at all is returned so `excluded` still
  says why. `filter_files(short_keep=False)` keeps v2.17.0's first-non-empty
  choice (only the overrides migration's consistency check passes it).
  `LOSSLESS_TITLE_FORMATS` is the broader, read-only set used for title
  recovery and deliberately includes `Shorten`, which is not a delivery
  format — measured load-bearing (sole lossless source for 209 of 2,095
  items in a decade-stratified `iacache` sample, not a rate over shows
  llama would select; the numbers and the sample's provenance caveat are
  in its comment), so don't "simplify" it away.
- Setlists in descriptions are convention, not schema; the parser must be
  defensive and report confidence, with an LLM extraction fallback.
  **`parse_setlist`'s items are NOT a reliable "was this song played" oracle,
  and its confidence does not tell you when they aren't.** Plenty of
  descriptions separate non-segued songs with nothing at all — `"Bertha &gt;
  Greatest Story Ever Told West L.A. Fadeaway C.C. Rider ... My Brother Esau"`
  — so only the `&gt;` chains and set markers can be split on; the parser
  merges the rest into one blob, drops it, and still reports
  `confidence="high"` (65 of 67 items in the 1984 GD corpus were "high").
  Anything asking *does this performance contain song X* must therefore match
  the **description text**, via `structure.contains_sequence`, never parsed
  items: on that corpus, of the 27 shows that played "My Brother Esau",
  item equality found **0**, item containment 8, and text containment 27.
  The 0 is not hypothetical — it shipped, as a populated
  `setlist_constraints` that silently emptied the shortlist.
  `contains_sequence` requires order but deliberately **not** adjacency:
  normalization leaves segue markers behind as tokens (`&gt;` → `and gt`), so
  genuinely adjacent songs are almost never adjacent in the normalized text.
  It is a matching-layer function and uses `fuzzy_norm_title` — the same
  `&`/`and` folding as `align()`, for the same reason, and `normalize_song`
  stays untouched (see the fuzzy-matching note above).
- Multiple recordings of the same performance are the norm; show-level merit
  (winnow) and recording-level quality (select-recording) are deliberately
  separate decisions.
- One archive date can hold two performances (early/late show). jerrybase
  `Nevents`/`ievent` is the ground truth; grouping partitions recordings by
  early/late text then description set-closer matching. A tape that spans the
  evening (`.../spans`) or resists assignment (`.../unassigned`) is held for
  review, never split or auto-shipped. gather re-checks the split and flags a
  per-event tape whose tracks actually span both events.

## Conventions

- Audio files (`*.mp3`, `*.flac`, `*.shn`) are gitignored; never commit audio.
  One exception: `packages/emcee/src/emcee/data/preflight_en.wav`, the ~2.6 s
  bundled check clip for the verification preflight (provenance in
  `docs/superpowers/2026-10-12-mlx-audio-calibration.md`).
- Test fixtures are captured real archive.org API responses (gd73-06-10 is the
  canonical one). Pipeline tests use the `fake` LLM backend and run offline;
  the only live end-to-end test is manual/opt-in.
