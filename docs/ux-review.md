# llama CLI — UX review

Reviewed against `src/llama/cli.py` (1437 lines, 23 commands across the root app and 4 sub-apps),
`src/llama/status.py`, `CLAUDE.md`, `README.md`, `docs/workflow.md`, and `docs/station-brief.md`.
Backward compatibility explicitly out of scope.

---

## Executive summary

**Verdict: restructure, not redesign.** The underlying conceptual architecture — a staged
pipeline over plain files, derived (never stored) state, durable `overrides.json`, a dedup
ledger — is genuinely good and should not change. What has decayed is the *command surface
layered on top of it*: it exposes the implementation's history rather than the operator's
intents. Feature after feature (batch selectors, holds, voice, presenters, metadata
overrides, broadcast-ready) was bolted onto existing commands instead of prompting a
re-cut of the verbs, and the result is a CLI where the docs must spend whole sections
apologizing for the surface ("the single most confusing part of the system," a
troubleshooting row for a *note the tool prints about its own flag being a no-op*).

The five highest-leverage problems:

1. **`show` is three commands wearing one trench coat** (cli.py:694–833). One command with
   ~22 options does single-show inspection, batch set-walking, *and* override
   editing/hold resolution — with TTY-dependent modality (the same invocation prints on a
   pipe but drops into an interactive prompt on a terminal, cli.py:784–786). This is the
   command operators live in, and it's the least predictable one.
2. **Four commands re-implement the same 8-flag selector vocabulary with divergent
   semantics.** `status`, `show`, `redo`, `deliver` each declare
   `--held/--packaged/--voiced/--unvoiced/--state/--artist/--run/--broadcast-ready`
   (32 near-identical option declarations; cli.py:707–714, 905–913, 1010–1018, 1069–1077),
   but `--held` means "filter to held" on `status`, is the *implicit default* on `show`'s
   set form (cli.py:735–736), and means "opt in to touching held shows" on `redo`/`deliver`
   (cli.py:847–848). Same words, three meanings.
3. **The redo/replay story is split across three overlapping commands** — `run` (replay a
   run), `run --stage X --force` (force one stage run-wide), `redo --from X` (force one
   stage per show) — with *inconsistent flag names for the same concept* (`--stage` vs
   `--from`) and help text that mostly exists to warn you the flag you're reading won't do
   what you want (`run --voice`'s help is a four-line apology pointing at `redo`,
   cli.py:391–396; there's a troubleshooting-table row for the runtime note it prints,
   workflow.md:797).
4. **Naming collisions actively fight the mental model.** "show" is the concert entity, a
   command, and (via `--title`) the on-air radio program; "run" is a noun (`runs`,
   `--run`), a verb (`llama run`), and a profile action (`profile run`); `review` (the
   command) is *gate 1* and has nothing to do with `needs-review` (the state), which is
   handled by `show`; `--title` forces a track title on `show` but names the radio program
   on `profile add`; `--clear` on `show` overrules a hold while `--clear-title` clears an
   override; `--all` means "skip junk filter" on `artists` and "include delivered" on
   `status`; `--full` means "narration=full" while `--full-rationale` means "don't truncate."
5. **The default posture of the fix workflow is "print the command you should run next"
   instead of running it.** Override edits print `next: llama redo <s> --from gather`
   unless you remember `--apply` (cli.py:827–833). The tool *knows* the right next step —
   it computes the stage from the edit — yet makes copy-paste the default and demands the
   operator learn stage names that are otherwise internal.

None of this requires touching the pipeline. A restructure of the command layer —
splitting `show`, unifying selection, collapsing the redo family, and a rename pass —
would remove most of the documentation burden and roughly halve the concept count an
operator has to hold.

---

## The current model, as-is

### Command surface (23 commands, 4 panels)

