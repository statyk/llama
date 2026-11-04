# Programs and the weekly lineup: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Name each show's program on every ticket, group Coming up under its clock blocks with their real spans, and add a standing weekly lineup to the player page. emcee records the program title in the manifest, and a new station lock keeps emcee and llama from writing station manifests at the same time.

**Architecture:** emcee writes `dj_audio.title` when it voices a show, and a new `emcee retitle` command stamps the shows already voiced. The transmitter reads the title from each manifest at publish time and adds it, plus each show's block occurrence and that occurrence's span, to `timeline.json` and `notes/<slug>.json`. It also publishes a lineup object, the clock's nominal occurrences, which the page renders as a seven-day picker. A lock file in the delivered folder (exclusive create, a random token, holder text) is taken per package by emcee and per show by llama. emcee and llama each implement it separately against one on-disk contract.

**Tech Stack:** Python 3.12 (emcee, llama), Python 3.11-compatible transmitter, pytest, plain ES modules with Vitest and Playwright in `antenna/`, Typer CLIs.

**Spec:** `docs/superpowers/specs/2026-11-04-programs-and-lineup-design.md` (approved). Model plan for the house style: `docs/superpowers/plans/2026-11-01-player.md`.

## Global Constraints

- `emcee`, `transmitter` and `llama` never import each other. The new `dj_audio.title` field and the station lock file are part of the on-disk contract. Only `scripts/` may import both emcee and llama.
- transmitter stays Python 3.11-compatible (hugo: Debian 12). Gate: `packages/transmitter/scripts/test-in-debian12.sh` when Docker runs. If it doesn't, say so in the report.
- `timeline.json` keeps every existing field and its meaning; additions only. A show's notes and page go up before any timeline that lists it.
- The title is read from the manifest at publish time, never from cached `ShowAnalysis.meta`.
- Page text reaches the DOM through `textContent` only, and the server escapes it in `show.html`. Nothing parses markup.
- `antenna/public/player.js`, `nowplaying.js` and `style.css` stay byte-for-byte unchanged. `antenna/src/` changes only through `npm run pages`. No new client-side settings. Keep the existing look (`assets/radio.css`).
- Exact copy: `LMA RADIO PRESENTS` (the fallback when there is no title); section heading `The weekly lineup`; block span `7:00a – 9:56a` (an en dash with a space either side; the start alone when the end is unknown). The first lineup tab is labelled `Today`, the rest by short weekday (`Thu`).
- A block's displayed title is its clock `title`, else its `name`, everywhere, including a block no longer in the clock. A block is a **variety** block when it lists no profiles or more than one.
- Occurrence identity is the pair (`block`, `nominal_start`), with `nominal_start` formatted by `grid.us_to_iso` (as in plan rows) on every side.
- Station manifest writes are raw-dict read-modify-writes. They preserve every key they don't own (including `awaiting_fix`) and refuse rather than reformat. The encoding is `json.dumps(m, indent=2) + "\n"`, with `ensure_ascii` left at its default.
- hugo's `quiet_minutes` is 10. A rewritten manifest must keep its original mtime. The writer and the go-live probe use one order: write the temp file, flush, fsync, close, then `os.utime`, then rename, then re-check the mtime and re-apply it if it differs.
- **Lock contract** (both tools): the file is `<delivered folder>/.lma-station.lock`, where the delivered folder is the package directory's absolute parent (`Path(".").parent` is `.`). Contents are UTF-8: line 1 is `lma-station-lock 1 <32 lowercase hex token>`, then `tool: <emcee|llama>`, `command: <text>`, `host: <hostname>`, `pid: <n>` and `started: <ISO-8601 local time with offset>`, each on its own line, with a trailing newline. It is created with `O_CREAT|O_EXCL|O_WRONLY`, mode 0644, written, then fsynced. Empty or unparseable contents count as held. A tool releases only on its own token. A lock is never broken automatically and never expires. No tool parses the holder text.
- No tool holds the station lock while waiting on an operator prompt. Only command entry points (and `bulk_apply`'s per-show step) acquire it. It is not re-entrant: a second acquire in one process raises `StationLockReentry`, a bug.
- Every station write keeps the operator gate. An agent runs the dry run, shows it, and passes `--yes` only after Shawn approves, in a separate tool call.
- Worktree: `<repo>/.claude/worktrees/programs`, branch `programs-lineup`, with its own `.venv`. Python tests run as `./.venv/bin/pytest` there, never a bare `pytest`. Antenna: `cd antenna && npm test` (plus `npm run smoke` for page tasks). Every task leaves every suite green. Every commit ends with the session's attribution lines.

## Review Focus

1. **A program or block title with markup, an ampersand or great length** (`Gravel & Steel`, `<b>Late</b> "Night"`, a 60-character title): it shows as literal text on the ticket, the panel and `show/<slug>.html`, and wraps at 320 px with no sideways scroll. Pinned in Task 1 (`test_show_page_escapes_program_title`) and Task 4 (the hostile and 320 px smoke scenarios).
2. **A listener in another zone, and the lineup on a daylight-saving day:** a block near midnight moves to the neighbouring tab for a listener west of the clock's zone, no tab is skipped or repeated on the spring-forward or fall-back day, and no block appears twice. Pinned in Task 3 (`lineupDays` DST and zone tests).
3. **A lock left by a killed process (SIGKILL, power loss):** every writer refuses and names the holder plus `emcee lock show` and `emcee lock clear`. Nothing breaks the lock until the operator runs `emcee lock clear` and confirms. Pinned in Task 5 (`test_lock_clear_*`) and Task 10 (`test_refusal_names_holder_and_emcee_commands`).
4. **A voiced manifest not in emcee's exact encoding** (non-ASCII written with `ensure_ascii=False`, no trailing newline, duplicate keys, a float written as `1.50`, `dj_audio` not an object): the backfill refuses it, lists it, and leaves the file byte-identical, mtime included. Pinned in Task 8 (`test_plan_refuses_foreign_encodings`).
5. **The page against an old or partial transmitter** (no `program`, no `blocks`, a 404 or malformed lineup object): tickets read `LMA RADIO PRESENTS`, Coming up is flat with no headings, the lineup section is hidden, and the console is clean. The reverse mix matters too during rollout: new assets with the old `index.html` still play and show tickets. Pinned in Task 3 (helpers on missing data) and Task 4 (smoke, including `new assets with the old index.html`).

## Setup (before Task 1)

- [ ] `git worktree add .claude/worktrees/programs -b programs-lineup` from `main`. In it: `python3 -m venv .venv && ./.venv/bin/pip install -e packages/herder -e "packages/llama[dev]" -e packages/emcee -e "packages/transmitter[dev]"`, then `cd antenna && npm ci`.
- [ ] Check: `./.venv/bin/python -c "import emcee, llama, transmitter; print(emcee.__file__, llama.__file__, transmitter.__file__)"` prints three paths inside the worktree. `./.venv/bin/pytest -q` and `cd antenna && npm test` are green. Record the baseline counts.

## File structure

```
packages/transmitter/src/transmitter/site.py        program_title, block_title, occurrence_spans, build_lineup; timeline/notes additions; $presents
packages/transmitter/src/transmitter/publish.py     clock load, program per show, lineup object (LINEUP_KEY), digest in state
packages/transmitter/src/transmitter/state.py       PublishState.lineup
antenna/templates/show.html                         $presents
antenna/public/assets/programs.js                   NEW: presentsLine, occurrenceKey, comingUpGroups, blockSpan, localDateKey, lineupDays, onAirKey
antenna/public/assets/notes.js                      panelModel.presents (imports presentsLine from programs.js)
antenna/public/assets/page.js, panel.js, radio.css  tickets, block headings, lineup section
antenna/public/index.html                           lineup section (then npm run pages)
packages/emcee/src/emcee/station_lock.py            NEW: the lock (emcee side)
packages/emcee/src/emcee/procs.py                   NEW: other emcee/llama processes (ps; campaign_gate's matching rules, ported)
packages/emcee/src/emcee/retitle.py                 NEW: plan + raw single-field writer for the title backfill
packages/emcee/src/emcee/models.py, process.py      DJAudioBlock.title, recorded on voicing
packages/emcee/src/emcee/cli.py                     run/voice take the lock; `emcee lock show|clear`; `emcee retitle`
packages/llama/src/llama/station_lock.py            NEW: the lock (llama side)
packages/llama/src/llama/models.py                  DJAudio.title
packages/llama/src/llama/cli.py                     deliver (creates the target dir first) and clear-mark take the lock; batch stop
packages/llama/src/llama/station_mark.py            docstring (emcee now locks)
scripts/bulk_apply.py                               mark / unmark take the lock; stop on held
scripts/station_probe.py                            NEW: stdlib-only, 3.11-compatible go-live probes (race, mtime, cross)
scripts/test_station_lock_contract.py               NEW: emcee <-> llama lock interop
scripts/test_dj_audio_handshake.py                  NEW: emcee DJAudioBlock -> llama DJAudio (scripts may import both)
CLAUDE.md, packages/*/CLAUDE.md, antenna/CLAUDE.md, scripts/CLAUDE.md   doc updates, each in its task
```

---

### Task 1: transmitter site data: program, block occurrences, lineup, show page

**Model hint:** sonnet.

**Files:**
- Modify: `packages/transmitter/src/transmitter/site.py`, `antenna/templates/show.html`, `packages/transmitter/src/transmitter/publish.py` (one temporary argument, Step 4)
- Test: `packages/transmitter/tests_transmitter/test_site.py`

**Interfaces:**
- Consumes: `clock.ClockConfig`, `clock.occurrences(clock, from_us, until_us) -> list[Occurrence]` (`.block`, `.nominal_us`, `.nominal_iso`, `.end_us`), `layout.PlanRow` (`.block`, `.nominal_start`, `.kind`), `grid.us_to_iso`.
- Produces:
  - `program_title(manifest: dict | None) -> str | None`: `manifest["dj_audio"]["title"]` stripped, when `dj_audio` is a dict and the title is a non-blank string; else None. Never raises.
  - `block_title(clock: ClockConfig, name: str) -> str`: the named block's `title`, else `name` (also for a name not in the clock).
  - `occurrence_spans(rows: Sequence[PlanRow], epoch: Epoch) -> dict[tuple[str, str], tuple[int, int | None]]`: (block, nominal_start) -> (start_us, end_us or None).
  - `build_timeline(..., clock: ClockConfig)`: a new required keyword. Each show gains `"block"`, `"nominal_start"` (null for pre-scheduler rows) and `"program": None` (publish fills it in, Task 2). The document gains `"blocks": [{"block", "nominal_start", "title", "start", "end"?}]`.
  - `build_notes(...)` gains `"program": program_title(manifest)`.
  - `build_lineup(clock: ClockConfig, now_us: int) -> dict`: `{"occurrences": [{"block", "nominal_start", "end", "title", "variety"}]}`, with no timestamp of its own, so equal content gives equal bytes.
  - `render_show_page` fills `$presents`.

- [ ] **Step 1: Write the failing tests** in `test_site.py`:

```python
def test_program_title_reads_dj_audio_title_only():
    assert site.program_title({"dj_audio": {"title": " Gravel & Steel "}}) == "Gravel & Steel"
    for m in (None, {}, {"dj_audio": None}, {"dj_audio": []}, {"dj_audio": {}},
              {"dj_audio": {"title": None}}, {"dj_audio": {"title": "  "}}, {"dj_audio": {"title": 7}}):
        assert site.program_title(m) is None

def test_block_title_falls_back_to_name_and_to_unknown_blocks():
    # clock with block "bluegrass" title "Bluegrass in the Morning" and block "dead" (no title)
    assert site.block_title(CLOCK, "bluegrass") == "Bluegrass in the Morning"
    assert site.block_title(CLOCK, "dead") == "dead"
    assert site.block_title(CLOCK, "renamed-away") == "renamed-away"

def test_occurrence_span_runs_to_the_first_row_of_the_next_occurrence():
    # rows in plan order: A show, A show, A station-id interstitial, B announcement, B show
    spans = site.occurrence_spans(ROWS, EPOCH)
    assert spans[("A", A_NOM)] == (start_us(ROWS[0]), start_us(ROWS[3]))   # interstitials included
    assert spans[("B", B_NOM)] == (start_us(ROWS[3]), None)                # no following occurrence planned

def test_occurrence_spans_ignore_pre_scheduler_rows():
    # a phase-1 row (block None) before A: not a key, and not A's start
    assert set(site.occurrence_spans([PHASE1_ROW, *ROWS], EPOCH)) == {("A", A_NOM), ("B", B_NOM)}

def test_timeline_adds_block_fields_and_blocks_without_changing_old_fields():
    doc = site.build_timeline(ROWS, ANALYSES, EPOCH, now_us=NOW, last_n=LAST, pause_samples=0, clock=CLOCK)
    old = site.build_timeline(...)  # the same call with the block fields stripped from the rows
    for s, o in zip(doc["shows"], old["shows"]):
        assert {k: v for k, v in s.items() if k not in ("block", "nominal_start", "program")} == o
    assert doc["shows"][0]["block"] == "A" and doc["shows"][0]["nominal_start"] == A_NOM
    assert doc["shows"][0]["program"] is None
    assert doc["blocks"] == [
        {"block": "A", "nominal_start": A_NOM, "title": "A title", "start": iso(ROWS[0]), "end": iso_start(ROWS[3])},
        {"block": "B", "nominal_start": B_NOM, "title": "B", "start": iso_start(ROWS[3])},   # no "end" key
    ]

def test_timeline_pre_scheduler_show_has_null_block_and_no_blocks_entry(): ...

def test_notes_carry_program():
    doc = site.build_notes("s", {"dj_audio": {"title": "One More from the Archive"}}, "", [], {})
    assert doc["program"] == "One More from the Archive"
    assert site.build_notes("s", None, None, [], {})["program"] is None

def test_show_page_escapes_program_title():
    page = _page(program='<b>Late</b> "Night" & Co')
    assert "&lt;b&gt;Late&lt;/b&gt; &quot;Night&quot; &amp; Co" in page and "<b>Late" not in page
    assert '<span class="presents">LMA RADIO PRESENTS</span>' in _page(program=None)

def test_lineup_lists_nominal_occurrences_from_a_day_before_to_eight_days_after():
    doc = site.build_lineup(CLOCK, NOW)
    starts = [grid.iso_to_us(o["nominal_start"]) for o in doc["occurrences"]]
    assert all(grid.iso_to_us(o["end"]) > NOW - site.DAY_US for o in doc["occurrences"])
    assert max(starts) < NOW + 8 * site.DAY_US and starts == sorted(starts) and len(set(starts)) == len(starts)
    assert sum(1 for o in doc["occurrences"] if o["block"] == "bluegrass") >= 8   # a daily block: 9 days spanned
    o = next(o for o in doc["occurrences"] if o["block"] == "bluegrass")
    assert set(o) == {"block", "nominal_start", "end", "title", "variety"} and o["title"] == "Bluegrass in the Morning"

@pytest.mark.parametrize("profiles,variety", [([], True), (["bluegrass"], False), (["a", "b"], True)])
def test_lineup_variety_flag(profiles, variety): ...

def test_lineup_bytes_are_stable_for_equal_content():
    assert json.dumps(site.build_lineup(CLOCK, NOW), sort_keys=True) == json.dumps(site.build_lineup(CLOCK, NOW + 1), sort_keys=True)
```

  Test helpers and existing tests: `_page` gains a `program=` argument written to `manifest["dj_audio"]["title"]` (the existing `**source` still goes to `manifest["source"]`). Every existing `build_timeline` call in `test_site.py` gains `clock=CLOCK`. Update `test_show_page_escapes_and_fills_every_placeholder` for `$presents`, and `test_the_template_uses_the_new_look_and_links_home`, which asserts the literal `LMA RADIO PRESENTS` in the template: it now asserts `$presents` there (the rendered fallback is pinned by `test_show_page_escapes_program_title`). `ROWS` are `PlanRow`s with `block`/`nominal_start` set and `kind="interstitial"` where noted. `CLOCK` is built with `ClockConfig(...)`.

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/transmitter/tests_transmitter/test_site.py -q`. Expected: the new tests fail.

- [ ] **Step 3: Implement** the Produces list in `site.py`. `occurrence_spans` walks rows in plan order over every kind, keyed rows only. A key's start is its first row's start. Its end is the start of the first row whose key differs, appearing after that key's first row; with no such row, the end is None. `build_timeline`'s `"blocks"` holds, in start order, every occurrence that a listed show belongs to, with `"end"` left out when it is None. `build_lineup` uses `occurrences(clock, now_us - DAY_US, now_us + 8 * DAY_US)`, `nominal_start = occ.nominal_iso`, `end = us_to_iso(occ.end_us)`, `title = block_title(clock, b.name)`, and `variety = len(b.profiles) != 1`. In `show.html`, change line 29 to `<span class="presents">$presents</span>`. `render_show_page` sets `presents = html.escape(_text(notes.get("program")) or "LMA RADIO PRESENTS")`.

- [ ] **Step 4: Run** the same command, then all of `./.venv/bin/pytest packages/transmitter -q`. Expected: PASS. `test_publish.py` calls `build_timeline` through `_publish_site`, so give `_publish_site` a temporary `clock=clock_mod.IMPLICIT_CLOCK` here. Task 2 replaces it.

- [ ] **Step 5: Commit.** `transmitter: program title, block occurrences and lineup data in site.py`.

---

### Task 2: transmitter publish: program per show, block titles, lineup object

**Model hint:** sonnet.

**Files:**
- Modify: `packages/transmitter/src/transmitter/publish.py`, `packages/transmitter/src/transmitter/state.py`, `packages/transmitter/CLAUDE.md`
- Test: `packages/transmitter/tests_transmitter/test_publish.py`, `test_state.py` (or wherever `PublishState` load and save is tested)

**Interfaces:**
- Consumes: Task 1's `program_title`, `build_timeline(..., clock=)`, `build_lineup`. Also `clock.live_clock(ws, save=False) -> LiveClock(.clock)`.
- Produces: `LINEUP_KEY = "notes/_lineup.json"` and `LINEUP_CACHE = "public, max-age=300"`. `PublishState.lineup: str | None = None`, the sha256 of the last lineup body PUT. `_publish_site(...) -> tuple[dict[str, str], str | None]` returns (notes digests, lineup digest).

**Why `notes/_lineup.json`:** the WAF allowlist (`docs/playout-setup.md` section 2 step 6) blocks any root key it doesn't list. `notes/` is allowlisted, and no slug starts with `_`. So this needs no dashboard change.

- [ ] **Step 1: Write the failing tests** in `test_publish.py`, using its existing fake uploader and station fixtures:

```
test_timeline_show_program_comes_from_the_manifest_at_publish_time
    manifest dj_audio.title "Gravel & Steel" -> timeline show "program" == "Gravel & Steel";
    cached analysis meta carries no title, and changing only the manifest changes the next timeline
test_unreadable_manifest_publishes_program_null_and_keeps_the_published_page
    (manifest read fails: program null for that publish; notes/<slug>.json not re-PUT)
test_title_change_republishes_notes_and_page
    same show, title added -> notes/<slug>.json and show/<slug>.html PUT again, notes body has "program"
test_block_titles_come_from_the_live_clock
    ws clock.toml block title "Bluegrass in the Morning" -> timeline blocks[].title;
    no clock.toml -> the implicit clock's "open"; invalid clock.toml + clock.last-good.toml -> last-good's title
test_lineup_is_put_once_and_again_only_when_its_content_changes
    first publish PUTs notes/_lineup.json with Cache-Control "public, max-age=300";
    a second publish with the same occurrences PUTs nothing at that key; a clock edit PUTs it again;
    the digest survives save/load of publish.json
test_lineup_failure_never_stops_the_timeline
    the uploader raises PublishError for notes/_lineup.json only: timeline.json is still PUT,
    the notes digests are kept in state, the lineup digest is unchanged, and the error is logged
test_lineup_put_budget_still_propagates   (PutBudgetExceeded at the lineup key -> report.stopped == "put-budget")
test_notes_and_page_still_precede_the_timeline   (existing ordering test, extended to the new fields)
test_old_publish_state_without_lineup_loads      (publish.json from before -> lineup None)
```

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/transmitter/tests_transmitter/test_publish.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.** In `_publish_site`, load `lc = clock_mod.live_clock(p.ws, save=False)` once per call and pass `clock=lc.clock` to `build_timeline`. Set `show["program"] = site.program_title(manifest)` for each listed show in the existing manifest loop, before the `continue` that skips unchanged notes, so every listed show gets it whether or not its notes are re-PUT. After the timeline PUT, build the lineup body as `put_json` encodes it and hash it. PUT it only when the hash differs from the state's. Catch any non-`PutBudgetExceeded` exception from the lineup step: log `lineup step failed: ...` and keep the old digest. Thread the digest through `publish_batch` into `PublishState`. In `state.py`, add the field and load it with `data.get("lineup")`.

- [ ] **Step 4: Run** `./.venv/bin/pytest packages/transmitter -q`, and `packages/transmitter/scripts/test-in-debian12.sh` if Docker is running. Expected: PASS.

- [ ] **Step 5: Docs.** In `packages/transmitter/CLAUDE.md`, write one sentence in the Overview: `timeline.json` shows carry `program`, `block` and `nominal_start`; the document carries `blocks` (spans from the full persisted plan); the publisher writes `notes/_lineup.json` (nominal occurrences, now -24 h to +8 d, rewritten only on change, `max-age=300`); and the clock is loaded with `live_clock(save=False)`.

- [ ] **Step 6: Commit.** `transmitter: publish program titles, block spans and the lineup object`.

---

### Task 3: antenna pure helpers

**Model hint:** sonnet.

**Files:**
- Create: `antenna/public/assets/programs.js`
- Modify: `antenna/public/assets/notes.js`
- Test: `antenna/test/programs.test.ts`, `antenna/test/notes.test.ts`

**Why a new module:** during rollout a browser can hold a cached old `timeline.js` beside a new `page.js`. A module that asks a stale `timeline.js` for an export it lacks fails to load, so every new helper lives in the new `programs.js`, and `timeline.js` gains no export. `programs.js` may import `timeline.js`'s existing exports (`airTime`).

**Interfaces:**
- Consumes: Task 2's data shapes. Timeline show `{program?, block?, nominal_start?}`, `timeline.blocks[] {block, nominal_start, title, start, end?}`, and lineup `{occurrences: [{block, nominal_start, end, title, variety}]}`.
- Produces (all exported from `programs.js`):
  - `presentsLine(x) -> string`: `x.program` trimmed when it is a non-blank string, else `"LMA RADIO PRESENTS"`.
  - `occurrenceKey(block, nominalStart) -> string | null`: `` `${block}\u0000${nominalStart}` ``, or null when either is not a non-empty string.
  - `comingUpGroups(timeline, shows) -> Array<{key: string|null, title: string|null, span: string|null, shows: object[]}>`: consecutive shows that share a key form one group. A show with no key, or whose key has no `timeline.blocks` entry, sits in a group with null `title` and `span`.
  - `blockSpan(entry, timeZone?) -> string`: `"7:00a – 9:56a"`, or `"7:00a"` with no `end`.
  - `localDateKey(ms, timeZone?) -> string`: `"YYYY-MM-DD"` in that zone, from `Intl.DateTimeFormat` parts.
  - `lineupDays(lineup, nowMs, timeZone?, onAir?) -> Array<{key, label, entries: Array<{key, title, time, variety}>}> | null`: null for a missing or malformed lineup. `onAir` is an occurrence key (from `onAirKey`) or null. When it names an occurrence whose nominal start falls on yesterday's local date, that occurrence leads Today's entries, so a late-night block stays listed (and highlighted) after midnight.
  - `onAirKey(timeline, atMs) -> string | null`: the on-air show's occurrence key.
- `notes.js`: `panelModel(notes)` gains `presents: presentsLine(notes)`, importing `presentsLine` from `programs.js`.

- [ ] **Step 1: Write the failing tests:**

```ts
it("presentsLine: the program, else the house line", () => {
  expect(presentsLine({ program: " Gravel & Steel " })).toBe("Gravel & Steel");
  for (const v of [undefined, null, "", "  ", 7]) expect(presentsLine({ program: v })).toBe("LMA RADIO PRESENTS");
  expect(presentsLine(null)).toBe("LMA RADIO PRESENTS");
});
it("comingUpGroups: consecutive shows of one occurrence share a heading; others get none", () => {
  const g = comingUpGroups(TL_BLOCKS, TL_BLOCKS.shows);
  expect(g.map((x) => [x.title, x.shows.map((s) => s.slug)])).toEqual([
    ["Bluegrass in the Morning", ["bg-1", "bg-2"]], ["Mid-morning Dead", ["dead-1"]], [null, ["legacy-1"]],
  ]);
});
it("comingUpGroups: an old timeline with no blocks is one headless group", () => {
  expect(comingUpGroups(TIMELINE, TIMELINE.shows)).toEqual([{ key: null, title: null, span: null, shows: TIMELINE.shows }]);
});
it("blockSpan: start – end, or the start alone", () => {
  expect(blockSpan({ start: "2026-11-04T12:00:00.000Z", end: "2026-11-04T14:56:00.000Z" }, "America/New_York")).toBe("7:00a – 9:56a");
  expect(blockSpan({ start: "2026-11-04T12:00:00.000Z" }, "America/New_York")).toBe("7:00a");
});
it("lineupDays: seven tabs from today, Today first, grouped by listener-local date", () => {
  const days = lineupDays(LINEUP, t("2026-11-04T15:00:00Z"), "America/New_York");
  expect(days.map((d) => d.label)).toEqual(["Today", "Thu", "Fri", "Sat", "Sun", "Mon", "Tue"]);
  expect(days[0].entries[0]).toMatchObject({ title: "Bluegrass in the Morning", time: "7:00a", variety: false }); // earlier today kept
  const all = days.flatMap((d) => d.entries.map((e) => e.key));
  expect(new Set(all).size).toBe(all.length);                     // no block twice
});
it("lineupDays: a block just before midnight Eastern lands on the previous day in Los Angeles", () => { ... });
it("lineupDays: no tab skipped or repeated across spring-forward and fall-back", () => {
  for (const now of ["2027-03-13T04:30:00Z" /* 23:30 EST Mar 12 */, "2027-03-14T04:30:00Z", "2026-10-31T03:30:00Z", "2026-11-01T03:30:00Z"]) {
    const keys = lineupDays(LINEUP_WEEK(now), t(now), "America/New_York").map((d) => d.key);
    expect(keys.length).toBe(7);
    keys.slice(1).forEach((k, i) => expect(Date.parse(k) - Date.parse(keys[i])).toBe(86_400_000));
  }
});
it("lineupDays: the block on air since before midnight leads Today's tab", () => {
  const days = lineupDays(LINEUP, t("2026-11-05T05:30:00Z") /* 00:30 EST */, "America/New_York", LATE_KEY); // LATE: nominal 23:00 Nov 4
  expect(days[0].entries[0].key).toBe(LATE_KEY);
  expect(lineupDays(LINEUP, t("2026-11-05T05:30:00Z"), "America/New_York", null)[0].entries.map((e) => e.key)).not.toContain(LATE_KEY);
});
it("lineupDays: missing or malformed lineups give null", () => {
  for (const v of [null, {}, { occurrences: "x" }]) expect(lineupDays(v, 0)).toBeNull();
});
it("onAirKey: the on-air show's occurrence, null for a legacy show or nothing on air", () => { ... });
```

  In `notes.test.ts`: `panelModel` with and without `program` gives `presents`. A hostile `program` (`<img onerror>`) comes back as the same string; escaping happens at render.

  Also assert `timeline.js`'s export list is unchanged (`Object.keys(await import("../public/assets/timeline.js"))` equals today's list).

- [ ] **Step 2: Run** `cd antenna && npx vitest run test/programs.test.ts test/notes.test.ts`. Expected: FAIL.

- [ ] **Step 3: Implement.** `lineupDays` must not do time-zone arithmetic. Build the seven date keys by formatting `nowMs + k * 12 h` for k = 0, 1, 2, … and keeping the first seven distinct keys. A local day lasts at least 23 h, so 12-hour steps never skip one. Then put each occurrence under `localDateKey(Date.parse(o.nominal_start))`, keep only the seven keys, sort each day by start, and drop entries whose `nominal_start` doesn't parse. Then, if `onAir` matches an occurrence whose date key sorts before Today's (yesterday's: the lineup starts 24 h back), put it first in Today. `time` is `airTime(nominal_start, timeZone).time`. Labels are `"Today"`, then `airTime(...).day`.

- [ ] **Step 4: Run** `cd antenna && npm test`. Expected: PASS.

- [ ] **Step 5: Commit.** `antenna: pure helpers for programs, block groups and the lineup`.

---

### Task 4: antenna page: program on tickets, block headings, the weekly lineup

**Model hint:** opus (layout and styling judgement within the existing look).

**Files:**
- Modify: `antenna/public/assets/page.js`, `panel.js`, `radio.css`, `antenna/public/index.html` (then `npm run pages`), `antenna/e2e/fixtures/timeline.mjs`, `antenna/e2e/serve.mjs` (an option to serve another file at `/`), `antenna/CLAUDE.md`
- Create: `antenna/e2e/fixtures/lineup.mjs`, `antenna/e2e/fixtures/old-index.html` (a copy of `main`'s `antenna/public/index.html`, taken before Step 3)
- Test: `antenna/e2e/smoke.pw.mjs`, `antenna/test/indexpage.test.ts`

**Interfaces:**
- Consumes: Task 3's helpers, imported from `programs.js`. The lineup is fetched from `/notes/_lineup.json`, which the smoke server answers from its `notes` map under the key `_lineup`.

**Mixed versions during rollout:** assets and `index.html` deploy separately (Task 16), so the new `page.js` and `panel.js` must work against the old `index.html`. `renderLineup` no-ops when `#lineup` is missing. When `#coming-up` is the old `.tickets` grid (no group container), Coming up renders flat tickets into it with no headings. `panel.js` shows `LMA RADIO PRESENTS` when `model.presents` is undefined (a stale cached `notes.js`).

- [ ] **Step 1: Write failing tests.** In `indexpage.test.ts`:

```ts
it("the player page has a hidden weekly lineup section after Just aired", () => {
  expect(PLAYER_PAGE).toMatch(/Just aired[\s\S]*id="lineup"[^>]*hidden[\s\S]*The weekly lineup/);
  expect(PLAYER_PAGE).toContain('id="lineup-days"');
  expect(PLAYER_PAGE).toContain('id="lineup-list"');
});
```

  In `smoke.pw.mjs`:

```
a ticket whose show has a program shows it in place of LMA RADIO PRESENTS; one without keeps LMA RADIO PRESENTS (coming up and just aired)
the panel's big ticket shows the program; notes without program show LMA RADIO PRESENTS
coming up groups tickets under block headings: title left, "7:00a – 9:56a" right; a block with no end shows its start alone; each group starts a new row
an old timeline with no blocks renders coming up flat with no heading, and no console error
Show all reveals the remaining tickets under their headings (a group cut by the first 6 continues under the same heading)
just aired stays a flat list with no headings
the lineup shows 7 tabs, Today selected on load, today's blocks listed with start time and title in the listener's zone
choosing a tab lists that day; variety blocks carry the variety style; tabs are buttons with role=tab and aria-selected
the block on air is highlighted in Today's tab only (aria-current), matched on block name and nominal start
after midnight, the block on air since before midnight is listed first in Today and highlighted
new assets with the old index.html (fixtures/old-index.html served at /): the page plays, Coming up shows flat tickets, no lineup, no console error
a 404 or malformed lineup hides the section with no console error; a later good fetch shows it
the hostile fixture: a program and a block title with markup appear as literal text and add no element
at 320 px with a 60-character program and block title, document.scrollWidth <= 320 on the main page and the panel
a program title change rebuilds the ticket (rebuild key includes the program)
```

  Extend `timeline.mjs` so a show can carry `program`, `block` and `nominal_start`, and a timeline can carry `blocks`. `lineup.mjs` builds a week of occurrences relative to the test's mocked now. Add the lineup's 404 to `EXPECTED_STATUS` if console filtering needs it.

- [ ] **Step 2: Run** `cd antenna && npm run pages && npm test && npm run smoke`. Expected: the new tests fail.

- [ ] **Step 3: Implement.**
  - `index.html`: below the Just aired section, add `<section id="lineup" class="schedule lineup" hidden><h2 class="kick">The weekly lineup</h2><div id="lineup-days" class="days" role="tablist"></div><ol id="lineup-list" class="lineup-list"></ol></section>`. `#coming-up` stops being the ticket grid (it loses the `tickets` class, which is how `page.js` tells the old page from the new): it holds one `div.block-group` per group, each with an optional `div.block-head` (`span.block-title`, `span.block-span`) followed by its own `div.tickets` grid.
  - `page.js`: `ticket()` uses `presentsLine(show)`. `renderTickets`' key adds `s.program`. Coming up applies `SHOWN` to the tickets first, then groups them with `comingUpGroups`. The group rebuild key covers each group's key, title, span and ticket keys. `refreshLineup()` fetches `/notes/_lineup.json` on the first timeline refresh and again once the last attempt is 30 minutes old. A failure keeps the old lineup. `renderLineup(atMs)` returns at once when `#lineup` is missing. It passes `onAirKey(timeline, atMs)` to `lineupDays` and hides the section when that gives null. It keeps the selected tab in memory and resets to Today when today's key changes. It highlights `onAirKey` only in Today. With the old `.tickets` `#coming-up`, Coming up renders its tickets flat. `textContent` only.
  - `panel.js`: `ticketView` uses `model.presents ?? "LMA RADIO PRESENTS"`.
  - `radio.css`: block heading in the existing `.kick` small-caps style with the span right-aligned; the day picker; `.variety` entries in italics; `.on-air` in the existing oxblood accent. No new colours outside the palette.

- [ ] **Step 4: Run** `cd antenna && npm run pages && npm test && npm run typecheck && npm run smoke`. Expected: all green. Check that `git diff --stat antenna/public/player.js antenna/public/nowplaying.js antenna/public/style.css` is empty.

- [ ] **Step 5: Docs.** In `antenna/CLAUDE.md`'s player bullet, add: tickets show `program` (fallback `LMA RADIO PRESENTS`, also in `show.html`'s `$presents` and the panel); Coming up groups by occurrence; the lineup comes from `notes/_lineup.json` (refetched every 30 min, section hidden when missing). Add `programs` to the pure modules, with the rule that new helpers go in a new module rather than new exports of a deployed one (a stale cached module would lack them), and that `page.js`/`panel.js` tolerate the previous `index.html`.

