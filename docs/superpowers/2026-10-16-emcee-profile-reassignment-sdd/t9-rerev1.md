### Finding Verdicts

- **(Important) Stale `--profile`/`--assigned` filter semantics and "keyed off source.profile" framing (CLAUDE.md:109-112, CLAUDE.md:215-217, README.md:315-316)**: ADDRESSED.
  - CLAUDE.md:109 now reads "limits it to packages whose EFFECTIVE profile (move > artist rule > llama's) is one of those, `--assigned` to packages whose effective profile has its OWN `[assign.profiles.<name>]` entry".
  - That matches the code. `cli.py:466-469` filters on `status.profile`, and `station.py:28` documents that field as the effective profile. `station.py:147-166` `effective_profile` resolves move first, then the `[assign.artists]` rule, then `manifest_profile`. `--assigned` uses `assignment_for(config, status.profile).source != "profile"`, which also keys off the effective profile.
  - CLAUDE.md:215-217 now says "keyed off the effective profile (`manifest["source"]["profile"]` ... unless a move or `[assign.artists]` rule overrides it)", which is correct.
  - README.md:317 now carries a parenthetical that points at "Moving shows between profiles". That heading exists at README.md:414.
- **(Controller ruling) The "only problem is missing track audio" wording (CLAUDE.md:108)**: ADDRESSED.
  - CLAUDE.md:108 now reads "A pending package with missing track audio is skipped (`re-deliver from llama`), not voiced, whatever else is wrong with it."
  - The code agrees. At `cli.py:480-484` the `if status.missing_tracks:` skip runs after the unsupported, error, move_problem and ready checks, and before dry-run and voicing. So any pending package with missing tracks is skipped, whatever other reasons it carries.
  - One narrow qualification: a package with a `move_problem` is reported as an error row before it reaches the tracks check (`cli.py:474-477`). The new wording says "a pending package ... is skipped". Error-row packages are a separate class that the same bullet already covers elsewhere, so this is not a defect.
  - I grepped README.md and docs/station-brief.md for "only problem", "missing track audio", "re-deliver from llama" and `missing_tracks`. Neither file makes the claim, so neither needs a change.

### New Breakage in the Fix Diff

None. The diff touches CLAUDE.md and README.md only (6 insertions, 7 deletions). Each changed line was checked against `cli.py` `run` (lines 403-520) and `station.effective_profile` at HEAD 885dad4.

### Out-of-Scope Observations

- (Minor) `packages/emcee/src/emcee/cli.py:436-438`: `run`'s own docstring still says "A pending package whose only problem is missing track audio is skipped". The code skips on missing tracks whatever else is wrong, so this is the same overstatement the controller ruled on for CLAUDE.md. cli.py is not in this fix diff. This line comes up in `emcee run --help` output.
- (Minor) `docs/station-brief.md:78-81`: still says the presenter is chosen "by matching the llama profile name stamped in the manifest (`source.profile`...) against emcee's own `[assign]` config", and mentions no move or artist rule. The same document's dj_audio example at line 278 does acknowledge moves and rules. This is the same stale-framing class as finding 1, but the finding did not name this file and the fix diff does not touch it.

### Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.

Checks run (read-only): read the review diff file and the implementer's fix report. Read `cli.py:400-520` (run filter and skip logic), `station.py` (the profile field at 28, `effective_profile` at 147-166) and `process.py:92-103` (`resolve_voicing`). Grepped CLAUDE.md, README.md and docs/station-brief.md for the filter, missing-audio and source.profile wording. I ran no tests: the docs-only diff raised no doubt that a test would answer.
