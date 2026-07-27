# llama CLI UX redesign: the show-centric command surface

**Status:** approved design, pre-plan (expands the ratified brief
`2026-07-27-llama-ux-redesign-brief.md`; the brief's open points were raised
back and resolved with the owner — the settled calls are noted inline and
summarized in §14)
**Date:** 2026-07-27
**Scope:** a full re-cut of the CLI command layer (`src/llama/cli.py`) around
operator intent, plus three clearly-scoped new behaviors: library-as-dedup,
`rm`, and archive-URL surfacing. Backward compatibility is explicitly NOT a
concern — no aliases, no migration.

**Companion reading:** `docs/ux-review.md` (rationale, as-is map, findings) and
the brief above (the design-of-record; it wins over the review where they
differ, and this spec wins over both on mechanics it makes concrete).

## Purpose

The current surface (~23 commands, 4 sub-apps, `src/llama/cli.py` ~1437 lines)
grew feature-by-feature and now exposes implementation history instead of
operator intent: `show` is three commands in one with TTY-dependent modality
(`cli.py:694-833`), four commands re-declare eight selectors with three
different meanings of `--held` (`cli.py:707-714, 905-913, 1010-1018,
1069-1077`), the redo/replay story spans three overlapping commands with two
flag spellings, and run-vs-show naming collisions tax every invocation. This
redesign adopts the ux-review's Altitude C: shows become the only first-order
daily object, runs demote to transient acquisition sessions, and every verb
maps to exactly one intent.

## Constraints (hard)

**Off-limits — do not touch:**

- The staged pipeline itself (`pipeline.process_show`, the stage modules under
  `src/llama/stages/`), except the one-line dedup change in winnow (§9).
- The on-disk workspace layout: `runs/<name>/`, `shows/<slug>/`, all artifact
  names and schemas (`workspace.py`), with the one addition of a per-run
  `session.json` lifecycle marker (§4).
- `overrides.json` semantics (which stage reads which field, self-clearing
  holds, `show.json` stays derived).
- The show library layout and `slugify(performance_id)` keying.
- The LLM layer, prompts, schemas, and the TTS layer.
- **When the `selected` ledger row is written** (`pipeline.py:127`, only after
  both needs-review gates pass) — library-dedup handles held-show re-offer;
  do NOT move the write.

**Decided in the brief — do not relitigate:** `get` (not `find`/`process`),
`fix`, `triage`, sessions under the `run` namespace (`run approve`/`run
resume`, not top-level), `history` (renamed from `ledger`),
`--allow-unvoiced`; deliver requires broadcast-ready with held and
missing-files non-overridable and unvoiced the sole exception (no deliver-time
hold bypass); `rm` default leaves history untouched with `--forget`/
`--suppress` as the overrides; the approval gate persists; sessions get
auto-unique ids; library-as-dedup is in scope.

## Background: current code this spec is grounded in

All anchors verified against the working tree at spec time.

- **Command surface:** `src/llama/cli.py` — root Typer app + 4 sub-apps
  (`profile`/`ledger`/`config`/`presenter`), 4 rich-help panels, ordered by
  `_COMMAND_ORDER` (`cli.py:40`).
- **Derived state:** `catalog.derive_state(ws, delivered)` (`catalog.py:59`) —
  `held > delivered > packaged > scripted > vetted > researched > gathered >
  selected`; `held` is `show.json`'s `needs_review` flag and beats everything.
  `derive_voiced` (`catalog.py:77`), `broadcast_readiness` (`catalog.py:89`,
  the five conditions + reasons list), `iter_shows` (`catalog.py:116`),
  `select_shows` (`catalog.py:140`), `resolve_show`/`resolve_run`
  (`catalog.py:169/177` — exact match first, then unique-substring).
- **Winnow dedup:** `stages/winnow.py:58` — `seen = ledger.played_ids() |
  ledger.rejected_ids()`; the candidate pool excludes `seen`. No library
  awareness today: a held show (which has no ledger row, see next) re-surfaces
  in every future acquisition. This is the gap §9 closes.
- **Ledger:** `ledger.py` + `LedgerEntry` (`models.py:257`:
  `performance_id, artist, date, venue?, status ∈
  {selected|delivered|rejected}, run, recorded_at`). `played_ids` =
  selected|delivered; `rejected_ids` = rejected. `record()` is append-once on
  `(performance_id, status, run)`; `remove(pid)` drops *all* rows for a pid.
  `pipeline.py:127` writes `selected` only after the synthesize
  (`pipeline.py:114-117`) and package (`pipeline.py:122-126`) needs-review
  gates pass — **held shows have no ledger row**. `_deliver_one`
  (`cli.py:867`) writes `delivered`; `ledger add` (`cli.py:1391`) writes any
  status with `run="manual"`.
- **Deliver guard today:** `_deliver_one` (`cli.py:867-897`) refuses a
  needs-review show unless `--force`, requires `package/manifest.json`,
  copytrees `package/` → dest, records `delivered`.
- **Selection provenance:** `shows/<slug>/selection.json` =
  `{"identifier": chosen, "scores": {<identifier>: {score, lineage,
  kept_tracks, downloads_norm, title_fraction}, ...}}`
  (`select_recording.py:105`); `scores` is keyed by every considered
  recording. Archive item URL = `https://archive.org/details/<identifier>`.
- **Run structure:** `RunWorkspace` (`workspace.py:92`) = `runs/<name>/`
  holding only `criteria.json`, `candidates.json`, `shortlist.json`,
  `artists.json` — no show data. Shows live in `shows/<slug>/`
  (`workspace.py:102`), shared across runs; `provenance.json`
  (`models.py:267`) lets a show detach from its run (`_redo_show`
  reconstructs a `RunWorkspace` from `prov.run` but uses only `.root` and
  `show_ws()`, so a deleted run dir never breaks `redo`).
- **Run-name collision (bug):** `find` names its run
  `f"{date.today()}-{slug(query)[:40]}"` (`cli.py:324`); `profile run` uses
  `f"{date.today()}-{name}"` (`cli.py:1263`). A second same-day invocation
  reuses the dir and silently resumes instead of pulling fresh.
- **Interactive resolve:** `_interactive_resolve` (`cli.py:596-625`) — the
  `[e]xclude/[v]ague/[c]lear/[s]kip/[q]uit` walkthrough, reachable only as a
  side effect of flagless `show` on a TTY; no metadata option.
- **Stage vocabulary:** `VALID_STAGES` (`cli.py:37`), `RUN_LEVEL_STAGES =
  {search, winnow}` (`cli.py:38`); show-level order and artifact mapping in
  `workspace.py:66-89` (`drop_stage_artifacts`).
- **Profile scratch leak:** `profile add` interprets its query in a
  `RunWorkspace(root, f"profile-setup-{name}")` (`cli.py:1228`) that lands in
  `runs/` and shows up in listings forever.

---

## 1. The redesigned model

Three conceptual shifts, then the surface:

