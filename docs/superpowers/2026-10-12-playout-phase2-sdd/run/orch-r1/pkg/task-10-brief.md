### Task 10: The send_email binding; index.html left to the clock

**Model hint:** sonnet

**Files:**
- Create: `antenna/test/wrangler-config.test.ts`
- Modify: `antenna/wrangler.jsonc` (the binding), `antenna/tsconfig.json` (Vite's client types), `antenna/scripts/deploy-assets.mjs` (no `index.html`)

**Interfaces:**
- Consumes: `antenna/wrangler.jsonc` (Tasks 8–9); `AlertEnv.ALERT_EMAIL` (Task 9); the clock's ownership of `index.html` (Tasks 7–8).
- Produces: the committed, unrestricted binding `"send_email": [{ "name": "ALERT_EMAIL" }]`, and a test that keeps `wrangler.jsonc` free of account details and addresses.

Amendment A3. The binding names no destination: a `send_email` binding can only reach the account's verified destination addresses, and the one the Worker writes to is the `ALERT_EMAIL_TO` secret. The deploy stays `npx wrangler deploy`. The test reads `wrangler.jsonc` as text through Vite's `?raw` import; `tsc` learns that import from `vite/client`'s types (Vite comes with vitest), so no declaration file is needed. The vitest pool binds `ALERT_EMAIL` from the same file, which the test also checks.

- [ ] **Step 1: Write the failing test**

`antenna/test/wrangler-config.test.ts`:

```ts
import { env } from "cloudflare:test";
import { describe, expect, it } from "vitest";
import wranglerText from "../wrangler.jsonc?raw";

/** wrangler.jsonc uses whole-line // comments only. */
const config = JSON.parse(wranglerText.split("\n").filter((l) => !l.trim().startsWith("//")).join("\n"));

describe("wrangler.jsonc (this repo is public)", () => {
  it("carries no account details and no email address", () => {
    expect(config).not.toHaveProperty("account_id");
    expect(wranglerText).not.toMatch(/@[a-z0-9-]+\.[a-z]/i);
    expect(config.workers_dev).toBe(false);
    expect(config.preview_urls).toBe(false);
  });

  it("binds send_email unrestricted: the destination is the ALERT_EMAIL_TO secret", () => {
    expect(config.send_email).toEqual([{ name: "ALERT_EMAIL" }]);
    const bound = (env as unknown as { ALERT_EMAIL?: { send?: unknown } }).ALERT_EMAIL;
    expect(typeof bound?.send).toBe("function");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/wrangler-config.test.ts`
Expected: FAIL. `config.send_email` is undefined and `env.ALERT_EMAIL` is not bound.

- [ ] **Step 3: Implement**

In `antenna/wrangler.jsonc`, insert before the line `  // One log line per invocation (~1,440/day) stays inside the free allowance.`:

```jsonc
  // Alert email (Email Routing). Unrestricted on purpose: a send_email binding
  // can only reach the account's verified destination addresses, and the one
  // used is the ALERT_EMAIL_TO secret. Never put an address in this file.
  "send_email": [{ "name": "ALERT_EMAIL" }],
```

In `antenna/tsconfig.json`, change `"types": ["@cloudflare/vitest-plugin/types"]` to `"types": ["@cloudflare/vitest-plugin/types", "vite/client"]` (Vite's own declaration of `?raw` imports).

In `antenna/scripts/deploy-assets.mjs`, make two edits:

1. Delete the `ASSETS` entry `["index.html", "public/index.html", HTML, "public, max-age=60"],` and its comment line `// last: short TTL, and it references everything above`.
2. Replace the header comment's second sentence with:

```js
// Upload antenna's static assets to the station's R2 bucket (spec "R2 object
// contract": offair.html and the app assets incl. hls.js). index.html is NOT
// uploaded: the clock writes it (the player page, or the off-air page while the
// station is blocked) from the copies bundled into the Worker (src/pages.ts).
```

- [ ] **Step 4: Run the tests and the checks**

Run: `cd antenna && npm test && npx tsc --noEmit && ANTENNA_BUCKET=b node scripts/deploy-assets.mjs --dry-run | grep -c "index.html"`
Expected:
- the tests pass, and `tsc` is clean (it now knows the `?raw` import);
- `grep -c` prints `0`.

Do **not** run `wrangler deploy`, not even `--dry-run`: the operator does, at Task 17.

- [ ] **Step 5: Commit**

```bash
git add antenna/wrangler.jsonc antenna/tsconfig.json antenna/scripts/deploy-assets.mjs antenna/test/wrangler-config.test.ts
git commit -m "feat(antenna): unrestricted send_email binding, destination in a secret; index.html left to the clock"
```

---

