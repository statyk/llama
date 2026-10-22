### Task 2: Slice B, a tied venue vote ships the selected recording's string

**Files:**
- Modify: `packages/llama/src/llama/stages/gather.py` (new `venue_tie_break`, wired into the venue chain in `compute_gather`)
- Modify: `CLAUDE.md` (one sentence in the "Tier 1 held-backlog guards" bullet)
- Test: `packages/llama/tests/test_stage_gather.py` (new section `# --- slice B: venue tie-break ---`)

**Interfaces:**
- Consumes: `grouping._make_candidate(pid, collection, recs)` (tests build candidates through it so the vote is grouping's), `structure.cities_compatible`, `venues_equivalent`, `_venues_equivalent_pre1b`, `gather._stripped`.
- Produces: `gather.venue_tie_break(candidate: Candidate, sel: RecordingSummary | None) -> tuple[str, str | None] | None`. It returns `(venue, city)` to ship, or `None` when the tie-break does not apply. It returns a value only when all of these hold:
  1. `sel` is not None and `_stripped(sel.venue)` is non-empty.
  2. With `counts = Counter(r.venue for r in candidate.recordings if r.venue)` (raw strings, exactly as `grouping._make_candidate` counts), the selected string has as many votes as the vote string: `counts.get(sel.venue, 0) == counts.get(candidate.venue, 0)`, and that count is > 0.
  3. `sel.venue != candidate.venue`.
  4. `_stripped(sel.coverage)` is None, or `cities_compatible(sel_city, candidate.city)`.

  The value returned is `(_stripped(sel.venue), sel_city or candidate.city)`. A candidate whose vote string is not among its recordings' venues (hand-edited, as `test_1d_does_not_fire_without_a_selected_city_or_with_compatible_cities` builds one) never ties, so that test stays green unmodified.

- [ ] **Step 1: Write the failing tests**

All tests use this file's `StubIA`, `IDENT` (gd73), `DSO`/`DSO_IDENT`, `_gather` and `_penns_landing_event`. The helper `RS = RecordingSummary` sets `date` on each recording. Build candidates with `_make_candidate`, and assert `cand.venue` (the vote) first, so the test documents the tie.

```python
from llama.grouping import _make_candidate
from llama.stages.gather import venue_tie_break

def _cand(pid, coll, date, *specs):   # specs: (identifier, venue, coverage)
    return _make_candidate(pid, coll, [RecordingSummary(identifier=i, date=date, venue=v, coverage=c)
                                       for i, v, c in specs])

def _gd(tmp_path, cand):
    return compute_gather(ShowWorkspace(tmp_path / "s"), StubIA(), None, cand, IDENT, jerrybase_enabled=False)

def _venue_flags(show):
    return [f for f in show.review_flags if f.startswith(("venue mismatch", "recordings of this date disagree"))]

def test_tie_ships_the_selected_recordings_string_without_jerrybase(tmp_path):
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "R.F.K. Stadium", "Washington"), (IDENT, " RFK Stadium ", "Washington, DC"))
    assert cand.venue == "R.F.K. Stadium"                         # listing order won the 1-1 tie
    res = _gd(tmp_path, cand)
    assert (res.show.venue, res.show.city, res.show.venue_source) == ("RFK Stadium", "Washington, DC", "item")
    assert _venue_flags(res.show) == []

def test_a_majority_keeps_the_consensus(tmp_path):   # (pin)
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("a", "R.F.K. Stadium", "Washington, DC"), ("b", "R.F.K. Stadium", "Washington, DC"),
                 (IDENT, "RFK Stadium", "Washington, DC"))
    assert _gd(tmp_path, cand).show.venue == "R.F.K. Stadium"

def test_a_tie_whose_selected_city_is_incompatible_ships_the_vote_unchanged(tmp_path):   # (pin)
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "RFK Stadium", "Washington, DC"), (IDENT, "RFK Stadium ", "Baltimore, MD"))
    res = _gd(tmp_path, cand)
    assert (res.show.venue, res.show.city) == ("RFK Stadium", "Washington, DC")

def test_a_tie_with_a_blank_selected_city_keeps_the_vote_city(tmp_path):
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "R.F.K. Stadium", "Washington, DC"), (IDENT, "RFK Stadium", None))
    assert (lambda s: (s.venue, s.city))(_gd(tmp_path, cand).show) == ("RFK Stadium", "Washington, DC")

def test_a_whitespace_only_selected_venue_never_ships(tmp_path):   # (pin) Review Focus 3
    cand = _cand("GratefulDead/1973-06-10", "GratefulDead", "1973-06-10",
                 ("gd73-other", "RFK Stadium", "Washington, DC"), (IDENT, "   ", "Washington, DC"))
    assert _gd(tmp_path, cand).show.venue == "RFK Stadium"

def test_step_1_tie_ships_the_selected_string_jerrybase_corroborates(tmp_path, monkeypatch):
    _penns_landing_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Philadelphia, PA"), (DSO_IDENT, "Penns Landing", "Philadelphia, PA"))
    assert cand.venue == "Penn's Landing"
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penns Landing" and _venue_flags(res.show) == []

def test_step_1_tie_keeps_the_vote_when_the_selected_string_is_newly_equivalent_and_cities_conflict(tmp_path, monkeypatch):   # (pin)
    # Narrowing S: the vote passes step 1 on pre-1b equivalence alone; the selected string is
    # equivalent only under 1b, and Camden is not jerrybase's Philadelphia, so it fails step 1's full test.
    _penns_landing_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Camden, NJ"), (DSO_IDENT, "Penns Landing", "Camden, NJ"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penn's Landing" and _venue_flags(res.show) == []

def test_step_1_tie_keeps_the_vote_when_jerrybase_does_not_corroborate_the_selected_string(tmp_path):   # (pin)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Barrymore Theatre", "Madison, WI"), (DSO_IDENT, "Orpheum Theater", "Madison, WI"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Barrymore Theatre" and _venue_flags(res.show) == []

def _blank_venue_event(monkeypatch, city="Philadelphia", state="PA"):
    from llama.models import JerrybaseEvent
    ev = JerrybaseEvent(event_id="e1", venue="", city=city, state=state)
    monkeypatch.setattr(gather_mod.jerrybase, "lookup", lambda artist, date: [ev])

def test_1a_tie_ships_the_selected_string_when_cities_agree(tmp_path, monkeypatch):
    _blank_venue_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Philadelphia, PA"), (DSO_IDENT, "Penns Landing", "Philadelphia, PA"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penns Landing" and _venue_flags(res.show) == []

def test_1a_tie_keeps_the_vote_when_the_cities_conflict(tmp_path, monkeypatch):   # (pin)
    _blank_venue_event(monkeypatch)
    cand = _cand("DarkStarOrchestra/2003-01-25", "DarkStarOrchestra", "2003-01-25",
                 ("ds-other", "Penn's Landing", "Camden, NJ"), (DSO_IDENT, "Penns Landing", "Camden, NJ"))
    res = _gather(tmp_path, DSO, cand, DSO_IDENT)
    assert res.show.venue == "Penn's Landing"
    assert "venue mismatch: archive 'Penn's Landing' vs jerrybase ''" in res.show.review_flags

def test_venue_tie_break_unit_cases():
    recs = [RecordingSummary(identifier="a", venue="X Hall", coverage="Austin, TX"),
            RecordingSummary(identifier="b", venue="X Hall ", coverage=None)]
    cand = _make_candidate("A/2000-01-01", "A", recs)
    assert venue_tie_break(cand, recs[1]) == ("X Hall", "Austin, TX")   # raw strings counted apart
    assert venue_tie_break(cand, recs[0]) is None                        # the selected string IS the vote
    assert venue_tie_break(cand, None) is None
    odd = cand.model_copy(update={"venue": "Elsewhere"})                 # a vote no recording carries
    assert venue_tie_break(odd, recs[1]) is None
    stray = RecordingSummary(identifier="z", venue="Y Hall", coverage=None)
    assert venue_tie_break(odd, stray) is None                           # 0 == 0 is not a tie
```

No separate "never changes a flag" test (plan's choice: dropped). With jerrybase off no venue flag can arise, so it was vacuous. Every arm test above asserts its venue flags (`_venue_flags(...) == []`, or the exact 1a flag), and Task 9's venue/city flag check covers the library.

Must stay green unmodified (the arms that keep the vote and flag): `test_the_signature_blocks_the_swap_when_the_selected_tape_agrees_with_jerrybase` (a hand-built 1-1 tie in which the selected Uptown tape agrees with jerrybase, and the signature arm must keep `'Rambler Room, Loyola College'`), and `test_1d_does_not_fire_without_a_selected_city_or_with_compatible_cities` (its hand-set vote `Barrymore Theatre` is on no recording, so it never ties). The same goes for every other existing venue test. If an existing test changes outcome, stop and report it to the orchestrator: it is a spec question, not a test to edit.

- [ ] **Step 2: Run them and see them fail**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_stage_gather.py -q -k "tie or majority or whitespace_only"`
Expected: FAIL. `venue_tie_break` cannot be imported, so the file does not collect. With a stub that returns None, the positive cases still ship the vote and the **(pin)** tests pass.

- [ ] **Step 3: Implement `venue_tie_break` and wire it into `compute_gather`'s venue chain**

Compute `tie = venue_tie_break(candidate, sel)` once, after `sel`/`sel_venue`/`sel_city` are set and before the chain. Apply it in exactly these three places, setting `venue, city = tie` and leaving `venue_source` as `"item"`:
- **No event** (`event is None`): add an `else` to `if event is not None:` that applies `tie` when it is not None.
- **1a with no flag**: inside `if not event.venue.strip():`, when `cities_compatible(archive_city, jb_city)` holds (the branch that appends nothing today).
- **Step 1** (the `pass` branch): only when `tie` is not None, `venues_equivalent(tie[0], event.venue)`, and `(_venues_equivalent_pre1b(tie[0], event.venue) or cities_compatible(archive_city, jb_city))`. This is step 1's full test, applied to the selected string.

It is not applied in enrichment, the swap, `two_venue_signature`, 1c, the final `else`, or flagged 1a. 1d and the operator overrides are unchanged and still read `vote_venue`/`vote_city`. Every `mismatch` string is built from the vote before the chain, as today.

Add to `CLAUDE.md`'s Tier 1 guards bullet: "**Venue tie-break** (`gather.venue_tie_break`, spec `2026-10-21-held-backlog-small-fixes-design.md` slice B): on a tied grouping vote (raw strings, counted as `grouping._make_candidate` counts) the selected recording's own stripped venue ships, with `sel_city or vote_city`. It applies only when its city is blank or `cities_compatible` with the vote's, and only in the arms that ship the vote unflagged: no event, unflagged 1a, and step 1 when the selected string passes step 1's full test. It never adds or removes a flag, `venue_source` stays `item`, and `provenance.json` is unchanged."

- [ ] **Step 4: Run the targeted tests, then the full suite**

Run: the Step 2 command, then `./.venv/bin/python -m pytest -q`
Expected: PASS, and the full suite is green with no existing test edited.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/stages/gather.py packages/llama/tests/test_stage_gather.py CLAUDE.md
git commit -m "feat(gather): a tied venue vote ships the selected recording's string (slice B)"
```

---