- [ ] **Step 6: Commit.** `antenna: program on tickets, block headings and the weekly lineup`.

---

### Task 5: emcee station lock and `emcee lock`

**Model hint:** opus (strict surface).

**Files:**
- Create: `packages/emcee/src/emcee/station_lock.py`
- Modify: `packages/emcee/src/emcee/cli.py` (a `lock` sub-app; `_COMMAND_ORDER`)
- Test: `packages/emcee/tests/test_station_lock.py`, `packages/emcee/tests/test_lock_cmd.py`, `packages/emcee/tests/test_cli_boundary.py`

**Interfaces:**
- Produces (`emcee.station_lock`):
  - `LOCK_NAME = ".lma-station.lock"` and `MAGIC = "lma-station-lock 1"`.
  - `class StationLocked(EmceeError)`: `.path: Path`, `.holder: str`. The message is `the station is locked by another writer ({path})`. `.details` holds the holder lines, then `check it with: emcee lock show; remove it with: emcee lock clear (only if that writer is gone)`.
  - `class StationLockReentry(RuntimeError)`.
  - `@dataclass(frozen=True) class Held: path: Path; token: str`.
  - `acquire(path: Path, *, command: str) -> Held` and `release(held: Held) -> None`. `acquire` turns any create error other than `EEXIST` (ENOENT for a missing delivered folder, EACCES, an SMB delete-pending error, …) into `EmceeError("cannot create the station lock at {path}: [Errno {n}] {strerror}")`: a refusal, never a traceback. `release` unlinks only on its own token. Otherwise it writes `warning: the station lock at {path} was not ours at release ({holder or 'missing'}); writes since {started} ran unguarded` to stderr. `release` never raises: an unlink (or read) error writes `warning: could not remove the station lock at {path} ({err}); clear it with: emcee lock clear` and leaves the file.
  - `@contextmanager station_lock(delivered: Path, *, command: str) -> Iterator[Held]`: on the main thread it installs SIGTERM and SIGHUP handlers that raise `SystemExit(128 + signum)`, then acquires at `delivered / LOCK_NAME`, both inside one `try`. The `finally` releases (when acquired) and restores the previous handlers.
  - `read_lock(delivered: Path) -> bytes | None`, `holder_text(raw: bytes) -> str` (`"(empty lock file)"` for empty contents), and `token_of(raw: bytes) -> str | None`.
