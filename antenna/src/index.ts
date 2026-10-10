import { type ClockResult, configFromEnv, r2Bucket, runClock } from "./clock";

export default {
  async scheduled(controller, env, _ctx): Promise<void> {
    const started = Date.now();
    let result: ClockResult | undefined;
    let error: string | undefined;
    try {
      result = await runClock({
        bucket: r2Bucket(env.BUCKET),
        now: () => Date.now(),
        sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
        scheduledTime: controller.scheduledTime,
        config: configFromEnv(env),
      });
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      throw e; // still a failed invocation in observability
    } finally {
      // One line per invocation, ALWAYS (including when runClock throws); the
      // phase-1 verification compares scheduled vs actual fire times (lagMs)
      // over a day from these.
      console.log(JSON.stringify({ event: "clock", scheduled: controller.scheduledTime, started,
                                   lagMs: started - controller.scheduledTime, ...result, ...(error ? { error } : {}) }));
    }
  },
} satisfies ExportedHandler<Env>;
