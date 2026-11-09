# Taper's Section allowlist: acceptance (plan Task 12)

Branch `taperssection-allowlist`, worktree `.claude/worktrees/taperssection`, from
merge base `1079044f`. Steps 1, 4 and 5 are offline (fake LLM backend, captured
fixtures, no live archive.org). Step 2's replay is blocked on an operator ruling.
Step 3 ran live with operator approval.

## Step 1: offline end-to-end

`packages/llama/tests/test_taperssection_e2e.py` drives `llama get "<query>" --auto`
through interpret, search, winnow, select, gather, research, vet, brief and package.
The config holds a populated allowlist (Phish `aud`; Jerry Garcia `sbd`/`aud` with
`jerrybase = "Jerry Garcia Band"`). The fake IA serves the Task 0 fixtures to every
scrape: the search query and the taperssection download-index build. The test asserts
that every scrape targeted `collection:taperssection`.

- **Phish**, `phish1997-12-29.003886.newyork.mk41.cmc6.flac1644`: packages as
  `shows/ts-phish-1997-12-29` with `artist == "Phish"`, performance id
  `ts-phish/1997-12-29`, 15 tracks, a vetted briefing, `needs_review` false and
  `review_flags == []`. Neither Task 10 hold fires: the scorer verdict carries
  `attribution: "ok"` (stored in `provenance.json`), and `ts_rules.classify` reads the
  item as `aud` ("Source: DFOB: Schoeps CMC6/MK41> ...").
- **Garcia**, `jg82-06-24.079428.jgb.sbd.late.sbeok.t-flac16`: jerrybase has two JGB
  events on 1982-06-24, so the late-show tape groups into `ts-jerry-garcia/1982-06-24/e2`
  (slug `ts-jerry-garcia-1982-06-24-e2`). The package carries jerrybase evidence:
  `structure.alignment == "jerrybase"`, the note `set breaks anchored from jerrybase`,
  and `set_breaks == [8]`, i.e. set 1 closes on Run For The Roses with Deal as the
  encore (the late event's rows). Venue Capitol Theatre, no review flags.
- Checked by changing the config in a scratch run, never in the tree. With `jerrybase`
  removed from the Garcia entry, the Garcia test fails: no `/e2` show exists, so the
  test is pinned on the routing. With the Phish entry set to `lineages = ["sbd"]`, the
  Phish test fails: nothing is shortlisted.
- One fixture fact the test records: the Phish item's own description defeats the
  deterministic alignment. `parse_setlist` keeps the `s1t01 - ` prefixes and reads the
  appended "original text file" block as extra encore items. Coverage then falls under
  the threshold and gather calls `align_structure`, as it would in production. The fake
  answers with the tape's layout. This comes from the LMA parser, not from the
  allowlist.

Command: `./.venv/bin/python -m pytest -q packages/llama/tests/test_taperssection_e2e.py`
gives 2 passed (commit `4e64ee90`).

## Step 2: empty-allowlist regression

**Full suite:** `./.venv/bin/python -m pytest -q` gives 7965 passed, 1 skipped, 8
deselected. The baseline before Task 12 was 7963 passed; Task 12 adds the 2 end-to-end
tests.

**Two-arm replay: BLOCKED-ON-RULING, not run.** Operator ruling R6 allows the replay
read-only over `~/.llama/shows` only. `scripts/replay_holds.py` needs more of
`~/.llama` than that. Read from the source, not run:

| path | read by | why |
|---|---|---|
| `~/.llama/config.toml` | `run` (`args.config or DEFAULT_ROOT / "config.toml"`) and `compare` (`_delivery_path`) | the default config. `--config` accepts a scratch file, but `root` must still be `~/.llama` to reach the shows. |
| `~/.llama/ledger.jsonl` | `run`: `Ledger(root / "ledger.jsonl").entries()` | the delivered set, which feeds `derive_state` and the replay's state |
| `~/.llama/cache/md_<id>.json` | `CacheOnlyIA(root / "cache")` in `run`; `_description` in `compare` | the replay is cache-only: every show's archive.org metadata |
| `~/.llama/cache/<setlist.fm key>.json` | `setlistfm_client(config)` -> `CacheOnlySetlistFM(config.root / "cache")` | setlist.fm evidence, when a key is configured |
| `~/.llama/shows/**` | `_targets`, `replay_show`, `compare` | allowed |
| `<delivery_path>/<slug>/manifest.json` (station root) | `compare` -> `_is_voiced` -> `cli._destination_is_voiced` | the voiced check, read-only. It is off when the config has no `delivery_path`. |

Writes: only `--out` (refused if it overlaps the root), `--scratch` (default
`tempfile.mkdtemp`, outside `~/.llama`) and the `compare --out` directory. Nothing is
written under `~/.llama`.

A scratch config whose `root` is a scratch directory with only `shows` linked in would
satisfy R6. It would also empty the cache and the ledger, so every show would replay
as a cache miss (unreplayable) and the arms would measure nothing. The ruling needs
one of these:

- (a) allow read-only access to `~/.llama/cache` and `~/.llama/ledger.jsonl`, with
  `--config` set to a scratch config whose `root = "/Users/shawn/.llama"`, `[jerrybase]`
  and `[structure]` copied from the operator's, and no `delivery_path` (voiced check
  off). The arms then reflect that config, not the operator's.
