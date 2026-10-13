### Task 5: Kill switch reconciliation (Rulesets API)

**Model hint:** opus (blocking path)

**Files:**
- Create: `antenna/src/waf.ts`, `antenna/test/waf.test.ts`

**Interfaces:**
- Consumes: `fakeFetch`, `json`, `FetchCall` (Task 1).
- Produces: `API = "https://api.cloudflare.com/client/v4"`, `PHASE = "http_request_firewall_custom"`, `interface WafConfig { zoneId; token; description }`, `class WafError extends Error`, and `reconcileKillSwitch(fetchFn, cfg, blocked): Promise<{ enabled: boolean; changed: boolean }>`.

`reconcileKillSwitch` works in four steps:

1. **Find.** It GETs `/zones/{zone}/rulesets/phases/http_request_firewall_custom/entrypoint` and finds exactly one rule whose `description` equals `cfg.description`, with action `block`.
2. **Compare.** It reads `enabled` as `true` when the field is absent. If that already equals `blocked`, it returns `changed: false`.
3. **Update.** Otherwise it PATCHes `/zones/{zone}/rulesets/{ruleset}/rules/{rule}` with the rule's full definition and only `enabled` changed.
4. **Verify.** It checks the PATCH response.

It throws `WafError` in four cases: an API failure, zero or more than one matching rule, a non-`block` action, or an update that did not take.

Notes for the implementer:

- The PATCH resends `action`, `expression`, `description`, `ref`, and `action_parameters` if present. The API's update replaces the rule definition, so every field must be there.
- It never touches another rule: the allowlist rule lives in the same ruleset.
- Required token permission: Zone → WAF → Edit, scoped to the station zone (Task 17 verifies it live).
- Each API call times out after 5 s: the reconcile runs before the playlist write in every invocation (amendment A4).

- [ ] **Step 1: Write the failing test**

`antenna/test/waf.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { API, reconcileKillSwitch, WafError } from "../src/waf";
import { type FetchCall, fakeFetch, json } from "./support";

const CFG = { zoneId: "zone1", token: "waf-token", description: "station: kill switch" };
const ENTRY = `GET ${API}/zones/zone1/rulesets/phases/http_request_firewall_custom/entrypoint`;
const PATCH = `PATCH ${API}/zones/zone1/rulesets/rs1/rules/`;

function rules(killEnabled: boolean | undefined, extra: Record<string, unknown>[] = []): Record<string, unknown>[] {
  const kill: Record<string, unknown> = { id: "r2", ref: "r2", action: "block", description: "station: kill switch",
                                          expression: 'http.host eq "h" and not (http.request.uri.path in {"/"})' };
  if (killEnabled !== undefined) kill.enabled = killEnabled;
  return [{ id: "r1", action: "block", description: "station: allowlist", expression: "x", enabled: true }, kill, ...extra];
}
const ok = (result: unknown) => json({ success: true, errors: [], messages: [], result });

/** The Rulesets API: GET returns `state`; PATCH applies the body to it. */
function api(state: { rules: Record<string, unknown>[] }) {
  return fakeFetch({
    [ENTRY]: () => ok({ id: "rs1", rules: state.rules }),
    [PATCH]: (c: FetchCall) => {
      const id = c.url.split("/").pop()!;
      const body = JSON.parse(c.body!);
      state.rules = state.rules.map((r) => (r.id === id ? { id, ...body } : r));
      return ok({ id: "rs1", rules: state.rules });
    },
  });
}

describe("reconcileKillSwitch", () => {
  it("only reads when the rule already matches", async () => {
    const f = api({ rules: rules(false) });
    expect(await reconcileKillSwitch(f.fetch, CFG, false)).toEqual({ enabled: false, changed: false });
    expect(f.calls.map((c) => c.method)).toEqual(["GET"]);
    expect(f.calls[0].headers.authorization).toBe("Bearer waf-token");
  });

  it("enables it when blocked, resending the whole rule with only enabled changed", async () => {
    const state = { rules: rules(false) };
    const f = api(state);
    expect(await reconcileKillSwitch(f.fetch, CFG, true)).toEqual({ enabled: true, changed: true });
    expect(f.calls[1].url).toBe(`${API}/zones/zone1/rulesets/rs1/rules/r2`);
    expect(JSON.parse(f.calls[1].body!)).toEqual({ action: "block", description: "station: kill switch", enabled: true, ref: "r2",
      expression: 'http.host eq "h" and not (http.request.uri.path in {"/"})' });
    expect(state.rules[0]).toMatchObject({ id: "r1", enabled: true }); // the allowlist is untouched
  });

  it("treats a missing enabled field as enabled, and disables it when not blocked", async () => {
    const f = api({ rules: rules(undefined) });
    expect(await reconcileKillSwitch(f.fetch, CFG, false)).toEqual({ enabled: false, changed: true });
  });

  it("refuses when the rule is missing, ambiguous or not a block rule", async () => {
    await expect(reconcileKillSwitch(api({ rules: [] }).fetch, CFG, true)).rejects.toThrow(/found 0/);
    await expect(reconcileKillSwitch(api({ rules: rules(false, [{ id: "r3", action: "block",
      description: "station: kill switch", expression: "y" }]) }).fetch, CFG, true)).rejects.toThrow(/found 2/);
    const skip = rules(false).map((r) => (r.id === "r2" ? { ...r, action: "skip" } : r));
    const f = api({ rules: skip });
    await expect(reconcileKillSwitch(f.fetch, CFG, true)).rejects.toThrow(/not "block"/);
    expect(f.calls.map((c) => c.method)).toEqual(["GET"]);
  });

  it("raises a WafError on an API failure or an update that did not take", async () => {
    const denied = fakeFetch({ [ENTRY]: () => json({ success: false, errors: [{ code: 10000, message: "Authentication error" }] }, 403) });
    await expect(reconcileKillSwitch(denied.fetch, CFG, true)).rejects.toThrow(WafError);
    await expect(reconcileKillSwitch(denied.fetch, CFG, true)).rejects.toThrow(/403: 10000 Authentication error/);
    const ignored = fakeFetch({ [ENTRY]: () => ok({ id: "rs1", rules: rules(false) }),
                                [PATCH]: () => ok({ id: "rs1", rules: rules(false) }) });
    await expect(reconcileKillSwitch(ignored.fetch, CFG, true)).rejects.toThrow(/did not take/);
    const html = fakeFetch({ [ENTRY]: () => new Response("<html>", { status: 502 }) });
    await expect(reconcileKillSwitch(html.fetch, CFG, true)).rejects.toThrow(/not JSON/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd antenna && npx vitest run test/waf.test.ts`
