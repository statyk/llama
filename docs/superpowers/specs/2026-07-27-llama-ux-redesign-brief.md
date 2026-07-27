# llama CLI UX redesign — design brief (input for the formal spec)

**Status:** Ratified design-of-record, produced via a brainstorming pass with the owner
(2026-07-27). This brief is the **input** to the formal design spec. The spec author
(Fable) should expand this into `docs/superpowers/specs/2026-07-27-llama-ux-redesign-design.md`
following the project's spec conventions, grounding every claim in the current code.

**Companion reading:** `docs/ux-review.md` — the full Fable UX review that started this. It
contains the as-is command-surface map, the findings by theme (with `cli.py` line
citations), and the three-altitude proposals. This redesign adopts **Altitude C** (the
show-centric big-bang) with the refinements below. Read it for rationale; this brief is
authoritative where the two differ.

## Goal & constraints

- **Goal:** Re-cut the CLI command surface around operator intent. The current surface
  grew organically across many features and now exposes implementation history rather
  than user intent (overloaded `show`, duplicated selectors, a fragmented redo/replay
  story, run-as-a-first-class-noun, naming collisions). See `docs/ux-review.md`.
- **Backward compatibility is explicitly NOT a concern.** No aliases required, no
  migration. The owner has no muscle memory to protect and wants the cleanest model.
- **Do NOT touch the pipeline, the staged on-disk workspace, `overrides.json` semantics,
  the show library layout, or the LLM/TTS layers.** This is a command-layer re-cut plus a
  small number of clearly-scoped new behaviors (library-as-dedup, `rm`, archive-URL
  surfacing). Existing pipeline tests should largely stand; CLI tests get rewritten.
- **Scope decomposition:** left to the spec author — keep as one spec or split into
  "surface re-cut" + "new behaviors" as you judge best.

## Background the spec author needs (grounding in current code)

- **Entry point / whole command surface:** `src/llama/cli.py` (Typer app, ~1436 lines,
  ~23 commands across the root app + 4 sub-apps `profile`/`ledger`/`config`/`presenter`,
  grouped into 4 rich-help panels).
- **State derivation (all derived, never stored):** `src/llama/catalog.py`
  - `derive_state(ws, delivered)` (~:59) — `held > delivered > packaged > scripted >
    vetted > researched > gathered > selected`. `held` is the `needs_review` flag and
    takes priority over everything.
  - `derive_voiced(ws)` (~:77), `broadcast_readiness(ws)` (~:89) — the five broadcast-ready
    conditions (see Deliver below).
  - `iter_shows(root, ledger)` (~:116) scans `shows/`; `select_shows(...)` (~:140) is the
    selector filter; `resolve_show`/`resolve_run` name resolution.
- **Winnow dedup:** `src/llama/stages/winnow.py:58` — `seen = ledger.played_ids() |
  ledger.rejected_ids()`; pool excludes `seen`. **No library awareness today** (the gap
  this redesign closes).
- **Ledger:** `src/llama/ledger.py` + `LedgerEntry` (`models.py:257`:
  `performance_id, artist, date, venue, status ∈ {selected|delivered|rejected}, run,
  recorded_at`). `played_ids = selected|delivered`; `rejected_ids = rejected`.
  Append-once dedup on `(performance_id, status, run)`.
- **Where ledger rows are written:** `pipeline.py:127` writes `selected` **only after
  both needs-review gates pass** (synthesize gate ~:115, package gate ~:123 each
  `return None` when held) — so **held shows have NO ledger row**. `deliver` writes
  `delivered` (`cli.py:891`). Manual `ledger add` writes any status (`cli.py:1391`).
- **Deliver guard:** `_deliver_one` (`cli.py:867`) refuses a held show unless `--force`,
  requires a package (reads `package/manifest.json`), copytrees `package/` → dest, records
  `delivered`.
- **Recording selection provenance:** `shows/<slug>/selection.json` =
  `{"identifier": chosen, "scores": {<identifier>: {...}, ...}}` (`select_recording.py:105`);
  `scores` is keyed by **every considered recording**. `Candidate.recordings`
  (`models.py`) is the grouped considered set. Archive item URL =
  `https://archive.org/details/<identifier>`.
