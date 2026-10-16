### Spec Compliance

- ✅ Spec compliant. `packages/emcee/src/emcee/station.py:61-160` matches the brief's Step 3 verbatim: `ProfileSource`, frozen `Effective`, `profile_label`, `_get`/`_nonempty_str`, the five total accessors, `effective_profile`, `target_problem` and `move_target_problem`. `packages/emcee/tests/test_effective.py` (146 lines) matches Step 1 verbatim. Both listed files are touched, and the existing station code is unchanged (the diff is additions only, plus 4 import lines at `station.py:8-14`).
- Spec §1 order is move > artist rule (normalized key, `from` gate on llama's profile) > llama's profile. The code follows it at `station.py:122-133`, and llama's profile is read through `manifest_profile` (`station.py:126`, `:113`, `:158`), as the global constraint requires.
- Spec §3 use-time rule: a target is valid when it equals the delivered profile or has an `[assign.profiles]` entry, and the message text is verbatim (`station.py:136-142`). Tests pin both the `"(none)"` rendering and the text (`test_effective.py:107-122`).
- Global constraint "moves never optional/defaulted": `effective_profile` and `move_target_problem` both take `moves: Moves` positionally with no default (`station.py:122`, `:145`), and the tests pass `no_moves()` explicitly.
- ⚠️ Cannot verify from this diff: the callers (scan, `run`, `voice`, `status`) come in later tasks. Those tasks need to show that every profile reader switches to `effective_profile` and that `move_target_problem` produces an error row rather than an exception.

### Strengths

- The resolver is total by construction rather than by try/except. `_get` returns None on any non-dict hop, `_nonempty_str` screens the types, and `Moves.get` already rejects a non-str key (`moves.py:91-94`). So garbage manifests degrade to the `llama` source without swallowing any real errors.
- `manifest_voiced_profile` tells "key present but null" apart from "key absent / legacy block" (`station.py:105-113`). The test pins both sides (`test_effective.py:136-146`). This is the distinction the readiness messages in Task 4 depend on.
- Tests cover every precedence edge the spec names: a move beats a rule, a move back to the delivered profile beats a rule, a move to None, a `from`-gated rule with a None llama profile, loose matching that reports the config key as written, and non-string artist and performance_id values.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- `test_effective.py:128-133`: `test_accessors_are_total` never exercises `manifest_voiced_profile` on garbage. It also has no case for a recorded non-string `dj_audio.profile`, such as `{"dj_audio": {"profile": 7}}`, which should read as None through `_nonempty_str`. The code handles both (`station.py:109-113`); the tests just don't pin them. Add both to the loop and the voiced-profile test.
- `station.py:65-71`: the invariant "`rule` is None unless `source == "artist"`" lives only in the docstring. Every constructor inside this module respects it, so this is not a defect today. A `__post_init__` assert would turn it from documentation into a guarantee if callers in later tasks ever build `Effective` directly.
- `station.py:94-96`: `manifest_voiced_source` returns any non-empty string, not a `ProfileSource`. Callers in later tasks compare it against `"move"`, so an unexpected recorded value just reads as "not a move". That is acceptable, but the return type could say `str | None` deliberately (it does). No change needed unless Task 4 relies on the narrowing.

### Named-risk checks run

- Circular import (station now imports `emcee.moves`, `emcee.config`, `emcee.artists`): grepped the imports. `moves.py` imports only `emcee.errors` and `emcee.workspace`, `config.py` imports `emcee.artists` and `emcee.errors`, and `artists.py` imports only `re`. Nothing in `packages/emcee/src` other than `cli.py:34` imports `station`. No cycle.
- `moves.get(None)` when a manifest has no performance_id: `moves.py:91-94` returns None for a non-str key. Safe.
- `llama in rule.from_` when llama is None: `ArtistRule.from_` is `list[str] | None` (`config.py:153`), and `from = []` is rejected at load (`config.py:185-187`). `None in list[str]` is False, so a gated rule never matches a profileless show, which matches the test at `test_effective.py:55-60`.
- Rule-order dependence: two keys that normalize alike are a load error (`config.py:180-183`), so the first-match loop at `station.py:130-132` cannot depend on file order.
- Tests: I did not re-run them. The implementer reports RED (ImportError) and then GREEN (22 passed; full suite 3023 passed, 1 skipped, 8 deselected) with clean output. Nothing in the code raised a doubt that a focused run would settle.

### Assessment

**Task quality:** Approved

**Reasoning:** The implementation is a faithful, verbatim realization of the brief. It is total without broad exception handling and matches spec §1/§3 precedence and message text exactly. The only findings are minor test-coverage additions and a docstring-only invariant.