| Panel | Command | Role | Notes |
|---|---|---|---|
| Discover & process | `find "query"` | full one-off pipeline | interactive by default |
| Discover & process | `artists ["query"]` | explore/preview artist index | read-only-ish |
| Discover & process | `run <run>` | resume/replay a run | auto by default; `--stage X --force` |
| Discover & process | `review <run>` | gate-1 shortlist approval | offers inline processing |
| Discover & process | `profile add/run/artists/list` | standing profiles | no `show`/`remove` |
| Discover & process | `presenter add/list/show` | on-air hosts | no `remove`/`edit` |
| Inspect & triage | `status [selectors]` | global triage table | + `--all`, `--json` |
| Inspect & triage | `runs` | list runs | no verbs on runs |
| Inspect & triage | `show [<show>] [selectors] [~15 edit flags]` | inspect + walk + edit + resolve | TTY-modal |
| Act on shows | `redo <show>|selectors --from STAGE` | re-run pipeline tail | `--with-research`, voice toggles |
| Act on shows | `deliver <show>|selectors` | ship package | `--force` bypasses hold |
| Housekeeping | `ledger list/add/remove` | dedup history | manual field entry |
| Housekeeping | `config init` | seed config | |
| Housekeeping | `version` (+ `--version`) | duplicated | cli.py:69–95 |

### Concepts an operator must hold to use this surface

1. **Runs vs shows** — two entity types, different commands accept each; shows are shared
   across runs; a show's `provenance.json` lets it detach from its run.
2. **Two modes** — one-off (`find`) vs standing profiles (`profile add/run`), converging
   on the same run machinery.
3. **Nine stage names** (`search winnow select gather research vet synthesize package` +
   interpret), needed as arguments to `redo --from` / `run --stage`, plus which stage
   fixes which problem.
4. **Two human gates** — gate 1 (shortlist approval, `review`) vs gate 2 (needs-review
   hold, `show`) — the docs' own "don't confuse them" table (workflow.md:180–192).
5. **Eight derived states** (`held packaged scripted vetted researched gathered selected
   delivered`) plus orthogonal derived properties (`voiced`, `broadcast-ready`).
6. **overrides.json semantics** — which field is read by which stage, what self-clears,
   what survives redo.
7. **The selector vocabulary** and its per-command meaning shifts.
8. **Voice resolution rules** — house voice vs presenter vs clone vs stamped-at-process
   replay; which edits are "live" vs need a fresh run (workflow.md:358–373 exists solely
   to explain this).
9. **Ledger identity** — performance identity vs archive item id.

That is a *large* model, and the CLI teaches almost none of it: there is no command that
shows the pipeline, the states, or the gates. The docs carry it all.

---

## Findings

### A. Conceptual model

**A1. Runs are over-exposed for what they now are.**
The system's own docs say "day to day, the workspace is show-centric" (workflow.md:40–43).
Shows carry provenance and can be redone standalone; runs matter only (a) while a
pipeline is mid-flight/crashed, and (b) as a gate-1 approval container. Yet runs claim
three top-level commands (`run`, `runs`, `review`) and a selector (`--run`), and the
operator must constantly decide whether a name they type is a run or a show. `runs` has
no verbs at all — you can list runs but not delete, rename, or inspect one (`llama runs`
is the only view; there is no `llama run show <name>` equivalent; inspection means
reading files). **Proposal:** demote runs to a namespace (`llama run list/show/resume/rm`)
and make shows the only entities at the top level. (See altitude C.)

**A2. The one-off vs profile split creates parallel, subtly different paths.**
`find` and `profile run` both end in `_execute` but differ in interactivity defaults
(`find` interactive, `profile run` interactive, `run` auto — cli.py:291, 387, 1254),
human-gate handling, and which flags exist (`find` has `--voice`, `profile run` doesn't —
voice comes only from the presenter/config there). A user who starts with `find` and
graduates to profiles must relearn the knobs. Also, `profile add` interprets the query at
save time via a scratch workspace named `profile-setup-<name>` (cli.py:1228) that lands
in the runs directory and then shows up forever in `llama runs` — an implementation
artifact leaking into a listing.

**A3. Gate 1 and gate 2 are named to be confused.**
The command for gate 1 is `review`; the state for gate 2 is `needs-review`; the command
for gate 2 is `show`. workflow.md:182 calls this "the single most confusing part of the
system" — that's a naming bug, not a documentation problem. **Proposal:** gate 1 becomes
`llama approve <run>` (it approves ranks; "review" oversells it), gate 2's walkthrough
becomes `llama triage` (see B2), and the state keeps "held" as its primary name (the code
already calls it `held` everywhere — `needs-review` vs `held` is itself a duplicated
concept name; pick `held`).