- `_COMMAND_ORDER` becomes `["run", "voice", "status", "move", "say", "lock", "presenter", "config"]`; Task 9 inserts `"retitle"` before `"lock"`. (`test_ordered_panel_group_lists_commands_in_declared_order` asserts `list_commands == _COMMAND_ORDER`, so the list holds only registered commands.)
- `emcee lock show [--station-root P]` prints the path and holder text, or `no station lock at {path}`, and exits 0. `emcee lock clear [--station-root P] [--yes]` prints the holder and asks `Remove this lock? [y/N]`. With no TTY and no `--yes` it exits 1. It removes the file only if its bytes still equal the bytes shown (else `the lock changed since it was shown; run again`, exit 1), then prints `station lock removed`. With no lock it says so and exits 0.

- [ ] **Step 1: Write the failing tests** in `test_station_lock.py`:

```
test_acquire_writes_magic_token_and_holder          (line 1 matches ^lma-station-lock 1 [0-9a-f]{32}$; tool: emcee; command; host; pid == os.getpid(); started has an offset)
test_lock_path_is_the_delivered_folder              (station_lock(tmp) -> tmp/.lma-station.lock)
test_held_lock_is_refused_naming_its_holder         (another token's file -> StationLocked; holder text in .holder and .details; the file is unchanged)
test_empty_lock_counts_as_held                      (b"" -> StationLocked, holder "(empty lock file)")
test_garbage_lock_counts_as_held                    (b"\xff\x00junk" -> StationLocked; the file is unchanged)
test_second_acquire_in_one_process_raises_reentry   (inside station_lock(tmp), station_lock(tmp) and station_lock(other) both raise StationLockReentry; the first lock still holds its token; after exit the file is gone)
test_release_unlinks_only_its_own_token             (the file rewritten with a foreign token mid-hold -> left in place; stderr has "not ours at release" and "unguarded")
test_release_warns_when_the_lock_is_missing         (the file deleted mid-hold -> warning, no exception)
test_exception_inside_releases                      (raise inside the with -> file gone, exception propagates)
test_sigterm_releases_the_lock                      (subprocess: `python -c` acquires, prints "held", sleeps; parent sends SIGTERM -> returncode 128+15, lock file gone)
test_sighup_releases_the_lock                       (same with SIGHUP)
test_previous_signal_handlers_are_restored          (also when acquire refuses: handlers installed before acquire are restored)
test_write_failure_after_create_removes_the_file    (os.write patched to raise -> OSError propagates, no lock file left)
test_create_error_other_than_eexist_is_a_refusal    (missing delivered folder -> EmceeError naming the path and "Errno 2"; os.open patched to raise EACCES -> EmceeError with "Errno 13"; no traceback type leaks)
test_release_unlink_error_warns_and_never_raises    (os.unlink patched to raise -> no exception out of the with; stderr names "emcee lock clear"; the file is left)
```

  In `test_cli_boundary.py`, the expected order gains `"lock"` after `"say"`.

  In `test_lock_cmd.py` (`CliRunner`, `[station] root` = tmp):