- (b) the same, plus a read of `~/.llama/config.toml` itself, which gives the
  operator's real config fingerprint and the voiced check.

The baseline tree was not materialized. No path under `~/.llama` was read or written
for Step 2. Commands for when the ruling lands (write check included):

```
H=~/.llama-harness/taperssection; S=<scratchpad>/t12; mkdir -p $H/baseline-tree
touch $S/stamp
git archive 1079044f | tar -x -C $H/baseline-tree
python3 -m venv $H/baseline-tree/.venv
$H/baseline-tree/.venv/bin/python -m pip install -e $H/baseline-tree/packages/herder -e $H/baseline-tree/packages/llama
$H/baseline-tree/.venv/bin/python -c "import llama; print(llama.__file__)"      # must be inside baseline-tree
(cd $H/baseline-tree && .venv/bin/python scripts/replay_holds.py run --all --config <cfg> --out $H/base-all.json)
./.venv/bin/python scripts/replay_holds.py run --all --config <cfg> --out $H/cand-all.json   # empty allowlist
./.venv/bin/python scripts/replay_holds.py compare $H/base-all.json $H/cand-all.json --config <cfg> --out $H/cmp-all
find ~/.llama/shows -newer $S/stamp | head      # must be empty
```

## Step 3: live smoke

**Result: pass on both commands.** Run 2026-11-09 with operator approval (both
commands, plan only, scratch config and workspace outside `~/.llama`), from the
worktree root at `c41a8b52`, with `./.venv/bin/python -m llama`.

Scratch config `<scratchpad>/t12smoke/ts-config.toml` (`root` is
`<scratchpad>/t12smoke/root`; the backend is the operator's production `claude_cli`
with default tiers):

```toml
root = "<scratchpad>/t12smoke/root"

[llm.default]
backend = "claude_cli"

[[taperssection.artists]]
name = "Phish"
creators = ["Phish"]
lineages = ["aud"]
exclude = ["webcast", "livephish"]
note = "audience only by operator choice; see research record"

[[taperssection.artists]]
name = "Warren Haynes"
creators = ["Warren Haynes"]
lineages = ["aud", "sbd", "matrix"]
```

The Phish entry is the spec's example. The spec gives Warren Haynes no lineages or
extra spellings, so the entry uses the brief's default `["aud", "sbd", "matrix"]`
and the one creator spelling `Warren Haynes` (the premises survey counts 51
exact-creator items for it).

**`llama --config <cfg> get "Phish 1997-11-22" --plan`** (exit 0). Key lines:

```
searching Taper's Section
scrape: 18/18 docs
building taperssection index (one request per allowlisted artist)
scrape: 11,133/1,133 docs
scrape: 91/91 docs
winnow: 1 candidates -> 1 after library+ledger -> 1 after mechanical
winnow: scoring reviews (1 batches)
winnow: researching shortlist (1 shows)
 1. 1997-11-22  Phish               ?                           score 3.3
      There are no reviews. The baseline comes from the 33rd download percentile, ...
shortlist ready — nothing processed.
```

- `criteria.json`: `collection: "ts-phish"`, `artist: "Phish"`, date 1997-11-22 to
  1997-11-22. Interpret resolved the query to `ts-phish` through the allowlist.
- One candidate, `ts-phish/1997-11-22`, with 18 taperssection recordings. The scorer
  verdict has `attribution: "ok"` and score 3.3: no reviews, a below-floor baseline
  from the download percentile. It shortlisted anyway because a single-date query
  skips the quality floor for ts shows. light_research found the show's reputation
  (phish.net "Best of 1997", JamBase).
