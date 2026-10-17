/** A caught value as text for a log line or an alert: an Error's message, else
 * the value as a string. Never throws: it runs inside catch blocks, and
 * `String()` throws on a null-prototype object, an object whose toString
 * throws, or an Error whose message getter does. */
export function describeError(e: unknown): string {
  try {
    return e instanceof Error ? String(e.message) : String(e);
  } catch {
    try {
      return Object.prototype.toString.call(e);
    } catch {
      return "(an unprintable value)";
    }
  }
}