```
test_lock_show_prints_holder / test_lock_show_without_lock
test_lock_clear_with_yes_removes_it
test_lock_clear_without_tty_or_yes_refuses          (exit 1, the file is untouched)
test_lock_clear_refuses_when_the_lock_changed_after_display   (confirm patched to rewrite the file -> exit 1, file kept)
test_lock_clear_never_holds_a_lock_itself           (no second lock file appears; a garbage lock is still clearable)
```

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/emcee/tests/test_station_lock.py packages/emcee/tests/test_lock_cmd.py packages/emcee/tests/test_cli_boundary.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** the Interfaces list. The re-entry guard is a module-level `_held: Held | None` checked before any filesystem call: a process holds at most one station lock. `acquire` handles `FileExistsError` by reading the file for the holder text. If it is already gone, the acquire is still refused (`(lock vanished while reading)`), never retried, so a refusal is always a refusal. The token is `secrets.token_hex(16)`. The started time is `datetime.now().astimezone().isoformat(timespec="seconds")`.

- [ ] **Step 4: Run** `./.venv/bin/pytest packages/emcee -q`. Expected: PASS (`test_no_llama_imports.py` included).

- [ ] **Step 5: Commit.** `emcee: station lock and emcee lock show/clear`.

---

### Task 6: emcee `run` and `voice` take the lock per package

**Model hint:** opus.

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py` (`run`'s per-package loop, `voice_cmd`), `packages/emcee/CLAUDE.md`, root `CLAUDE.md`
- Test: `packages/emcee/tests/test_run_lock.py`

**Interfaces:**
- Consumes: Task 5's `station_lock(delivered, command=...)`, `StationLocked`.
- Produces: in `run`, each `_process_one(...)` call is wrapped in `station_lock(status.path.absolute().parent, command="emcee run")`. In `voice_cmd`, the `_process_one` call is wrapped in `station_lock(pkg.dir.absolute().parent, command="emcee voice")`. `.absolute()` matters: `Path(".").parent` is `.`, so `emcee voice .` run from inside a package would otherwise lock the package itself. `_process_one` stays lock-free (it already starts with the manifest re-read).

- [ ] **Step 1: Write the failing tests** (fake LLM and TTS, as `test_run_cmd.py` does):

```
test_run_holds_the_lock_for_each_package_and_releases_between
    _process_one wrapped to record (lock exists, token) on entry: present for each of 3 packages,
    a different token each time; no lock file after the run
test_run_takes_no_lock_while_asking_proceed
    TTY run: typer.confirm patched to assert no lock file exists, then True
test_run_dry_run_takes_no_lock          (works while a foreign lock is held; the lock is unchanged)
test_run_stops_at_a_held_lock_and_lists_what_it_did_not_attempt
    acquire raises StationLocked on the 2nd package: pkg1 voiced; stderr "error: pkg2: the station is locked by another writer",
    the holder lines, "not attempted: pkg2, pkg3"; exit 1; pkg2/pkg3 manifests byte-identical
