# Handoff: Taper's Section allowlist, ready to implement

Date: 2026-11-09. From the design session `llama-tapersection`.

## Where things are

- **Worktree:** `/Users/shawn/projects/llama/.claude/worktrees/taperssection`, branch `taperssection-allowlist`, off `main` @ `1079044f`. Nothing is merged or pushed.
- **Spec:** `docs/superpowers/specs/2026-11-09-taperssection-allowlist-design.md`.
  - Approved by the operator.
  - Two Opus review rounds, both reviewers rating the foundation SOUND. Review then stopped on circuit-breakers: spec growth over 50% and most round-2 findings being faults in round-1 fixes. The lineage rule was simplified to a stated rule plus nine acceptance cases.
- **Plan:** `docs/superpowers/plans/2026-11-09-taperssection-allowlist.md` (commit `35e34dc2`, 615 lines).
  - Tasks 0, 1, 2, 2b, 3, 4, 5, 6a, 6b, 7, 8, 9, 10, 11, 12.
  - Run 6b after 7.
  - Reviewed by two blind Opus reviewers. All 36 findings were accepted and applied, including the Critical: allowlist-aware stages fail closed on a `ts-` key, and `process_show` requires the allowlist.
- **The worktree has no `.venv` yet.** Task 0, Step 0 creates it. Run tests as `./.venv/bin/python -m pytest -q` from the worktree, never with a bare `pytest`.

## How to run it

- **Execution method:** not chosen yet. Ask the operator.
  - Recommended: **subagent-driven**, via a peer orchestrator on Opus per `~/.claude/CLAUDE.md`. There are 15 tasks with heavy shared interfaces, so per-task review earns its cost.
  - Implementers on Sonnet for the mechanical tasks: 1, 2, 3, 7, 11. Use Opus for 4, 5, 6a, 6b, 8, 9, 10 and 12; they thread through the guarded surface. Ask the operator if this split looks borderline.
  - Reviewers always on Opus.
- **Final branch reviewer: Opus** (the spec's review mode).
- **Two operator checkpoints** (STOP and ask):
  - **Checkpoint A**, after Task 2. Lineage coverage and precision on the Phish catalogue, plus the date-cross-check drop count. The operator rules rule (a) or (b), with this guidance:
    - if the vast majority of unknown dates gain positive evidence → (a);
    - if only a minority do → likely (b).
  - **Checkpoint B**, after Task 8. A live-LLM scorer measurement over about 20 Phish shows; the operator approves the spend first. It checks the spread against `min_quality_score` 6.0 and consistency across batch orders.

## Operator rulings to carry (verbatim intent)

- **Allowlist, not the whole collection.** Phish and Garcia get dedicated profiles. Others join existing profiles through discovery.
- **Show merit is downloads per day since upload** (age-adjusted): "we'll see how helpful a signal it is in practice." phish.net ratings are wanted later, not in phase 1.
- **Phish ships audience tapes only.** This is the operator's choice. An unclassified tape for a restricted-policy artist holds ("for now let's say held").
- **Permission is not a strict surface** ("we're pretty under the radar"). The guarded surface is no regression for LMA artists.
- **Misattribution needs checking.** Uploader metadata lies: `gd2015-05-14` is filed as "Grateful Dead" but is a 2015 tribute. This motivates the `active_*` bounds and the scorer's attribution check.
- **The build never writes `~/.llama/config.toml`.**

## Not in the plan (separate work)

- **The research round.** Sonnet workers per artist, Opus synthesis. It records each artist's taping and hosting policy with sources and suggests `[[taperssection.artists]]` entries. Write it to a file NOT named REPORT/SUMMARY/FINDINGS/ANALYSIS. Context so far:
  - DMB was removed from archive.org in 2003 at the band's request;
  - Phish management reportedly bars LMA hosting (unconfirmed);
  - nothing was found on Garcia.
- **The `phish` and `garcia` profiles.** Operator work, first runs with `human_gate = true`.
- **The pin-plus-exclude profile enhancement** (excluded-artists backlog). Not a prerequisite. Until it lands, `jam` and `dead-family` will discover Phish and Garcia.

## Evidence and data from this session

- **Scratchpad** (session-local, may be gone): `/private/tmp/claude-501/-Users-shawn-projects-llama/687ed1b3-5ef1-41b7-9a1e-e519208cfcd0/scratchpad/`.
  - `ts/items.json`: the full 31,096-item scrape.
  - `ts/by_artist.json`.
  - The round decision files: `r1-decisions.md`, `r2-decisions.md`, `plan-decisions.md`.

  The plan re-derives everything it needs through `scripts/taperssection_probe.py` (Task 0).
- **Key numbers**, all in the spec:
  - Phish: 11,134 items on 1,882 dates;
  - 80% of dates are unknown lineage under today's `lineage_class`;
  - 168 Phish items have a date that disagrees with their identifier or title;
  - the download counter reads 0 for the first 45-60 days, hence the 75-day no-evidence rule.
