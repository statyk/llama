# Durable Objects facts for the antenna alarm-chain plan (researched 2026-10-14)

Source pages were fetched through a summarizing tool, so the quotes are the tool's extracts, not verified verbatim. Re-check the load-bearing ones in the browser before committing spend assumptions.

## 1. Pricing (Workers Paid)
Source: https://developers.cloudflare.com/durable-objects/platform/pricing/

- **Requests:** 1M/month included, then $0.15 per million. Counted: HTTP requests, RPC sessions, WebSocket messages, and alarm invocations. "Alarm invocations count as requests."
- **RPC:** "Every RPC method call on a Durable Objects stub is its own RPC session" and is billed as one request. Calls on objects returned from that call are part of the same session.
- **Duration:** 400,000 GB-s/month included, then $12.50 per million GB-s. It is wall-clock time while the object is actively running, or idle in memory but unable to hibernate. Each object is billed as 128 MB regardless of real use. So one object running continuously is 0.125 GB x 2.6M s/month = about 324k GB-s, which is inside the 400k included.
- **Hibernation:** idle objects that qualify for hibernation are not billed for duration, even before the runtime hibernates them.
- **Hibernation and eviction rules** (https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/): hibernation needs no pending setTimeout/setInterval, no unfinished I/O or waitUntil promises, no open outbound connections, no standard WebSocket API use, and no request in progress. Idle hibernateable objects move to hibernation "after 10 seconds of inactivity". Non-hibernateable idle objects are evicted from memory "after 70-140 seconds of inactivity".
- **Alarm-only objects:** the docs are SILENT on whether an object that receives only alarms hibernates. They do not list alarms as a hibernation or eviction blocker. Inference, not documented: with a 10.24 s gap and a 10 s hibernate timeout, an alarm-only object could hibernate between alarms. Plan to budget the worst case, continuous 128 MB billing (about 324k GB-s/month, about 0.36 of one object-month under the included amount), and verify against GraphQL.
- **Pending I/O changelog, 2026-10-01:** "Pending I/O keeps Durable Objects running without a connected client, including service binding calls, RPC, and timers. Duration charges continue during this time." (https://developers.cloudflare.com/changelog/product/durable-objects/). I could not fetch the individual post (404). Outbound fetch() and awaited R2 calls in the alarm keep the object billable for their duration.
- **SQLite storage backend billing:**
  - Rows read: 25 billion/month included, then $0.001 per million.
  - Rows written: 50 million/month included, then $1.00 per million. Deletes count as rows written.
  - Stored data: 5 GB-month included, then $0.20 per GB-month.
  - KV-API methods (get/put/delete/list) on SQLite objects are billed as rows read/written.
- **Key-value backend:** existing namespaces only; reads and writes are billed in 4 KB request units (1M included, then $0.20/M reads, $1.00/M writes), and storage is $0.20 per GB-month beyond 1 GB. The Jul 9 2026 changelog says new namespaces must use SQLite unless the account already has a KV namespace.
- **Alarm storage ops:** the pricing page says setAlarm() is "billed as one row written (SQLite) or one write request unit (key-value)". getAlarm() and deleteAlarm() are not addressed. DOCS SILENT. Budget one row written per setAlarm, about 8,440/day, about 253k/month, far under the 50M included. If the handler also does storage writes, add them.
- **Is SQLite storage billing enabled?** The pricing page and the Dec 12 2025 changelog (https://developers.cloudflare.com/changelog/post/2025-12-12-durable-objects-sqlite-storage-billing/) still say it "will be enabled in January 2026, with a target date of January 7, 2026 (no earlier)". The changelog listing through Oct 2026 shows no later entry confirming it started or was delayed. The docs are ambiguous and still future-tense. Assume it is ON. The cost is negligible for us (a few rows).

Estimated DO bill for this plan: about 253k alarm requests + about 43k cron-driven RPC requests (one per minute) = about 0.3M, under the 1M included. Duration at worst case is under the 400k GB-s included. This assumes DO usage is otherwise nil on the account.

## 2. Alarm semantics
Source: https://developers.cloudflare.com/durable-objects/api/alarms/

- "Alarms have guaranteed at-least-once execution."
- Retries: on an uncaught exception, exponential backoff "starting at a 2 second delay from the first failure," for up to 6 retries. Retries apply only to the most recent setAlarm(). The docs recommend catching exceptions and re-arming before returning. `alarmInfo` gives `retryCount` and `isRetry`.
- Changelog 2026-08-25: setting `retryAlarm: false` on `ctx.abort()` stops an interrupted alarm from retrying.
- One alarm per object: "Each Durable Object is able to schedule a single alarm at a time by calling setAlarm()". A second setAlarm() overrides the first.
- "Only one instance of alarm() runs at a time per Durable Object instance." A running handler therefore serializes with the next one. The exact queueing behavior when the handler overruns the next scheduled time is not documented.
- getAlarm(): returns epoch ms or null. "While alarm() is running, it returns null unless setAlarm() was called after the handler started."
- deleteAlarm() inside alarm() may prevent retries on a best-effort basis.
- Constructor caveat: check getAlarm() before setAlarm() there, or you may overwrite the next alarm after the object wakes.
- Changelog 2026-02-24: deleteAll() also deletes the alarm for compatibility date 2026-02-24 or later.
- Limits (https://developers.cloudflare.com/durable-objects/platform/limits/): "Alarm handler invocations have a maximum wall time of 15 minutes." CPU is 30 s default per invocation (HTTP request, WebSocket message, or alarm), configurable up to 5 minutes via `limits.cpu_ms`.
- Deploy: https://developers.cloudflare.com/durable-objects/concepts/durable-object-lifecycle/ says code updates and deployments make objects shut down and restart automatically; in-flight requests get "up to 30 seconds to complete", and a request that touches storage during shutdown is stopped with an error. It does NOT say what happens to a pending alarm. The storage best-practices page only says deployments "trigger Durable Objects to restart and lose their in-memory state". DOCS SILENT on pending alarms across deploys. Alarm state is persisted in storage, so it should survive, but that is inference. This is why the cron-driven "ensure armed" RPC is a good design. An interrupted handler is re-instantiated and retried, which can re-run a PUT (idempotent here).
- Alarms example (https://developers.cloudflare.com/durable-objects/examples/alarms-api/): "If an unexpected error terminates the Durable Object, the alarm() handler will be re-instantiated on another machine... Following a short delay, the alarm() handler will run from the beginning."

## 3. Outbound fetch / R2 binding in alarm
- Nothing says it is forbidden. The alarms example POSTs to an upstream service with fetch() inside alarm(). DOs can have bindings like any Worker (R2 binding in the DO class's env). The docs have no explicit sentence "alarms can use R2 bindings" that I found.
- Subrequest limits: the DO limits page gives NO total subrequest cap, only "Simultaneous outgoing connections/request" = 6. The Workers limits page governs subrequests (50 free / 10,000 paid per request), but I did not verify how it applies per alarm invocation. DOCS SILENT for DOs. One R2 PUT per alarm is well below any plausible cap.
- Outbound fetch and open connections keep the object from being evicted, for up to 15 minutes each (changelog 2026-06-19).

## 4. Migrations
Source: https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/

- `new_sqlite_classes` maps to SQLite storage; `new_classes` maps to key-value storage. Example: `{ "tag": "v1", "new_sqlite_classes": ["ChatRoom"] }`.
- Free plan: only SQLite-backed DOs are available. Paid: SQLite available; KV backend "only available to accounts that already have a key-value-backed namespace" (also changelog 2026-07-09). Use `new_sqlite_classes` on either plan.
- Changelog 2026-07-04: a declarative `exports` field replaces the `migrations` array for class lifecycle. Example: `[exports.ChatRoom] type = "durable-object" storage = "sqlite"`.
- Deleting: with `exports`, a tombstone `[exports.Old] type="durable-object" state="deleted"`. This permanently removes the namespace and its data, with no Trash. The fetched migrations page did not mention `deleted_classes`. It is the legacy migrations key I know from older docs, so verify it in the current migrations docs before relying on it. Call deleteAlarm()/deleteAll() before deleting, since alarm and storage are billed otherwise.
- Whether the legacy `migrations` array is still accepted alongside `exports` is not confirmed. Check `wrangler deploy --dry-run`.

## 5. GraphQL analytics
Source: https://developers.cloudflare.com/durable-objects/observability/graphql-analytics/ and https://developers.cloudflare.com/durable-objects/observability/metrics-and-analytics/

- Datasets listed: `durableObjectsInvocationsAdaptiveGroups`, `durableObjectsPeriodicGroups`, `durableObjectsStorageGroups`, `durableObjectsSubrequestsAdaptiveGroups`. Queried under `viewer { accounts(filter: {accountTag: ...}) }`, so account-scoped.
- Fields documented in examples: `sum { requests responseBodySize }` (invocations), `sum { cpuTime }` and `memoryUsageBytes` with quantiles (periodic), `max { storedBytes }` (storage).
- NOT documented in these pages: duration/activeTime/GB-s fields, rows read/written fields, any data lag, whether alarm invocations appear in `requests`, and any double counting with `workersInvocationsAdaptive` (the Workers tutorial page is also silent). Use GraphQL introspection (`__type(name: "...")`) on each dataset to find the fields. In particular, check for a duration/wall-time field on `durableObjectsPeriodicGroups` and rows fields on the storage dataset. UNKNOWN, do not guess.
- Practical consequence: the cost guard cannot rely on docs alone for DO duration and rows. Either introspect and verify, or compute the DO cost from known quantities (alarm count x constants) and use the dashboard Billable Usage as a check. The DO's R2 PUTs are R2 Class A ops and appear in R2 metrics, not DO metrics.

## 6. Location
Source: https://developers.cloudflare.com/durable-objects/reference/data-location/

- Without a hint, the object is created near the first `get()` caller. `get(id, { locationHint: "enam" })` is honored only on the first get for an object. Values: wnam, enam, sam, weur, eeur, apac, apac-ne, apac-se, oc, afr, me. "Hints are a best effort and not a guarantee." sam/afr/me do not currently spawn locally. The cron-triggered Worker's first `get()` decides placement if no hint is given, so pass a hint.
- Objects do not currently change location after creation (dynamic relocation is "planned for the future").
- Jurisdictions: eu, us, fedramp (hard constraints).
- Alarm reliability when the region has issues: DOCS SILENT. Only the at-least-once guarantee and re-instantiation on another machine after an unexpected termination are documented.
- Alarms as a ~10 s periodic timer: the alarms example runs `alarm()` "once every 10 seconds" for batching, and this is the closest documented guidance. There is no documented minimum interval, drift or jitter guarantee. A self-re-arming alarm drifts if you schedule from "now"; schedule against absolute 10.24 s boundaries and re-arm at the start of the handler so a crash does not break the chain. The per-minute cron ensure-armed check is the right backstop, and a failed retry chain stops after 6 retries, so catch errors and always re-arm.

## Gaps to verify empirically before relying on them
1. Pending alarm survival across deploy.
2. Alarm-only hibernation, and therefore real GB-s.
3. GraphQL fields for duration and rows, and any lag.
4. Whether SQLite storage billing actually went live.
5. Subrequest cap per alarm invocation.
6. `deleted_classes` versus `exports` tombstone in the current wrangler.