- The session parked as awaiting approval (`llama run approve 2026-11-09-phish-1997-11-22`).
  Nothing was processed, downloaded or delivered. The scratch root holds only
  `runs/<session>/` (request, criteria, candidates, shortlist, session) and `cache/`
  (one item's metadata and `taperssection_index.json`, two artists).

Observations, none a failure of this step:

- The venue prints as `?`: a taperssection candidate carries no venue (the LMA
  `venue` field is absent there). light_research found Hampton Coliseum from the date.
- winnow's review fetch picked a set-1-only item
  (`ph1997-11-22d1t04...kmi84.set1.flac16`) as the show's best recording. The scorer
  lists "Source one (KMi84) is missing Set II" among its complaints. Recording
  selection happens later, in select, so this changes only which item's reviews the
  scorer read. It is the per-set case Step 4 records.
- `scrape: 11,133/1,133 docs` is cosmetic and comes from existing code: archive.org's
  scrape API reports the *remaining* count as `total` on cursor pages. The artist
  index build shows the same thing (`270,000/36,834`). `ia_client.scrape` is
  unchanged by this branch.

**`llama --config <cfg> artists "blues rock"`** (exit 0). It built the LMA artist
index (9,334 collections). It reused the taperssection index the `get` run had just
built, with no rebuild line. Then it made one matcher call. Key lines:

```
building artist index (~30 requests, a minute or two)
matching artists against the artist inventory (LLM)
 1. Derek Trucks Band                          1063 rec  1991-2009     3.4M dl
 2. Tedeschi Trucks Band                       1353 rec  2010-2026     5.0M dl
 3. North Mississippi Allstars                 1536 rec  1998-2026     1.7M dl
 4. Warren Haynes                                51 rec  1993-2026    18.8k dl
      Premier blues-rock guitarist and vocalist, Taper's Section recordings
 5. Marcus King Band                            374 rec  2014-2026   559.4k dl
 ...
20. Robert Jon & The Wreck                       44 rec  2021-2026    14.4k dl
```

Warren Haynes is listed at rank 4 with 51 recordings, the survey's exact-creator
count. The matcher saw the `Taper's Section` annotation (the "artist inventory"
step label and the reason text). Phish is not listed, which is right for the query.

**LLM calls: 4**, against an approved estimate of about 2-3 and a stop line of 6.
`get --plan` made 3: interpret, score_reviews (one ts batch) and light_research (one
shortlist entry). `artists` made 1: find_artists. The count comes from the code path
(`_get_query` -> `_execute` -> `run_winnow`; `artists` -> `find_matching_artists`)
and from the step lines above. The `pacing:` line is the live `/usage` meter read,
which costs no tokens. No retry or `llm-failures/` directory appeared.

**`~/.llama`:** nothing was read or written. Both commands ran with `--config` on the
scratch file, whose `root` is the scratch directory. `load_config` reads only the
given path, and every write went under the scratch root (`runs/`, `cache/`). No
command named `~/.llama` or the station root. Full output:
`.superpowers/sdd/taperssection/t12-smoke/t12-smoke.log` (not committed).

## Step 4: per-set items

**Result: no.** No existing hold catches a per-set item as such.

The dates come from `lineage-dates.csv`: 15 Phish dates whose only classified-`aud`
item carries a `set2`/`set3`/`partial` token. Two were run offline, each through the
same `llama get --auto` harness as Step 1. Each run used the item's real scrape doc
(description, title, addeddate and downloads, from the Checkpoint A probe cache), a
file list built from the description's own track list, and fake LLM answers.

- `phish1991-02-22.035119.carrboro.aud.set2.flac16`: set 2 only, 9 tracks. Its one
  sibling, `...sbd.set2.partial`, is forbidden under an `aud` entry. The description
  gives no durations, so the file list uses 330 s per track as a stand-in.
  `parse_setlist` ranks no parse, so the `extract_setlist` fake returns the
  description's list as set 2. The alignment is deterministic, with coverage 1.0.
  **It packages with `review_flags == []`.** It holds only when the research LLM states
  an explicit set total: vet's `research asserts 2 sets but structure has 1`
  (research-sets). That depends on the research text, not on the item.
- `phish1990-01-29.096764.ithaca.aud.set2.flac16` ("Set II-partial" plus encore, 10
  tracks, real durations; the date's only taperssection item). It holds, but on
  `low-confidence setlist`: the description's parse is weak. The hold is not about the
  missing set. With `align_structure` failing, `low-confidence structure alignment` is
  added. With the LLM answering set 2 or set 1 for the partial set, nothing else is
  added. A research claim of 2 sets adds research-sets, as above.
- The structure guard (`single-set structure for a long show`) needs 150 minutes
  (`guard_min_minutes`), so one set never trips it. `setlist evidence shows multiple
  sets` needs more than one numbered set in the evidence, and a set-2-only item has
  one.

This is recorded as a known limitation in `packages/llama/CLAUDE.md` (Taper's Section
bullet). Per the plan, no new mechanism was added. The probe script and its outputs
are in the session scratchpad, not the repo.

## Step 5: spec Success #1

**Spec Success #1 (profile runs that deliver taperssection shows) is operator
follow-up**, after the research round. Acceptance measures the pipeline offline and,
once approved, live via `--plan`. A profile run that delivers is the operator's to run
and judge.
