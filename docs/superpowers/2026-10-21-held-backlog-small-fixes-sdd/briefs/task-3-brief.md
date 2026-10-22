### Task 3: Harness `venue_changes.txt` report

**Files:**
- Modify: `scripts/replay_holds.py` (`OUTPUT_FILES`, new `_venue_changes`, `compare`, `summary.txt`)
- Test: `scripts/test_replay_holds.py`

**Interfaces:**
- Consumes: the arm row keys `venue`/`city` (each `{"old", "new"}` or null, where null means "replay equals the stored value"), `state`, `outcome`, and `_all_flags(r)`.
- Produces: `_venue_changes(base: dict, cand: dict) -> tuple[list[str], int, int]`, which returns the lines, the number of shows listed, and how many of those have a flag change. It writes `venue_changes.txt` and adds the summary line `f"venue_changes.txt: {n} show(s), {m} with a flag change"`.

Rules (plan's call):
- Each arm's shipped value of a field is `row[field]["new"]` when the row has a diff. Otherwise it is the stored value, which is `old` from whichever arm has a diff.
- A show is listed when base and cand differ on venue or city.
- Shows that are `unreplayable` in either arm are skipped and counted in a header line, because their fields are absent.
- Each row, in slug order:
  - `f"{slug}  [{state}]"` plus `"  DELIVERED"` when the cand `state == "delivered"`
  - `f"  venue: {_j(bv)} -> {_j(cv)}"`
  - `f"  city: {_j(bc)} -> {_j(cc)}"`
  - `"  flags: unchanged"`, or `f"  flags CHANGED: added {_j(sorted(added))}; removed {_j(sorted(removed))}"` over `_all_flags`

- [ ] **Step 1: Write the failing tests**

```python
def _venue(arm, slug, new, state=None, old="RFK Stadium"):
    s = arm["shows"][slug]
    s["venue"] = {"old": old, "new": new}
    if state:
        s["state"] = state

def test_venue_changes_lists_both_strings_and_delivery(tmp_path):
    slug = "gratefuldead-1973-06-11"
    base, cand = _two_arms(tmp_path, mutate_cand=lambda a: _venue(a, slug, "R.F.K. Stadium", "delivered"),
                           mutate_base=lambda a: a["shows"][slug].update(state="delivered"))
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "venue_changes.txt").read_text()
    assert f"{slug}  [delivered]  DELIVERED" in text
    assert 'venue: "RFK Stadium" -> "R.F.K. Stadium"' in text and "flags: unchanged" in text
    assert "venue_changes.txt: 1 show(s), 0 with a flag change" in (out / "summary.txt").read_text()
    assert "venue_changes.txt" in rh.OUTPUT_FILES

def test_venue_changes_ignores_an_identical_diff_and_counts_a_flag_change(tmp_path):
    slug = "gratefuldead-1973-06-11"
    def both(a): _venue(a, slug, "R.F.K. Stadium")
    def cand_m(a):
        both(a)
        a["shows"][slug]["city"] = {"old": "Washington, DC", "new": "Washington, D.C."}
        a["shows"][slug]["gather_flags"] = ["venue mismatch: archive 'A' vs jerrybase 'B'"]
    base, cand = _two_arms(tmp_path, mutate_cand=cand_m, mutate_base=both)
    out = tmp_path / "cmp"
    assert rh.main(["compare", str(base), str(cand), "--out", str(out)]) == 0
    text = (out / "venue_changes.txt").read_text()
    assert "R.F.K. Stadium" in text                                   # unchanged venue still shown on the row
    assert 'city: "Washington, DC" -> "Washington, D.C."' in text
    assert "flags CHANGED: added" in text
    assert "venue_changes.txt: 1 show(s), 1 with a flag change" in (out / "summary.txt").read_text()
```

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest scripts/test_replay_holds.py -q -k venue_changes`
Expected: FAIL, because there is no `venue_changes.txt`.

- [ ] **Step 3: Implement**

Add `"venue_changes.txt"` to `OUTPUT_FILES`, implement `_venue_changes`, and call it in `compare` next to `packaged_exposure.txt`. Add the summary line after the `packaged_exposure.txt` line.

- [ ] **Step 4: Run the file's tests, then the full suite**

Run: `./.venv/bin/python -m pytest scripts/test_replay_holds.py -q`, then `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/replay_holds.py scripts/test_replay_holds.py
git commit -m "feat(harness): venue_changes.txt lists shipped venue/city changes between arms"
```

---

