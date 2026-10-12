import { r2Bucket } from "./bucket";
import { type ClockResult, configFromEnv, runClock } from "./clock";
import type { AntennaEnv } from "./env";
import { guardConfigFromEnv, guardStep } from "./guard";

export default {
  async scheduled(controller, env, _ctx): Promise<void> {
    const started = Date.now();
    const bucket = r2Bucket(env.BUCKET);
    const now = () => Date.now();
    const fetchFn: typeof fetch = (input, init) => fetch(input, init);
    let result: ClockResult | undefined;
    let error: string | undefined;
    try {
      result = await runClock({
        bucket,
        now,
        sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        scheduledTime: controller.scheduledTime,
        config: configFromEnv(env),
        guard: () => guardStep({ bucket, now, fetch: fetchFn, config: guardConfigFromEnv(env) }),
      });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      throw e; // still a failed invocation in observability
    } finally {
      // One line per invocation, ALWAYS (including when runClock throws); the
      // phase-1 verification compares scheduled vs actual fire times (lagMs).
      console.log(JSON.stringify({ event: "clock", scheduled: controller.scheduledTime, started,
                                   lagMs: started - controller.scheduledTime, ...result, ...(error ? { error } : {}) }));
    }
  },
} satisfies ExportedHandler<AntennaEnv>;
