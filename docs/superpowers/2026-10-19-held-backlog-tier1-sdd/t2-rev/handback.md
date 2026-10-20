### Spec Compliance

- ✅ Spec compliant. Every interface in the brief is present with the exact name and signature, and both orchestrator rulings are applied:
  - `setlistfm.cache_key` is at setlistfm.py:43-45, and the client uses it at setlistfm.py:85. The key formula is byte-identical to the old literal, and the pre-existing test_setlistfm.py:107 still pins the literal hex key, so existing `~/.llama/cache/slfm_*` files keep hitting.
  - `CacheMiss(LlamaError)` is at replay.py:22.
  - `CacheOnlyIA` is at replay.py:26-47: `metadata` reads `md_<id>.json` and raises `CacheMiss("cache miss: md_<id>.json")` after appending to `misses`. `search`, `scrape` and `download_file` raise `CacheMiss(_REFUSED)`. The class has no HTTP client at all, so it cannot reach the network by construction.
  - `CacheOnlySetlistFM` is at replay.py:50-64. It builds its path with `cache_key` (factored, not restated, as the spec requires), returns `_pick(...)`, and on a miss returns None and appends `(artist, date)` to `misses`.
  - `input_digests` is at replay.py:71-91. It returns all five keys, and `vetting.extraction` is the sha256 of `vetting.model_dump_json()` only, so flags and `adopted_date` are excluded.
  - `setlistfm_configured` and `setlistfm_client` are at replay.py:94-103. `setlistfm_client` uses `config.root / "cache"`, the same directory as `make_client` (setlistfm.py) and `IAClient(config.root / "cache")` (cli.py:123).
  - `config_fingerprint` is at replay.py:106-113 and uses `"audio_format": config.audio_format`, per the ruling.
  - `code_identity` is at replay.py:116-126, following the brief's rev-parse, `-dirty` and `version:` fallback rules.
  - `capture_fixture.py --from-cache <id> [out] [--cache DIR]` is at capture_fixture.py:40-45 and 69-76. `main(argv)` matches the brief.
  - The setlist.fm test uses the existing `make(tmp_path, handler)` builder, per the ruling (test_setlistfm.py:163-169).
- No do-not-retune constant appears in the diff's changed lines. The grep hit `normalize_song` only as an unchanged context line in setlistfm.py, and `align_coverage_threshold` only in a test that builds a non-default `Config` (test_replay.py:52). No default changed.
- ⚠️ Cannot verify from this diff, for the Task 5 owner:
  - `CacheMiss` is deliberately not an `IAError`. Gather's sibling loops catch only `IAError` (gather.py:185-194 and 358-361), so a sibling's cache miss aborts the whole gather instead of becoming a "could not fetch sibling" note. That matches the spec ("a miss marks the show `unreplayable: cache miss`"), and `misses` is populated before the raise.
  - Task 5 must catch `CacheMiss`, and should also catch `read_model` validation errors from `input_digests` on a malformed `vetting.json`, so that one show cannot stop the run.

### Strengths
- The `_slim()` refactor (capture_fixture.py:20-28) is the right call. Both paths now share one projection instead of duplicating the dict literal, and the output shape is unchanged.
- The digest test (test_replay.py:37-48) proves both directions: changing only the flags leaves the digest the same, and changing the extraction changes it.
- `misses` is recorded before the raise or the None return, so the harness can count misses even when gather swallows or propagates them.
- The `code_identity` fallback is sound. `llama.__version__` always resolves (`__init__.py:5-13`). In this worktree the function returned `1ba08193…` (clean), and `llama.__file__` resolves inside the worktree.

### Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
1. **replay.py:58-64: `CacheOnlySetlistFM.setlist` can raise where the real client cannot.** `SetlistFMClient.setlist` never raises: it wraps the read in `except Exception` and returns None (setlist.fm docstring, ~lines 81-99). The call site at gather.py:790-792 is not wrapped. So in replay, a malformed or non-dict `slfm_*.json` would raise a non-`LlamaError` (`JSONDecodeError` or `AttributeError`) out of gather, where a real gather would continue with None.
   - I measured the real cache: 3,466 `slfm_*` files, and 0 of them raise on load plus `_pick`. The risk is currently theoretical.
   - Fix: mirror the client by wrapping the read and `_pick` in try/except, returning None without recording a miss (the real client would not fetch either).
2. **test_replay.py:50-55: the fingerprint test does not cover two of its inputs.** It checks `structure` and the setlist.fm key, but not `audio_format` or `jerrybase`. `audio_format` is the field the brief's typo affected, so one assertion such as `Config(audio_format="flac")` would pin the ruling.
3. **test_replay.py:58-61: `code_identity` is only checked against an either-branch regex.** The `-dirty` suffix and the `version:` fallback are never exercised, for example with a monkeypatched `subprocess.run` raising `CalledProcessError`, or returning porcelain output. A regression that always returned the version string, or never appended `-dirty`, would pass. Task 20's `load_list` depends on this behaviour.
4. **test_replay.py:64-69: the client test checks the type but not the cache directory.** It asserts `isinstance(client, CacheOnlySetlistFM)` but not `client.cache_dir == tmp_path / "cache"`. A wrong cache directory would make every lookup a silent miss.
5. **replay.py:94-95 restates `make_client`'s key test** (`os.environ.get("SETLISTFM_API_KEY") or config.setlistfm.api_key`) instead of sharing it. This is plan-mandated: the brief limits setlistfm.py to moving the literal. It is a one-line drift risk between "configured" and what `make_client` actually does.
6. **capture_fixture.py:69-76: bad arguments fail with a raw `IndexError`.** This happens when `--cache` has no value or the identifier is missing. The same is true of the pre-existing `capture_ia` path; it is a developer script.

### Checks run
- Named risk: does gather call any IA method that `CacheOnlyIA` lacks? Gather calls only `ia.metadata` (gather.py:186, 359, 866), so there is no `AttributeError` path.
- Named risk: the real `IAClient._cached` read semantics (ia_client.py:73-79) are the same `json.loads` as `CacheOnlyIA.metadata`.
- Named risk: does any later task change `ResearchVetting`, which would make `vetting.extraction` digests differ between arms? The plan never modifies it.
- Focused tests: `./.venv/bin/python -m pytest packages/llama/tests/test_replay.py packages/llama/tests/test_setlistfm.py scripts/test_capture_fixture.py -q` gave 19 passed, with no warnings.
- Exercised `--from-cache` on the real cache item `gd73-06-10.sbd.hollister.174.sbeok.shnf`, writing to a `mktemp -d` directory only. Output: keys `{metadata, files, reviews}`, 279 files, and file keys a subset of the slim set. There was no network call, and `git status` stayed clean.

### Assessment

**Task quality:** Approved

**Reasoning:** Every brief interface is implemented exactly, including both rulings. The cache-only clients cannot reach the network by construction, and the setlist.fm key is factored without changing its bytes. What remains is test-coverage gaps and one fidelity edge (malformed setlist.fm cache files) that is currently unpopulated.