1. **Shows are the only first-order daily object.** Inspect (`show`), fix
   (`fix`/`triage`), re-execute (`redo`/`voice`), ship (`deliver`), delete
   (`rm`) all address shows by name/substring, exactly as today.
2. **A "run" becomes a transient acquisition session.** It exists from "I
   asked" until "approved & finished", surfaces only when it needs the
   operator (awaiting approval, or crashed/incomplete), and vanishes from
   view when complete. Session ids are auto-unique; the operator picks from a
   short attention-list by substring, never from memory.
3. **Dedup memory has two halves:** the on-disk show library ("what I
   currently have, in any state") and the ledger/history ("dispositions for
   shows no longer on disk"). Winnow consults both (§9).

### Command tree

```
Acquire        get · artists
Watch          status · show · pipeline
Fix & ship     triage · fix · redo · voice · deliver · rm · suppress · unsuppress
Namespaces     run · profile · presenter · history · config
```

| Command | Purpose | Replaces / moves |
|---|---|---|
| `get "query"` / `get --profile NAME` | acquire shows (one-off or standing) | `find` (`cli.py:288`), `profile run` (`cli.py:1252`) |
| `artists ["query"]` | explore the LMA artist index (read-only) | unchanged (`cli.py:350`); `--all` → `--include-junk` |
| `status [SELECTOR] [--by-run]` | global triage table + session attention-list | `status` (`cli.py:1068`) + `runs` (`cli.py:1143`) |
| `show <show>` | inspect one show, strictly read-only | `show`'s single-inspect half (`cli.py:751-787`) |
| `pipeline` | print stages / states / gates (teaching) | new |
| `triage [SELECTOR]` | interactive held-show walkthrough | `show`'s flagless set form + `_interactive_resolve` (`cli.py:596-625, 729-749`) |
| `fix <show> <edit-flags>` | edit overrides / resolve holds, auto-redo | `show`'s edit-flag half (`cli.py:797-833`) |
| `redo <show \| --run S \| SELECTOR> --from STAGE` | deliberate re-execution | `redo` (`cli.py:999`) + `run --stage X --force` (`cli.py:420-427, 439`) |
| `voice <show \| SELECTOR> [--off]` | TTS as a verb (sugar over redo) | the four-flag `redo --unvoiced --from package --voice --yes` idiom |
| `deliver <show \| SELECTOR>` | ship packages, broadcast-ready gated | `deliver` (`cli.py:901`), minus `--force` |
| `rm <show \| SELECTOR>` | delete a show dir, history-intentional | new (today: manual `rm -rf`) |
| `suppress` / `unsuppress <show>` | deliberate reject / undo | `ledger add --status rejected` (`cli.py:1391`) |
| `run list/approve/resume/rm` | session namespace | `runs`, `review` (`cli.py:444`), `run` (`cli.py:384`), new |
| `history list` | dispositions view (collapsed; `--log`) | `ledger list` (`cli.py:1384`) |
| `profile add/list/show/remove/artists` | standing profiles | + new `show`/`remove` |
| `presenter add/list/show/remove` | on-air hosts | + new `remove` |
| `config init` | seed config | unchanged (`cli.py:1168`) |

Deleted outright: the `version` command (`cli.py:90`; `--version` stays),
`ledger add`/`ledger remove` (`cli.py:1391/1406`; superseded by
`suppress`/`unsuppress`/`rm --forget` — the JSONL stays hand-editable as the
escape hatch), `deliver --force`, `run --stage/--force`, `show`'s set form
and edit flags, `review`.

The brief counts "16 top-level commands"; with `suppress`/`unsuppress`
counted separately and `artists` retained (owner-confirmed) the tree above
is 18. The grouping, not the count, is normative.

### Help panels

Four panels via `rich_help_panel`, in this order (extend the
`OrderedPanelGroup` ordering list, `cli.py:40-49`):

- **Acquire:** `get`, `artists`
- **Watch:** `status`, `show`, `pipeline`
- **Fix & ship:** `triage`, `fix`, `redo`, `voice`, `deliver`, `rm`,
  `suppress`, `unsuppress`
- **Sessions & config:** `run`, `profile`, `presenter`, `history`, `config`

This fixes the misfiled `presenter` (today next to `find` in "Discover &
process", `cli.py:64-66`).

---

## 2. The shared selector layer

One implementation, one help string per flag, one semantics — used by
`status`, `triage`, `redo`, `voice`, `deliver`, `rm`. Today's two code paths
(`_batch_select` `cli.py:836` vs inline `select_shows` calls) and 32 drifting
option declarations collapse into a single module-level helper (suggested:
`src/llama/cli_select.py`, or a section of `cli.py` — implementer's choice)
that owns option declaration, reconciliation, and the held opt-in rule.

### Grammar

```
--state STATE          repeatable; validated enum (see below)
--held                 sugar for --state held
--packaged             sugar for --state packaged
--voiced / --unvoiced  voiced is True / voiced is False (both imply packaged;
                       pre-package shows are voiced=None and match neither)
--broadcast-ready      broadcast_ready is True (positive-only; no inverse)
--artist SUBSTR        case-insensitive substring on artist
--run SESSION          shows whose provenance.run matches (resolved via
                       resolve_run, so substrings work)
```

- All filters AND together; `--state` values OR together (repeatable).
  Backed by the existing `catalog.select_shows` (`catalog.py:140`), which
  already has exactly these axes; the CLI layer only reconciles flags.
- **`--state` becomes a validated enum** (Python `enum.Enum` handed to Typer
  so it validates and lists values in help): `held | selected | gathered |
  researched | vetted | scripted | packaged | delivered`. A typo is now a
  CLI error, not a silent empty match (fixes ux-review C6).
- `--held`/`--packaged` survive as blessed shorthands (owner-confirmed):
  they are pure sugar that adds to the same states set, declared once in
  the shared layer. No other state gets a shorthand.
- The three-copy voiced reconciliation (`True if voiced else (False if
  unvoiced else None)`, `cli.py:737, 843, 1096`) is written once here.

### Command argument shape

Every selector-capable action command takes `[NAME] [SELECTOR-FLAGS]` with
uniform rules, errored identically by the shared layer:

- Positional `NAME` and selector flags are mutually exclusive ("give a show
  OR selectors, not both").
- Neither given → error naming an example selector (except `status` and
  `triage`, which have defaults: all shows / held shows respectively).
- Batch actions print a plan (count + slugs + the action + any per-show
  annotation) and confirm `Proceed? [y/N]`; `--yes` skips. Per-show failures
  print `FAILED <slug>: …` and the sweep continues (today's behavior,
  `cli.py:1045-1051`).

### The held opt-in rule

**Acting on held shows via a selector requires explicit opt-in.** Enforced in
the shared layer, not per command:

- Commands are classed **read-only** (`status`, `show`) or **acting**
  (`triage`, `redo`, `voice`, `deliver`, `rm`).
- For an acting command, selector matches in state `held` are dropped unless
  the selector *explicitly* included held (`--held` or `--state held`). When
  any are dropped, the plan prints one note:
  `note: N held show(s) excluded (add --held to include them)`.
- `triage` is the exception that proves the rule: its default selector *is*
  held (resolution is its purpose), so no opt-in applies; a broader `triage`
  selector walks held shows and print-skips the rest (§6).
- **Naming a single show positionally is itself explicit opt-in** — `redo
  gd73 --from gather` on a held show runs (that is how holds self-clear
  today); `deliver gd73` on a held show proceeds to the per-show gate and is
  refused there with the reason (§7.3). The rule governs *implicit batch
  inclusion* only.

This replaces today's third meaning of `--held` ("include held in the batch",
`cli.py:847-848`) with the same words meaning the same filter everywhere,
plus one uniformly-enforced acting rule.

---

## 3. Acquire: `get`

```
llama get "query"        [--limit N] [--auto] [--plan] [--name NAME]
                         [--script/--no-script] [--voice/--no-voice]
                         [--artist-cap F] [--min-score F] [--year-cap F]
                         [--full-rationale]
llama get --profile NAME [--auto] [--plan] [--full-rationale]
```

One verb replaces `find` + `profile run`; honest that it spends. Exactly one
of `"query"` / `--profile` is required.

- **Query mode** preserves today's `find` behavior verbatim (`cli.py:288-346`
  → `_execute` `cli.py:196`): interpret → stamp explicit flags into the run's
  `criteria.json` for replay → artist-prune prompt (discovery path) →
  search → winnow → shortlist print → shortlist-approval prompt → per-entry
  processing with per-show failure isolation. Flag names and validation
  (the `--artist-cap/--year-cap` zero guard, voice-implies-script) carry over
  unchanged.
- **Profile mode** preserves today's `profile run` (`cli.py:1251-1280`):
  loads the profile, stamps count/script/voice/presenter/title into the
  session's criteria, honors `human_gate`. Profile mode accepts only
  `--auto`, `--plan`, `--full-rationale`; the query-mode tuning flags error
  with "set these on the profile" (they would silently fight the profile's
  persisted settings).
- `--name` replaces `--run-name`: an explicit session id override, mainly
  for tests/scripting. Without it, ids are auto-unique (§4).
- The winnow pool now also excludes library shows (§9).

### `get --plan`

A cheap, explicit preview: run interpret → search → winnow exactly as normal
(winnow's LLM scoring and light research still spend — that is what produces
the shortlist), print the shortlist, then **stop before any approval prompt
or per-show processing**. The session is parked as *awaiting approval* (§4)
and the command exits with:

```
shortlist ready — nothing processed.
to approve & process:  llama run approve <session-id>
to discard:            llama run rm <session-id>
```

Mechanics: `--plan` behaves like a mandated-but-unanswered human gate — after
`run_winnow` returns, `_execute` writes the session marker
`awaiting-approval` and returns without calling `choose_entries`/
`process_show`. Nothing downstream of winnow runs, so no downloads, no deep
research, no packaging. `--plan` composes with both modes and with `--auto`
(`--plan` wins; `--auto --plan` is "spend on winnow, never prompt, park it").

### `artists` (retained)

The brief's redesigned tree omitted `artists` by accident; the owner
confirmed keeping it — it is the one genuinely read-only exploration command
and the natural companion to `get`. It is retained unchanged
(`cli.py:350-380`) under the Acquire panel, with one hygiene rename:
`--all` → `--include-junk` (ux-review C1; `--all` keeps its "include
delivered" meaning on `status` only).

---

## 4. Sessions: the `run` namespace

### Auto-unique ids

Session ids keep the readable `YYYY-MM-DD-<slug>` base (`slug` = query slug
truncated to 40 chars, or the profile name) and append `-2`, `-3`, … when the
directory already exists (first collision gets `-2`; scan for the lowest free
suffix). This fixes the silent same-day reuse (`cli.py:324, 1263`). The
operator never types an id from memory — `run list`/`status` display them and
`resolve_run`'s exact-match-first rule (`catalog.py:158-166`) keeps
`2026-07-27-x` addressable even when `2026-07-27-x-2` exists.

### Session lifecycle marker: `runs/<id>/session.json`

Show state stays derived-never-stored — that principle is absolute for show
content (`show.json` and everything under `shows/`), and this marker never
lives there. A **session is a process object, not a derived view of
content**: its lifecycle is event-like and **cannot** be derived from
artifacts (a shortlist with no processed shows is indistinguishable between
"gate deferred deliberately" and "crashed after winnow"). Recording process
state on the process's own directory is therefore legitimate lifecycle
state, not an erosion of the principle. The session runner writes a tiny
marker at clean stopping points:

```json
{"state": "awaiting-approval" | "complete", "updated_at": "<ISO-8601 UTC>",
 "outcome": "<one-line summary or null>"}
```

- Written `awaiting-approval` when `_execute` stops at the human gate
  (`choose_entries` returns `None`, today's `cli.py:255-257`) or at `--plan`.
- Written `complete` when `_execute` finishes its processing loop (including
  degenerate completions: "no shows survived winnowing", zero approved
  entries processed). `outcome` carries the one-liner ("2 packaged, 1 held").
- Never written mid-flight — absence of the file (or `awaiting-approval`
  with the operator having since crashed an approve-and-process) plus a
  non-`complete` state means the session needs attention.
- `write_artifact` (atomic temp+rename, `workspace.py:17`) writes it.
- Pre-redesign run dirs have no marker and will list as *incomplete*; there
  is deliberately no migration — the owner purges old sessions with
  `run rm` (consistent with the project's no-legacy-handling norm).

Derived session state, given the marker:

| Condition | State | In attention-list? |
|---|---|---|
| `session.json` state == `complete` | complete | no (hidden everywhere) |
| state == `awaiting-approval` | awaiting approval | yes |
| no marker / anything else | incomplete (crashed or interrupted) | yes |

### `run list`

The attention-list: sessions that are awaiting approval or incomplete,
newest first. Complete sessions are not shown (their dirs remain on disk
harmlessly; shows detach via provenance).

```
SESSION                              STATE               AGE   CRITERIA
2026-07-27-sunday-dead-hour-2        awaiting approval   3h    profile: sunday-dead-hour
2026-07-27-china-rider               incomplete          2d    "GD '73-'74 with a china>rider"
```

`AGE` from the marker's `updated_at`, else the dir mtime. `CRITERIA` from
`criteria.json` (`profile: <name>` when the criteria carry a presenter/title
stamp from a profile — record the profile name in criteria for display;
otherwise the query, quoted, truncated). `--json` emits
`[{id, state, updated_at, query, profile}]`.

### `run approve <session>`

Gate 1, today's `review` (`cli.py:444-486`) renamed and moved: print the
persisted shortlist (`--full-rationale` honored), prompt
`Approve which ranks?`, mark approved (unnamed ranks stay undecided — today's
semantics, `cli.py:470`), then confirm `Process approved shows now? [Y/n]`.

- Processing now → run `_execute`'s processing tail with the persisted
  criteria (script/voice/presenter/title from the stamped criteria), then
  write the `complete` marker.
- Declining → keep `awaiting-approval` and print
  `next: llama run resume <session-id>` — by **id**, not directory path
  (fixes the E3 seam, `cli.py:486`).
- The shortlist approval **persists** (winnow is non-deterministic; a
  deferred approval must approve the exact list that was shown). Unchanged
  mechanism: `approved` flags written back into `shortlist.json`.
- The `--script/--voice` overrides today's `review` carries are dropped;
  post-hoc voice changes are `voice`'s job (§7.2).

### `run resume <session>`

Today's `run` (`cli.py:384-440`) reduced to resume-only: re-execute the
session from its artifacts, stages skipping work already done. No `--stage`,
no `--force` (run-scoped re-execution moved to `redo --run`, §7.1). Keeps
`--auto/--interactive` (default `--auto`, as today) and `--full-rationale`.
The persisted criteria fully determine script/voice/presenter — the
`--script`/`--voice` overrides are dropped from resume (post-hoc voice
changes are `voice`'s job, §7.2). Writes the `complete` marker on finish.

### `run rm <session>`

Discard a session: delete `runs/<id>/` (rmtree) after a y/N confirmation
showing the id and state (`--yes` skips). Shows the session processed are
untouched (they live in `shows/` and carry provenance). No ledger
interaction — sessions have no history rows of their own.

### Whether `run` needs a `show`/inspect verb

No (owner-confirmed): `run approve` already displays the shortlist,
`status --by-run` shows per-session show rollups, and the session dir is
plain JSON for the rare deep inspection. A `run show` would be a fifth verb
with no daily use.

---

## 5. Watch: `status`, `show`, `pipeline`

### 5.1 `status [SELECTOR] [--all] [--by-run] [--json]`

The global triage table, held-first (unchanged sort, `cli.py:1101,
_STATE_RANK`), now fronted by the session attention-list.

- **Attention-list header:** when any session is awaiting approval or
  incomplete, print before the show table:

  ```
  sessions needing attention:
    2026-07-27-sunday-dead-hour-2   awaiting approval   llama run approve sunday-dead-hour-2
    2026-07-27-china-rider          incomplete          llama run resume china-rider
  ```

  (id, state, and the copy-pasteable next command using a unique substring —
  use the full id if unsure of uniqueness). Suppressed when a selector or
  `--json` is given? No — always shown in the human view; in `--json` it
  becomes a `sessions` key.
- **Selectors:** the shared layer (§2), read-only class (no held opt-in).
  `--all` keeps its meaning: include all delivered shows instead of the
  recent-5 tail (`cli.py:1102-1111`).
- **`--by-run`** absorbs today's `runs` command (`cli.py:1143-1165`): one row
  per session — id, per-state show counts, query — for *all* sessions with
  shows or artifacts (not just attention ones). Mutually exclusive with
  selectors and `--all`.
- **Row format** unchanged (slug, state, artist, date, run, marks
  `[broadcast-ready, voiced, vague, Nx-excl]`, indented flags).
- **`--json` shape change** (breaking; owner-accepted — their own scripts
  are the only consumers): the payload becomes an object
  `{"sessions": [...], "shows": [...]}` where `shows` rows keep today's
  fields (`cli.py:1113-1120`). With `--by-run`:
  `{"sessions": [...], "runs": [{id, query, states: {state: n}}]}`.

### 5.2 `show <show> [--tracks] [--json]`

Strictly read-only single-show inspection. **Never prompts, never edits** —
the TTY-modality special-casing (`cli.py:780-787`) and the set form are gone.
Content = today's `_print_show_entry` (`cli.py:628-691`) plus:

- **Archive URLs (new, §10):** after the `recording:` line, print the
  selected recording's URL; then a `considered:` block listing every other
  identifier from `selection.json`'s `scores` with its score, sorted
  descending, so the operator can see what the pipeline weighed and why the
  chosen one won. Bare identifiers suffice for reconstruction but the URL is
  printed for the *chosen* one (the operator's first stop on a held show).
- The `broadcast-ready: yes|no` (+ reasons) line stays (`cli.py:681-688`).
- The overrule hint (`cli.py:680`) becomes
  `to overrule after inspecting: llama fix <slug> --overrule`.
- `--json`: full machine-readable detail —
  `{slug, state, flags, artist, date, venue, city, identifier, archive_url,
  considered: [{identifier, score, lineage, kept_tracks}], tracks?, path,
  run, voiced, broadcast_ready, broadcast_reasons, overrides, stages: {name:
  age_days|null}, needs_review}`. `--tracks` adds the tracks array in JSON
  and the numbered list in text (today's `_format_tracks`).
- A show with no `show.json` yet (state `selected`) prints what exists
  (identity from provenance, stage table, URLs) instead of today's hard error
  (`cli.py:630-632`) — a read-only command should describe any show it can
  resolve. Implementation keeps it simple: print slug/state/path + stage
  table + selection URLs when `selection.json` exists.

### 5.3 `pipeline`

A teaching command: static text, no I/O beyond config-free printing. Content
(sourced from `docs/workflow.md`'s diagram and tables, maintained inline):

1. The stage flow with the two gates marked:
   `interpret → search → winnow →(gate 1: run approve)→ select → gather →
   research → vet → synthesize → package →(gate 2: held / triage · fix)→
   deliver`, one line per stage with a phrase on what it does and what it
   writes.
2. The eight `--state` values with one-line meanings, plus the two derived
   annotations (`voiced`, `broadcast-ready` with its five conditions).
3. The redo cheat-sheet: which fix redoes from which stage
   (excludes/metadata → gather, narration → synthesize, overrule → package,
   new recording → select, re-research → research) — with the note that
   `fix` applies these automatically and `redo --from` is the manual escape
   hatch.

Include-vs-defer: **include** (owner-confirmed) — it is a static print
command (~60 lines + one test) and the redesign's teaching story (validated
enum, `fix` auto-stage) is complete only with it. It remains the first thing
to cut if the plan runs long.

---

## 6. Fix & resolve: `triage`, `fix`

Holds are cleared **only** via these two commands — either a real fix whose
re-gather/re-synth self-clears the flag (gather recomputes
`needs_review`/`review_flags` from scratch every run), or an explicit
`--overrule`. There is no other bypass anywhere (deliver's held refusal is
non-overridable, §7.3).

### 6.1 `triage [SELECTOR]`

The interactive walkthrough, promoted from a side effect (`cli.py:596-625,
744-748`) to a named command. Always interactive, always predictable:

- **Requires a TTY**; off-TTY it errors
  (`triage is interactive; use status/show for scripted reads`). No
  TTY-dependent job switching, ever.
- Default selector: `--held`. Any shared-layer selector is accepted; held
  shows get the resolve prompt, non-held matches are printed and skipped
  (nothing to resolve) — today's set-form behavior, kept.
- Per show: print the full inspection block (as `show <name>`, **including
  the archive URL block** — the operator's first stop), then prompt:

  ```
  [e]xclude tracks / [m]etadata / [v]ague / [o]verrule / [s]kip / [q]uit
  ```

  - **[e]xclude** — numbered track list, pick indices (today's
    `_pick_excludes`, `cli.py:588`), write `overrides.exclude`, redo from
    gather.
  - **[m]etadata (new)** — a mini-editor for the gather-consumed override
    fields. Sequence of prompts, each showing the current effective value,
    empty input = keep: `venue`, `city`, `date (YYYY-MM-DD)`,
    `title overrides (N=Title, comma-separated)`,
    `set breaks after tracks (e.g. 9,17)`. Inputs validate exactly as
    `fix`'s flags do (§6.2); on any change, write the overrides and redo
    from gather. Nothing entered → back to the prompt.
  - **[v]ague** — `overrides.narration=vague`, clear the hold, redo from
    synthesize.
  - **[o]verrule** — clear the hold, redo from package. (Renamed from
    today's `[c]lear`.)
  - **[s]kip** / **[q]uit** — next show / stop.
- After each action: re-resolve and report
  `packaged: <path>` / `still held: <slug>` before advancing (today's
  behavior, `cli.py:623-625`).

### 6.2 `fix <show> <edit-flags> [--no-run]`

The flag-driven editor for `overrides.json` and hold resolution. **Applies
the correct redo by default** — the inversion of today's print-a-command
default (`cli.py:827-833`); the tool already computes the stage, so it runs
it. `--no-run` stages the edit and prints the next step instead (for
batching several edits before one redo).

Flags (renames from today's `show` flags in parentheses):

| Flag | Effect | Redo stage |
|---|---|---|
| `--exclude FILE\|N` (repeatable, comma groups) | add to `overrides.exclude`; numbers resolve via show.json (`_resolve_exclude_tokens`, `cli.py:538`) | gather |
| `--unexclude FILE\|N` (was `--include`) | remove from `overrides.exclude` | gather |
| `--set-venue V` / `--set-city C` / `--set-date YYYY-MM-DD` | force the field | gather |
| `--set-title N="…"` (was `--title`) / `--clear-title N` | force/drop a track title | gather |
| `--set-breaks "9,17"` / `--clear-set-breaks` | force/drop set breaks | gather |
| `--narration vague\|full` (was `--vague`/`--full`; validated enum) | set `overrides.narration`; `vague` also clears the hold | synthesize |
| `--overrule` (was `--clear`) | clear `needs_review`/`review_flags`: "I've reviewed it, ship it" | package |

- At least one flag is required (bare `fix <show>` errors, pointing at
  `show`/`triage`).
- Combining flags is allowed; the redo runs once from the **earliest**
  applicable stage (gather < synthesize < package) — today's precedence
  (`cli.py:827`).
- Hold-clearing semantics unchanged: excludes/metadata do *not* pre-clear
  (the re-gather decides, self-clearing only if the derivation comes out
  clean); `--narration vague` and `--overrule` clear immediately (operator
  judgment).
- Input validation (title `N="…"` shape, numeric breaks, numeric
  clear-title) carries over verbatim (`cli.py:754-773`).
- Output: the per-edit confirmations (today's, `cli.py:804-826`), then
  either the redo result (`packaged: …` / `still held: …`) or, with
  `--no-run`, `staged; next: llama redo <slug> --from <stage>`.
- `fix` works on non-held shows too (overrides are general inputs, not
  hold-only); `--overrule` on a non-held show is a no-op + note.
- Single-show only. Batch resolution is `triage`; there is deliberately no
  batch `fix` (bulk blind edits to per-show overrides are a foot-gun).

---

## 7. Act & ship: `redo`, `voice`, `deliver`

### 7.1 `redo <show | --run SESSION | SELECTOR> --from STAGE [--redo-research] [--script/--no-script] [--voice/--no-voice] [--yes]`

The deliberate re-execution escape hatch (new recording, re-research,
re-voice, replay after a code change). One verb, one flag name (`--from`).

Three addressing forms:

1. **Single show:** `redo gd73 --from gather` — today's per-show redo
   (`_redo_show`, `cli.py:953`) unchanged: drop the stage's artifacts and
   everything downstream (`drop_stage_artifacts`), re-run the tail via
   `process_show` with provenance-derived context. Stage ∈
   `select | gather | research | vet | synthesize | package`. A show without
   `provenance.json` errors as today (`cli.py:962-964`).
2. **Selector batch:** `redo --unvoiced --from package …` — shared layer
   (§2), acting class (held opt-in), plan + confirm + per-show failure
   isolation.
3. **Session scope (new home for `run --stage X --force`):**
   `redo --run <session> --from STAGE`.
   - `STAGE ∈ {search, winnow}` (run-level, valid **only** with `--run`):
     re-execute the session pipeline from that stage — delete the stale
     downstream run artifacts (`candidates.json`+`shortlist.json` for
     search, `shortlist.json` for winnow; today's `cli.py:420-426`), then
     re-run `_execute`. When the doomed shortlist carries approvals, confirm
     `this rebuilds the shortlist and discards the approvals recorded on it`
     first (today's guard, `cli.py:414-419`). Today's whole-run
     `run X --force` is spelled `redo --run X --from search`.
   - `STAGE` show-level: batch-redo the session's shows — identical to the
     selector form with `--run` as the only filter (this is today's `redo
     --run X` selector meaning, kept).
- `--redo-research` (renamed from `--with-research`, which *sounded*
  additive but deletes `research.md`): also drop research when redoing from
  `select`/`gather` (today's `keep_research` logic, `cli.py:968`).
- `--script/--no-script`, `--voice/--no-voice` keep today's replay-override
  semantics (`_replay_voice`, `cli.py:138`): unset defers to the provenance
  stamp.
- Stage-name validation errors list the legal set for the addressing form
  used.

### 7.2 `voice <show | SELECTOR> [--off] [--yes]`

TTS as a first-class verb; pure sugar over
`redo --from package --voice/--no-voice`:

- `voice <show>` ≡ `redo <show> --from package --voice`
- `voice --off <show>` ≡ `redo <show> --from package --no-voice`
  (strips DJ audio + broadcast.m3u from the rebuilt package)
- `voice --unvoiced --yes` replaces the four-flag incantation
  `redo --unvoiced --from package --voice --yes`.
- Selector form uses the shared layer (acting class). No default selector —
  bare `voice` errors with `give a show or a selector (e.g. --unvoiced)`.
- **Its help text owns the stamped-voice replay rules** (today scattered
  across `workflow.md:358-373` and two commands' help): re-voicing replays
  the voice stamped at process time when one exists (presenter clone edits
  are live because the stamp is the clone path; preset changes need the
  stamp cleared / a fresh process); with no stamp, the house `[tts]`
  voice applies; `--off` always wins.

### 7.3 `deliver <show | SELECTOR> [--dest DIR] [--allow-unvoiced] [--yes]`

Ship `package/` to `--dest` or `config.delivery_path` and record `delivered`
(unchanged mechanics: copytree + ledger row, `cli.py:867-897`).

**Gating (per show, single or batch): requires broadcast-ready.**
`broadcast_readiness(ws)` (`catalog.py:89`) is the authority; its reasons
partition into:

| Reason (from `catalog.py:89`) | Class |
|---|---|
| `not packaged` | non-overridable |
| `held for review` | **non-overridable** — resolve via `fix`/`triage` |
| `N of M audio files missing` | **non-overridable** — broken package; re-package |
| `no DJ script` | voice bundle — bypassed by `--allow-unvoiced` |
| `no DJ audio (unvoiced)` | voice bundle — bypassed by `--allow-unvoiced` |
| `no broadcast.m3u` | voice bundle — bypassed by `--allow-unvoiced` |

- A show delivers iff its reasons list is empty after removing (with
  `--allow-unvoiced`) the three voice-bundle reasons. `--allow-unvoiced`
  ships a packaged, file-complete, non-held, music-only show — the **sole**
  exception, and it carries no extra confirmation beyond the normal batch
  plan; the flag itself is the consent.
- Refusals print the failing reasons and the pointer:
  `refusing to deliver <slug>: held for review — resolve with llama triage`
  (or `re-run: llama redo <slug> --from package` for missing files).
- **`--force` is removed entirely.** There is no deliver-time hold bypass of
  any kind; the old `needs-review + --force` path (`cli.py:879-884`) is
  deleted. Station norm: shows *should* be voiced; broadcast-ready-by-default
  is correct friction.
- Batch form: shared selector layer; `deliver --broadcast-ready` is the
  natural "ship everything ready" sweep. The held opt-in rule applies at the
  selector layer, but held shows are refused per-show regardless (defense in
  depth; the note steers to `triage`).
- The delivered ledger row is unchanged (`performance_id` from the manifest,
  `status="delivered"`).

---

## 8. Remove & suppress: `rm`, `suppress`, `unsuppress`

### 8.1 `rm <show | SELECTOR> [--forget | --suppress] [--yes]`

A real, tested show delete — today there is none (owner does `rm -rf` by
hand). Removes `shows/<slug>/` recursively. Always leaves history in an
intentional, *stated* state; never a stale row causing an accidental,
irreversible banish.

**Three history dispositions** (mutually exclusive; default = no flag):

| Mode | Ledger effect | Net effect by prior state |
|---|---|---|
| default | untouched | held/pre-package show (no ledger row): becomes **re-eligible** in future `get`s. Packaged/delivered show (has `selected`/`delivered` rows): **stays out** (history dedup). |
| `--forget` | purge **all** rows for this performance (`Ledger.remove(pid)`, `ledger.py:34`) | fully re-eligible — a clean slate. Meaningful for packaged/delivered shows. |
| `--suppress` | additionally append a `rejected` row (`run="manual"`) | guaranteed out, reversibly (`unsuppress`). The only way to keep a *held* show (which has no keep-out row) from returning; also upgrades an incidental `selected` into a deliberate rejection. |

- **`rm` echoes what it did to history**, e.g.
  `removed shows/gd1972-08-27 — no history rows; this show can be re-offered`
  / `… — history kept (selected, delivered): stays excluded from future gets`
  / `… — forgot 2 history rows: re-eligible`
  / `… — suppressed: will not be offered again (undo: llama unsuppress …)`.
  The library half of dedup (§9) obviously ends at deletion; the echo makes
  the ledger half explicit.
- **Confirmation by default**: print the dir(s)
  to delete + the per-show history disposition line, confirm y/N; `--yes`
  skips. Deletion is the one irreversible local operation.
- Performance-id resolution: provenance → show.json (existing
  `catalog._performance_id`, `catalog.py:51`). If no pid is resolvable
  (degenerate dir), the default mode still deletes; `--forget`/`--suppress`
  error (nothing to key history on). `--suppress` needs artist/date for the
  row: from `show.json`, else provenance's candidate.
- Selector form: shared layer, acting class (held opt-in — note `rm --held`
  is the legitimate "purge my junk holds" sweep and must be spelled
  explicitly). Batch plan lists each slug with its disposition line.
- Delivered copies at the station are out of scope: `rm` touches the
  workspace only.

### 8.2 `suppress <show-or-performance-id>` / `unsuppress <show-or-performance-id>`

The standalone deliberate reject / undo — replaces hand-assembled
`ledger add … --status rejected` (`cli.py:1391-1403`, deleted).

- `suppress`: append `LedgerEntry(status="rejected", run="manual")`.
  Append-once dedup (`ledger.py:26`) makes repeats harmless. The show, if on
  disk, is untouched (library dedup already excludes it; suppression is the
  durable half that survives `rm`).
- `unsuppress`: remove this performance's `rejected` rows **only** — new
  `Ledger.remove_status(performance_id, status)` (the existing `remove`
  drops all rows and remains for `rm --forget`). Prints the count; 0 is a
  clean no-op message.
- Argument resolution: try `resolve_show` first (metadata from
  show.json/provenance); if no show matches, accept a raw performance id —
  it must look like `collection/date[/eN]`, from which
  `artist=collection`, `date=date-part` derive for the row
  (owner-confirmed). This keeps "never offer me this again" usable
  for shows long gone from disk.
- No confirmation prompts (reversible by construction).

---

## 9. Dedup: library ∪ ledger

`stages/winnow.py:58` changes from

```python
seen = ledger.played_ids() | ledger.rejected_ids()
```

to

```python
seen = library_ids | ledger.played_ids() | ledger.rejected_ids()
```

- **`library_ids`** = the performance id of every show currently on disk, in
  *any* state (held, selected, packaged, delivered, mid-anything). New
  helper `catalog.library_performance_ids(root) -> set[str]`: walk
  `shows/*/`, collect `_performance_id(ws)` (`catalog.py:51` — provenance
  first, then show.json), skip unresolvable dirs. Cheap at this scale (~10²
  dirs, and `iter_shows` already does this walk).
- Plumbing: `run_winnow` gains a `library_ids: set[str]` keyword (default
  `set()` keeps the function's contract honest for existing tests); the
  session runner (`_execute`) computes it via the helper and passes it. The
  winnow log line extends to
  `"%d candidates -> %d after library+ledger -> %d after mechanical"`.
- **Effect:** a show in the library is never re-offered (you have it; act
  locally) — closing the gap where **held** shows (which have no ledger row,
  `pipeline.py:127` writing `selected` only post-gates) re-surfaced in every
  future `get`. Delivered/rejected shows no longer on disk stay excluded via
  the ledger. Gone from both → re-eligible (the `rm` default for held shows,
  deliberately).
- **What it does NOT affect:** `redo`, `fix`, `triage`, `voice`, `deliver`,
  and any direct show operation — none of them run winnow. Re-winnowing a
  session (`redo --run X --from winnow`) now also excludes shows that
  session itself created — consistent (they are on disk; act locally).
- The "`selected` row written post-gate" behavior stays exactly as-is.

---

## 10. Archive-URL surfacing

The operator's first stop on a held show is the archive.org item page; today
they read `selection.json` by hand. Two surfaces:

1. **`show <name>`** (§5.2): under the `recording:` line —

   ```
   recording: gd73-06-10.sbd.hollister.174.sbeok.shnf  (24 tracks)
     https://archive.org/details/gd73-06-10.sbd.hollister.174.sbeok.shnf
   considered:
     gd1973-06-10.sbd.miller.32350.sbeok.flac16   7.9
     gd73-06-10.aud.weiner.gems.95443.flac16      5.1
   ```

   `considered` = `selection.json`'s `scores` keys minus the chosen one,
   with each recording's `score`, sorted descending. Bare identifiers (the
   URL prefix is constant and printed once above); omit the block when
   `scores` has only the chosen entry. Absent `selection.json` → omit both.
   `--json` carries `archive_url` and the full `considered` array (§5.2).
2. **`triage`** (§6.1): the same lines appear in each show's header block
   (it prints the full inspection view), putting the URL at the top of every
   resolution decision.

No other command changes; `status` rows stay one-line.

---

## 11. Namespaces: `profile`, `presenter`, `config`, `history`

### `history` (renamed from `ledger`)

- **`history list [--log] [--json]`** — default: **one row per performance,
  latest disposition** (group by `performance_id`, keep the row with the
  greatest `recorded_at`; file order breaks ties):

  ```
  2026-07-25  delivered  GratefulDead/1977-06-09      (2026-07-20-china-rider)
  2026-07-26  rejected   DelMcCouryBand/2003-04-19    (manual)
  ```

  `--log` prints the full append trail (today's `ledger list` output,
  `cli.py:1384`). `--json` emits the corresponding rows (collapsed:
  `[{performance_id, status, run, recorded_at}]`; `--log`: every row).
- `add`/`remove` are **deleted** (owner-confirmed): `suppress`
  covers reject, `unsuppress`/`rm --forget` cover removal, and the JSONL
  remains hand-editable for anything exotic (e.g. marking a never-processed
  show as played).
- The ledger's role statement (docs + help): "dispositions for shows no
  longer on disk"; the library covers what is currently held.

### `profile`

- Kept: `add`, `artists` (view/`--set` re-pin, `cli.py:1283`), `list`.
- **`profile show <name>` (new):** print the profile's fields — name, query,
  count, human_gate, script, presenter, title, pinned roster, and the
  interpreted criteria highlights (collection/artist, date range, caps,
  min score). Reads the TOML via `load_profile`; no LLM call.
- **`profile remove <name>` (new):** delete `profiles/<name>.toml` with y/N
  confirmation (`--yes` skips). Sessions/shows already created are
  untouched.
- **`profile list` enriched:** columns name, count, presenter (or `-`),
  query (truncated) — replacing today's bare stems (`cli.py:1309-1314`).
- **Scratch-dir leak fixed:** `profile add`'s interpret runs in a temp
  directory (`tempfile.TemporaryDirectory` wrapping a throwaway
  `RunWorkspace`-shaped path, or `root/cache/profile-setup/` cleaned after)
  — never under `runs/` (`cli.py:1228`). Existing `profile-setup-*` dirs are
  the owner's to delete; `run rm` can also take them.

### `presenter`

- Kept: `add`, `list`, `show`.
- **`presenter remove <id>` (new):** delete `presenters/<id>.toml` with y/N
  confirmation (`--yes` skips). If any profile references the id, refuse
  with the list of referencing profiles (scan `profiles/*.toml`) —
  `--force` overrides (the next run of that profile will then fail fast at
  `load_presenter`, which is the existing behavior for a missing id).

### `config`

- `config init` unchanged (`cli.py:1168`).
- **`--config` moves to the app callback** (`@app.callback`, stored on
  `ctx.obj` / a module-level holder): declared once instead of on all ~23
  commands (`cli.py:77-87` shows the callback pattern via `--version`). Every
  command's `_setup(...)` reads it from the context. `--config` before the
  subcommand (`llama --config X status`) is the supported spelling.
- The `version` **command** is deleted; `--version` stays.

---

## 12. Hygiene bundle: include now

Owner-confirmed: the whole hygiene bundle rides
**in** this redesign rather than a follow-up, because the re-cut already
rewrites every command declaration and every CLI test — touching them twice
is strictly more work. Items, consolidated from the sections above:

- `--config` → app callback; `version` command dropped (§11).
- `--state` validated enum everywhere (§2).
- `--json` on `show` (§5.2) and `history list` (§11); `status --json` shape
  (§5.1); `run list --json` (§4).
- `profile show/remove`, enriched `profile list`, `presenter remove`,
  scratch-dir fix (§11).
- Renames: `--include`→`--unexclude`, `--title N=`→`--set-title N=`,
  `--vague/--full`→`--narration vague|full`, `--clear`→`--overrule`,
  `--with-research`→`--redo-research`, `artists --all`→`--include-junk`.
- Panel regrouping (§1).
- Docs alignment: the CLI stage token stays `select`; sweep docs that spell
  it `select-recording` in argument positions.
- `pipeline` (§5.3) — include; first candidate to cut.

Explicitly deferred (not in this redesign): `profile set` (general profile
field editing beyond `artists`), `config show`, any localization of
`profile add --title` naming (the `fix --set-title` rename already resolves
the collision from the dangerous side).

---

## 13. Testing strategy

Offline, deterministic, `fake` LLM backend, real fixtures — unchanged
posture. **Pipeline and stage tests stand as-is** (nothing below the command
layer changes except winnow's `seen` and the catalog/ledger helpers). **CLI
tests are rewritten** around the new surface — `test_cli.py`,
`test_cli_commands.py`, `test_cli_voice.py`, `test_cli_errors.py`, plus the
CLI halves of `test_broadcast_ready.py`; `test_catalog.py` and
`test_ledger.py` grow, not shrink.

New/rewritten coverage, by area:

- **Selector layer:** each flag maps to the right `select_shows` call; enum
  rejects bad `--state` with the value list; `--held`/`--packaged` sugar ≡
  `--state`; repeatable `--state` ORs; positional-vs-selector exclusivity
  and the empty-selector error, identical across commands (parameterized
  over `redo`/`voice`/`deliver`/`rm`); held opt-in — batch drops held with
  the note, `--held`/`--state held` includes, single positional bypasses;
  plan/confirm/`--yes`; per-show failure isolation.
- **Sessions:** id uniquing (same query twice a day → `-2`; lowest free
  suffix); marker writes at gate-stop, plan-stop, completion (incl. empty
  winnow); `run list` shows awaiting/incomplete only, hides complete,
  markerless dir → incomplete; `run approve` persists approvals, processes
  on confirm, writes complete, prints `run resume <id>` (not a path) on
  decline; `run resume` resumes without `--stage`/`--force`; `run rm`
  deletes with confirm and leaves `shows/` intact; `status` attention header
  + `--json` `sessions` key; `--by-run` rollup matches today's `runs`
  content.
- **`get`:** query and profile modes hit `_execute` with the same
  stamped-criteria behavior as today's `find`/`profile run` (port existing
  tests); mutual-exclusion of query/`--profile`; profile-mode flag
  restriction; `--plan` stops after shortlist (no `process_show` call —
  assert via stub), parks awaiting-approval, prints the approve hint;
  library-dedup: a show on disk in each of {held, packaged, delivered,
  selected} states is excluded from the winnow pool, one gone from disk but
  `rejected`/`delivered` in ledger stays excluded, gone-from-both
  re-eligible (unit-test `library_performance_ids` + a winnow-level test
  with `library_ids` passed).
- **`show`:** read-only guarantee — a held show on a (pytest-faked) TTY
  never prompts; `--tracks`; `--json` schema; archive URL + considered block
  (with scores, sorted, chosen excluded; absent selection.json → omitted);
  pre-show.json show prints instead of erroring.
- **`triage`:** scripted stdin drives e/m/v/o/s/q; `[m]` round-trips
  venue/date/titles/breaks into `overrides.json` and redoes from gather
  (stubbed `process_show`); off-TTY errors; default-held selection; broader
  selector print-skips non-held; URL in header.
- **`fix`:** each flag writes the right override; renamed flags exist and
  old spellings do not; auto-redo fires with the right stage (stub asserts),
  earliest-stage precedence on combos; `--no-run` stages and prints;
  `--narration vague` and `--overrule` clear the hold, excludes don't;
  bare `fix` errors; input-validation errors (bad title spec, non-numeric
  breaks).
- **`redo`:** `--from` validation per addressing form (run-level stages only
  with `--run`); `--run` + run-level stage deletes the right artifacts and
  confirms approvals-wipe; `--run` + show-level stage ≡ selector batch;
  `--redo-research` drops research; replay overrides defer to provenance
  stamps (port existing tests).
- **`voice`:** desugars to `redo --from package` with the right voice want
  (on/off), single and selector forms; help text mentions the stamp rule
  (string assertion is fine).
- **`deliver`:** table-driven over `broadcast_readiness` reason sets:
  ready→delivers; held / missing-files / unpackaged → refused even with
  `--allow-unvoiced`; voice-bundle-only reasons → refused without,
  delivered with `--allow-unvoiced`; `--force`/`--deliver-held` do not
  exist; ledger `delivered` row written; batch gating per show.
- **`rm`:** deletes the dir; default leaves ledger rows untouched and echoes
  the state-appropriate message (held vs packaged/delivered); `--forget`
  purges all rows; `--suppress` appends the rejected row (and `unsuppress`
  reverses exactly it); `--forget`+`--suppress` mutually exclusive; confirm
  default + `--yes`; selector batch with held opt-in; pid-less dir: default
  ok, flags error.
- **`suppress`/`unsuppress`:** on-disk resolution; off-disk pid parsing
  (`collection/date[/eN]`); malformed off-disk id errors; append-once;
  `remove_status` removes only rejected rows (a `selected`+`rejected` pid
  keeps its `selected` row).
- **`history`:** collapse picks latest disposition per pid; `--log` full
  trail; `--json` both forms; `ledger add/remove` gone.
- **Hygiene:** `--config` accepted at the app level and honored;
  `version` command gone, `--version` works; panels advertise the four
  groups; `profile show/remove`, `presenter remove` (incl.
  referenced-by-profile refusal), enriched `profile list`; `profile add`
  leaves nothing under `runs/`; `pipeline` prints stage/state/gate keywords.

---

## 14. Resolved decisions (raised back to the owner, 2026-07-27)

The brief's "known open points" plus the ambiguities found while grounding
this spec were raised back and settled with the owner; the body already
reflects every one. For the record:

1. **`artists` stays** unchanged under Acquire (the brief's omission was
   accidental); `--all` → `--include-junk` (§3).
2. **`--held`/`--packaged` survive** as sugar over the `--state` enum (§2).
3. **No `run show` verb** (§4).
4. **`pipeline` and the hygiene bundle are IN scope now**; `pipeline` is the
   first cut if the plan runs long (§5.3, §12).
5. **`get --plan`:** full winnow spend, print shortlist, park
   awaiting-approval, exit with the `run approve` hint; no processing prompt
   (§3).
6. **Session ids:** `YYYY-MM-DD-<slug>` + `-2`/`-3` collision suffixes;
   attention rows = id / state / age / criteria (§4).
7. **Prompts:** `rm` confirms by default (`--yes` skips);
   `--allow-unvoiced` carries no extra prompt beyond the batch plan confirm
   (§7.3, §8.1).
8. **`runs/<id>/session.json` accepted** as legitimate *process/lifecycle*
   state — a session is a process object, not a derived view of content, so
   this does not erode derived-never-stored, which remains absolute for show
   state; the marker never lives under `shows/` (§4).
9. **`status --json` becomes an object** `{"sessions", "shows"}` /
   `{"sessions", "runs"}` — breaking is fine, owner updates their scripts
   (§5.1).
10. **Off-disk `suppress`** accepts a raw `collection/date[/eN]` id,
    deriving artist/date from it (§8.2).
11. **`get --profile`** accepts only `--auto`/`--plan`/`--full-rationale`
    (§3).
12. **`--name`** kept as an explicit session-id override on `get` (§3).
13. **`run resume` drops** the `--script`/`--voice` overrides (§4).
14. **`history add`/`remove` deleted** — `suppress`/`unsuppress`/
    `rm --forget` + the hand-editable JSONL cover the territory (§11).

Scope decomposition (§15) — one spec, two layer-split plans — is likewise
owner-accepted.

---

## 15. Scope decomposition

**One spec (this document), two implementation plans** (owner-accepted),
sequenced:

1. **Plan A — foundations beneath the surface** (no CLI changes; every task
   testable in isolation): `catalog.library_performance_ids` + the winnow
   `seen` change; `Ledger.remove_status`; the history-collapse helper;
   session id uniquing + `session.json` marker writes in `_execute` +
   session-state derivation; the shared selector layer (reconciliation +
   held opt-in as plain functions); the deliver gating classifier over
   `broadcast_readiness` reasons; `rm` disposition machinery; archive-URL/
   considered-recordings extraction from `selection.json`; the
   profile-scratch relocation.
2. **Plan B — the surface re-cut** (consumes Plan A; the big `cli.py` and
   CLI-test rewrite): the full command tree (§1), panels, callback `--config`,
   renames, `pipeline`, docs pass (`workflow.md` command reference, README,
   `CLAUDE.md` command list).

Rationale: a single plan would exceed comfortable review scope (~25+ tasks)
and force awkward mixed states inside `cli.py`; splitting *by layer* (not by
feature) keeps Plan A merge-safe on its own (nothing user-visible changes
except winnow dedup, which is independently desired) and makes Plan B a
mostly-mechanical consumption pass. The docs rewrite rides Plan B — the old
command reference must not survive the re-cut.
