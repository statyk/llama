# Task 15 handback (antenna scaffold + playlist builder)

Status: DONE

Commit: 6091a65 feat(antenna): Worker scaffold and the wall-clock playlist builder (one commit; HEAD was 675cb6c)

Files: .gitignore (+antenna/node_modules/, antenna/.wrangler/); antenna/{package.json, package-lock.json, tsconfig.json, wrangler.jsonc, vitest.config.ts, worker-configuration.d.ts (wrangler types, 16253 lines)}, antenna/src/{grid.ts, playlist.ts, index.ts (placeholder scheduled())}, antenna/test/playlist.test.ts. antenna/templates/show.html untouched. node_modules/.wrangler not committed (verified git status / check-ignore).

Installed versions: wrangler 4.149.0, vitest 5.0.3, @cloudflare/vitest-plugin 1.4.0, typescript 5.9.3. Plugin export is `cloudflareTest` with `options.wrangler.configPath`, as the brief states; no fallback needed.

Tests:
- TDD: suite failed first ("Cannot find module '../src/playlist'"), then green.
- cd antenna && npm test: 1 file, 12 passed. npm run typecheck (tsc --noEmit): clean.
- ./.venv/bin/python -m pytest -q -p no:cacheprovider: 2438 passed, 7 deselected (no Python touched).

Brief vs code / JSON shapes: no differences. publish.horizon_doc writes {epoch_id, epoch, d, first, last, published_at, container, fallback_version}; epoch is ISO with milliseconds + "Z" (grid.us_to_iso), which Date.parse handles; d = 10.24 -> dMs 10240 exactly. fallback FallbackBuild.index() writes {len, notice, d}, notice a full key "fallback/<v>/notice.aac", matching FallbackIndex.

Safety: no deploy/login/remote commands; `wrangler types` only (offline). No account IDs/tokens in committed files (the only "account_id" string is in generated runtime type docs).

Concerns (minor, none blocking):
1. `wrangler types` printed "Since your Worker has Node.js compatibility enabled, install @types/node" although wrangler.jsonc sets no nodejs_compat flag. Did not install @types/node (not in brief); typecheck is clean without it.
2. Edge at the very start of an epoch, pre-live only: when the window starts at n=0 and segment 0 is fallback, the brief's `Math.max(0, floor(n/len) - tagsThrough)` clamps to 0, so segment 0 is tagged and carries disc 1 rather than floor(0/len)=0. With len > window (6) this is self-consistent across reloads; with len <= 6 a later loop-start segment could change its discontinuity number between the first and second window. Only possible in the first ~minute after an epoch with no live segments; implemented verbatim per brief, flagging for the reviewer.
3. npm ls shows 3 "extraneous" packages (@emnapi/runtime, @img/sharp-wasm32, tslib) — optional transitive deps of wrangler's sharp; harmless.
