import type { AlertEnv } from "./alerts";
import type { ClockEnv } from "./clock";
import type { GuardEnv } from "./guard";

/** Everything the Worker reads from its environment: wrangler vars, Worker
 * secrets (account details and tokens, never in the repo) and bindings. */
export interface AntennaEnv extends ClockEnv, GuardEnv, AlertEnv {
  BUCKET: R2Bucket;
}
