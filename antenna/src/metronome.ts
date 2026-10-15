/** The metronome Durable Object (metronome spec): one instance, addressed by
 * cron as idFromName(METRONOME_NAME), writes live.m3u8 on the grid from an
 * alarm chain under the lease cron renews every minute. This file only binds
 * MetronomeEngine (metronome-engine.ts) to the object's storage, alarm, R2
 * binding and env; every rule lives in the engine and metronome-core.ts. */

import { DurableObject } from "cloudflare:workers";
import { r2Bucket } from "./bucket";
import { configFromEnv } from "./clock";
import type { AntennaEnv } from "./env";
import { putLive } from "./live";
import { type Lease, type MetronomeClient, METRONOME_NAME, type MetronomeStatus, RENEW_TIMEOUT_MS, STORAGE_KEYS,
         type StorageKey } from "./metronome-core";
import { MetronomeEngine } from "./metronome-engine";

export class Metronome extends DurableObject<AntennaEnv> {
  private readonly engine: MetronomeEngine;

  constructor(ctx: DurableObjectState, env: AntennaEnv) {
    super(ctx, env);
    const storage = ctx.storage;
    this.engine = new MetronomeEngine({
      now: () => Date.now(),
      // this.env is read on every call: deploying METRONOME != "on" reaches the object directly.
      switchOn: () => this.env.METRONOME === "on",
      config: () => configFromEnv(this.env),
      load: async () => Object.fromEntries(await storage.get<unknown>([...STORAGE_KEYS])) as
        Partial<Record<StorageKey, unknown>>,
      save: async (changes) => {
        const puts: Record<string, unknown> = {};
        const deletes: string[] = [];
        for (const [k, v] of Object.entries(changes)) {
          if (v === undefined) deletes.push(k);
          else puts[k] = v;
        }
        if (Object.keys(puts).length > 0) await storage.put(puts);
        if (deletes.length > 0) await storage.delete(deletes);
      },
      getAlarm: () => storage.getAlarm(),
      setAlarm: (atMs) => storage.setAlarm(atMs),
      deleteAlarm: () => storage.deleteAlarm(),
      putLive: (body, liveMaxAge) => putLive(r2Bucket(this.env.BUCKET), body, liveMaxAge),
      timer: (ms) => {
        let id: ReturnType<typeof setTimeout> | undefined;
        const done = new Promise<void>((resolve) => { id = setTimeout(resolve, ms); });
        return { done, clear: () => { if (id !== undefined) clearTimeout(id); } };
      },
      log: (event, fields) => console.error(JSON.stringify({ event, ...fields })),
    });
  }

  /** Cron's RPC, every minute (metronome spec, "renew(lease | null)"). */
  async renew(lease: Lease | null): Promise<MetronomeStatus> {
    return this.engine.renew(lease);
  }

  async alarm(): Promise<void> {
    await this.engine.alarm();
  }
}

/** The namespace surface the client needs (a DurableObjectNamespace, or a test fake). */
export interface MetronomeNamespace {
  idFromName(name: string): DurableObjectId;
  get(id: DurableObjectId): unknown;
}

/** The single instance, addressed by its fixed name; each renew bounded by
 * timeoutMs (RENEW_TIMEOUT_MS: over two 5 s PUT timeouts, plus slack). The
 * stub is made inside renew, so anything that fails -- a missing binding
 * included -- rejects there, and cron treats it as trigger (a), like a timeout. */
export function metronomeClient(ns: MetronomeNamespace | undefined, timeoutMs = RENEW_TIMEOUT_MS): MetronomeClient {
  return {
    async renew(lease) {
      let id: ReturnType<typeof setTimeout> | undefined;
      try {
        if (ns === undefined) throw new Error("the METRONOME_DO binding is missing");
        const stub = ns.get(ns.idFromName(METRONOME_NAME)) as MetronomeClient;
        return await Promise.race([
          stub.renew(lease),
          new Promise<never>((_, reject) => {
            id = setTimeout(() => reject(new Error(`renew timed out after ${timeoutMs} ms`)), timeoutMs);
          }),
        ]);
      } finally {
        if (id !== undefined) clearTimeout(id);
      }
    },
  };
}
