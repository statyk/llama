# t12-impl handback
Status: DONE
Commits (on 9b74164): 9417681 feat (1b predicates), e1a7606 test (floor pins), 715c3db test (Barton/Burton fix)
Tests: ./.venv/bin/python -m pytest -q -> 3523 passed, 1 skipped, 8 deselected (includes scripts/test_replay_holds.py, 44 pass, nothing moved)
Callers of venues_equivalent( in packages/: gather.py:1350 only. scripts/replay_holds.py uses structure._place_tokens (closest_calls); unchanged behaviour in its tests.
Deviations: none from brief; B2 applied (race track fold in _place_tokens). Extra tests beyond brief: Bryce/Bruce (venue neg), Barton/Burton (venue pos, 6 chars), Macon/Mason (city neg), Austin/Austen (city pos) to pin the floor.
Mutation table (all scratch copies under own mktemp, shadowing proven):
a venue floor >=5 -> test_venues_not_equivalent[Bryce Hall-Bruce Hall] -> caught (first run SURVIVED; test added)
a2 city floor >=5 -> test_cities_not_compatible[Macon, GA-Mason, GA] -> caught (first run SURVIVED; test added)
g venue floor >=7 -> test_venues_equivalent_true[Barton Hall-Burton Hall] -> caught (after test added)
g2 city floor >=7 -> test_cities_compatible[Austin, TX-Austen, TX] -> caught
b univ-strip empties side returns True -> test_venues_not_equivalent[UCLA-UCSB] -> caught
c cities ignore differing regions -> test_cities_not_compatible[Portland, OR-Portland, ME] (+2) -> caught
d substring containment -> test_cities_not_compatible[LA-Dallas, TX] -> caught
e country noise not removed -> test_cities_compatible[Santa Cruz, CA-Santa Cruz, CA USA] -> caught
f race track fold removed -> test_venues_equivalent_true[Meramec Race Track-Merramec Racetrack] -> caught

## Fix round 1
Commit: see git log (fix(structure): drop region punctuation ... name the one-edit floor)
Covering tests: test_structure.py::test_cities_compatible (new rows Washington D.C./DC, Utica N.Y./NY, New York N.Y./NY), floor pins unchanged.
Command: ./.venv/bin/python -m pytest packages/llama/tests/test_structure.py -q -> 192 passed; full suite -> 3526 passed, 1 skipped, 8 deselected.
Mutant (region punctuation -> space): predicted a new D.C./N.Y. row red; result: CAUGHT, 3 failed (all three new rows).
Also: _ONE_EDIT_MIN_LEN = 6 named constant citing spec "New constants" replaces both bare 6s.