**A4. Stage names are internal model leaking through the front door.**
`redo --from STAGE` requires the operator to know that excludes/metadata → `gather`,
narration → `synthesize`, overrule → `package`, re-research → `research`, new recording →
`select`. The tool itself encodes this mapping (cli.py:827: `stage = "gather" if ... else
"synthesize" ... else "package"`), then prints it for the human to type back in. Stage
selection should be an *advanced* escape hatch, not the primary interface for "I fixed
the data, make it take effect." Also the CLI stage is `select` while docs say
`select-recording` (cli.py:37 vs CLAUDE.md) — pick one string.

### B. Command surface

**B1. `show` does three jobs (cli.py:694–833).**
Jobs: (1) inspect one show (`show <name>`, `--tracks`); (2) walk a set of shows
(`show --held`, selectors); (3) edit overrides / resolve holds (`--exclude`, `--vague`,
`--clear`, `--set-*`, `--title`, `--apply`). Twenty-two options, of which any given
invocation can meaningfully use maybe four. Worse, which job you get depends on argument
presence *and* flag presence *and* whether stdin is a TTY:

- `llama show gd73` on a held show, on a TTY → interactive resolution prompt.
- `llama show gd73 | cat` → printed report.
- `llama show gd73 --tracks` → printed report (special-cased to defeat the prompt,
  cli.py:784–787 — the comment block explaining this is longer than the logic).
- `llama show` (no args) → walks *held* shows (implicit default, cli.py:735–736).
- `llama show --voiced` → walks voiced shows but never prompts (non-held entries are
  print-only, cli.py:744–748).

That's five behaviors for one verb. TTY-modality is fine for *confirmation prompts*; it
is not fine for *which job the command performs*. **Proposal:** split into
`show` (inspect, always), `triage` (interactive walkthrough, always), and `fix`
(override edits, always applies) — details in altitude B below.

**B2. The interactive walkthrough is good — and buried.**
`_interactive_resolve`'s `[e]xclude / [v]ague / [c]lear / [s]kip / [q]uit` loop
(cli.py:596–625) is the best UX in the product: it shows the evidence, offers exactly the
three resolutions, and runs the right redo on the spot. But it's reachable only as a side
effect of `show` with no flags, and its prompt doesn't offer the metadata corrections
(`--set-venue`/`--set-date`/`--title`/`--set-breaks`) that are the fourth real resolution
per the docs (workflow.md:231–238) — from the walkthrough you can't fix a wrong venue,
you must quit and reconstruct a flag invocation. Give it a name (`llama triage`), and add
`[m]etadata` to the prompt.

**B3. Selector duplication: 32 option declarations, 3 semantic variants.**
`status` (cli.py:1069–1077), `show` set form (707–714), `redo` (1010–1018), `deliver`
(905–913) each re-declare the same eight selectors, backed by *two* different helper
paths (`_batch_select` for redo/deliver vs inline `select_shows` calls in show/status)
with different held-show handling. Consequences:

- Help text drifts: `--held` is "Only shows held for review" (status), "Set form: only
  held shows" (show), "Selector: include held shows" (redo/deliver) — the third is a
  *different semantic* (opt-in to acting on holds, cli.py:847–848) disguised as the same
  flag.
- `--state` duplicates `--held`/`--packaged` (they just add to the same `states` set,
  cli.py:732–734, 1089–1095) — two spellings for two of the eight states, a flagless
  spelling for the other six. Why do held and packaged get flags and `vetted` doesn't?
  (Answer: history.)
- "give a show OR selectors, not both" (cli.py:918–921, 1027–1030) is an error the user
  must learn per command.

**Proposal:** one selector implementation, one help string, one semantics — and make
"acting on held shows requires explicit `--held`" a documented property of *acting*
commands rather than a flag meaning shift. Better still, collapse `--held/--packaged/--state X`
into one `--state held|packaged|...` (repeatable), keeping `--held`/`--packaged` as the
two blessed shorthands if desired.

**B4. The redo family: three commands, two flag spellings, one job.**
"Re-run part of the pipeline" is spelled:
- `redo <show> --from package` (per show, implicit force),
- `run <run> --stage package --force` (per run, explicit force, *different flag name*),
- `run <run> --force` (everything, with an approvals-wipe confirmation, cli.py:414–419).

