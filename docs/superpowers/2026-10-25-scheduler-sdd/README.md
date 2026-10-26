# Playout phase 3 (scheduler): SDD record

This is the subagent-driven-development record for
`docs/superpowers/plans/2026-10-25-scheduler.md` (spec
`docs/superpowers/specs/2026-10-25-scheduler-design.md`, review mode Fable). It
was copied out of the worktree's gitignored `.superpowers/sdd/` before merge.
`handoff.md` is the pre-build handoff that launched the run.

- **`run/`** holds one directory per dispatch (`taskN-impl`, `-review`,
  `-fixN`, `-rereviewN`; `name-*` for the station-name change; `final-review`
  (Fable, stopped for the name ruling), `final-review-r2` (Fable, the verdict of
  record), `fixwave-impl` (Sonnet), `fixwave-rereview` (Opus) and
  `fixwave-fable` (Fable re-check of the fix diff)). Each holds its
  `handback.md`, log and `dispatched`/`done` sentinels.
- The orchestrator ledgers are `run/orch/ledger.md` (Tasks 1-14, 1b, the
  station-name commits, both final reviews; ends in a `HANDOFF`) and
  `run/orch-r1/ledger.md` (the successor: the final fix wave, the gates, a
  `FINAL` section). Every `Ruling` and every verbatim operator ruling is in one
  of them. `run/orch-r1/gate-*.log` are the final gate runs at `dbd3601`;
  `run/orch-r1/fixwave-brief.md` is the fix wave's brief.
- **`briefs/`** holds the per-task briefs, the global constraints and the final
  review's context file. The review diff packages were not copied; regenerate
  any of them with `git diff <base>..<head>` from the ranges in the ledgers.

## Gates at dbd3601 (last code commit)

- `./.venv/bin/python -m pytest -q`: 5216 passed, 1 skipped, 8 deselected
- `cd antenna && npm test`: 426 passed (21 files, pages freshness check included)
- `packages/transmitter/scripts/test-in-debian12.sh`: 888 passed (Python 3.11.2, ffmpeg 5.1.9)

## Verdict hashes (SHA-256 of each `handback.md`)

| Verdict | SHA-256 |
|---|---|
| `final-review-r2` | `42d5dea6df496b917daedf101441cb33f1ad07684b541c8181667c7bf9fc4723` |
| `final-review` | `490e7dfbffacca6c888fcb7a220bc055c1f903fb5b2402b6d807ae3b2b52637b` |
| `fixwave-fable` | `240d1db00672a42ad9a20f04cdc902b7abf11ec790c1785cac3591a9518b4cb5` |
| `fixwave-rereview` | `3a18e85f40593e9cb0bd1220df7f381a877e38977c36186ddce10a8d40bb02cb` |
| `name-docs-review` | `799f67d51ce0f5d1a3adbbbe190c2856ecd7b300eaf367ec069804ada0f07299` |
| `name-review` | `3dce80c1c1f7a462ca49b31df886dd0fccda2be8a07fb883b6c7531fca3d260a` |
| `task1-rereview1` | `3518f53c23e0ec2f5b34d7fd57d96f9caf00d1061b529e11355d88f0aa53f62a` |
| `task1-review` | `4e17fc34d472cae41ddaee43df89722076fee53dd6e8f85c1e318507ac895766` |
| `task10-rereview1` | `b9928518fec7543ae5f4d6734cdcccc0164566105643ea83abfa46df47967c0f` |
| `task10-rereview2` | `563b7e2abc10afaee874524252f018761ac68aa8e04b6a4088e779ade09ce036` |
| `task10-rereview3` | `f3fe4ee272188e9fd45bb289cb3c2ea0b4725bf61b084bb28ce85c8358c9dc69` |
| `task10-review` | `ffdc3c47e34c85100577c3079b220fc0d594e9602a6d7c3afe0aae99024dff87` |
| `task11-rereview1` | `3783bd783e67fdf04959497c97a5f319eda6aa205ecb5bdb537f0a7aa8bb73de` |
| `task11-review` | `826bd8142237eaaafb1f5cebd5a2a6155a903004fe04b66213d098b932757b03` |
| `task12-review` | `a3cb7332b6f3ef69c4145985196a04465d47c595067b28c566ccbc121ab90f2f` |
| `task13-rereview1` | `c1b609027d8f61c7d9fd6a2251bb78cdafe9937d1f96c7584bd21b0de67817a3` |
| `task13-rereview2` | `5c5aa6edfd1933ca3aeb4c4408caa9158d5d5afe9b5ba12837f69c66515dcec5` |
| `task13-review` | `e6ff4d02e3d6130842b48f750f199127ad08de44038a7c08900910b1e418c2f6` |
| `task14-rereview1` | `2f5b572b1210bc49a82d7ae54eeddd3851eb6b0ed083c7f42e2cec479bdd7d16` |
| `task14-rereview2` | `8a82e709d9e02026eb06d5fcede11552ed73e86402d3a1b28b7b160582161a4c` |
| `task14-review` | `190f457b56d06a36bfcd3dbf84f0f0b965c35b00610db33a5673f1979b37734d` |
| `task1b-rereview1` | `113cbd380fb7e5ed7e9114f1c48df72b9604630a654d8bec667cf3216fd063e3` |
| `task1b-review` | `db35505d50d217124031eed1f6180e0ac3f24f3f96bbfdc8b7ab91d77dd5476f` |
| `task2-review` | `cb40b85c538f20a256019627bd6536afbb3228ce7e95e086d07dc47e8d2f8fbc` |
| `task3-rereview1` | `a92b0896293296ee1a9bcfdf612d46d469ff3089f2727d4ec94ca142cc6e3cdf` |
| `task3-review` | `fadb8ed702e4c3d3757a85f690a3fad9820ebc6c32a40b1a7cae6c6e313c217c` |
| `task4-rereview1` | `2df8308036343413f7ba374f5db25b36f822cca0a1862996f4268932fb0c5fef` |
| `task4-review` | `53d042c380508c68bede635252aed10728d93a7e21487d96b1394a261148ff15` |
| `task5-rereview1` | `4a397647f4670827118a92649a08b6d149af11382ae255711650337ef1bd094b` |
| `task5-review` | `4e18e21aecfc87289c3fb5ef56be4788075485c6edd28b23197ef0a78a7a4cc4` |
| `task6-review` | `3bfaf612a24ca31704c99e89c41c7b86ef1ad56835c52619a0c266b1b908b310` |
| `task7-rereview1` | `98bb72c0c2e6f7aba29f13b1a61877ca7fa03039b2fa2ec985ed1df0fe6fc005` |
| `task7-review` | `5d53d718f27b427376f3da8aef54fd2de3f2e0454529f5adc1f6f0c0be168dae` |
| `task8-rereview1` | `ca6a81491a0fe56b1707c682a059c929aac4137a2233026cf7dabe3443641d53` |
| `task8-rereview2` | `e67f2452a9fbb6dfb8bf5b32a77ae804d4766e65cc3173e9d864b51cbf2c9a7f` |
| `task8-review` | `75bef4bd45f39e0bf7f003316be4df3342d8fe7976567181c8453c83b7ad2510` |
| `task9-rereview1` | `b814a1f69474275989ee6e23597cd21b78403f377de62b4ff0f95ef83e7bf8e0` |
| `task9-review` | `a7862d1cabb6dc11e250199f106d0b19f5c5573f6fb967e1d829736302272d6c` |