test_run_keep_script_also_takes_the_lock
test_voice_takes_the_lock_at_the_package_parent   (emcee voice <path outside [station] root> -> lock in that path's parent)
test_voice_dot_from_inside_the_package_locks_the_delivered_folder   (monkeypatch.chdir(pkg); emcee voice . -> lock at pkg.parent/.lma-station.lock, none in pkg)
test_voice_refuses_a_held_lock                    (exit 1, holder printed, manifest untouched, no LLM call)
test_status_move_and_say_take_no_lock             (each succeeds while a foreign lock is held; the lock is unchanged)
test_lock_released_when_process_one_raises        (failure in pkg1 -> lock gone, run continues to pkg2 as before)
```

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/emcee/tests/test_run_lock.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.** In `run`'s loop, catch `StationLocked` around the `with`. Print `error: {slug}: {exc}` and its details, then `not attempted: {this and the remaining slugs}`, set failed, and `break`. Every other exception keeps today's handling, including the `MAX_CONSECUTIVE_FAILURES` stop. In `voice_cmd`, `StationLocked` flows into the existing `error: <slug>:` boundary.

- [ ] **Step 4: Run** `./.venv/bin/pytest packages/emcee -q`. Expected: PASS.

- [ ] **Step 5: Docs.** Root `CLAUDE.md` line 40 becomes: "Run one `emcee run` at a time against a station root. emcee takes the station lock (`<delivered>/.lma-station.lock`) per package, so llama's station writes refuse while a package is being voiced. An agent (no TTY) …" (the rest unchanged). In `packages/emcee/CLAUDE.md`, replace the "**Single-writer station, no lock.**" paragraph: the station lock is per package in `run`/`voice`, held from the manifest re-read through the last write. A held lock stops `run` (`not attempted: …`, exit 1). `move`, `say` and read-only commands don't take it. `emcee lock show|clear` handles it. Two concurrent `emcee run`s are still not supported (double spend). Add `emcee lock` to Commands, with the agent rule: an agent runs `emcee lock show`, reports it, and runs `emcee lock clear --yes` only after Shawn approves, in a separate tool call.

- [ ] **Step 6: Commit.** `emcee: run and voice take the station lock per package`.

---

### Task 7: the title field: emcee records it, llama's copy carries it

**Model hint:** sonnet.

**Files:**
- Modify: `packages/emcee/src/emcee/models.py` (`DJAudioBlock`), `packages/emcee/src/emcee/process.py` (`process_package`), `packages/llama/src/llama/models.py` (`DJAudio`)
- Create: `scripts/test_dj_audio_handshake.py`
- Test: `packages/emcee/tests/test_process.py`, `packages/llama/tests/test_the_cut.py` (where `DJAudio` is tested)

**Why the cross-model check is in `scripts/`:** emcee's tests must not import llama (`packages/emcee/tests/test_no_llama_imports.py`), and `scripts/` is the only place that may import both.

**Interfaces:**
- Produces: `DJAudioBlock.title: str | None = None`, declared **last** (after `voiced_before`), so a voiced block and a backfilled one carry it in the same position. It is always serialized. `process_package` passes `title=voicing.title`. llama's `DJAudio.title: str | None = None  # emcee-written: the program's title when voiced`.

- [ ] **Step 1: Write the failing tests:**

```
test_voicing_records_the_program_title         ([assign.profiles.bluegrass] title = "Gravel & Steel" -> manifest dj_audio.title == "Gravel & Steel", last key of dj_audio)
test_voicing_by_default_or_house_records_null_title   ("title": null present in dj_audio)
test_title_follows_the_effective_profile       (an [assign.artists] rule moves the show to a titled profile -> that title)
# packages/llama/tests/test_the_cut.py
test_llama_dj_audio_parses_a_block_with_title_and_without   (literal dicts: with "title": "Gravel & Steel" -> .title kept and model_dump round-trips; without -> .title None)
# scripts/test_dj_audio_handshake.py
test_emcee_dj_audio_block_parses_as_llama_dj_audio          (emcee DJAudioBlock(..., title="X").model_dump() and title=None both parse as llama DJAudio, title preserved)
```

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/emcee/tests/test_process.py packages/llama/tests/test_the_cut.py scripts/test_dj_audio_handshake.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** the three fields and the one argument. Update existing tests that assert an exact `dj_audio` dict.

- [ ] **Step 4: Run** `./.venv/bin/pytest -q` (whole suite). Expected: PASS.

- [ ] **Step 5: Docs.** In `packages/emcee/CLAUDE.md`'s `dj_audio records …` sentence, add `title` (the program's current `[assign.profiles.<p>] title`, null when none, last key). In the llama `DJAudio` docstring, nothing beyond the field comment.

- [ ] **Step 6: Commit.** `emcee: record the program title in dj_audio; llama's DJAudio copy carries it`.

---

### Task 8: the title backfill: plan and raw single-field writer

**Model hint:** opus (strict surface: station manifests).

**Files:**
- Create: `packages/emcee/src/emcee/retitle.py`, `packages/emcee/src/emcee/procs.py`
- Test: `packages/emcee/tests/test_retitle_writer.py`, `packages/emcee/tests/test_procs.py`

