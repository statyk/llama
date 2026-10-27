### Task 1: Overrule records and flag normalisation

**Spec:** "Overrules persist" (Matching). **Implementer: Sonnet.**

**Files:** Modify `packages/llama/src/llama/models.py`; Create `packages/llama/src/llama/overrules.py`, `packages/llama/tests/fixtures/arm_flags.json`; Test `packages/llama/tests/test_overrules.py` (new).

**Interfaces:**
- Produces in `models.py`: `class Overrule(BaseModel): identifier: str; kind: str; subject: list[str] | None = None; flag: str; source: str; at: str`; `Overrides.overrules: list[Overrule] = Field(default_factory=list)` (after `encore_after`).
- Produces in `overrules.py`:

```python
NOTE_PREFIX = "overruled: "
class FlagKey(NamedTuple):
    kind: str
    subject: tuple[str, ...] | None
def flag_key(flag: str, show: Show) -> FlagKey | None       # None: not overrulable (package family)
def rule_matches(rule: Overrule, key: FlagKey, identifier: str) -> bool
def split_overruled(flags: list[str], rules: Sequence[Overrule], show: Show
                    ) -> tuple[list[str], list[str]]          # (still holding, notes "overruled: <flag>")
def records_for(flags: list[str], show: Show, *, source: str, at: str) -> list[Overrule]
def merge_rules(existing: Sequence[Overrule], new: Sequence[Overrule]) -> list[Overrule]
    # appends new ones; one with the same (identifier, kind, subject) as an existing rule is dropped
```

- [ ] **Step 1: Build the fixture.** One read-only one-liner writes the sorted unique strings of `flags`, `gather_flags`, `vet_flags`, `brief_flags` and `stored_flags` over every row of `~/.llama-harness/piece4/migration-post.json` and `migration-base.json` to `arm_flags.json` (2,016 strings when written; record count and sha256 in the commit message).
- [ ] **Step 2: Write the failing tests:**
  - `test_every_arm_flag_has_a_kind`: for every fixture string, `flag_key(f, show)` is None exactly when `f.startswith("duration mismatch on ")`, and never has kind `other`.
  - `test_subjects`: `research asserts unknown song: Fixin’ to Die` → `("research-song", ("fixin' to die",))`; `jerrybase set closer 'Knockin' on Heaven's Door' is not at a set break` → subject `("knockin' on heaven's door",)`; the venue example in Contracts → two-item subject; `research asserts 1973-09-17; item date 1973-01-01 looks like a year-only placeholder` → `("research-date", ("1973-09-17",))`; `single-set structure for a long show (155 min)` and `(199 min)` give equal keys.
  - `test_titles_subject_is_a_subset_match`: a rule recorded with unresolved `{a.mp3, b.mp3}` matches a show whose unresolved set is `{a.mp3}` and not one with `{a.mp3, c.mp3}`.
  - `test_another_identifier_never_matches`.
  - `test_split_overruled`: two flags, one matching → `(["unmatched"], ["overruled: matched"])`; order of held flags preserved.
  - `test_records_for_skips_package_flags_and_merge_dedupes`.
  - `test_old_overrides_json_reads_no_overrules` **(pin)** and `test_overrules_round_trip_through_write_artifact`.
- [ ] **Step 3:** Run `./.venv/bin/python -m pytest packages/llama/tests/test_overrules.py -q` → FAIL (ImportError).
- [ ] **Step 4: Implement** per the Contracts table; `fold_curly_apostrophes` comes from `llama.structure`. `overrules.py` must not import `llama.replay` or any stage (gather imports it).
- [ ] **Step 5:** Full suite → PASS. Commit `feat(overrules): overrule records and per-family flag keys`.

---

