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
