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

  it("trusts neither an HTTP error nor success: false, even with a result", async () => {
    const result = { id: "rs1", rules: rules(true) };
    const unsuccessful = fakeFetch({ [ENTRY]: () => json({ success: false, errors: [{ code: 7003, message: "x" }], result }) });
    await expect(reconcileKillSwitch(unsuccessful.fetch, CFG, true)).rejects.toThrow(/HTTP 200: 7003 x/);
    const httpError = fakeFetch({ [ENTRY]: () => json({ success: true, errors: [], result }, 500) });
    await expect(reconcileKillSwitch(httpError.fetch, CFG, true)).rejects.toThrow(/HTTP 500/);
  });

  it("resends action_parameters when the rule has them", async () => {
    const params = { response: { status_code: 403, content: "off air", content_type: "text/plain" } };
    const state = { rules: rules(false).map((r) => (r.id === "r2" ? { ...r, action_parameters: params } : r)) };
    const f = api(state);
    await reconcileKillSwitch(f.fetch, CFG, true);
    expect(JSON.parse(f.calls[1].body!).action_parameters).toEqual(params);
  });

  it("gives every API call an abort signal (the 5 s timeout)", async () => {
    const f = api({ rules: rules(false) });
    const signals: (AbortSignal | null | undefined)[] = [];
    const spy = ((input: RequestInfo | URL, init?: RequestInit) => {
      signals.push(init?.signal);
      return f.fetch(input, init);
    }) as typeof fetch;
    await reconcileKillSwitch(spy, CFG, true);
    expect(f.calls.map((c) => c.method)).toEqual(["GET", "PATCH"]);
    expect(signals).toHaveLength(2);
    for (const s of signals) {
      expect(s).toBeInstanceOf(AbortSignal);
      expect(s!.aborted).toBe(false);
    }
  });
});
