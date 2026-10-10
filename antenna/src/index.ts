import { configFromEnv, r2Bucket, runClock } from "./clock";

export default {
  async scheduled(controller, env, _ctx): Promise<void> {
    const started = Date.now();
    const result = await runClock({
      bucket: r2Bucket(env.BUCKET),
      now: () => Date.now(),
      sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
      scheduledTime: controller.scheduledTime,
      config: configFromEnv(env),
    });
    // One line per invocation; the phase-1 verification compares scheduled vs
    // actual fire times (lagMs) over a day from these.
    console.log(JSON.stringify({ event: "clock", scheduled: controller.scheduledTime, started,
                                 lagMs: started - controller.scheduledTime, ...result }));
  },
} satisfies ExportedHandler<Env>;