- **Session/run structure:** `RunWorkspace` (`workspace.py:92`) = `runs/<name>/` holding
  only `criteria.json`, `candidates.json`, `shortlist.json`, `artists.json` — **no show
  data**. Shows live in `shows/<slug>/` keyed by `slugify(performance_id)`
  (`workspace.py:103`), shared across runs.
- **Run naming collision (bug to fix):** run dir name is date-keyed with no uniquifier —
  `find`: `f"{date.today()}-{slug(query)}"` (`cli.py:324`); `profile run`:
  `f"{date.today()}-{name}"` (`cli.py:1263`). Running the same profile/query twice a day
  reuses the same dir and silently resumes instead of doing a fresh pull.

---

## The redesigned model

### Conceptual shift

- **Shows are the only first-order daily object.** Inspect, fix, redo, voice, deliver, rm
  all address shows.
- **A "run" is a transient acquisition session**, not a daily noun. It exists only from
  "I asked" until "approved & finished." It surfaces solely when it needs the operator,
  via an **attention-list** (in `status`) with two states: *awaiting approval* and
  *crashed/incomplete*. Completed sessions vanish from view. Sessions get **auto-unique
  ids** (fixes the twice-a-day collision); the operator never types an id from memory —
  they pick from the short attention-list by substring, exactly like held shows today.
