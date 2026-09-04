/**
 * Runs once when the server process starts (both `next dev` and `next
 * start`, node runtime only -- see the runtime guard below). Fails loudly
 * here rather than lazily on the first request that happens to need
 * LEDGERPROOF_API_BASE_URL, so a missing env var is a startup error you
 * see immediately, not a mysterious first-click failure.
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  if (!process.env.LEDGERPROOF_API_BASE_URL) {
    throw new Error(
      "LEDGERPROOF_API_BASE_URL is not set. Copy web/.env.example to web/.env.local and point it at your running api/ " +
        "(see scripts/dev_api_server.py for local development, or the deployed API Gateway URL in production).",
    );
  }
}