**Interfaces:**
- Consumes: `process.assignment_for(config, profile).title`, `station.manifest_voiced_profile(manifest)`, `station.awaiting_fix_reason(manifest)`, `package_io.MIN_SUPPORTED_SCHEMA_VERSION`.
- Produces (`emcee.retitle`):
  - `@dataclass(frozen=True) class TitleWrite: slug: str; dir: Path; raw: bytes; old: str | None; new: str | None`.
  - `@dataclass class RetitlePlan: writes: list[TitleWrite]; awaiting: list[str]; refused: list[tuple[str, str]]; unchanged: int; unvoiced: int`.
  - `plan_retitle(station_root: Path, config: EmceeConfig) -> RetitlePlan`: reads only. It covers every non-dot directory under the root that contains `manifest.json` (`station.scan`'s rule, `station.py:388-391`), sorted, so `interstitials/` and other folders without a manifest are ignored.
  - `class TitleWriteFailed(EmceeError)`.
  - `write_title(pkg_dir: Path, *, expect: bytes, title: str | None) -> bytes | None`: returns the bytes written, or None when the file changed before the rename (skipped, nothing written). It raises `TitleWriteFailed` when the post-rename check fails.
  - `encode(data: dict) -> bytes` is `(json.dumps(data, indent=2) + "\n").encode()`.
- Produces (`emcee.procs`): `tool_lines(ps_lines: Iterable[str], tools: Sequence[str], *, self_pid: int) -> list[str]` (pure; `self_pid` and its ancestors never match) and `other_tool_processes(tools=("emcee", "llama")) -> list[str]` (runs `ps -axo pid=,ppid=,command=`). The matching is a port, in full, of llama's `campaign_gate._runs_tool` and its helpers (`packages/llama/src/llama/campaign_gate.py:65-90`; emcee cannot import it): the first word's basename is the tool; a python with `-m <tool>`, or whose first non-option argument is the tool (by basename) or a `.py` under a `scripts/` directory; a shell's `-c` string, judged per simple command. One difference: a `scripts/*.py` counts as matching for **both** tools (campaign_gate counts it for llama only), since `scripts/backfill_*` import emcee.

**Plan rules, in order, for each package:** unreadable bytes or JSON, or not an object → refused. `schema_version` below 3 → refused (`unsupported`), voiced or not. `dj_audio` key absent or null → unvoiced (not listed). `dj_audio` not a dict → refused. Bytes not equal to `encode(json.loads(bytes))` → refused (`not in emcee's encoding`). A non-null `awaiting_fix` → awaiting (listed). Then target = `assignment_for(config, manifest_voiced_profile(m)).title`; current = `dj_audio.get("title")`; equal (absent and null are the same title) → unchanged. Otherwise it is a write. A clear writes `"title": null`.

**Writer order (spec, verbatim in effect):**
1. `st = os.stat(manifest)`.
2. Build `new = encode(data with dj_audio["title"] = title)`, touching no other key.
3. Write a unique temp `.manifest.json.emcee-<hex>.tmp` in the package dir with `"xb"`, flush, fsync and close it.
4. `os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))`, on the closed file.
5. Re-read the manifest. If it doesn't equal `expect`, unlink the temp and return None.
6. `os.replace`.
7. If `os.stat(manifest).st_mtime_ns != st.st_mtime_ns`, re-apply `os.utime` once.
8. Re-read and verify: every top-level key but `dj_audio` equal, `dj_audio` minus `title` equal, and `title` equal to the target. On failure, if the file still holds exactly `new`, put `expect` back the same way (temp, flush, fsync, close, utime, replace, mtime re-check) and raise `TitleWriteFailed("<slug>: … ; the original was put back")`. Otherwise raise `TitleWriteFailed("<slug>: … ; left as the other writer wrote it")`.

- [ ] **Step 1: Write the failing tests:**

```
test_plan_absent_and_null_title_are_the_same          (target None: absent -> unchanged, null -> unchanged; neither written)
test_plan_writes_additions_changes_and_clears         (absent -> "X": write; "Old" -> "X": write; "Old" -> None: write new=None)
test_plan_skips_awaiting_fix_and_lists_it             (awaiting_fix {"reason": ...} -> in .awaiting, not in .writes; awaiting_fix null -> normal)
test_plan_uses_the_voiced_profile_with_legacy_fallback   (dj_audio without "profile" -> source.profile's title)
test_plan_refuses_foreign_encodings                   (ensure_ascii=False non-ASCII; no trailing newline; indent=4; duplicate keys; a float written as 1.50; dj_audio a list; invalid JSON -> each refused with a reason, file bytes and mtime unchanged)
test_plan_refuses_pre_v3_voiced_or_not                (schema_version 2 with and without dj_audio -> refused "unsupported", never counted unvoiced)
test_plan_ignores_unvoiced_and_dot_directories        (unvoiced -> counted, not listed; .hidden/ and interstitials/ (no manifest.json) -> not in any list or count)
test_write_sets_only_the_title_key                    (result == encode(original with title set); every other byte region identical)
test_write_sets_mtime_before_the_rename               (os.replace wrapped: os.stat(src).st_mtime_ns == original at the moment of rename; os.utime wrapped: the temp is already closed and fsynced when it runs)
test_write_mtime_is_the_original_afterwards           (and re-applied when a patched replace bumps it)
test_write_skips_when_the_file_changed_before_rename  (file rewritten between plan and step 5 -> returns None, the other writer's bytes kept, no temp left)
test_write_post_rename_verify_failure_puts_back_own_bytes   (verify patched to fail -> original bytes back, original mtime, TitleWriteFailed "put back")
test_write_post_rename_verify_failure_leaves_a_foreign_write  (replace wrapped to land another writer's bytes after the rename -> file keeps them, TitleWriteFailed "left as the other writer wrote it")
test_write_preserves_awaiting_fix_and_unknown_keys    (a manifest with extra top-level keys keeps them all)
test_tool_lines_matches_emcee_and_llama_but_not_self_or_ancestors   (procs)
test_tool_lines_matches_campaign_gate_cases           (procs: `python3 scripts/backfill_voiced_on.py`, `python scripts/bulk_apply.py mark ...`, `python -m llama`, `llama deliver`, `emcee run`, `bash -c 'cd x && llama status'` match; `code ~/projects/llama` and `git -C ~/projects/llama status` do not)
```

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/emcee/tests/test_retitle_writer.py packages/emcee/tests/test_procs.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** the Interfaces list with the rules and order above. Isolate the verify as `_unchanged_except_title(before: dict, after: dict, title: str | None) -> bool` so the failure-path test can patch it.

- [ ] **Step 4: Run** `./.venv/bin/pytest packages/emcee -q`. Expected: PASS.

- [ ] **Step 5: Commit.** `emcee: title backfill plan and raw single-field writer`.

---

### Task 9: `emcee retitle`

**Model hint:** opus.

**Files:**
- Modify: `packages/emcee/src/emcee/cli.py` (the command; `_COMMAND_ORDER`), `packages/emcee/CLAUDE.md`
- Test: `packages/emcee/tests/test_retitle_cmd.py`, `packages/emcee/tests/test_cli_boundary.py`

**Interfaces:**
- Consumes: Task 8's `plan_retitle`, `write_title`, `TitleWriteFailed`, `procs.other_tool_processes`. Task 5's `station_lock`, `StationLocked`. `_resolve_station_root(config, override)`, `_stdin_is_tty()`.
- Produces: `emcee retitle [--station-root P] [--dry-run] [--yes/-y]`, and `"retitle"` inserted before `"lock"` in `_COMMAND_ORDER`.
  - Plan output, one line each: `would write <slug>: <old> -> <new>` (`(none)` for null), `skip <slug>: awaiting fix from llama`, `refused <slug>: <reason>`, then a summary: `<n> to write, <n> unchanged, <n> awaiting fix, <n> refused, <n> unvoiced`.
  - With `--dry-run`, it stops after the plan.
  - Nothing to write: `nothing to write`.
  - Confirm as `emcee run` does: TTY → `Proceed?`; no TTY and no `--yes` → `error: refusing to write without confirmation; pass --yes`, exit 1.
  - Then the `ps` check: any other emcee or llama process → `refusing: other emcee or llama processes are running` plus the lines, exit 1.
  - Then, under `station_lock(root, command="emcee retitle")` for the whole write phase:
    1. Re-read every planned manifest. If any differs from its planned bytes: `refusing: <n> manifest(s) changed since the plan; nothing written; run again` plus the slugs, exit 1.
    2. Create the backup dir `<config.root>/title-backups/<UTC %Y%m%dT%H%M%SZ>/`.
    3. Per write: save `<slug>.json` (the original bytes, flushed and fsynced) and append `{"slug", "before_sha256", "mtime_ns"}` (the original mtime) to `record.jsonl` (fsynced). If that fails: `error: <slug>: backup failed (<err>); stopping before writing it`, `not attempted: …`, exit 1. Then `write_title`. On success, print `<slug>: <old> -> <new>` and append `{"slug", "after_sha256"}`. On None, print `skip <slug>: changed since the plan` and list it at the end. On `TitleWriteFailed`, print the error and `not attempted: …`, exit 1.
  - Exit code, the same rule with and without `--dry-run`: 1 only when a package was refused, a write was skipped as changed before the rename, or the run stopped on plan drift, the `ps` refusal, a held lock, or a backup, write or verify failure (and for the no-TTY confirmation refusal above). Awaiting-fix, unchanged and unvoiced packages never affect it. Otherwise 0.

- [ ] **Step 1: Write the failing tests:**

```
test_dry_run_lists_writes_awaiting_and_refused_and_writes_nothing   (all manifests byte- and mtime-identical; no lock file; no backup dir)
test_yes_prints_every_write_and_stamps_titles
test_no_tty_without_yes_refuses
test_no_lock_is_held_while_asking_proceed       (confirm patched to assert no lock file)
test_lock_is_held_for_the_whole_write_phase     (write_title wrapped: the lock exists with "command: emcee retitle" on every call; gone after)
test_held_lock_refuses_and_writes_nothing       (foreign lock -> exit 1, holder printed, nothing written, no backup dir)
test_ps_refusal_writes_nothing_and_takes_no_lock   (other_tool_processes patched non-empty -> exit 1, lines printed)
test_plan_drift_under_the_lock_refuses_the_whole_run   (one manifest changed after planning, before the lock -> nothing written to ANY package, exit 1, slug listed)
test_backup_saved_before_each_write_with_sha    (before bytes equal the original; record.jsonl has before_sha256, mtime_ns == the original's, and after_sha256 == sha of the new file)
test_backup_failure_aborts_before_writing_that_show   (backup write patched to fail on show 2 -> show 1 written, show 2 and later untouched, "not attempted", exit 1)
test_write_failure_stops_the_run_non_zero       (write_title raises TitleWriteFailed on show 2 -> show 3 untouched, exit 1)
test_changed_before_rename_is_skipped_and_listed   (write_title returns None -> others written, exit 1, slug listed)
test_awaiting_fix_shows_are_never_written       (byte-identical after --yes)
test_rerun_after_success_has_nothing_to_write   (idempotent; exit 0)
test_exit_code_ignores_awaiting_unchanged_and_unvoiced   (a station of only awaiting-fix, unchanged and unvoiced shows plus writes: --dry-run exit 0, --yes exit 0)
test_exit_code_is_1_when_a_package_is_refused   (one refused manifest: --dry-run exit 1; --yes writes the others and exits 1)
test_retitle_after_rename_in_config_changes_and_clears   (config title edited -> new title; title removed -> null written)
```

  In `test_cli_boundary.py`, the expected order gains `"retitle"` before `"lock"`.

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/emcee/tests/test_retitle_cmd.py packages/emcee/tests/test_cli_boundary.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** as specified. The `ps` check runs before the lock is taken, so the refusal leaves nothing to release.

- [ ] **Step 4: Run** `./.venv/bin/pytest packages/emcee -q`. Expected: PASS.

- [ ] **Step 5: Docs.** In `packages/emcee/CLAUDE.md` Commands, describe `emcee retitle`: what it writes and skips (awaiting fix: 136 at design time; it breaks `bulk_apply unmark` for a stamped show, and a wave snapshot restore covering one refuses with station-changed, accepted 2026-11-04), the encoding refusal, the mtime restore and why (hugo `quiet_minutes` 10), the lock and `ps` refusals, and the backups under `<emcee root>/title-backups/<stamp>/`. Hand restore: put `<slug>.json` back only where the current sha256 equals the record's `after_sha256`. Add the agent rule: dry run, show it, `--yes` only after approval, in a separate call.

- [ ] **Step 6: Commit.** `emcee: retitle, the program-title backfill`.

---

### Task 10: llama station lock helper

**Model hint:** opus (strict surface).

**Files:**
- Create: `packages/llama/src/llama/station_lock.py`
- Test: `packages/llama/tests/test_station_lock.py`

**Interfaces:**
- Produces (`llama.station_lock`), the same contract as Task 5, implemented separately:
  - `LOCK_NAME` and `MAGIC` with the same values.
  - `class StationLocked(LlamaError)`, with `.path` and `.holder`. Its message is three lines: `the station is locked by another writer ({path}):`, then the holder lines indented two spaces, then `  check it with: emcee lock show; remove it with: emcee lock clear (only if that writer is gone)`.
  - `StationLockReentry(RuntimeError)`, `acquire`, `release`, and `station_lock(delivered, *, command)` with the same signal handling (handlers installed before `acquire`, inside the same `try`, restored in `finally`). `acquire` turns any create error other than `EEXIST` into `LlamaError("cannot create the station lock at {path}: [Errno {n}] {strerror}")`. `release` never raises: an unlink error warns `… clear it with: emcee lock clear` and leaves the file.
  - `for_package(out: Path, *, command: str) -> ContextManager[Held]`, which is `station_lock(out.absolute().parent, command=command)`. This is the **one shared helper** every llama caller uses.
  - The holder's `tool:` line is `llama`.

- [ ] **Step 1: Write the failing tests**, mirroring Task 5's `test_station_lock.py` list name for name (magic and holder; per-folder path; held refused naming holder; empty and garbage held; re-entry raises; own-token release and warnings; exception releases; SIGTERM; SIGHUP; handlers restored, also on a refused acquire; write failure cleans up; a non-EEXIST create error is a `LlamaError` naming path and errno; a release unlink error warns and never raises), plus:

```
test_for_package_locks_the_parent_folder           (also for a relative `out`: chdir into the folder, for_package(Path("slug")) -> lock in the folder, by absolute path)
test_refusal_names_holder_and_emcee_commands    (str(exc) contains the holder's "tool: emcee" line, "emcee lock show" and "emcee lock clear")
```

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/llama/tests/test_station_lock.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.** The same algorithm as `emcee.station_lock`. Keep the two files structurally parallel so a reviewer can diff them.

- [ ] **Step 4: Run** `./.venv/bin/pytest packages/llama -q`. Expected: PASS.

- [ ] **Step 5: Commit.** `llama: station lock helper (shared contract with emcee)`.

---

### Task 11: llama `deliver` and `clear-mark` take the lock

**Model hint:** opus.

**Files:**
- Modify: `packages/llama/src/llama/cli.py` (`_deliver_one`, `_deliver_batch`, `_clear_mark_one`), `packages/llama/src/llama/station_mark.py` (module docstring), `packages/llama/CLAUDE.md`
- Test: `packages/llama/tests/test_deliver_cmd.py`, `packages/llama/tests/test_clear_mark.py`

**Interfaces:**
- Consumes: Task 10's `for_package(out, command=...)`, `StationLocked`.
- Produces:
  - In `_deliver_one`, inside the existing `file_lock(show_ws.lock)` and after `_awaiting_fix_check`: first `target_dir.mkdir(parents=True, exist_ok=True)` (the same reach as today's `copytree`, which creates missing parents), so a delivery to a not-yet-existing inbox still works rather than failing the lock's create with ENOENT. Then `with station_lock.for_package(out, command=f"llama deliver {entry.slug}")` spans `_read_destination_manifest(out)` through `_replace_destination` or `shutil.copytree`. The ledger record and `_purge_after_delivery` run after release, still under the show lock.
  - In `_clear_mark_one`, inside `file_lock`: `with station_lock.for_package(out, command=f"llama clear-mark {slug}")` spans `read_station_manifest(out)` through `clear_mark`, `campaign.add_clear` and any `put_back`. The purge runs after release.
  - The library show lock is always taken before the station lock.
  - `_deliver_batch`: on `StationLocked`, print `{slug}: {exc}`, then `not attempted: {this and the remaining slugs}`, and `raise typer.Exit(1)`. Other per-show errors keep today's continue-on behaviour.
  - Single `deliver <name>` and `clear-mark` print the error and exit 1 through their existing `LlamaError` handling.
  - The `station_mark.emcee_running()` checks stay.

- [ ] **Step 1: Write the failing tests:**

```
test_deliver_lock_spans_the_destination_read_through_the_copy
    _read_destination_manifest, _replace_destination and shutil.copytree wrapped: at each call the lock file exists and holds "tool: llama";
    after deliver returns it is gone (overlay case and replace case both)
test_deliver_refuses_a_held_lock_naming_the_holder
    foreign lock in the dest folder -> exit 1; stderr has the holder and "emcee lock show"; destination untouched; ledger unchanged; library audio not purged
test_deliver_takes_the_lock_after_the_awaiting_fix_refusal   (an awaiting show refuses with no lock file ever created)
test_deliver_batch_stops_at_a_held_lock_and_lists_the_rest
    acquire raises StationLocked on the 2nd show: 1st delivered, "not attempted: s2, s3", exit 1, s2/s3 destinations untouched
test_deliver_batch_takes_no_lock_while_confirming   (_confirm_plan patched to assert no lock file)
test_clear_mark_lock_spans_read_through_clear_and_put_back
    read_station_manifest, clear_mark and put_back (record-failure path) wrapped: the lock is held at each call; released before the purge
test_clear_mark_refuses_a_held_lock                 (exit 1, station mark kept, campaign.json unchanged)
test_library_show_lock_is_taken_before_the_station_lock   (order recorded by wrapping file_lock and acquire)
test_deliver_creates_a_missing_nested_inbox_before_locking   (--dest tmp/a/b/inbox, none existing -> delivered, exit 0, no lock left)
```

  Existing tests that already deliver into a `--dest` that does not exist yet, and must stay green unchanged: `test_ready_show_delivers_and_records_ledger_row`, `test_deliver_purges_library_audio_and_keeps_the_rest`, `test_deliver_by_name_records_provenance_run`, `test_deliver_batch_excludes_held` and `test_deliver_batch_excludes_held_via_nonstate_selector` (all in `test_deliver_cmd.py`).

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/llama/tests/test_deliver_cmd.py packages/llama/tests/test_clear_mark.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** as specified.

- [ ] **Step 4: Run** `./.venv/bin/pytest packages/llama -q`. Expected: PASS.

- [ ] **Step 5: Docs.** `station_mark.py` docstring: replace "emcee, which takes no lock, may be rewriting at the same moment" with "emcee may be rewriting at the same moment unless the caller holds the station lock (`llama.station_lock`), which every station-writing command takes". In `packages/llama/CLAUDE.md` near line 178 ("`emcee` does not share this locking scheme"), say: emcee and llama share the station lock (`<delivered>/.lma-station.lock`), taken per show by `deliver` and `clear-mark` (and `bulk_apply` mark/unmark) inside the show lock. A held lock refuses (a batch stops and lists the rest). Clear it with `emcee lock clear`. A delivery during an emcee run may need a retry after the current package.

- [ ] **Step 6: Commit.** `llama: deliver and clear-mark take the station lock`.

---

### Task 12: `bulk_apply` takes the lock; lock contract test

**Model hint:** opus (strict surface: station marks).

**Files:**
- Modify: `scripts/bulk_apply.py` (`_mark_one`, `mark_apply`, `unmark`), `scripts/CLAUDE.md`
- Create: `scripts/test_station_lock_contract.py`
- Test: `scripts/test_bulk_apply_mark.py`

**Interfaces:**
- Consumes: Task 10's `for_package`, `StationLocked`. Task 5's `emcee.station_lock` (in the contract test only).
- Produces:
  - `_mark_one(...) -> tuple[str, bool, _Stop | None]` with `@dataclass(frozen=True) class _Stop: reason: str; lines: list[str]`. The emcee-running stop becomes `_Stop("emcee is running", running)`. Once the show is delivered and `_station_root_problem` passes, `with station_lock.for_package(out, command="bulk_apply mark")` is taken **before** `_station_copy_problem(out)` (`scripts/bulk_apply.py:972-975`), so it covers the first read of the station copy, and spans the `emcee_running()` check and `_mark_station`. On `StationLocked`, the station outcome is `refused: the station is locked` (retryable: it starts with `refused`) and the result is `_Stop("the station is locked", holder lines)`. `mark_apply` prints `refusing to mark station copies: {reason}; the batch stops` and lists later items as `not reached ({reason})`.
  - `unmark(..., apply=True)` wraps each `_unmark_one` call in `for_package(station_root / slug, command="bulk_apply unmark")` inside the show lock. On `StationLocked`, it echoes `{slug}: refused: the station is locked`, lists every remaining slug as `not attempted`, and returns 1. With `apply=False` it takes no lock.

- [ ] **Step 1: Write the failing tests:**

```
test_mark_holds_the_station_lock_around_write_mark        (write_mark wrapped: lock present with "command: bulk_apply mark")
test_mark_takes_the_lock_before_the_first_station_read    (_station_copy_problem wrapped: the lock exists when it runs)
test_mark_stops_at_a_held_lock_and_lists_the_rest         (foreign lock: item 1 station "refused: the station is locked", library mark added; items 2.. "not reached (the station is locked)"; exit 1; station copies byte-identical)
test_mark_emcee_running_stop_unchanged                    (existing message "not reached (emcee is running)")
test_unmark_apply_holds_the_lock_around_put_back
test_unmark_apply_stops_at_a_held_lock_and_lists_the_rest (returns 1; later slugs "not attempted"; nothing put back)
test_unmark_dry_run_takes_no_lock                         (works while a foreign lock is held)
# test_station_lock_contract.py
test_lock_constants_agree                                 (emcee and llama LOCK_NAME and MAGIC equal)
test_emcee_lock_refuses_llama_naming_emcee_holder
test_llama_lock_refuses_emcee_naming_llama_holder
test_emcee_lock_show_and_clear_handle_a_llama_lock        (CliRunner: show prints "tool: llama"; clear --yes removes it)
test_release_of_one_tool_never_unlinks_the_others_lock
```

- [ ] **Step 2: Run** `./.venv/bin/pytest scripts/test_bulk_apply_mark.py scripts/test_station_lock_contract.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** as specified. Existing tests that unpack `_mark_one`'s third element get updated for `_Stop`.

- [ ] **Step 4: Run** `./.venv/bin/pytest -q` (whole suite). Expected: PASS.

- [ ] **Step 5: Docs.** In `scripts/CLAUDE.md`: `bulk_apply mark`/`unmark --apply` take the station lock per show and stop on a held one. The campaign worktree pinned at v2.20.1 predates this and ignores the lock (`emcee retitle`'s `ps` check is the guard). The `backfill_*.py` one-offs are not lock-aware.

- [ ] **Step 6: Commit.** `scripts: bulk_apply takes the station lock; lock contract test`.

---

### Task 13: the go-live probe script

**Model hint:** sonnet.

**Files:**
- Create: `scripts/station_probe.py`, `scripts/test_station_probe.py`
- Modify: `scripts/CLAUDE.md`

**Interfaces:**
- Produces `scripts/station_probe.py`: stdlib only and Python 3.11-compatible, so it also runs on hugo (Debian 12) with `python3`. It imports neither emcee nor llama.
  - `race --dir D [--n 1000] [--workers 2]`: workers race exclusive create and token-checked unlink on a scratch name `.lock-race-<hex>`. A worker that loses the create reads the file the way `acquire` reports a holder (a vanished file counts as `vanished`), so the race also exercises read-during-unlink. While holding, a worker creates a `.lock-race-<hex>.held-<worker>` marker, notes whether another worker's marker exists, re-reads that the file holds its own token after ~5 ms, then removes its marker and unlinks. A **double** acquisition is counted only when that token re-read finds another token; the marker overlap count is advisory. It prints `acquired <n> contended <n> vanished <n> double <n> marker-overlap <n> (advisory)`, exits 0 only when `double 0`, and removes every scratch file.
  - `mtime --dir D --create`: creates `.mtime-probe-<hex>` and prints its name, for hugo to `stat` first (so hugo's attribute cache holds the old entry). `mtime --dir D --replace NAME`: replaces it in the writer's order (Global Constraints: temp, flush, fsync, close, `os.utime` to `2026-01-01T00:00:00Z`, rename, re-check and re-apply the mtime) and prints the expected epoch seconds. `mtime --dir D --remove NAME` deletes it.
  - `cross --dir D --role a|b --n N --tag T`: the race loop for one side, run at the same time on two hosts with the same `--tag`. It prints the same counts.
  - Test-only switch: when the environment variable `STATION_PROBE_TEST_DROP_EXCL=1` is set, workers open without `O_EXCL`. It is left out of `--help`. (macOS multiprocessing spawns its workers, so a monkeypatch in the test process never reaches them; the environment does.)

- [ ] **Step 1: Write the failing tests** in `scripts/test_station_probe.py` (run the script as a subprocess with `sys.executable`):

```
test_race_on_local_disk_reports_no_double_acquisition     (--n 50 in tmp_path -> exit 0, "double 0", no scratch files left)
test_race_detects_a_broken_exclusive_create               (STATION_PROBE_TEST_DROP_EXCL=1 -> double > 0, exit 1, no scratch files left)
test_mtime_replace_sets_mtime_before_rename               (--create, then --replace -> file mtime == 1767225600; printed seconds match)
test_mtime_remove_deletes_the_probe_file
test_probe_imports_only_the_stdlib                        (every import in the file is in sys.stdlib_module_names; no emcee/llama)
```

- [ ] **Step 2: Run** `./.venv/bin/pytest scripts/test_station_probe.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement** as specified. No syntax or stdlib newer than 3.11.

- [ ] **Step 4: Run** `./.venv/bin/pytest -q` (whole suite) and `cd antenna && npm test`. Expected: all green.

- [ ] **Step 5: Docs.** In `scripts/CLAUDE.md`, describe `station_probe.py race|mtime|cross` (stdlib-only, runs on hugo; its go-live use is in this plan's Task 19).

- [ ] **Step 6: Commit.** `scripts: station_probe, the go-live lock and mtime probes`.

---

### Task 14: final review and merge

**Model hint:** opus (the review mode is Opus).

- [ ] **Step 1:** Run the whole suite in the worktree: `./.venv/bin/pytest -q`, `cd antenna && npm test && npm run typecheck && npm run smoke`, and the Debian 12 script if Docker runs. Record the counts against the baseline.
- [ ] **Step 2:** Final branch review on Opus against the spec, the Global Constraints and the Review Focus. Fix through the usual implementer and review loop.
- [ ] **Step 3: HUMAN CHECKPOINT.** Stop and report: counts, review verdict, the finish menu. The merge to `main` and the push are the operator's call. Everything after this runs from the main checkout at the merged commit.

---

### Task 15: hugo deploy (transmitter)

**Model hint:** sonnet for the checks. The restart is the operator's.

- [ ] **Step 1:** On hugo (ssh): `cd <repo> && git pull`, confirm `git log -1` is the merged commit, then `~/.venvs/transmitter/bin/pip install -e packages/transmitter`.
- [ ] **Step 2: HUMAN CHECKPOINT.** The operator runs `sudo systemctl restart transmitter@shawn` (sudo needs Shawn's password). Wait for the operator's word.
- [ ] **Step 3: Verify** within a few minutes of the restart. `systemctl status transmitter@shawn` shows active. `~/.venvs/transmitter/bin/transmitter status` shows no new alert. Then: `curl -s https://listen.lma-radio.com/timeline.json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d["blocks"]), sum(1 for s in d["shows"] if s.get("block")), sum(1 for s in d["shows"] if s.get("program")))'` prints a non-zero first and second count; the third is 0 until the backfill. `curl -sI https://listen.lma-radio.com/notes/_lineup.json` returns 200 with `cache-control: public, max-age=300`, and its body has a non-empty `occurrences`. Rollback: revert on `main`, push, pull on hugo, and the operator restarts.

---

### Task 16: page deploy

**Model hint:** sonnet.

- [ ] **Step 1:** From `antenna/` in the main checkout: `npm ci`, then `npm run pages`. `git status` must stay clean (`src/pages.ts` was committed fresh).
- [ ] **Step 2: Preview.** `ANTENNA_BUCKET=lma-radio npm run deploy:assets -- --preview <n>`, with `<n>` the next unused round number (round 3 was the player launch; `docs/playout-setup.md` section 4 step 3). It uploads the new assets and the new `index.html` under `assets/preview/<n>/`. Open `https://listen.lma-radio.com/assets/preview/<n>/index.html`.
- [ ] **Step 3: HUMAN CHECKPOINT.** Shawn judges the preview on a phone and on a computer: tickets, block headings and spans, the lineup's seven tabs and the on-air highlight, 320 px with no sideways scroll. Wait for his word. Then, as a separate tool call, `ANTENNA_BUCKET=lma-radio npm run deploy:assets -- --remove-preview <n>`.
- [ ] **Step 4:** `ANTENNA_BUCKET=lma-radio npm run deploy:assets -- --dry-run` (shows the changed `assets/*.js`, the new `assets/programs.js` and `radio.css`). **HUMAN CHECKPOINT:** show the list and wait for approval. Then, as a separate tool call, `ANTENNA_BUCKET=lma-radio npm run deploy:assets`. The live page is now the old `index.html` with the new assets (Task 4's mixed-version tolerance): check it still plays and shows tickets.
- [ ] **Step 5:** Wait out the one-hour `max-age=3600` on the changed assets, then run `npx wrangler deploy --dry-run`. **HUMAN CHECKPOINT:** show the output and wait for approval. Then, as a separate tool call, `npx wrangler deploy`.
- [ ] **Step 6: Verify** on `https://listen.lma-radio.com/`: Coming up has block headings with spans, tickets read `LMA RADIO PRESENTS` (no titles yet), and the weekly lineup shows seven tabs with Today selected and the on-air block highlighted. Check a phone at 320 px as well. Rollback is the same order in reverse: revert, then `npx wrangler deploy` (the old `index.html`), `npm run deploy:assets`, `npm run pages` (the spec's reverse order). The same tolerance applies while cached new assets meet the old `index.html`.

---

### Task 17: emcee and llama releases

**Model hint:** sonnet. The tag push and the install are operator-gated.

- [ ] **Step 1:** Choose the version: `v2.22.0` (the latest tag is `v2.21.1`; lockstep, one tag builds both binaries). `CAMPAIGN_MIN_VERSION` stays `"2.20.0"`: it is a floor, and the campaign's pin gate is handled in Task 18.
- [ ] **Step 2: HUMAN CHECKPOINT.** Report the version and the release notes (dj_audio title, `emcee retitle`, `emcee lock`, the station lock in emcee and llama). On approval: `git tag -a v2.22.0 -m "<notes>" && git push origin v2.22.0`.
- [ ] **Step 3:** Watch with `gh run watch <id>`. If the macOS leg fails on notarytool `HTTP 403: A required agreement is missing or has expired`, the owner accepts the agreement at developer.apple.com, and after a short wait `gh run rerun <id> --failed`. Expected: every job green, with the Release carrying both macOS binaries and `SHA256SUMS`.
- [ ] **Step 4: HUMAN CHECKPOINT: install on the Mac.** Installing llama 2.22.0 makes the stopped campaign's gate refuse until it is re-pinned (Task 18). Confirm with the operator first. Then copy the current `~/.local/bin/{llama,emcee}` to `~/.llama-harness/pre-v2.22-bin/`, record each binary's `--version` output beside them (`~/.llama-harness/pre-v2.22-bin/versions.txt`), and write the restore step next to them (`~/.llama-harness/pre-v2.22-bin/RESTORE.txt`: copy both back into `~/.local/bin/` and check `--version` against `versions.txt`). Then `gh release download v2.22.0 -D ~/.llama-harness/release-v2.22.0` (the macOS assets and `SHA256SUMS`), verify with `shasum -a 256 -c` on those lines, and install both into `~/.local/bin/`. Check: `llama --version` and `emcee --version` both print 2.22.0, and `emcee lock show` prints `no station lock at /Volumes/media/lma-radio/delivered/.lma-station.lock`.

---

### Task 18: handoff note: re-pin the bulk-apply campaign

**Model hint:** sonnet.

- [ ] **Step 1:** Append a dated section to `~/.llama-harness/bulk-apply/handoff-campaign.md` (outside the repo; do not re-pin now). It says:
  - The campaign is stopped and pinned at llama v2.20.1, and v2.22.0 is now on PATH. Before resuming, re-pin with `bulk_apply.py pin --tag v2.22.0 --replace`, run from a new worktree at that tag with its own venv, then retire the v2.20.1 worktree.
  - v2.22.0's `bulk_apply` mark and unmark take the station lock and stop on a held one. The v2.20.1 worktree ignores it.
  - `emcee retitle` changes the sha256 of every stamped voiced manifest, so a wave snapshot restore covering a stamped show refuses with station-changed. Shawn accepted this on 2026-11-04. Awaiting-fix shows are not stamped until they are re-delivered and re-voiced.
- [ ] **Step 2:** Report the appended text in the task report.

---

### Task 19: go-live checks

**Model hint:** sonnet. The hugo steps run over ssh; record everything in `docs/superpowers/2026-11-04-programs-go-live.md` and commit it on `main` at the end of Task 20.

- [ ] **Step 1: hugo's delivered path.** On hugo, read `[station] root` from the transmitter config (`~/.transmitter/config.toml`, or `$TRANSMITTER_ROOT/config.toml`). Call it `<hugo-delivered>` below and record it; never hardcode it.
- [ ] **Step 2: Lock race on the Mac (required).** `python3 scripts/station_probe.py race --dir /Volumes/media/lma-radio/delivered --n 1000`. Expected: `double 0`, exit 0, no scratch file left (`ls -a` the folder for `.lock-race-*`). If `double` is above 0, stop: **HUMAN CHECKPOINT**, the lock is not safe over SMB, and the backfill does not run.
- [ ] **Step 3: mtime over SMB read back on hugo.** On the Mac: `python3 scripts/station_probe.py mtime --dir /Volumes/media/lma-radio/delivered --create` gives the name. On hugo: `stat -c %Y <hugo-delivered>/<name>`, so hugo's attribute cache holds the old entry. On the Mac: `... mtime --dir /Volumes/media/lma-radio/delivered --replace <name>` gives the expected seconds. On hugo, immediately: `stat -c %Y <hugo-delivered>/<name>`, which must equal the expected seconds; after 60 s, `stat` again with the same expectation. Then `--remove <name>` on the Mac. If they differ, stop: **HUMAN CHECKPOINT** (the backfill's mtime guard does not hold; the fallback is the second guard, running soon after hugo fills to `lead_hours`).
- [ ] **Step 4: Cross-host lock (best effort).** Use the same `--tag` on both sides, started within a few seconds of each other: `python3 scripts/station_probe.py cross --dir /Volumes/media/lma-radio/delivered --role a --n 300 --tag <t>` on the Mac and `python3 <repo>/scripts/station_probe.py cross --dir <hugo-delivered> --role b --n 300 --tag <t>` on hugo (system Python 3.11; the script is stdlib-only). Record both outputs. If hugo's mount is read-only (the create fails with a read-only or permission error), or the run cannot be shown clean, record it as an unverified limitation for the future hugo integration (spec, "Across hosts"); either way this does not block the backfill.

---

### Task 20: the title backfill

**Model hint:** sonnet. The `--yes` is operator-gated.

- [ ] **Step 1:** `emcee retitle --dry-run` (installed 2.22.0, `[station] root` on the SMB mount). Expected: 0 refused (all 710 voiced manifests reproduce as `json.dumps(m, indent=2)+"\n"`) and 136 awaiting fix (or today's count). Writes are the voiced shows whose profile has a title. Exit 0. Save the full output to the go-live doc.
- [ ] **Step 2: HUMAN CHECKPOINT.** Show the summary and a sample of the write lines and the refused or awaiting lists. Stop for Shawn's approval.
- [ ] **Step 3:** After approval, check hugo: `~/.venvs/transmitter/bin/transmitter status` shows the lead at `lead_hours` (filled). If it is mid-fill, wait for it to reach `lead_hours`. Then, in a separate tool call soon after, run `emcee retitle --yes`. Expected: every write printed (`<slug>: <old> -> <new>`), exit 0 (awaiting-fix, unchanged and unvoiced shows never affect it). A changed-before-rename skip exits 1 and lists the slugs; re-run the dry run for them.
- [ ] **Step 4: Verify.** `emcee retitle --dry-run` shows 0 to write. For three stamped manifests, `stat -f %m` equals `mtime_ns // 10**9` from the backup `record.jsonl`. On hugo, `transmitter library` shows no rise in ineligible packages, and `transmitter status` shows no dropped planned shows. Within a few minutes, `timeline.json` shows non-null `program` on stamped shows and the page's tickets name their programs.
- [ ] **Step 5:** Commit `docs/superpowers/2026-11-04-programs-go-live.md` (the checks, the dry run, the `--yes` output summary and the backup directory path) on `main`. The push is the operator's call.
