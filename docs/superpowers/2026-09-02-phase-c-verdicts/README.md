# Phase C — sibling title transfer: reviewer verdicts and task briefs

The audit trail beneath `docs/superpowers/2026-09-02-sibling-transfer-evidence.md`
(the measurements) and `2026-09-02-sibling-transfer-sdd-ledger.md` (the rulings).

Every agent that ran during Phase C wrote one report. Reviewer verdicts state the
verdict, then the method the verdict rests on — which mutation was applied, the
verbatim failing output, how the out-of-worktree copy was proven to shadow the real
package, whether `__pycache__` was purged, and what could **not** be verified.

Preserved because they lived in gitignored `.superpowers/` and a `/private/tmp`
scratchpad, both of which are lost on cleanup. The evidence doc and ledger are the
durable record; these are what makes their numbers auditable rather than merely
believable.

## Naming

- `tN-rev-spec` / `tN-rev-qual` — the two independent Opus reviewers for task N.
- `tN-rerev` — the scoped re-review that closed task N's fix round.
- `tN-<name>` — the implementer's own report (e.g. `t3-siblings`, `t5-gather`).
- `final-review` / `final-rerev` / `final-fix` — the whole-branch review and its wave.
- `phb-audit` — retrospective audit of Phase B's mutation results after the
  `.venv/bin` shebang defect was found (verdict: Phase B sound, nothing merged
  rests on an invalid run).
- `t7-singledonor` — the merge-blocking measurement that sized the single-donor
  population (1.26% of targets, one slide case, stopped twice).
- `task-N-brief.md` — the requirements file each implementer was dispatched with.

## Findings worth reading first

- `t5-rev-qual` — the automatic band gate was deletable with all 1,629 tests green;
  the tests that named it passed for an unrelated reason (zero-anchor tapes).
- `final-review` — `FLOOR = 0.50` was half-loose: the both-directions rule passed
  because the mutation landed far from the boundary.
- `t4-rerev` — the donor-span-slide fixture had the right arithmetic signature but
  stipulated its error rather than exhibiting one.
- `t7-rev-spec` — reproduced Task 7's cache independently (716 targets / 11,258
  pairs / 230,600 rows) rather than reading the doc.