- **Dedup memory has two halves:** the **on-disk show library** ("what I currently have,
  any state") and the **ledger/history** ("dispositions for shows no longer on disk").

### Top-level command surface (16)

```
Acquire     get
Watch       status · show · pipeline
Fix & ship  triage · fix · redo · voice · deliver · rm · suppress · unsuppress
Namespaces  run · profile · presenter · history · config
```

### Acquire

- **`get "query"`** (one-off) and **`get --profile NAME`** (standing profile) — one verb
  replaces today's `find` + `profile run`. Honest that it spends. Preserve today's
  `_execute` behavior (artist prune prompt, shortlist approval prompt, per-entry
  processing, flags stamped into criteria for replay).
- **`--plan`** — stop after the winnow shortlist (no heavy downstream spend) for a cheap
  preview. Interactive mode already nearly does this; `--plan` makes it explicit and
  side-effect-free past winnow.
- The **approval gate stays and stays persisted** (winnow is non-deterministic; a deferred
  approval must approve the exact shortlist that was shown).

### Sessions (the `run` namespace)

- **`run list`** — the attention-list (awaiting-approval + crashed/incomplete only).
- **`run approve <session>`** — gate 1: show the persisted shortlist, approve ranks, then
  process. (Today's `review`.)
- **`run resume <session>`** — continue a crashed/incomplete pull. (Today's `run`,
  resume-only — no `--stage`.)
- **`run rm <session>`** — discard a session.
- Auto-unique session ids. `status` also surfaces pending/crashed sessions so the operator
  sees them without running `run list`.

### Dedup: library ∪ ledger

Winnow's `seen` becomes:
```
seen = library_performance_ids ∪ ledger.played_ids ∪ ledger.rejected_ids
```
- In the library (any state — held/packaged/delivered) → not re-offered (you have it; act
  locally). **Closes the gap where held shows re-surfaced in every future `get`.**
- Delivered/rejected in history but no longer on disk → still not re-offered.
- Gone from both → re-eligible.
- Building `library_performance_ids` is cheap (~10² shows; `iter_shows` already resolves
  performance ids). This only affects new acquisition (`get`), never `redo`/direct
  show ops.

### Watch (read-only)

- **`show <name>`** — inspect one show, **strictly read-only** (never prompts, never
  edits). Add `--json`. Surfaces the archive URL (see below) and, for a held show, the
  `broadcast-ready: no` reasons line (already exists) — the read-only investigation view.
- **`status [SELECTOR]`** — global triage table (held-first). Absorbs today's `runs` via
  `--by-run`; surfaces the session attention-list. Keep `--json`, `--broadcast-ready`.
- **`pipeline`** — a teaching command: prints the stages / states / gates (the workflow
  diagram + stage/state table) so the CLI stands without the docs. *(Scope-expander; the
  owner approved it but is open to deferring to a follow-up if the spec author wants to
  keep the first cut tight — flag your recommendation.)*

### Fix & resolve

- **`triage [SELECTOR]`** — the interactive held-show walkthrough (today buried as a side
  effect of flagless `show`; see `_interactive_resolve` `cli.py:596`). Always interactive,
  always predictable (no TTY-dependent job selection). Default selector: held. Add a
  `[m]etadata` option so venue/date/titles/set-breaks are fixable in-loop (today you must
  quit and reconstruct flags). Prints the archive URL at the top of each show.
- **`fix <show> <edit-flags> [--no-run]`** — edit `overrides.json` / resolve holds.
  **Auto-applies the correct redo by default** (the tool already computes the stage:
  excludes/metadata→gather, narration→synthesize, overrule→package — `cli.py:827`);
  `--no-run` stages without running. Absorbs today's `show` edit flags with clearer names:
  - `--exclude` / `--unexclude` (today's `--include`, which is an un-exclude, not a filter)
  - `--set-venue` / `--set-city` / `--set-date` / `--set-title N="…"` (today's bare
    `--title`, renamed to match its `--set-*` siblings) / `--set-breaks` + `--clear-*`
  - `--narration vague|full` (replaces the `--vague`/`--full` pair that didn't read as one
    setting and squatted on the word "full")
  - `--overrule` (today's `--clear`; deliberate "I've reviewed it, ship it" — clears
    `needs_review`, redoes from package)
- **Holds are cleared ONLY via `fix`/`triage`** — either a real fix (re-gather/re-synth
  self-clears the flag when the problem is gone; gather recomputes `needs_review` from
  scratch) or `--overrule`. There is no other bypass anywhere (see Deliver).

### Act & ship

- **`redo <show | --run RUN | SELECTOR> --from STAGE`** — deliberate re-execution escape
  hatch (new recording, re-research, re-voice). Folds in today's `run --stage X --force`
  (run-scoped re-execution moves here via `--run`); one verb, one flag name (`--from`).
  Rename `--with-research` (which *deletes* research) to `--redo-research`.
- **`voice <show | SELECTOR> [--off]`** — TTS as a first-class verb; sugar over
  `redo --from package --voice/--no-voice`. Owns the stamped-voice replay rules in its
  help. Replaces the four-flag incantation `redo --unvoiced --from package --voice --yes`.
- **`deliver <show | SELECTOR>`** — ship the package to `--dest` or `config.delivery_path`.
  - **Requires broadcast-ready by default.** Broadcast-ready = packaged + not-held + has
    DJ script + has DJ audio + has `broadcast.m3u` + all manifest track audio files on
    disk (`catalog.py:89`). (Functionally: voiced + file-complete + not-held.)
  - **Non-overridable refusals:** *held* (→ resolve via `fix`/`triage`) and *missing audio
    files* (→ broken package, re-package). These must never ship.
  - **Only overridable exception: `--allow-unvoiced`** — ships a packaged, file-complete,
    non-held, **music-only** show (bypasses only the voice-bundle reasons: DJ script / DJ
    audio / broadcast.m3u).
  - **Remove the old `--force`/`--deliver-held` entirely.** No deliver-time hold bypass.
- **`rm <show | SELECTOR> [--yes]`** — a real, tested show delete (removes `shows/<slug>/`);
  today there is none (only manual `rm -rf`). Always leaves history in an intentional
  state — never a stale row causing an accidental, irreversible "banish."
  - **Default (no flag): leave history untouched.** State-appropriate: a held show
    (no ledger row) becomes re-eligible; a packaged/delivered show (has a row) stays out.
    `rm` echoes what it did to history.
  - **`--forget`** — also purge this performance's ledger rows → fully re-eligible ("clean
    slate"). Meaningful for packaged/delivered shows.
  - **`--suppress`** — also write a reversible `rejected` row → guaranteed out. The only
    way to keep a *held* show (which otherwise has no keep-out row) from returning; also
    upgrades an incidental `selected` into a deliberate rejection.
- **`suppress <show> / unsuppress <show>`** — standalone deliberate reject / undo (replaces
  hand-assembling `ledger add … --status rejected`). Writes/removes a `rejected` row.

### History (renamed from `ledger`)

- **`history list`** — collapsed to **one row per performance (latest disposition)** by
  default; **`--log`** for the full append trail. Role shrinks to "dispositions for shows
  no longer on disk"; the library covers what's currently held.

### Archive URL surfacing

- Print the **selected recording's `https://archive.org/details/<identifier>`** by default
  in `show <name>` detail and at the top of each show in `triage` — the operator's first
  stop on a held show (today they read JSON).
- Also surface the **other considered recording identifiers** (the `scores` keys minus the
  chosen one, `selection.json`), optionally with their scores, so the operator can see the
  curated subset the pipeline weighed and why the chosen one won. Bare identifiers suffice
  (archive.org reconstructs the rest).

### Selector grammar (unify)

- **One selector implementation and one semantics** shared by `status`, `triage`, `redo`,
  `deliver`, `voice`, `rm`. Today four commands re-declare ~8 selectors via two code paths
  with drifting help and three different meanings of `--held` (see `docs/ux-review.md`
  B3). Consolidate behind one helper.
- **`--state` becomes a validated enum** listing all states (today it's a bare string;
  typos silently match nothing). Keep `--held`/`--packaged` as blessed shorthands if
  desired, or fold into `--state` (repeatable).
- **Acting on held shows requires explicit opt-in** — enforce and error uniformly in the
  shared layer, not as a per-command flag-meaning shift.

### Teaching & hygiene

- Move `--config` to the app callback (declared once, not on all ~23 commands).
- Drop the redundant `version` command (keep `--version`).
- `--json` on `show` and `history` (today only `status`).
- `profile` gains `show` / `remove` (today only `add/run/artists/list`, and inspecting
  means reading TOML); `presenter` gains `remove`. Enrich `profile list` (query, count,
  presenter).
- Stop the `profile-setup-*` scratch dirs from leaking into session listings.
- Regroup help panels (e.g. `presenter` → a Configure panel with `config`/`profile`, not
  next to `get`).
- *(The hygiene bundle + `pipeline` are scope-expanders the owner approved but is willing
  to defer to a follow-up — flag your recommendation on inclusion vs. deferral.)*

## Decisions already made — do NOT relitigate

- `get` (not `find`/`process`), `fix`, `triage`, `run approve`/`run resume` (sessions stay
  under the `run` namespace, not top-level `approve`), `history` (renamed), `--allow-unvoiced`.
- `deliver` requires broadcast-ready; held & missing-files non-overridable; unvoiced the
  sole exception. No deliver-time hold bypass.
- `rm` default leaves history untouched; `--forget` / `--suppress` are the overrides.
- Station norm for now: shows *should* be voiced, so broadcast-ready-by-default is correct
  friction (owner may revisit later).
- Approval gate persists (non-determinism). Sessions auto-unique-id'd.
- Library-as-dedup is IN scope. The "`selected` row written post-gate" behavior stays
  as-is (library-dedup handles re-offer of held shows); do NOT change when `selected` is
  written.

## Known open points to resolve in the spec (raise back if unsure)

- Exact wording/mechanics of the unified selector "held opt-in" rule and whether
  `--held`/`--packaged` survive as shorthands or fold entirely into `--state`.
- Whether `run` also needs a `show`/inspect verb, or `status --by-run` suffices.
- `pipeline` command's exact content/format, and the include-vs-defer call on it + the
  hygiene bundle.
- `get --plan` exact stop point and output shape.
- Session attention-list label format (how a session is displayed/addressed).
- Whether `--allow-unvoiced` / `rm` dispositions want confirmation prompts by default.