Expected: FAIL. `../src/waf` cannot be resolved.

- [ ] **Step 3: Implement**

`antenna/src/waf.ts`:

```ts
/** The kill switch: a pre-created WAF custom rule on the station zone, found
 * by its description (never a hard-coded rule ID) and toggled through the
 * Rulesets API with a zone-scoped WAF-edit token. Level-triggered: every run
 * reads the rule's actual state and corrects it (spec "Blocking"). */

export const API = "https://api.cloudflare.com/client/v4";
export const PHASE = "http_request_firewall_custom";
/** Short: the reconcile runs before the playlist write in every invocation. */
const TIMEOUT_MS = 5_000;

export interface WafConfig {
  zoneId: string;
  token: string;
  description: string; // the rule's description, e.g. "station: kill switch"
}

interface Rule {
  id: string;
  action: string;
  expression: string;
  description?: string;
  enabled?: boolean;
  ref?: string;
  action_parameters?: unknown;
}

interface Envelope<T> {
  success?: boolean;
  errors?: { code?: number; message?: string }[];
  result?: T;
}

export class WafError extends Error {}

async function call<T>(fetchFn: typeof fetch, cfg: WafConfig, method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetchFn(`${API}${path}`, {
    method,
    headers: { authorization: `Bearer ${cfg.token}`, "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  const text = await res.text();
  let env: Envelope<T>;
  try {
    env = JSON.parse(text) as Envelope<T>;
  } catch {
    throw new WafError(`${method} ${path}: HTTP ${res.status}, not JSON: ${text.slice(0, 200)}`);
  }
  if (!res.ok || env.success !== true || env.result === undefined) {
    const msg = (env.errors ?? []).map((e) => `${e.code ?? ""} ${e.message ?? ""}`.trim()).join("; ");
    throw new WafError(`${method} ${path}: HTTP ${res.status}${msg ? `: ${msg}` : ""}`);
  }
  return env.result;
}

function killSwitch(rules: Rule[], description: string): Rule {
  const matches = rules.filter((r) => r.description === description);
  if (matches.length !== 1) {
    throw new WafError(`expected exactly one custom rule described "${description}", found ${matches.length}`);
  }
  if (matches[0].action !== "block") {
    throw new WafError(`the rule described "${description}" has action "${matches[0].action}", not "block"; refusing to toggle it`);
  }
  return matches[0];
}

/** Make the kill switch's enabled state equal `blocked`. Returns its state
 * after the call; throws WafError (or a network error) when it cannot. */
export async function reconcileKillSwitch(fetchFn: typeof fetch, cfg: WafConfig, blocked: boolean):
    Promise<{ enabled: boolean; changed: boolean }> {
  const base = `/zones/${encodeURIComponent(cfg.zoneId)}/rulesets`;
  const ruleset = await call<{ id: string; rules?: Rule[] }>(fetchFn, cfg, "GET", `${base}/phases/${PHASE}/entrypoint`);
  const rule = killSwitch(ruleset.rules ?? [], cfg.description);
  const enabled = rule.enabled !== false; // the API may omit enabled when true
  if (enabled === blocked) return { enabled, changed: false };
  // Resend the whole rule definition with only `enabled` changed: the update
  // replaces the rule, so every field must be present.
  const update: Record<string, unknown> = { action: rule.action, expression: rule.expression,
                                            description: rule.description, enabled: blocked };
  if (rule.ref !== undefined) update.ref = rule.ref;
  if (rule.action_parameters !== undefined) update.action_parameters = rule.action_parameters;
  const after = await call<{ rules?: Rule[] }>(fetchFn, cfg, "PATCH",
    `${base}/${encodeURIComponent(ruleset.id)}/rules/${encodeURIComponent(rule.id)}`, update);
  const now = (after.rules ?? []).find((r) => r.id === rule.id);
  const nowEnabled = now ? now.enabled !== false : undefined;
  if (nowEnabled !== blocked) {
    throw new WafError(`the kill switch update did not take: enabled is ${String(nowEnabled)}, wanted ${blocked}`);
  }
  return { enabled: blocked, changed: true };
}
```

- [ ] **Step 4: Run the tests and the type check**

Run: `cd antenna && npx vitest run test/waf.test.ts && npx tsc --noEmit`
Expected: PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add antenna/src/waf.ts antenna/test/waf.test.ts
git commit -m "feat(antenna): kill switch found by description and reconciled through the Rulesets API"
```

---

