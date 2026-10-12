/** index.html is the clock's: the player page normally, the off-air page while
 * the station is blocked (spec "Blocking"). Level-triggered against R2 itself:
 * the object's customMetadata carries the SHA-256 of the body last written, so
 * a HEAD (Class B) per invocation decides, and a deploy that changed either
 * page, or a hand upload, is corrected within a minute. */

import type { BucketLike } from "./bucket";
import { OFFAIR_PAGE, PLAYER_PAGE } from "./pages";

export const INDEX_KEY = "index.html";
export const INDEX_HTTP = { contentType: "text/html; charset=utf-8", cacheControl: "public, max-age=60" };

export async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function reconcileIndex(bucket: BucketLike, blocked: boolean): Promise<"written" | "unchanged"> {
  const body = blocked ? OFFAIR_PAGE : PLAYER_PAGE;
  const sha256 = await sha256Hex(body);
  const info = await bucket.head(INDEX_KEY);
  if (info?.customMetadata?.sha256 === sha256) return "unchanged";
  await bucket.put(INDEX_KEY, body, { httpMetadata: INDEX_HTTP,
                                      customMetadata: { sha256, page: blocked ? "offair" : "player" } });
  return "written";
}