The equivalence `run --stage package --force --voice` ≡ `redo --from package --voice`
for each show is documented in *four* places (run's help text, redo's docs, README:327,
workflow.md:797). When you need a troubleshooting-table row for a note your own flag
prints, the flag is wrong. **Proposal:** `run` keeps only resume semantics (no `--stage`);
run-level re-execution moves to `redo` growing `--run <run>` scope with `--from search|winnow`
allowed there — or simpler: `redo <run-or-show> --from STAGE` resolves either entity and
validates stage scope. One verb, one flag name (`--from`).

**B5. Missing commands (the surface is wide yet has holes).**
- `profile show <name>` and `profile remove <name>` don't exist (`profile list` prints
  bare names only, cli.py:1309–1314 — no query, no count, no presenter). To inspect a
  profile you read TOML; to edit anything but the roster you hand-edit TOML — yet
  `profile artists` exists as a bespoke single-field editor (cli.py:1283–1306), an odd
  asymmetry. Either commit to "profiles are app-managed" (`profile show/set/remove`) or
  drop `profile artists`.
- `presenter remove` doesn't exist.
- No way to delete a show or a run from the CLI (project memory shows the owner doing
  "full show purge" by hand).
- `--json` exists only on `status` (cli.py:1079); `show`, `runs`, `ledger list` have no
  machine-readable form.
- No read-only preview of what `find` would do. `find` immediately spends LLM calls
  (interpret → winnow scoring) before its first prompt; `artists` previews the artist
  match only. A `find --dry-run`/`plan` that stops after the shortlist would make the
  spend legible.

**B6. `ledger add/remove` is a pre-app-managed vestige.**
`ledger add <performance-id> --artist A --date D --status rejected` (cli.py:1391–1403)
asks the operator to hand-assemble internal identity fields and know the status
vocabulary, for what is really one intent: "never offer me this show again." The docs'
recipe (workflow.md:775–777) confirms this is its only real use. **Proposal:**
`llama suppress <show-or-performance>` / `llama unsuppress <...>`, with `ledger list`
retained as the audit view (`history` would be a better name than `ledger`).

**B7. `version` is both a command and a flag** (cli.py:69–95). Keep the flag, drop the
command (or vice versa); having both in the Housekeeping panel is noise.

### C. Flag design

**C1. Same flag, different meaning.**
- `--title`: on `show`, forces a *track title* (`--title 4="Dark Star"`, cli.py:720); on
  `profile add`, the *radio program's on-air name* (cli.py:1202). These will collide in
  every operator's muscle memory. Rename show's to `--set-title N="..."` (matching its
  `--set-*` siblings — it's the only override setter missing the prefix) and profile's
  to `--show-title` or `--program`.
- `--all`: skip junk filter (`artists`, cli.py:357) vs include delivered (`status`,
  cli.py:1078).
- `--force`: re-run stages (`run`), bypass a hold at delivery (`deliver`), overwrite a
  file (`presenter add`). Three risk profiles under one name; `deliver --force`
  especially deserves a scarier, specific name (`--deliver-held`?) since it's the one
  that puts un-vetted content on air.
- `--run` (selector) vs `run` (command) vs `runs` (command) vs `--run-name` (`find`).

**C2. Inconsistent boolean styles.**
`--script/--no-script` and `--voice/--no-voice` are proper Typer pairs; `--voiced` and
`--unvoiced` are two independent flags that the code manually reconciles
(`True if voiced else (False if unvoiced else None)`, cli.py:737, 843, 1096 — three
copies); `--vague`/`--full` is a pair that doesn't look like one, and `--full` invites
confusion with `--full-rationale` (declared four times: cli.py:310, 397, 452, 1255).
`--auto/--interactive` exists on `run` but `find`/`profile run` have bare `--auto`.

**C3. Inverted or mislabeled flags.**
- `--include` (cli.py:699) undoes `--exclude` — but "include" reads as a filter, not an
  undo. `--unexclude` or `--restore` is honest.
- `--with-research` on `redo` (cli.py:1003–1004) *sounds* additive but means "also
  **delete** research.md." `--redo-research` or `--drop-research` says what it does.
- `--clear` (overrule the hold) vs `--clear-title`/`--clear-set-breaks` (drop an
  override): same prefix, unrelated operations, on the same command. The overrule verb
  deserves its own word: `--overrule` (the docs already call it that, README:219).
- `--vague`/`--full` set `overrides.narration` but nothing in the flag names says
  narration: `--narration vague|full` is one flag, self-describing, and stops squatting
  on the word "full."

**C4. `--apply` inverts the expected default.**
An edit command that by default *doesn't* trigger the consequence — it prints a command
to copy-paste (cli.py:828–833) — is the CLI equivalent of a Save button that prints
"click File→Save to save." The conservative default made sense when the redo was
expensive-by-surprise; the right shape is: apply by default, offer `--no-run` (or
`--print-only`) for staging multiple edits. At minimum flip it for the interactive
walkthrough context where it already auto-applies (cli.py:622–625) — the inconsistency
(walkthrough applies; flags print) is itself a finding.

**C5. `--config` is declared on all 23 commands** instead of once on the app callback
(cli.py:77–87). Pure noise in every `--help` screen; move it up (Typer supports callback
options fine, as `--version` shows).

**C6. `--state` takes a bare string with no enumeration** (cli.py:711, 909, 1014, 1073).
The eight legal values appear nowhere in help; a typo returns "no matching shows" rather
than an error. Use an Enum so Typer validates and documents it.

### D. Naming

**D1. "show" triple-duty.** The concert entity ("show"), the command (`llama show` — which
also collides with the generic CLI convention where `X show` means "display X",
cf. `presenter show`), and the radio program (`--title`, "the radio show's on-air name",
cli.py:1203). You cannot fix all three, but you can stop the *command* from also being
the editor and the walker (B1), which is where the ambiguity does damage. If bolder:
rename the entity's inspect command to `llama inspect <show>` or keep `show` strictly
read-only so "show shows a show" at least stays true.

**D2. `find` undersells its cost.** "Find" implies read-only search; `llama find` runs
the *entire* pipeline including paid LLM calls, downloads, packaging (cli.py:315:
"One-off: find, vet, research, and package"). A new operator will type `llama find
"grateful dead 1977"` to *look around* and start a spend. Either rename (`llama get`,
`llama pull`, or the honest `llama process "query"`) or make `find` stop at the
shortlist by default with processing as the confirm step (which is nearly what
interactive mode does — but `--auto` flips it into full spend).

**D3. `redo` vs `run` vs `runs` vs `review`.** Four r-words doing adjacent things is a
recall tax. In the restructured surface (altitude B): `resume` (run continuation),
`redo` (stage re-execution), `approve` (gate 1), `run list` (listing) leaves each word
unique.

### E. Workflow / task flow

**E1. The happy path is fine; the fix loop is where friction lives.** Walking the core
journey: `find` → prune artists prompt → shortlist prompt → process → `status` →
`show --held` walkthrough → `deliver --packaged`. That works, and status's
held-first sort + inline flags (cli.py:1101, 1137–1139) is good triage design. The
friction concentrates in: (a) resolving holds that need metadata fixes (must leave the
walkthrough, B2); (b) anything voice-related (E2); (c) knowing whether to type a run
name or show name (A1).

**E2. Voice operations need a verb.** "Voice everything that's silent" is
`llama redo --unvoiced --from package --voice --yes` — four flags reconstructing one
intent. Re-voicing one show is `redo <s> --from package --voice`; switching a preset
voice requires knowing the stamped-voice replay rule (workflow.md:358–373, ~15 lines of
doc for one gotcha: clone edits are live, preset edits are not). **Proposal:** a
`llama voice <show|selector> [--off]` command that owns these semantics, explains
stamped-voice resolution in *its* help, and leaves `redo` as the general machinery.

**E3. Two-step approve-then-resume has a seam.** `review` approves then asks "Process
approved shows now?"; declining prints `next: llama run <ws.dir>` (cli.py:486) — note it
prints the *directory path*, while everywhere else teaches names/substrings. Minor, but
the seam between `review` and `run` is exactly where a `--human-gate` profile user lands
every time.

**E4. `status` vs `runs` vs `show` set form are three read-only views with no shared
shape.** `status` is per-show rows; `runs` per-run rows; `show --voiced` (off-TTY)
prints full multi-line blocks per show. An operator asking "what's going on?" has to
pick a view by knowing implementation boundaries. Fold `runs` into `status --by-run` or
`run list`, and drop `show`'s set-form-as-printer entirely (that's `status`'s job).

### F. Discoverability & help

**F1. The CLI never teaches its own model.** No command names the stages, the states, or
the gates; `redo --from`'s help enumerates stages (cli.py:1002) but nothing says what
each does. A `llama pipeline` (or `llama stages`) printing the workflow.md diagram +
stage table, and states enumerated in `--state`'s help (C6), would let the CLI stand
without the docs. The docs are excellent, but "read workflow.md" is the current
onboarding.

**F2. Panels are close but misassigned.** `presenter` (persona/voice configuration) sits
in "Discover & process" (cli.py:64–66) where it's noise next to `find`/`run`; it belongs
in a "Configure" panel with `config` and `profile`-management verbs. `show` (the most
action-heavy command) sits in "Inspect & triage" while its `--exclude/--apply` half is
squarely "Act on shows."

**F3. Help text is doing structural repair work.** The longest help strings in the file
are warnings about the surface itself: `run --voice` (cli.py:391–396, points to two other
commands), `show`'s in-code comments about prompt pre-emption (cli.py:780–787). When
flags need paragraph-length disclaimers, the fix is structural, not editorial.

---

## Proposals at three altitudes

### Altitude A — small tweaks (safe, high yield, no model change)

1. **Rename pass:**
   - `review` → `approve` (keep `review` as hidden alias for a release).
   - `show --clear` → `--overrule`; `--include` → `--unexclude`; `--with-research` →
     `--redo-research`; `--vague/--full` → `--narration vague|full`;
     `--title N=` → `--set-title N=`; `profile add --title` → `--show-title`.
   - `run --stage` → `run --from` (align with `redo`) as a stepping stone to B3.
   - `artists --all` → `--include-junk`; keep `status --all`.
2. **Move `--config` to the app callback**; delete the `version` command (keep `--version`).
3. **Make `--state` an Enum** (all eight states, validated, listed in help) everywhere.
4. **`--apply` becomes default; add `--no-run`** on override edits (or at minimum print
   the next-command hint *and* offer a y/N "run it now?" on a TTY).
5. **Add `[m]etadata` to the triage prompt** (walkthrough can fix venue/date/titles/breaks).
6. **Add `profile show`, `profile remove`, `presenter remove`;** enrich `profile list`
   (query, count, presenter columns). Exclude/hide `profile-setup-*` scratch dirs from
   `llama runs` (or stop creating them under `runs/`).
7. **`--json` on `show <name>` and `runs`.**
8. Unify the three copies of voiced-flag reconciliation and the two selector code paths
   behind one helper with one help string (pure refactor, prevents future drift).

Before → after:

```
llama show gd73 --title 4="Dark Star" --set-breaks "9,17" --apply
llama show gd73 --set-title 4="Dark Star" --set-breaks "9,17"     # applies by default

llama show gd73 --clear && llama redo gd73 --from package
llama show gd73 --overrule                                        # runs the redo itself
```

### Altitude B — medium restructure (split `show`, unify selection, collapse redo)

**B-1. Split `show` into three honest commands:**

```
llama show <show> [--tracks] [--json]     # inspect only; never prompts, never edits
llama triage [SELECTOR]                   # the walkthrough (default: held); TTY prompts,
                                          #   [e]xclude [m]etadata [v]ague [o]verrule [s]kip [q]uit
llama fix <show> [--exclude N,..] [--unexclude ..] [--set-venue ..] [--set-city ..]
                 [--set-date ..] [--set-title N=".."] [--set-breaks "9,17"]
                 [--narration vague|full] [--overrule] [--no-run]
                                          # edits overrides / resolves holds; applies the
                                          #   correct redo automatically (that's the point)
```

`fix` owns the stage-precedence logic internally; `--from` never appears. `redo` remains
for deliberate re-execution (new recording, re-research, re-voice).

**B-2. One selector grammar, one semantics.** All batch-capable commands (`status`,
`triage`, `redo`, `deliver`, future `voice`) accept the identical selector set with the
identical meanings; the "held shows require explicit `--held` to be *acted* on" rule is
enforced (and error-messaged) uniformly by the shared layer, not encoded as a flag
meaning shift. Collapse `--held`/`--packaged` into `--state` (repeatable) with those two
kept as shorthands.

**B-3. Collapse the redo family.** `run <run>` = resume only (no `--stage`, no `--force`
beyond the approvals-wipe path, which moves to `redo --run <run> --from winnow`).
`redo` gains `--run <run>` scope and accepts `search|winnow` only in run scope. One
verb for re-execution, one flag (`--from`), everywhere.

**B-4. `llama voice <show|SELECTOR> [--off] [--fresh]`** — sugar over
`redo --from package --voice/--no-voice`, whose help text owns the stamped-voice rules.
`llama voice --unvoiced --yes` replaces today's four-flag incantation.

**B-5. `llama suppress <show>` / `unsuppress`;** `ledger` shrinks to `ledger list`
(or renames to `history`).

Before → after:

```
llama redo --unvoiced --from package --voice --yes
llama voice --unvoiced --yes

llama run countryish --stage package --force --voice
llama redo --run countryish --from package --voice

llama show --held                     # (TTY walkthrough)
llama triage                          # same, but findable and predictable

llama ledger add GratefulDead/1980-05-16 --artist "Grateful Dead" --date 1980-05-16 --status rejected
llama suppress gd80-05-16
```

### Altitude C — bolder redesign (optional): show-centric tree, runs demoted

Keep the pipeline and files exactly as-is; re-cut the surface around the four operator
intents — **get shows, watch state, fix holds, ship** — with runs and configuration as
namespaces:

```
llama get "query" [--auto|--plan] [--limit N] [--voice] ...   # today's find; --plan stops
                                                              #   at the shortlist (no spend past winnow)
llama get --profile sunday-dead-hour                          # today's profile run
llama approve <run>                                           # gate 1
llama resume <run>                                            # today's run (resume only)

llama status [SELECTOR] [--by-run] [--json]                   # absorbs `runs`
llama show <show> [--tracks] [--json]                         # inspect (read-only)
llama triage [SELECTOR]                                       # gate-2 walkthrough
llama fix <show> <edit-flags> [--no-run]                      # overrides + resolutions
llama redo <show|--run RUN|SELECTOR> --from STAGE             # deliberate re-execution
llama voice <show|SELECTOR> [--off]                           # TTS sugar
llama deliver <show|SELECTOR> [--dest] [--deliver-held]
llama suppress / unsuppress <show>

llama profile  add|list|show|set|remove|artists <name>
llama presenter add|list|show|remove <id>
llama run      list|show|remove <run>                          # runs as a namespace
llama history  list                                            # the ledger, renamed
llama config   init|show
llama pipeline                                                 # prints stages/states/gates
```

Notable choices: `get` replaces `find` (honest about spend; `--plan` gives the missing
cheap preview); one-off vs profile collapse into one verb (`get "query"` vs
`get --profile X` — the two modes stop being two command families); `runs`' listing moves
under `run list`; every read-only command is guaranteed side-effect-free. The whole tree
is 14 top-level words, each mapping to exactly one intent, and the "don't confuse the
gates" section of the docs can be deleted.

---

## Prioritized recommendation

1. **First (biggest pain, no model risk): split `show` → `show`/`triage`/`fix`** (B-1)
   with apply-by-default and metadata in the walkthrough. This is where operators spend
   their interactive time and where the TTY-modality surprises live.
2. **Second: unify selectors** (B-2) — one implementation, one semantics, Enum'd
   `--state`. Do it while touching the commands from step 1.
3. **Third: collapse the redo family** (B-3) and add `voice` (B-4). Deletes the worst
   help-text apologies and a troubleshooting row.
4. **Fourth: the rename pass** (Altitude A #1) riding on the above — `approve`,
   `--overrule`, `--narration`, `--set-title`, `suppress`.
5. **Fifth: hygiene** — `--config` to callback, drop `version` command, `profile
   show/remove`, `presenter remove`, scratch-run leak, `--json` coverage, `llama
   pipeline` teaching command.
6. **Optional, later: Altitude C's `get`/`--plan` and run-namespace demotion** — worth it
   if new operators are expected; skippable for a single-operator tool whose owner has
   already internalized today's model.

Steps 1–4 are one coherent release ("the CLI re-cut"), all surface-level, fully covered
by existing pipeline tests plus new CLI tests, and they eliminate the majority of the
documentation currently spent explaining the interface to itself.
